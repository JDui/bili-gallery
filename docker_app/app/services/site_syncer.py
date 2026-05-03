from __future__ import annotations

import threading
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as datetime_time
from typing import Any

from app.db import Database
from app.services.media_indexer import MediaIndexer
from app.services.site_downloader import MediaDownloader
from app.services.site_filtering import RuleEngine
from app.services.site_parser import PageFetcher, ParsedPost, SourceParser
from app.services.storage import StorageService
from app.services.utils import TIMEZONE, clean_filename, parse_date, safe_slug


SITE_PAGE_REQUEST_TIMEOUT = 60
SITE_MEDIA_DOWNLOAD_TIMEOUT = 300
SITE_MEDIA_DOWNLOAD_CONCURRENCY = 3


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

    def test_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        settings = self.db.get_settings()
        fetcher = PageFetcher(timeout=SITE_PAGE_REQUEST_TIMEOUT, user_agent=str(settings.get("site_user_agent")))
        parser = SourceParser(fetcher)
        return [self._preview_dict(post) for post in parser.preview(source, limit=3)]

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

    def execute_sync(self, source_id: int | None = None, cooperate=None) -> dict[str, int]:
        details = {"sources": 0, "posts": 0, "downloaded": 0, "blocked": 0, "errors": 0}
        self._status = {"running": True, "message": "正在同步站点来源"}
        sources = [self.db.get_site_source(source_id)] if source_id else self.db.list_site_sources(include_disabled=False)
        for source in [item for item in sources if item]:
            if cooperate:
                cooperate()
            details["sources"] += 1
            self._status = {"running": True, "message": f"正在同步站点：{source.get('name') or source.get('slug') or source['id']}"}
            result = self._sync_source(source, cooperate=cooperate)
            for key, value in result.items():
                details[key] = int(details.get(key, 0)) + int(value)
        self._status = {"running": False, "message": "站点同步完成"}
        return details

    def _sync_source(self, source: dict[str, Any], cooperate=None) -> dict[str, int]:
        settings = self.db.get_settings()
        fetcher = PageFetcher(timeout=SITE_PAGE_REQUEST_TIMEOUT, user_agent=str(settings.get("site_user_agent")))
        parser = SourceParser(fetcher)
        engine = RuleEngine(self.db.get_site_rules())
        start_date = parse_date(source.get("start_date") or settings.get("site_default_start_date")) or date(2026, 4, 1)
        request_sleep = max(float(settings.get("site_request_sleep") or 0), 0)
        max_media = max(int(settings.get("site_max_media_per_post") or 100), 1)
        counters = {"posts": 0, "downloaded": 0, "blocked": 0, "errors": 0}

        for parsed in parser.discover(source, parse_assets=True):
            if cooperate:
                cooperate()
            pub_date = parse_date(parsed.pub_date)
            if pub_date and pub_date < start_date:
                self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, "skipped", "早于起始日期")
                continue
            counters["posts"] += 1
            post = self.db.upsert_site_post(source["id"], self._post_payload(parsed))
            decision = engine.evaluate(parsed.title, parsed.tags)
            self.db.add_site_filter_log(source["id"], parsed.url, parsed.title, decision.decision, decision.reason)
            if not decision.allowed:
                self.db.set_site_post_status(post["id"], "blocked", decision.reason)
                self.db.set_site_post_flag(post["id"], "is_blocked", True)
                counters["blocked"] += 1
                continue
            if post.get("is_blocked"):
                continue

            post_folder = self.storage.site_post_folder(source["slug"], parsed.pub_date, post["slug"])
            download_assets = self._apply_image_skip(parsed.assets, source)[:max_media]
            download_jobs = []
            for index, asset in enumerate(download_assets, start=1):
                if cooperate:
                    cooperate()
                filename = clean_filename(asset.url, parsed.title, index, asset.media_type)
                db_asset = self.db.upsert_site_asset(post["id"], {"url": asset.url, "media_type": asset.media_type, "filename": filename})
                target = post_folder / filename
                if db_asset.get("status") == "ready" and target.exists():
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
                    counters["errors"] += 1
            self.db.update_site_post_counts(post["id"])
            self._mirror_post_to_gallery(source, self.db.get_site_post(post["id"]) or post, parsed)
        return counters

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
        try:
            downloader = self._new_media_downloader(settings)
            target = job["target"]
            downloader.download(job["url"], target)
            if request_sleep:
                time.sleep(request_sleep)
            return {**job, "target": target, "error": None}
        except Exception as exc:
            return {**job, "error": exc}

    def _new_media_downloader(self, settings: dict[str, Any]) -> MediaDownloader:
        return MediaDownloader(timeout=SITE_MEDIA_DOWNLOAD_TIMEOUT, user_agent=str(settings.get("site_user_agent")))

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
                "metadata": {"source": "site"},
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
