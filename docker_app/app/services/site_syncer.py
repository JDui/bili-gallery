from __future__ import annotations

import threading
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as datetime_time
from typing import Any

from PIL import Image, ImageOps

from app.db import Database
from app.services.media_indexer import MediaIndexer
from app.services.site_downloader import MediaDownloader
from app.services.site_filtering import RuleEngine
from app.services.site_parser import PageFetcher, ParsedPost, SourceParser
from app.services.storage import StorageService
from app.services.utils import TIMEZONE, clean_filename, parse_date, safe_slug


SITE_PAGE_REQUEST_TIMEOUT = 300
SITE_MEDIA_DOWNLOAD_TIMEOUT = 300
SITE_MEDIA_DOWNLOAD_CONCURRENCY = 3
SITE_MEDIA_DOWNLOAD_RETRIES = 5


class SiteSyncManager:
    def __init__(self, db: Database, storage: StorageService, indexer: MediaIndexer | None = None) -> None:
        self.db = db
        self.storage = storage
        self.indexer = indexer
        self._lock = threading.Lock()
        self._task_queue: Any | None = None
        self._status: dict[str, Any] = {"running": False, "message": "空闲"}

    def bind_task_queue(self, task_queue: Any) -> None:
        self._task_queue = task_queue

    def status(self) -> dict[str, Any]:
        return {
            **self._status,
            "last_run": self.db.last_task_run("site-sync"),
        }

    def start_sync(self, source_id: int | None = None) -> dict[str, Any]:
        if self._task_queue is not None:
            return self._task_queue.start_site_sync(source_id)
        if not self._lock.acquire(blocking=False):
            return {"ok": True, "queued": False, "message": "已有站点同步任务正在运行"}
        thread = threading.Thread(target=self._run_sync_thread, args=(source_id,), daemon=True)
        thread.start()
        return {"ok": True, "queued": False, "message": "已开始站点同步"}

    def start_full_validation(self, source_id: int) -> dict[str, Any]:
        if self._task_queue is not None:
            return self._task_queue.start_site_validation(source_id)
        if not self._lock.acquire(blocking=False):
            return {"ok": True, "queued": False, "message": "已有站点同步任务正在运行"}
        thread = threading.Thread(target=self._run_full_validation_thread, args=(source_id,), daemon=True)
        thread.start()
        return {"ok": True, "queued": False, "message": "已开始站点全量校验"}

    def test_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        settings = self.db.get_settings()
        fetcher = PageFetcher(
            timeout=self._page_request_timeout(settings),
            user_agent=str(settings.get("site_user_agent")),
            proxies=self._site_proxies(settings),
        )
        parser = SourceParser(fetcher)
        return [self._preview_dict(post) for post in parser.preview(source, limit=3)]

    def suggest_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.db.get_settings()
        fetcher = PageFetcher(
            timeout=self._page_request_timeout(settings),
            user_agent=str(settings.get("site_user_agent")),
            proxies=self._site_proxies(settings),
        )
        parser = SourceParser(fetcher)
        suggestion = parser.suggest(str(payload.get("entry_url") or ""))
        try:
            suggestion["preview"] = [self._preview_dict(post) for post in parser.preview(suggestion, limit=3)]
        except Exception:
            suggestion["preview"] = suggestion.get("preview") or []
        return suggestion

    def _run_sync_thread(self, source_id: int | None) -> None:
        task_id = self.db.create_task_run("site-sync", "running", "同步站点来源")
        try:
            details = self.execute_sync(source_id)
            self.db.finish_task_run(task_id, "success", "站点同步完成", details)
            self._status = {"running": False, "message": "站点同步完成"}
        except Exception as exc:
            details = {"sources": 0, "posts": 0, "downloaded": 0, "blocked": 0, "errors": 0}
            details["errors"] += 1
            self.db.finish_task_run(task_id, "failed", str(exc), details)
            self._status = {"running": False, "message": f"站点同步失败: {exc}"}
        finally:
            self._lock.release()

    def _run_full_validation_thread(self, source_id: int) -> None:
        task_id = self.db.create_task_run("site-sync", "running", "站点全量校验")
        try:
            details = self.execute_full_validation(source_id)
            self.db.finish_task_run(task_id, "success", "站点全量校验完成", details)
            self._status = {"running": False, "message": "站点全量校验完成"}
        except Exception as exc:
            details = {"sources": 0, "posts": 0, "downloaded": 0, "blocked": 0, "errors": 1}
            self.db.finish_task_run(task_id, "failed", str(exc), details)
            self._status = {"running": False, "message": f"站点全量校验失败: {exc}"}
        finally:
            self._lock.release()

    def execute_sync(self, source_id: int | None = None, cooperate=None) -> dict[str, Any]:
        settings = self.db.get_settings()
        details: dict[str, Any] = {
            "sources": 0,
            "discovered": 0,
            "posts": 0,
            "downloaded": 0,
            "blocked": 0,
            "skipped": 0,
            "no_media": 0,
            "errors": 0,
            "proxy": self._site_proxy_summary(settings),
        }
        self._status = {"running": True, "message": "正在同步站点来源"}
        sources = [self.db.get_site_source(source_id)] if source_id else self.db.list_site_sources(include_disabled=False)
        for source in [item for item in sources if item]:
            if cooperate:
                cooperate()
            details["sources"] += 1
            self._status = {
                "running": True,
                "message": f"正在同步站点：{source.get('name') or source.get('slug') or source['id']}",
                "current_source": source.get("name") or source.get("slug") or source["id"],
                "source_index": details["sources"],
                "source_total": len([item for item in sources if item]),
            }
            self._log_site_event(source, "sync-start", "开始同步站点来源")
            try:
                result = self._sync_source(source, cooperate=cooperate)
            except Exception as exc:
                details["errors"] += 1
                self.db.add_site_filter_log(
                    source.get("id"),
                    str(source.get("entry_url") or ""),
                    str(source.get("name") or source.get("slug") or source.get("id") or "站点来源"),
                    "error",
                    f"同步失败: {exc}",
                )
                continue
            for key, value in result.items():
                details[key] = int(details.get(key, 0)) + int(value)
            if not result.get("discovered"):
                self._log_site_event(
                    source,
                    "empty",
                    "未发现可同步内容",
                    f"入口: {source.get('entry_url') or '-'}; 类型: {source.get('source_type') or '-'}; 起始日期: {source.get('start_date') or settings.get('site_default_start_date') or '-'}",
                )
            self._log_site_event(
                source,
                "sync-complete",
                "站点同步完成",
                f"发现 {result.get('discovered', 0)} 条，入库 {result.get('posts', 0)} 条，下载 {result.get('downloaded', 0)} 个，拦截 {result.get('blocked', 0)} 条，跳过 {result.get('skipped', 0)} 条，失败 {result.get('errors', 0)} 个",
            )
        self._status = {"running": False, "message": "站点同步完成"}
        return details

    def execute_full_validation(self, source_id: int, cooperate=None) -> dict[str, Any]:
        source = self.db.get_site_source(source_id)
        if not source:
            raise RuntimeError("站点来源不存在")
        self._status = {"running": True, "message": f"正在全量校验站点：{source.get('name') or source_id}"}
        settings = self.db.get_settings()
        cleared = self.db.clear_site_source_content(source_id)
        removed_files = 0
        for folder_name in cleared.get("folder_names", []):
            removed_files += self.storage.remove_folder_assets(folder_name)
        removed_files += self.storage.remove_site_source_assets(source.get("slug") or source.get("name") or str(source_id))
        self._log_site_event(source, "validation-start", "开始站点全量校验")
        self._log_site_event(
            source,
            "validation-cleared",
            "已清理旧内容",
            f"旧帖子 {int(cleared.get('posts') or 0)} 条，旧素材 {int(cleared.get('assets') or 0)} 个，图库动态 {int(cleared.get('folders') or 0)} 个，删除文件 {removed_files} 个",
        )
        result = self.execute_sync(source_id, cooperate=cooperate)
        result["cleared_posts"] = int(cleared.get("posts") or 0)
        result["cleared_assets"] = int(cleared.get("assets") or 0)
        result["cleared_folders"] = int(cleared.get("folders") or 0)
        result["removed_files"] = removed_files
        result["validation_mode"] = True
        result["source"] = {
            "id": source.get("id"),
            "name": source.get("name"),
            "entry_url": source.get("entry_url"),
            "source_type": source.get("source_type"),
            "start_date": source.get("start_date") or settings.get("site_default_start_date"),
        }
        if not result.get("discovered"):
            self._log_site_event(source, "validation-empty", "全量校验未发现可同步内容")
        self._log_site_event(
            source,
            "validation-complete",
            "站点全量校验完成",
            f"发现 {result.get('discovered', 0)} 条，入库 {result.get('posts', 0)} 条，下载 {result.get('downloaded', 0)} 个，失败 {result.get('errors', 0)} 个",
        )
        self._status = {"running": False, "message": "站点全量校验完成"}
        return result

    def _sync_source(self, source: dict[str, Any], cooperate=None) -> dict[str, int]:
        settings = self.db.get_settings()
        fetcher = PageFetcher(
            timeout=self._page_request_timeout(settings),
            user_agent=str(settings.get("site_user_agent")),
            proxies=self._site_proxies(settings),
        )
        parser = SourceParser(fetcher)
        engine = RuleEngine(self.db.get_site_rules())
        start_date = parse_date(source.get("start_date") or settings.get("site_default_start_date")) or date(2026, 4, 1)
        incremental_cutoff_date = self._latest_site_sync_date(source)
        request_sleep = max(float(settings.get("site_request_sleep") or 0), 0)
        max_media = max(int(settings.get("site_max_media_per_post") or 100), 1)
        counters = {"discovered": 0, "posts": 0, "downloaded": 0, "blocked": 0, "skipped": 0, "no_media": 0, "errors": 0}

        posts = parser.discover(source, parse_assets=True)
        counters["discovered"] = len(posts)
        self._status = {
            **self._status,
            "running": True,
            "message": f"已发现 {len(posts)} 条，开始处理：{source.get('name') or source.get('slug') or source['id']}",
            "discovered": len(posts),
            "processed": 0,
            "progress": 0,
            "counters": dict(counters),
        }
        if not posts:
            return counters

        def mark_processed(processed: int) -> None:
            self._status = {
                **self._status,
                "processed": processed,
                "progress": int((processed / len(posts)) * 100) if posts else 100,
                "counters": dict(counters),
            }

        for index, parsed in enumerate(posts, start=1):
            if cooperate:
                cooperate()
            self._status = {
                **self._status,
                "running": True,
                "message": f"正在处理 {index}/{len(posts)}：{parsed.title or parsed.url}",
                "current_post": parsed.title or parsed.url,
                "processed": index - 1,
                "total": len(posts),
                "progress": int(((index - 1) / len(posts)) * 100) if posts else 0,
                "counters": dict(counters),
            }
            pub_date = parse_date(parsed.pub_date)
            if not pub_date:
                counters["skipped"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "skipped", "无有效发布日期")
                mark_processed(index)
                continue
            if pub_date and pub_date < start_date:
                counters["skipped"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "skipped", "早于起始日期")
                mark_processed(index)
                continue
            if incremental_cutoff_date and pub_date and pub_date < incremental_cutoff_date:
                counters["skipped"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "skipped", "早于本地最新时间")
                mark_processed(index)
                continue
            if self.db.is_site_post_in_active_trash(source["id"], parsed.url):
                counters["skipped"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "skipped", "仍在内容垃圾桶")
                mark_processed(index)
                continue
            decision = engine.evaluate(parsed.title, parsed.tags)
            if not decision.allowed:
                existing_post = self.db.get_site_post_by_source_url(source["id"], parsed.url)
                if existing_post:
                    self.db.set_site_post_status(existing_post["id"], "blocked", decision.reason)
                    self.db.set_site_post_flag(existing_post["id"], "is_blocked", True)
                    self._remove_post_from_gallery(source, existing_post)
                counters["blocked"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, decision.decision, decision.reason)
                mark_processed(index)
                continue
            counters["posts"] += 1
            post = self.db.upsert_site_post(source["id"], self._post_payload(parsed))
            dynamic_id = f"site:{source['id']}:{post['id']}"
            if self.db.is_blacklisted(dynamic_id, dynamic_id):
                self.db.set_site_post_status(post["id"], "blocked", "仍在黑名单")
                self.db.set_site_post_flag(post["id"], "is_blocked", True)
                counters["blocked"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "blocked", "仍在黑名单")
                mark_processed(index)
                continue
            self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, decision.decision, decision.reason)
            if post.get("is_blocked"):
                if post.get("filter_reason") == "手动屏蔽":
                    self._remove_post_from_gallery(source, post)
                    mark_processed(index)
                    continue
                self.db.set_site_post_flag(post["id"], "is_blocked", False)
                self.db.set_site_post_status(post["id"], "discovered", None)
                post = self.db.get_site_post(post["id"]) or {**post, "is_blocked": False, "filter_reason": None}

            post_folder = self.storage.site_post_folder(source["slug"], parsed.pub_date, post["slug"])
            download_assets = self._apply_image_skip(parsed.assets, source)[:max_media]
            if not download_assets:
                counters["no_media"] += 1
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "no-media", "未发现可下载媒体")
            download_jobs = []
            seen_urls: set[str] = set()
            for index, asset in enumerate(download_assets, start=1):
                if cooperate:
                    cooperate()
                asset_url = str(asset.url or "").strip()
                if not asset_url or asset_url in seen_urls:
                    continue
                seen_urls.add(asset_url)
                filename = clean_filename(asset.url, parsed.title, index, asset.media_type)
                db_asset = self.db.upsert_site_asset(post["id"], {"url": asset.url, "media_type": asset.media_type, "filename": filename})
                target = post_folder / filename
                if db_asset.get("status") == "duplicate":
                    continue
                if db_asset.get("status") == "ready" and target.exists() and target.stat().st_size > 0:
                    continue
                download_jobs.append({"asset_id": db_asset["id"], "url": asset.url, "target": target})
            for result in self._download_assets(download_jobs, settings, request_sleep):
                try:
                    if cooperate:
                        cooperate()
                    if result.get("error"):
                        raise result["error"]
                    target = result["target"]
                    self.db.set_site_asset_result(result["asset_id"], "ready", self.storage.relative_to_storage(target))
                    counters["downloaded"] += 1
                except Exception as exc:
                    self.db.set_site_asset_result(result["asset_id"], "failed", error=str(exc))
                    self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "download-error", f"下载失败: {exc}")
                    counters["errors"] += 1
            self.dedupe_post_images(post["id"])
            self.db.update_site_post_counts(post["id"])
            self._mirror_post_to_gallery(source, self.db.get_site_post(post["id"]) or post, parsed)
            mark_processed(index)
        return counters

    def dedupe_post_images(self, post_id: int) -> int:
        ready_images = [
            asset
            for asset in self.db.list_site_assets(int(post_id))
            if asset.get("status") == "ready" and asset.get("rel_path") and asset.get("media_type") == "image"
        ]
        seen: list[tuple[int, int]] = []
        removed = 0
        for asset in ready_images:
            source_path = self.storage.resolve_storage_path(asset.get("rel_path"))
            if not source_path or not source_path.exists():
                continue
            image_hash = self._image_content_hash(source_path)
            if image_hash is None:
                continue
            if any(self._hamming_distance(image_hash, existing_hash) <= 8 for existing_hash, _asset_id in seen):
                source_path.unlink(missing_ok=True)
                self.db.set_site_asset_result(int(asset["id"]), "duplicate", error="重复图片")
                removed += 1
                continue
            seen.append((image_hash, int(asset["id"])))
        if removed:
            self.db.update_site_post_counts(int(post_id))
        return removed

    def _download_assets(self, jobs: list[dict[str, Any]], settings: dict[str, Any], request_sleep: float) -> list[dict[str, Any]]:
        if not jobs:
            return []
        worker_count = min(SITE_MEDIA_DOWNLOAD_CONCURRENCY, len(jobs))
        if worker_count <= 1:
            return [self._download_asset(job, settings, request_sleep) for job in jobs]
        results = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(self._download_asset, job, settings, request_sleep): job for job in jobs}
            for future in as_completed(future_map):
                results.append(future.result())
        return results

    def _download_asset(self, job: dict[str, Any], settings: dict[str, Any], request_sleep: float) -> dict[str, Any]:
        target = job["target"]
        last_error: Exception | None = None
        for attempt in range(SITE_MEDIA_DOWNLOAD_RETRIES):
            try:
                downloader = self._new_media_downloader(settings)
                downloader.download(job["url"], target)
                if request_sleep:
                    time.sleep(request_sleep)
                return {**job, "target": target, "error": None}
            except Exception as exc:
                last_error = exc
                if attempt >= SITE_MEDIA_DOWNLOAD_RETRIES - 1:
                    break
                time.sleep(0.2 + attempt * 0.15)
        target.with_suffix(f"{target.suffix}.part").unlink(missing_ok=True)
        return {**job, "error": last_error}

    def _new_media_downloader(self, settings: dict[str, Any]) -> MediaDownloader:
        return MediaDownloader(
            timeout=SITE_MEDIA_DOWNLOAD_TIMEOUT,
            user_agent=str(settings.get("site_user_agent")),
            proxies=self._site_proxies(settings),
        )

    def _site_proxies(self, settings: dict[str, Any]) -> dict[str, str] | None:
        if not settings.get("site_proxy_enabled"):
            return None
        host = str(settings.get("site_proxy_host") or "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(settings.get("site_proxy_port") or 7890)
        except (TypeError, ValueError):
            port = 7890
        port = max(1, min(port, 65535))
        proxy = f"http://{host}:{port}"
        return {"http": proxy, "https": proxy}

    def _site_proxy_summary(self, settings: dict[str, Any]) -> dict[str, Any]:
        proxies = self._site_proxies(settings)
        if not proxies:
            return {"enabled": False}
        return {"enabled": True, "http": proxies["http"], "https": proxies["https"]}

    def _log_site_event(self, source: dict[str, Any], decision: str, title: str, reason: str = "") -> None:
        self.db.add_site_filter_log(
            source.get("id"),
            str(source.get("entry_url") or ""),
            title,
            decision,
            reason or str(source.get("name") or source.get("slug") or source.get("id") or ""),
        )

    def _page_request_timeout(self, settings: dict[str, Any]) -> int:
        try:
            timeout = int(settings.get("site_request_timeout") or SITE_PAGE_REQUEST_TIMEOUT)
        except (TypeError, ValueError):
            timeout = SITE_PAGE_REQUEST_TIMEOUT
        return max(30, min(timeout, 900))

    def _latest_site_sync_date(self, source: dict[str, Any]) -> date | None:
        source_id = int(source["id"])
        dates: list[date] = []
        for folder in self.db.list_site_gallery_folders(source_id):
            pub_ts = int(folder.get("pub_ts") or 0)
            if pub_ts > 0:
                dates.append(datetime.fromtimestamp(pub_ts, TIMEZONE).date())
        for post in self.db.list_site_posts(source_id=source_id):
            pub_date = parse_date(post.get("pub_date"))
            if pub_date:
                dates.append(pub_date)
        return max(dates) if dates else None

    def _remove_post_from_gallery(self, source: dict[str, Any], post: dict[str, Any]) -> None:
        fallback_folder_name = self._gallery_folder_name(source, post)
        folder_names = self.db.delete_site_gallery_post(source["id"], post["id"], fallback_folder_name)
        for folder_name in folder_names:
            self.storage.remove_folder_assets(folder_name)

    def _mirror_post_to_gallery(self, source: dict[str, Any], post: dict[str, Any], parsed: ParsedPost) -> None:
        ready_images = [
            asset
            for asset in self.db.list_site_assets(int(post["id"]))
            if asset.get("status") == "ready" and asset.get("rel_path") and asset.get("media_type") == "image"
        ]
        ready_videos = [
            asset
            for asset in self.db.list_site_assets(int(post["id"]))
            if asset.get("status") == "ready" and asset.get("rel_path") and asset.get("media_type") == "video"
        ]
        if not ready_images:
            return

        folder_name = self._gallery_folder_name(source, post)
        image_folder = self.storage.image_folder(folder_name)
        image_folder.mkdir(parents=True, exist_ok=True)
        for existing in image_folder.iterdir():
            if existing.is_file() and not existing.name.startswith("."):
                existing.unlink(missing_ok=True)
        for pair_index, asset in enumerate(ready_images, start=1):
            source_path = self.storage.resolve_storage_path(asset.get("rel_path"))
            if not source_path or not source_path.exists():
                continue
            target = image_folder / f"{pair_index:03d}__{asset['filename']}"
            if not target.exists() or target.stat().st_mtime < source_path.stat().st_mtime:
                shutil.copy2(source_path, target)

        pub_ts = self._pub_ts(parsed.pub_date)
        top_dynamic_id = f"site:{source['id']}:{post['id']}"
        source_dynamic_id = f"site:{source['id']}:{post['id']}"
        subscription_uid = self.site_subscription_uid(source["id"])
        subscription_name = str(source.get("name") or post.get("source_name") or f"站点 {source['id']}")
        title = str(post.get("title") or parsed.title or folder_name)
        excerpt = str(post.get("excerpt") or parsed.excerpt or "")
        metadata = {
            "source": "site",
            "site_post_id": int(post["id"]),
            "site_post_url": str(post.get("url") or parsed.url or ""),
        }

        if self.indexer:
            self.indexer.index_folder(
                folder_name=folder_name,
                pub_ts=pub_ts,
                title=title,
                text_prefix=excerpt,
                top_dynamic_id=top_dynamic_id,
                source_dynamic_id=source_dynamic_id,
                subscription_uid=subscription_uid,
                subscription_name=subscription_name,
                metadata=metadata,
            )
            self._replace_gallery_videos(folder_name, ready_videos)
            return

        image_assets = [
            {
                "pair_index": index,
                "filename": path.name,
                "rel_path": self.storage.relative_to_storage(path),
                "metadata": {"kind": "site-image"},
            }
            for index, path in enumerate(sorted(image_folder.iterdir()), start=1)
            if path.is_file() and not path.name.startswith(".")
        ]
        self.db.upsert_folder(
            {
                "folder_name": folder_name,
                "title": title,
                "text_prefix": excerpt,
                "pub_ts": pub_ts,
                "pub_time": datetime.fromtimestamp(pub_ts, TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
                "top_dynamic_id": top_dynamic_id,
                "source_dynamic_id": source_dynamic_id,
                "subscription_uid": subscription_uid,
                "subscription_name": subscription_name,
                "has_images": bool(image_assets),
                "has_livephoto": False,
                "metadata": metadata,
            }
        )
        self.db.replace_folder_assets(folder_name, "image", image_assets)
        self._replace_gallery_videos(folder_name, ready_videos)

    def _replace_gallery_videos(self, folder_name: str, ready_videos: list[dict[str, Any]]) -> None:
        video_assets = []
        for index, asset in enumerate(ready_videos, start=1):
            rel_path = asset.get("rel_path")
            if not rel_path:
                continue
            video_assets.append(
                {
                    "pair_index": index,
                    "filename": asset["filename"],
                    "rel_path": rel_path,
                    "metadata": {"kind": "site-video"},
                }
            )
        self.db.replace_folder_assets(folder_name, "video", video_assets)

    def _gallery_folder_name(self, source: dict[str, Any], post: dict[str, Any]) -> str:
        title = str(post.get("title") or "post")
        return f"site_{source['id']}_{post['id']}_{safe_slug(title, 'post', 48)}"

    def _pub_ts(self, value: str | None) -> int:
        parsed = parse_date(value)
        if not parsed:
            return 0
        return int(datetime.combine(parsed, datetime_time.min, tzinfo=TIMEZONE).timestamp())

    def mirror_existing_site_post(self, post: dict[str, Any]) -> None:
        source = {
            "id": post["source_id"],
            "slug": post.get("source_slug") or f"site-{post['source_id']}",
            "name": post.get("source_name") or f"站点 {post['source_id']}",
        }
        parsed = ParsedPost(
            url=str(post.get("url") or ""),
            title=str(post.get("title") or ""),
            pub_date=post.get("pub_date"),
            tags=[],
            excerpt=str(post.get("excerpt") or ""),
            assets=[],
        )
        self._mirror_post_to_gallery(source, post, parsed)

    @staticmethod
    def _image_content_hash(path) -> int | None:
        try:
            with Image.open(path) as image:
                normalized = ImageOps.exif_transpose(image).convert("L").resize((16, 16), Image.Resampling.LANCZOS)
                pixels = list(normalized.getdata())
        except Exception:
            return None
        average = sum(pixels) / len(pixels)
        value = 0
        for pixel in pixels:
            value = (value << 1) | (1 if pixel >= average else 0)
        return value

    @staticmethod
    def _hamming_distance(left: int, right: int) -> int:
        return (left ^ right).bit_count()

    @staticmethod
    def site_subscription_uid(source_id: int | str) -> str:
        return f"site:{source_id}"

    def _apply_image_skip(self, assets: list[Any], source: dict[str, Any]) -> list[Any]:
        skip_head = max(int(source.get("skip_head_images") or 0), 0)
        skip_tail = max(int(source.get("skip_tail_images") or 0), 0)
        if not skip_head and not skip_tail:
            return list(assets)

        image_positions = [index for index, asset in enumerate(assets) if asset.media_type == "image"]
        kept_image_positions = set(image_positions[skip_head:])
        if skip_tail:
            kept_image_positions -= set(image_positions[-skip_tail:])

        output = []
        for index, asset in enumerate(assets):
            if asset.media_type != "image" or index in kept_image_positions:
                output.append(asset)
        return output

    def _post_payload(self, parsed: ParsedPost) -> dict[str, Any]:
        return {
            "url": parsed.url,
            "title": parsed.title,
            "pub_date": parsed.pub_date,
            "tags": parsed.tags,
            "excerpt": parsed.excerpt[:1000],
            "status": "discovered",
        }

    def _preview_dict(self, post: ParsedPost) -> dict[str, Any]:
        return {
            "url": post.url,
            "title": post.title,
            "pub_date": post.pub_date,
            "tags": post.tags,
            "excerpt": post.excerpt[:240],
            "assets": [{"url": asset.url, "media_type": asset.media_type} for asset in post.assets],
        }
