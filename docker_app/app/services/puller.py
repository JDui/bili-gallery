from __future__ import annotations

from http.client import IncompleteRead
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.db import Database
from app.services.bilibili import BilibiliAuthService
from app.services.cleanup import CleanupService
from app.services.filtering import FilterEngine
from app.services.legacy_import import LegacyImporter
from app.services.legacy_bridge import (
    API_FEED,
    build_headers,
    feed_params,
    extract_picture_nodes,
    extract_primary_text,
    extract_pub_ts,
    is_top_item,
    find_nine_pic_blocks,
    safe_filename,
)
from app.services.media_indexer import MediaIndexer
from app.services.storage import StorageService
from app.services.utils import build_folder_name, compact_text, dumps_json, extract_chinese_prefix, loads_json
from app.services.utils import now_iso

API_NAV = "https://api.bilibili.com/x/web-interface/nav"


class ResourceDownloadError(RuntimeError):
    def __init__(self, url: str, detail: str) -> None:
        self.url = url
        self.detail = detail
        super().__init__(f"资源下载失败: {url} ({detail})")


@dataclass
class MatchCandidate:
    top_item: dict
    source_item: dict
    top_dynamic_id: str
    source_dynamic_id: str
    pub_ts: int
    text: str
    subscription_uid: str = ""
    subscription_name: str = ""
    pictures: list[dict] = field(default_factory=list)
    live_assets: list[dict] = field(default_factory=list)


@dataclass
class QueuedTask:
    queue_id: int
    kind: str
    label: str
    payload: dict[str, Any] = field(default_factory=dict)


def live_url(pic: dict) -> str:
    url = (pic.get("live_url") or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url.replace("http://", "https://")


def image_url(pic: dict) -> str:
    url = (pic.get("src") or pic.get("img_src") or pic.get("url") or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url.replace("http://", "https://")


def normalized_media_url(url: str) -> str:
    return url.split("?", 1)[0].strip()


def extract_live_assets(item: dict) -> list[dict]:
    assets = []
    for pic in extract_picture_nodes(item):
        url = live_url(pic)
        if not url:
            continue
        assets.append(
            {
                "live_url": url,
                "cover_url": image_url(pic),
            }
        )
    return assets


def live_cover_url(asset: dict) -> str:
    url = (asset.get("cover_url") or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url.replace("http://", "https://")


def find_live_blocks(item: dict, include_forwarded: bool) -> list[tuple[dict, dict, list[dict]]]:
    blocks: list[tuple[dict, dict, list[dict]]] = []
    assets = extract_live_assets(item)
    if assets:
        blocks.append((item, item, assets))
    if include_forwarded:
        orig = item.get("orig")
        if isinstance(orig, dict):
            orig_assets = extract_live_assets(orig)
            if orig_assets:
                blocks.append((item, orig, orig_assets))
    return blocks


class PullManager:
    def __init__(
        self,
        db: Database,
        storage: StorageService,
        indexer: MediaIndexer,
        cleanup: CleanupService,
        auth: BilibiliAuthService,
        legacy_importer: LegacyImporter,
    ) -> None:
        self.db = db
        self.storage = storage
        self.indexer = indexer
        self.cleanup = cleanup
        self.auth = auth
        self.legacy_importer = legacy_importer
        self._lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._queue: deque[QueuedTask] = deque()
        self._next_queue_id = 1
        self._pause_requested = False
        self._cancel_requested = False
        self.site_syncer: Any | None = None
        self._event_log: deque[dict[str, Any]] = deque(maxlen=120)
        self._status: dict[str, Any] = {
            "running": False,
            "message": "空闲",
            "mode": "idle",
        }
        self._user_agents = [
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
        ]
        self._accept_languages = [
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.95,en;q=0.75",
            "zh-CN,zh;q=0.9,ja;q=0.7,en;q=0.6",
        ]
        self._feed_web_locations = ["333.1387", "333.1368", "333.999"]
        self._feed_feature_variants = [
            "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete,onlyfansQaCard,commentsNewVersion",
            "itemOpusStyle,opusBigCover,commentsNewVersion,onlyfansAssetsV2",
            "itemOpusStyle,commentsNewVersion,onlyfansAssetsV2",
            "itemOpusStyle,opusBigCover",
        ]
        self._navigation_accept = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        )

    def attach_site_syncer(self, site_syncer: Any) -> None:
        self.site_syncer = site_syncer

    def start_startup_sync(self) -> bool:
        if not self._acquire(mode="startup", message="正在整理图库"):
            return False
        thread = threading.Thread(target=self._run_startup_sync, daemon=True)
        thread.start()
        return True

    def start_pull(self) -> dict[str, Any]:
        settings = self.db.get_settings()
        force_reload = bool(settings.get("reload_all_once"))
        label = "全量重载当前动态" if force_reload else "拉取动态"
        queued = self._queue_or_start("pull", label, self._run_pull)
        message = "已加入任务队列" if queued else ("已开始全量重载当前动态" if force_reload else "已开始拉取")
        return {"ok": True, "message": message, "queued": queued}

    def start_reload_all(self) -> dict[str, Any]:
        self.db.save_settings({"reload_all_once": True})
        return self.start_pull()

    def start_subscription_reload(self, uid: str) -> dict[str, Any]:
        subscription = self.db.get_subscription(uid)
        if not subscription:
            raise RuntimeError("订阅不存在")
        label = f"全量校验拉取 {subscription.get('uname') or uid}"
        queued = self._queue_or_start("subscription-reload", label, self._run_subscription_reload, str(uid))
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始全量校验拉取", "queued": queued}

    def start_subscription_pull(self, uid: str) -> dict[str, Any]:
        subscription = self.db.get_subscription(uid)
        if not subscription:
            raise RuntimeError("订阅不存在")
        label = f"拉取 {subscription.get('uname') or uid}"
        queued = self._queue_or_start("subscription-pull", label, self._run_subscription_pull, str(uid))
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始拉取当前订阅", "queued": queued}

    def toggle_subscription(self, uid: str) -> dict[str, Any]:
        subscription = self.db.get_subscription(uid)
        if not subscription:
            raise RuntimeError("订阅不存在")
        next_status = "paused" if subscription.get("status") == "active" else "active"
        self.db.update_subscription_status(uid, next_status)
        return {
            "ok": True,
            "status": next_status,
            "message": "订阅已暂停" if next_status == "paused" else "订阅已继续",
        }

    def unsubscribe_and_delete(self, uid: str) -> dict[str, Any]:
        subscription = self.db.get_subscription(uid)
        if not subscription:
            raise RuntimeError("订阅不存在")
        folders = [folder for folder in self.db.list_folders() if str(folder.get("subscription_uid") or "") == str(uid)]
        removed_dirs = 0
        for folder in folders:
            self.db.clear_deleted_pair_marks(folder["top_dynamic_id"], folder["source_dynamic_id"])
            removed_dirs += self.storage.remove_folder_assets(folder["folder_name"])
            self.db.delete_folder(folder["folder_name"])
        self.cleanup.run()
        self.db.delete_subscription(uid)
        return {"ok": True, "message": "已退订并删除相关内容", "removed_folders": len(folders), "removed_dirs": removed_dirs}

    def start_review_approval(self, item_id: int) -> dict[str, Any]:
        if not self.db.get_review_item(item_id):
            raise RuntimeError("待审核项不存在")
        self.db.set_review_status(item_id, "queued")
        queued = self._queue_or_start(
            "review",
            f"处理待审核项 {item_id}",
            self._run_review_download,
            item_id,
        )
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始下载审核通过内容", "queued": queued}

    def start_validation(self) -> dict[str, Any]:
        queued = self._queue_or_start("validate", "校验当前内容", self._run_validation)
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始校验当前内容", "queued": queued}

    def start_gallery_index_rebuild(self) -> dict[str, Any]:
        queued = self._queue_or_start("index", "重建页面索引", self._run_gallery_index_rebuild)
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始重建页面索引", "queued": queued}

    def start_site_sync(self, source_id: int | None = None) -> dict[str, Any]:
        if self.site_syncer is None:
            raise RuntimeError("站点同步器未初始化")
        source = self.db.get_site_source(source_id) if source_id else None
        label = f"同步站点 {source.get('name') or source_id}" if source else "同步全部站点"
        queued = self._queue_or_start("site-sync", label, self._run_site_sync, source_id)
        return {"ok": True, "message": "已加入任务队列" if queued else "已开始站点同步", "queued": queued}

    def status(self) -> dict[str, Any]:
        latest = self._latest_task_run(["pull", "review", "validate", "startup", "index", "site-sync"])
        return {
            **self._status,
            "paused": self._pause_requested,
            "cancel_requested": self._cancel_requested,
            "queue": [task.__dict__ for task in list(self._queue)],
            "events": self._runtime_events(),
            "last_run": latest,
            "gallery_index": self.db.gallery_index_status(),
        }

    def pause_current(self) -> dict[str, Any]:
        if not self._lock.locked():
            raise RuntimeError("当前没有可暂停的任务")
        self._pause_requested = True
        self._status = {**self._status, "message": f"{self._status.get('message', '任务执行中')} · 已暂停"}
        return {"ok": True, "message": "当前任务已暂停"}

    def resume_current(self) -> dict[str, Any]:
        if not self._lock.locked():
            raise RuntimeError("当前没有可恢复的任务")
        self._pause_requested = False
        return {"ok": True, "message": "当前任务已继续执行"}

    def cancel_current(self) -> dict[str, Any]:
        if not self._lock.locked():
            raise RuntimeError("当前没有可取消的任务")
        self._cancel_requested = True
        return {"ok": True, "message": "已请求取消当前任务"}

    def cancel_queued(self, queue_id: int) -> dict[str, Any]:
        removed: QueuedTask | None = None
        with self._queue_lock:
            next_queue: deque[QueuedTask] = deque()
            while self._queue:
                task = self._queue.popleft()
                if removed is None and task.queue_id == queue_id:
                    removed = task
                    continue
                next_queue.append(task)
            self._queue = next_queue
        if removed is None:
            raise RuntimeError("排队任务不存在")
        if removed.kind == "review":
            item_id = int(removed.payload.get("args", [0])[0])
            if self.db.get_review_item(item_id):
                self.db.set_review_status(item_id, "pending")
        return {"ok": True, "message": f"已撤销排队任务：{removed.label}"}

    def retry_task_run(self, task_id: int) -> dict[str, Any]:
        task = self.db.get_task_run(task_id)
        if not task:
            raise RuntimeError("任务不存在")
        details = self._loads_payload(task.get("details_json") or "{}")
        retry_action = details.get("retry_action") or {}
        kind = str(retry_action.get("kind") or "").strip()
        if not kind:
            raise RuntimeError("当前任务不支持重试")
        if kind == "pull":
            return self.start_pull()
        if kind == "subscription-pull":
            return self.start_subscription_pull(str(retry_action.get("uid") or ""))
        if kind == "subscription-reload":
            return self.start_subscription_reload(str(retry_action.get("uid") or ""))
        if kind == "review":
            return self.start_review_approval(int(retry_action.get("item_id") or 0))
        if kind == "validate":
            return self.start_validation()
        if kind == "index":
            return self.start_gallery_index_rebuild()
        if kind == "site-sync":
            source_id = retry_action.get("source_id")
            return self.start_site_sync(int(source_id) if source_id is not None else None)
        raise RuntimeError("当前任务不支持重试")

    def move_to_trash(self, folder_name: str, reason: str = "不喜欢") -> dict[str, Any]:
        folder = next((item for item in self.db.list_folders() if item["folder_name"] == folder_name), None)
        if not folder:
            raise RuntimeError("动态不存在")
        assets = self.db.list_assets_for_folder(folder_name)
        self.db.upsert_trash_item(folder, assets)
        self.db.add_blacklist_item(
            folder["top_dynamic_id"],
            folder["source_dynamic_id"],
            folder_name,
            folder.get("title") or folder_name,
            reason,
        )
        self.db.clear_deleted_pair_marks(folder["top_dynamic_id"], folder["source_dynamic_id"])
        removed_dirs = self.storage.remove_folder_assets(folder_name)
        self.db.delete_folder(folder_name)
        self.cleanup.run()
        self._finalize_deleted_folder(folder_name)
        return {"ok": True, "message": "已加入黑名单并移入垃圾桶", "removed_dirs": removed_dirs}

    def restore_from_trash(self, item_id: int, repull_now: bool = False) -> dict[str, Any]:
        trash_item = self.db.get_trash_item(item_id)
        if not trash_item or trash_item.get("restored_at"):
            raise RuntimeError("垃圾桶内容不存在")
        folder = self._loads_payload(trash_item["folder_json"])
        self.db.delete_blacklist_item(folder["top_dynamic_id"], folder["source_dynamic_id"])
        self.db.clear_deleted_pair_marks(folder["top_dynamic_id"], folder["source_dynamic_id"])
        self.db.mark_trash_restored(item_id)
        if repull_now:
            self.restore_dynamic_now(folder["top_dynamic_id"], folder["source_dynamic_id"])
            return {"ok": True, "message": "已恢复并重新拉取当前动态"}
        return {"ok": True, "message": "已恢复黑名单状态，下次拉取时会重新纳入"}

    def reject_review_item(self, item_id: int) -> dict[str, Any]:
        review_item = self.db.get_review_item(item_id)
        if not review_item:
            raise RuntimeError("待审核项不存在")
        payload = self._loads_payload(review_item["payload_json"])
        candidate = self._candidate_from_payload(payload)
        folder_name = review_item.get("folder_name_candidate") or self._folder_preview_name(candidate.pub_ts, candidate.text)
        trash_folder = {
            "folder_name": folder_name,
            "title": candidate.text or folder_name,
            "text_prefix": extract_chinese_prefix(candidate.text),
            "pub_ts": candidate.pub_ts,
            "pub_time": self._folder_pub_time(candidate.pub_ts),
            "top_dynamic_id": candidate.top_dynamic_id,
            "source_dynamic_id": candidate.source_dynamic_id,
            "subscription_uid": candidate.subscription_uid,
            "subscription_name": candidate.subscription_name,
            "has_images": bool(candidate.pictures),
            "has_livephoto": bool(candidate.live_assets),
        }
        self.db.upsert_trash_item(trash_folder, [])
        self.db.add_blacklist_item(
            candidate.top_dynamic_id,
            candidate.source_dynamic_id,
            folder_name,
            candidate.text or folder_name,
            "审核忽略",
        )
        self.db.set_review_status(item_id, "rejected")
        return {"ok": True, "message": "已忽略并移入垃圾桶"}

    def clear_all_content(self) -> dict[str, Any]:
        if not self._acquire(mode="clear", message="正在清空内容数据"):
            raise RuntimeError("已有任务正在执行")
        try:
            removed = self.storage.clear_library_data()
            self.db.clear_content_data()
            self.cleanup.run()
            self.indexer.rebuild_gallery_indexes()
            self._status = {"running": False, "message": "内容数据已清空", "mode": "idle"}
            return {"ok": True, "message": "已清空所有内容数据，登录状态已保留", "removed": removed}
        finally:
            self._release()
            self._run_next_queued_task()

    def delete_pair(self, folder_name: str, pair_index: int) -> dict[str, Any]:
        folder = next((item for item in self.db.list_folders() if item["folder_name"] == folder_name), None)
        if not folder:
            raise RuntimeError("动态不存在")
        assets = [asset for asset in self.db.list_assets_for_folder(folder_name) if int(asset["pair_index"]) == int(pair_index)]
        if not assets:
            raise RuntimeError("当前图片组不存在或已经删除")
        self.db.add_deleted_pair_mark(
            folder["top_dynamic_id"],
            folder["source_dynamic_id"],
            folder_name,
            int(pair_index),
            reason="手动删除",
        )
        removed_files = 0
        for asset in assets:
            removed_files += self.storage.remove_asset_files(asset)
            self.db.delete_asset(int(asset["id"]))
        self._finalize_deleted_folder(folder_name, folder)
        return {"ok": True, "message": "当前图片组已永久删除，后续全量拉取不会恢复", "removed_files": removed_files}

    def _finalize_deleted_folder(self, folder_name: str, folder: dict[str, Any] | None = None) -> None:
        time.sleep(0.2)
        assets = self.db.list_assets_for_folder(folder_name)
        if assets:
            target_folder = folder or self.db.get_folder(folder_name)
            if not target_folder:
                return
            self.indexer.index_folder(
                folder_name=folder_name,
                pub_ts=int(target_folder.get("pub_ts") or 0),
                title=target_folder.get("title") or folder_name,
                text_prefix=target_folder.get("text_prefix") or "",
                top_dynamic_id=str(target_folder.get("top_dynamic_id") or ""),
                source_dynamic_id=str(target_folder.get("source_dynamic_id") or ""),
                subscription_uid=str(target_folder.get("subscription_uid") or ""),
                subscription_name=target_folder.get("subscription_name"),
                review_status=target_folder.get("review_status", "approved"),
                review_reason=target_folder.get("review_reason"),
                metadata=loads_json(target_folder.get("metadata_json"), {}),
                generate_derivatives=False,
            )
            return
        self.storage.remove_folder_assets(folder_name)
        self.db.delete_folder_if_empty(folder_name)
        if self.db.get_folder(folder_name):
            self.db.delete_folder(folder_name)

    def restore_dynamic_now(self, top_dynamic_id: str, source_dynamic_id: str, subscription_uid: str | None = None) -> None:
        cookie_state = self.auth.get_cookie_state()
        if not cookie_state.cookie:
            raise RuntimeError("未登录哔哩哔哩，请先扫码登录")
        settings = self.db.get_settings()
        host_mid = int(subscription_uid or settings["host_mid"])
        subscription = self.db.get_subscription(str(subscription_uid)) if subscription_uid else None
        options = self._subscription_options(settings, subscription_uid, subscription)
        detail_item = self.auth.fetch_dynamic_detail(top_dynamic_id, host_mid, cookie_state.cookie)
        candidates = self._collect_candidates(detail_item, options["include_forwarded"])
        candidate = next(
            (
                item for item in candidates
                if item.top_dynamic_id == str(top_dynamic_id) and item.source_dynamic_id == str(source_dynamic_id)
            ),
            None,
        )
        if not candidate:
            raise RuntimeError("未找到可恢复的动态内容")
        candidate.subscription_uid = str(subscription_uid or settings["host_mid"])
        candidate.subscription_name = self._subscription_name(candidate.subscription_uid)
        candidate = self._apply_deleted_pair_marks(candidate)
        if not self._candidate_has_selected_media(candidate, options):
            raise RuntimeError("当前订阅已关闭相关抓取类型，无法恢复这条动态")
        self._download_candidate(candidate, settings, cookie_state.cookie, subscription=subscription)
        self.cleanup.run()

    def _run_pull(self) -> None:
        task_id = self.db.create_task_run("pull", "running", "开始拉取", {"retry_action": {"kind": "pull"}})
        schedule_index_check = False
        try:
            stats = self._execute_pull()
            cleanup_stats = self.cleanup.run()
            stats["cleanup"] = cleanup_stats
            gallery_index_check, schedule_index_check = self._evaluate_auto_gallery_index_check("拉取")
            stats["gallery_index_check"] = gallery_index_check
            stats["events"] = self._runtime_events()
            self.db.finish_task_run(task_id, "success", "拉取完成", stats)
            self._status = {"running": False, "message": "拉取完成", "mode": "idle", "stats": stats}
        except Exception as exc:
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {"error": str(exc), "retry_action": {"kind": "pull"}, "events": self._runtime_events()},
            )
            self._status = {"running": False, "message": f"拉取失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            if schedule_index_check:
                self._enqueue_index_task("拉取后自动重建页面索引")
            self._run_next_queued_task()

    def _run_subscription_reload(self, uid: str) -> None:
        task_id = self.db.create_task_run(
            "pull",
            "running",
            f"开始全量校验拉取 {uid}",
            {"retry_action": {"kind": "subscription-reload", "uid": str(uid)}},
        )
        schedule_index_check = False
        try:
            stats = self._execute_pull(target_uids=[uid], force_reload=True)
            validation = self._execute_validation(target_uids=[uid])
            cleanup_stats = self.cleanup.run()
            stats["validation"] = validation
            stats["cleanup"] = cleanup_stats
            gallery_index_check, schedule_index_check = self._evaluate_auto_gallery_index_check("全量校验拉取")
            stats["gallery_index_check"] = gallery_index_check
            stats["events"] = self._runtime_events()
            self.db.finish_task_run(task_id, "success", "全量校验拉取完成", stats)
            self._status = {"running": False, "message": "全量校验拉取完成", "mode": "idle", "stats": stats}
        except Exception as exc:
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {
                    "error": str(exc),
                    "retry_action": {"kind": "subscription-reload", "uid": str(uid)},
                    "events": self._runtime_events(),
                },
            )
            self._status = {"running": False, "message": f"全量校验拉取失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            if schedule_index_check:
                self._enqueue_index_task("全量校验拉取后自动重建页面索引")
            self._run_next_queued_task()

    def _run_subscription_pull(self, uid: str) -> None:
        task_id = self.db.create_task_run(
            "pull",
            "running",
            f"开始拉取订阅 {uid}",
            {"retry_action": {"kind": "subscription-pull", "uid": str(uid)}},
        )
        schedule_index_check = False
        try:
            stats = self._execute_pull(target_uids=[uid], force_reload=False)
            cleanup_stats = self.cleanup.run()
            stats["cleanup"] = cleanup_stats
            gallery_index_check, schedule_index_check = self._evaluate_auto_gallery_index_check("订阅拉取")
            stats["gallery_index_check"] = gallery_index_check
            stats["events"] = self._runtime_events()
            self.db.finish_task_run(task_id, "success", "订阅拉取完成", stats)
            self._status = {"running": False, "message": "订阅拉取完成", "mode": "idle", "stats": stats}
        except Exception as exc:
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {
                    "error": str(exc),
                    "retry_action": {"kind": "subscription-pull", "uid": str(uid)},
                    "events": self._runtime_events(),
                },
            )
            self._status = {"running": False, "message": f"订阅拉取失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            if schedule_index_check:
                self._enqueue_index_task("订阅拉取后自动重建页面索引")
            self._run_next_queued_task()

    def _run_site_sync(self, source_id: int | None = None) -> None:
        if self.site_syncer is None:
            self._release()
            self._run_next_queued_task()
            return
        retry_action = {"kind": "site-sync", "source_id": source_id}
        task_id = self.db.create_task_run("site-sync", "running", "开始同步站点来源", {"retry_action": retry_action})
        try:
            stats = self.site_syncer.execute_sync(source_id, cooperate=self._cooperate)
            stats["retry_action"] = retry_action
            stats["events"] = self._runtime_events()
            self.db.finish_task_run(task_id, "success", "站点同步完成", stats)
            self._status = {"running": False, "message": "站点同步完成", "mode": "idle", "stats": stats}
        except Exception as exc:
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {"error": str(exc), "retry_action": retry_action, "events": self._runtime_events()},
            )
            self._status = {"running": False, "message": f"站点同步失败: {exc}", "mode": "idle"}
            if self.site_syncer is not None:
                self.site_syncer._status = {"running": False, "message": f"站点同步失败: {exc}"}
        finally:
            self._release()
            self._run_next_queued_task()

    def _active_subscriptions(self, target_uids: list[str] | None = None) -> list[dict[str, Any]]:
        subscriptions = self.db.list_subscriptions(include_paused=True)
        if target_uids is not None:
            wanted = {str(uid) for uid in target_uids}
            subscriptions = [item for item in subscriptions if str(item["uid"]) in wanted]
        else:
            if subscriptions:
                subscriptions = [item for item in subscriptions if item.get("status") != "paused"]
            else:
                settings = self.db.get_settings()
                default_uid = str(settings["host_mid"])
                return [self.db.upsert_subscription(default_uid)]
        if subscriptions:
            return subscriptions
        if target_uids is not None:
            return []
        raise RuntimeError("当前没有启用中的订阅")

    def _subscription_name(self, uid: str) -> str:
        subscription = self.db.get_subscription(uid)
        return subscription.get("uname") or f"UID {uid}" if subscription else f"UID {uid}"

    def _subscription_options(
        self,
        settings: dict[str, Any],
        subscription_uid: str | None = None,
        subscription: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        record = subscription or (self.db.get_subscription(str(subscription_uid)) if subscription_uid else None) or {}
        raw_threshold = record.get("image_min_count", settings.get("image_min_count", 6))
        try:
            image_min_count = int(raw_threshold)
        except (TypeError, ValueError):
            image_min_count = 6
        image_min_count = max(-1, min(12, image_min_count))
        pull_images_enabled = bool(record.get("pull_images", settings.get("pull_images", True))) and image_min_count >= 0
        return {
            "pull_images": pull_images_enabled,
            "image_min_count": image_min_count,
            "pull_livephoto": bool(record.get("pull_livephoto", settings.get("pull_livephoto", True))),
            "include_forwarded": bool(record.get("include_forwarded", settings.get("include_forwarded", True))),
        }

    def _candidate_has_selected_media(self, candidate: MatchCandidate, options: dict[str, bool]) -> bool:
        return bool(self._candidate_matches_image_threshold(candidate, options) or (options["pull_livephoto"] and candidate.live_assets))

    def _candidate_picture_count_for_threshold(self, candidate: MatchCandidate) -> int:
        return sum(1 for picture in candidate.pictures if not picture.get("live_cover"))

    def _candidate_matches_image_threshold(self, candidate: MatchCandidate, options: dict[str, bool]) -> bool:
        if not options["pull_images"]:
            return False
        threshold = int(options.get("image_min_count", 6))
        if threshold < 0:
            return False
        picture_count = self._candidate_picture_count_for_threshold(candidate)
        return picture_count > 0 and picture_count >= threshold

    def _required_image_count(self, candidate: MatchCandidate, options: dict[str, bool]) -> int:
        required = 0
        if self._candidate_matches_image_threshold(candidate, options):
            required = max(required, len(candidate.pictures))
        if options["pull_livephoto"] and candidate.live_assets:
            cover_urls = {normalized_media_url(live_cover_url(asset)) for asset in candidate.live_assets if live_cover_url(asset)}
            required = max(required, len(cover_urls))
        return required

    def _pictures_for_download(self, candidate: MatchCandidate, options: dict[str, bool]) -> list[dict]:
        if self._candidate_matches_image_threshold(candidate, options):
            return list(candidate.pictures)
        if options["pull_livephoto"] and candidate.live_assets:
            cover_urls = {normalized_media_url(live_cover_url(asset)) for asset in candidate.live_assets if live_cover_url(asset)}
            return [picture for picture in candidate.pictures if normalized_media_url(image_url(picture)) in cover_urls]
        return []

    def _normalize_candidate_media(self, candidate: MatchCandidate, options: dict[str, bool]) -> MatchCandidate:
        if not options["pull_livephoto"] or not candidate.live_assets:
            return candidate
        pictures = list(candidate.pictures)
        seen_urls = {normalized_media_url(image_url(picture)) for picture in pictures if image_url(picture)}
        changed = False
        for asset in candidate.live_assets:
            cover_url = live_cover_url(asset)
            if not cover_url:
                continue
            cover_key = normalized_media_url(cover_url)
            if not cover_key or cover_key in seen_urls:
                continue
            pictures.append(
                {
                    "src": cover_url,
                    "img_src": cover_url,
                    "url": cover_url,
                    "live_cover": True,
                }
            )
            seen_urls.add(cover_key)
            changed = True
        if not changed:
            return candidate
        return MatchCandidate(
            top_item=candidate.top_item,
            source_item=candidate.source_item,
            top_dynamic_id=candidate.top_dynamic_id,
            source_dynamic_id=candidate.source_dynamic_id,
            pub_ts=candidate.pub_ts,
            text=candidate.text,
            subscription_uid=candidate.subscription_uid,
            subscription_name=candidate.subscription_name,
            pictures=pictures,
            live_assets=list(candidate.live_assets),
        )

    def _build_request_headers(
        self,
        host_uid: str,
        cookie: str,
        purpose: str = "feed",
        referer_url: str | None = None,
        profile: dict[str, str] | None = None,
        navigation: bool = False,
    ) -> dict[str, str]:
        headers = dict(build_headers(host_mid=int(host_uid), cookie=cookie))
        active_profile = profile or self._make_request_profile()
        headers["User-Agent"] = active_profile["user_agent"]
        headers["Accept-Language"] = active_profile["accept_language"]
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
        headers["DNT"] = "1"
        headers["Priority"] = active_profile["priority"]
        headers["Sec-CH-UA"] = '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="24"'
        headers["Sec-CH-UA-Mobile"] = "?0"
        headers["Sec-CH-UA-Platform"] = active_profile["platform"]
        if referer_url:
            headers["Referer"] = referer_url
        if navigation:
            headers["Accept"] = self._navigation_accept
            headers["Upgrade-Insecure-Requests"] = "1"
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Site"] = "same-origin" if referer_url and "space.bilibili.com" in referer_url else "none"
            headers["Sec-Fetch-User"] = "?1"
        elif purpose == "asset":
            headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,video/*,*/*;q=0.8"
        elif purpose == "detail":
            headers["Referer"] = f"https://www.bilibili.com/opus/{host_uid}"
        return headers

    def _make_request_profile(self) -> dict[str, str]:
        return {
            "user_agent": random.choice(self._user_agents),
            "accept_language": random.choice(self._accept_languages),
            "priority": random.choice(["u=1, i", "u=2, i", "u=3"]),
            "platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        }

    def _session_profile(self, session: requests.Session) -> dict[str, str]:
        profile = getattr(session, "_bg_profile", None)
        if isinstance(profile, dict):
            return profile
        profile = self._make_request_profile()
        setattr(session, "_bg_profile", profile)
        return profile

    def _prime_feed_session(self, session: requests.Session, host_uid: str, strong: bool = False) -> None:
        profile = self._session_profile(session)
        session.headers.update(
            self._build_request_headers(
                host_uid,
                session.headers.get("Cookie", ""),
                purpose="feed",
                referer_url=f"https://space.bilibili.com/{host_uid}/dynamic",
                profile=profile,
            )
        )
        routes = [
            ("https://www.bilibili.com/", None),
            (f"https://space.bilibili.com/{host_uid}", "https://www.bilibili.com/"),
            (f"https://space.bilibili.com/{host_uid}/dynamic", f"https://space.bilibili.com/{host_uid}"),
            (API_NAV, f"https://space.bilibili.com/{host_uid}/dynamic"),
        ]
        if strong:
            random.shuffle(routes)
            routes = routes[: random.randint(3, 4)]
        for index, (url, referer_url) in enumerate(routes):
            try:
                session.headers.update(
                    self._build_request_headers(
                        host_uid,
                        session.headers.get("Cookie", ""),
                        purpose="feed",
                        referer_url=referer_url,
                        profile=profile,
                        navigation=url != API_NAV,
                    )
                )
                session.get(url, timeout=15)
                dwell_base = 0.18 + index * 0.06
                if strong:
                    dwell_base += 0.22
                self._sleep_request_jitter(dwell_base, spread=0.46 if strong else 0.22)
            except requests.RequestException:
                continue

    def _parse_cookie_header(self, cookie: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for chunk in str(cookie or "").split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            name = name.strip()
            value = value.strip()
            if name and value:
                result[name] = value
        return result

    def _new_feed_session(self, host_uid: str, cookie: str) -> requests.Session:
        session = requests.Session()
        profile = self._make_request_profile()
        setattr(session, "_bg_profile", profile)
        session.headers.update(
            self._build_request_headers(
                host_uid,
                cookie,
                purpose="feed",
                referer_url=f"https://space.bilibili.com/{host_uid}/dynamic",
                profile=profile,
            )
        )
        session.cookies.update(self._parse_cookie_header(cookie))
        return session

    def _feed_param_variants(self, host_uid: str, offset: str) -> list[dict[str, str]]:
        base = dict(feed_params(int(host_uid), offset))
        variants: list[dict[str, str]] = []
        for web_location in self._feed_web_locations:
            for features in self._feed_feature_variants:
                variant = dict(base)
                variant["web_location"] = web_location
                variant["features"] = features
                variants.append(variant)
        return variants

    def _feed_referer(self, host_uid: str, offset: str, attempt: int) -> str:
        referers = [
            f"https://space.bilibili.com/{host_uid}/dynamic",
            f"https://space.bilibili.com/{host_uid}",
            "https://www.bilibili.com/",
        ]
        if offset:
            referers.insert(1, f"https://space.bilibili.com/{host_uid}/dynamic?offset={offset}")
        return referers[attempt % len(referers)]

    def _request_feed_page(
        self,
        session: requests.Session,
        host_uid: str,
        offset: str,
        cookie: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        variants = self._feed_param_variants(host_uid, offset)
        profile = self._session_profile(session)
        for attempt in range(12):
            self._cooperate()
            referer_url = self._feed_referer(host_uid, offset, attempt)
            session.headers.update(
                self._build_request_headers(
                    host_uid,
                    cookie,
                    purpose="feed",
                    referer_url=referer_url,
                    profile=profile,
                )
            )
            if attempt:
                self._prime_feed_session(session, host_uid, strong=attempt >= 2)
            self._sleep_request_jitter(0.16 + attempt * 0.04, spread=0.26 + attempt * 0.08)
            try:
                params = dict(variants[attempt % len(variants)])
                response = session.get(
                    API_FEED,
                    headers=session.headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                code = int(payload.get("code", 0))
                if code == 0:
                    return payload.get("data") or {}
                last_error = RuntimeError(f"API error: {code} {payload.get('message')}")
                if code in (-352, -401) and attempt < 11:
                    self._refresh_feed_session(session, host_uid, cookie)
                    self._sleep_request_jitter(0.42 + attempt * 0.08, spread=0.58)
                    continue
                raise last_error
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 412 and attempt < 11:
                    self._refresh_feed_session(session, host_uid, cookie)
                    self._sleep_request_jitter(0.5 + attempt * 0.1, spread=0.7)
                    continue
                raise RuntimeError(f"动态列表请求失败: {exc}") from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 11:
                    self._refresh_feed_session(session, host_uid, cookie)
                    self._sleep_request_jitter(0.28 + attempt * 0.06, spread=0.46)
                    continue
                raise RuntimeError(f"动态列表请求失败: {exc}") from exc
        raise RuntimeError(str(last_error or "动态列表请求失败"))

    def _refresh_feed_session(self, session: requests.Session, host_uid: str, cookie: str) -> None:
        session.cookies.clear()
        session.cookies.update(self._parse_cookie_header(cookie))
        session.headers.clear()
        profile = self._session_profile(session)
        session.headers.update(self._build_request_headers(host_uid, cookie, purpose="feed", profile=profile))
        self._prime_feed_session(session, host_uid, strong=True)

    def _sleep_feed_page_dwell(self, page_num: int, item_count: int, has_more: bool) -> None:
        if not has_more:
            return
        base = 0.42 + min(item_count, 12) * 0.045 + min(page_num, 4) * 0.06
        spread = 0.42 + min(item_count, 10) * 0.03
        self._sleep_request_jitter(base, spread=spread)

    def _iter_feed_pages(self, host_uid: str, cookie: str):
        session = self._new_feed_session(host_uid, cookie)
        self._prime_feed_session(session, host_uid, strong=True)
        offset = ""
        page = 0
        seen_offsets: set[str] = set()
        while True:
            page += 1
            try:
                data = self._request_feed_page(session, host_uid, offset, cookie)
            except RuntimeError as exc:
                if "412" not in str(exc) and "-352" not in str(exc) and "-401" not in str(exc):
                    raise
                session.close()
                session = self._new_feed_session(host_uid, cookie)
                self._prime_feed_session(session, host_uid)
                try:
                    data = self._request_feed_page(session, host_uid, offset, cookie)
                except RuntimeError:
                    if page == 1:
                        raise
                    self._append_event(
                        "分页请求失败，提前结束本订阅扫描",
                        uid=host_uid,
                        page=page,
                        offset=offset or "<first>",
                        error=str(exc),
                    )
                    break
            items = data.get("items") or []
            next_offset = data.get("offset") or ""
            has_more = bool(data.get("has_more"))
            yield page, items
            self._sleep_feed_page_dwell(page, len(items), has_more)
            if not has_more or not next_offset or next_offset in seen_offsets:
                break
            seen_offsets.add(next_offset)
            offset = next_offset
        session.close()

    def _apply_deleted_pair_marks(self, candidate: MatchCandidate) -> MatchCandidate:
        deleted_pairs = self.db.list_deleted_pair_indices(candidate.top_dynamic_id, candidate.source_dynamic_id)
        if not deleted_pairs:
            return candidate
        pair_plan = self._pair_plan(candidate)
        filtered_pictures = []
        for index, picture in enumerate(candidate.pictures, start=1):
            url = image_url(picture)
            pair_index = pair_plan["picture_indices"].get(normalized_media_url(url), index) if url else index
            if pair_index not in deleted_pairs:
                filtered_pictures.append(picture)
        filtered_live_assets = []
        for index, asset in enumerate(candidate.live_assets, start=1):
            asset_key = normalized_media_url(asset["live_url"])
            pair_index = pair_plan["live_indices"].get(asset_key, index)
            if pair_index not in deleted_pairs:
                filtered_live_assets.append(asset)
        if len(filtered_pictures) == len(candidate.pictures) and len(filtered_live_assets) == len(candidate.live_assets):
            return candidate
        return MatchCandidate(
            top_item=candidate.top_item,
            source_item=candidate.source_item,
            top_dynamic_id=candidate.top_dynamic_id,
            source_dynamic_id=candidate.source_dynamic_id,
            pub_ts=candidate.pub_ts,
            text=candidate.text,
            subscription_uid=candidate.subscription_uid,
            subscription_name=candidate.subscription_name,
            pictures=filtered_pictures,
            live_assets=filtered_live_assets,
        )

    def _sleep_request_jitter(self, base: float, spread: float = 0.22) -> None:
        self._cooperate()
        floor = 0.04
        actual_base = max(base, floor)
        duration = random.uniform(max(floor, actual_base * 0.7), actual_base + spread)
        time.sleep(duration)

    def _run_startup_sync(self) -> None:
        task_id = self.db.create_task_run("startup", "running", "启动后正在整理图库")
        try:
            existing_folders = self.db.list_folders()
            import_stats = {"skipped": True}
            cleanup_stats = {"skipped": True}
            reindexed = False
            if not existing_folders:
                import_stats = self.legacy_importer.import_if_needed()
                cleanup_stats = self.cleanup.run()
                if self._needs_library_reindex():
                    self.indexer.reindex_library()
                    reindexed = True
            if self.db.gallery_index_needs_rebuild():
                self.db.set_gallery_index_rebuilding(True)
                self.indexer.rebuild_gallery_indexes()
            else:
                self.db.set_gallery_index_rebuilding(False)
            details = {
                "import": import_stats,
                "cleanup": cleanup_stats,
                "reindexed": reindexed,
                "gallery_index": self.db.gallery_index_status(),
                "events": self._runtime_events(),
            }
            self.db.finish_task_run(task_id, "success", "图库整理完成", details)
            self._status = {"running": False, "message": "图库已就绪", "mode": "idle", "stats": details}
        except Exception as exc:
            self.db.set_gallery_index_rebuilding(False)
            self.db.finish_task_run(task_id, "failed", str(exc), {"error": str(exc), "events": self._runtime_events()})
            self._status = {"running": False, "message": f"图库整理失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            self._run_next_queued_task()

    def _run_gallery_index_rebuild(self) -> None:
        task_id = self.db.create_task_run(
            "index",
            "running",
            "开始重建页面索引",
            {"retry_action": {"kind": "index"}},
        )
        self.db.set_gallery_index_rebuilding(True)
        try:
            self.indexer.rebuild_gallery_indexes()
            details = {"gallery_index": self.db.gallery_index_status(), "events": self._runtime_events()}
            self.db.finish_task_run(task_id, "success", "页面索引重建完成", details)
            self._status = {"running": False, "message": "页面索引重建完成", "mode": "idle", "stats": details}
        except Exception as exc:
            self.db.set_gallery_index_rebuilding(False)
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {"error": str(exc), "retry_action": {"kind": "index"}, "events": self._runtime_events()},
            )
            self._status = {"running": False, "message": f"页面索引重建失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            self._run_next_queued_task()

    def _evaluate_auto_gallery_index_check(self, trigger: str) -> tuple[dict[str, Any], bool]:
        settings = self.db.get_settings()
        enabled = bool(settings.get("auto_gallery_index_check", True))
        status = self.db.gallery_index_status()
        stale = bool(status.get("stale"))
        scheduled = enabled and stale and not bool(status.get("rebuilding"))
        return (
            {
                "trigger": trigger,
                "enabled": enabled,
                "stale": stale,
                "scheduled": scheduled,
                "status": status,
            },
            scheduled,
        )

    def _enqueue_index_task(self, label: str) -> bool:
        with self._queue_lock:
            if any(task.kind == "index" for task in self._queue):
                return False
            queue_id = self._next_queue_id
            self._next_queue_id += 1
            self._queue.append(QueuedTask(queue_id=queue_id, kind="index", label=label, payload={"args": []}))
        return True

    def _run_review_download(self, item_id: int) -> None:
        task_id = self.db.create_task_run(
            "review",
            "running",
            f"处理审核项 {item_id}",
            {"retry_action": {"kind": "review", "item_id": int(item_id)}},
        )
        candidate: MatchCandidate | None = None
        try:
            review_item = self.db.get_review_item(item_id)
            if not review_item:
                raise RuntimeError("待审核项不存在")
            self.db.set_review_status(item_id, "processing")
            payload = self._loads_payload(review_item["payload_json"])
            settings = self.db.get_settings()
            cookie = self.auth.get_cookie_state().cookie
            if not cookie:
                raise RuntimeError("未登录哔哩哔哩，无法下载")
            if payload.get("validation_mode"):
                self.restore_dynamic_now(
                    str(payload["top_dynamic_id"]),
                    str(payload["source_dynamic_id"]),
                    str(payload.get("subscription_uid") or ""),
                )
            else:
                candidate = self._candidate_from_payload(payload)
                options = self._subscription_options(
                    settings,
                    candidate.subscription_uid or str(settings["host_mid"]),
                    self.db.get_subscription(candidate.subscription_uid) if candidate.subscription_uid else None,
                )
                candidate = self._normalize_candidate_media(candidate, options)
                candidate = self._apply_deleted_pair_marks(candidate)
                self._download_candidate(candidate, settings, cookie)
            self.db.set_review_status(item_id, "approved")
            self.cleanup.run()
            self.db.finish_task_run(task_id, "success", "审核项下载完成", {"item_id": item_id, "events": self._runtime_events()})
            self._status = {"running": False, "message": "审核项下载完成", "mode": "idle"}
        except Exception as exc:
            if isinstance(exc, ResourceDownloadError) and candidate is not None:
                self._queue_candidate_for_review(candidate, self._download_review_reason(exc))
            if self.db.get_review_item(item_id):
                self.db.set_review_status(item_id, "pending")
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {
                    "item_id": item_id,
                    "retry_action": {"kind": "review", "item_id": int(item_id)},
                    "events": self._runtime_events(),
                },
            )
            self._status = {"running": False, "message": f"审核项处理失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            self._run_next_queued_task()

    def _run_validation(self) -> None:
        task_id = self.db.create_task_run("validate", "running", "校验当前内容", {"retry_action": {"kind": "validate"}})
        schedule_index_check = False
        try:
            stats = self._execute_validation()
            gallery_index_check, schedule_index_check = self._evaluate_auto_gallery_index_check("内容校验")
            stats["gallery_index_check"] = gallery_index_check
            stats["events"] = self._runtime_events()
            self.db.finish_task_run(task_id, "success", "校验完成", stats)
            self._status = {"running": False, "message": "内容校验完成", "mode": "idle", "stats": stats}
        except Exception as exc:
            self.db.finish_task_run(
                task_id,
                "failed",
                str(exc),
                {"error": str(exc), "retry_action": {"kind": "validate"}, "events": self._runtime_events()},
            )
            self._status = {"running": False, "message": f"内容校验失败: {exc}", "mode": "idle"}
        finally:
            self._release()
            if schedule_index_check:
                self._enqueue_index_task("内容校验后自动重建页面索引")
            self._run_next_queued_task()

    def _execute_pull(self, target_uids: list[str] | None = None, force_reload: bool | None = None) -> dict[str, Any]:
        settings = self.db.get_settings()
        cookie_state = self.auth.get_cookie_state()
        if not cookie_state.cookie:
            raise RuntimeError("未登录哔哩哔哩，请先扫码登录")
        force_reload = bool(settings.get("reload_all_once")) if force_reload is None else bool(force_reload)
        if force_reload and target_uids is None:
            self.db.save_settings({"reload_all_once": False})
        filter_engine = FilterEngine(settings)
        stats = {
            "subscriptions": 0,
            "matched": 0,
            "downloaded_candidates": 0,
            "review_candidates": 0,
            "saved_files": 0,
            "force_reload": force_reload,
            "added_items": [],
        }
        for subscription in self._active_subscriptions(target_uids=target_uids):
            self._execute_pull_subscription_with_retry(
                subscription,
                settings,
                cookie_state.cookie,
                filter_engine,
                stats,
                force_reload,
            )
        return stats

    def _execute_pull_subscription_with_retry(
        self,
        subscription: dict[str, Any],
        settings: dict[str, Any],
        cookie: str,
        filter_engine: FilterEngine,
        stats: dict[str, Any],
        force_reload: bool,
    ) -> None:
        last_error: Exception | None = None
        subscription_name = subscription.get("uname") or f"UID {subscription['uid']}"
        for attempt in range(3):
            try:
                self._execute_pull_for_subscription(subscription, settings, cookie, filter_engine, stats, force_reload)
                return
            except RuntimeError as exc:
                last_error = exc
                if not self._is_transient_pull_error(exc) or attempt >= 2:
                    raise
                self._status = {
                    "running": True,
                    "message": f"{subscription_name} 拉取波动，正在重试 {attempt + 2}/3",
                    "mode": "pull",
                    "stats": stats,
                }
                self._sleep_request_jitter(0.9 + attempt * 0.45, spread=0.9)
        if last_error is not None:
            raise RuntimeError(str(last_error))

    def _is_transient_pull_error(self, exc: Exception) -> bool:
        message = str(exc)
        transient_markers = [
            "412",
            "-352",
            "Connection broken",
            "IncompleteRead",
            "Read timed out",
            "RemoteDisconnected",
            "temporarily unavailable",
            "Connection reset",
            "ChunkedEncodingError",
        ]
        return any(marker in message for marker in transient_markers)

    def _execute_validation(self, target_uids: list[str] | None = None) -> dict[str, Any]:
        settings = self.db.get_settings()
        stats = {
            "checked": 0,
            "deduped_files": 0,
            "repaired_folders": 0,
            "review_archived": 0,
            "site_deduped_images": 0,
            "skipped": 0,
        }
        cookie_state = self.auth.get_cookie_state()
        folders = self.db.list_folders()
        wanted_uids = {str(uid) for uid in target_uids} if target_uids else None
        if wanted_uids is not None:
            folders = [folder for folder in folders if str(folder.get("subscription_uid") or "") in wanted_uids]
        candidate_maps: dict[str, dict[tuple[str, str], MatchCandidate]] = {}
        if cookie_state.cookie:
            for subscription in self._active_subscriptions(target_uids=target_uids):
                options = self._subscription_options(settings, str(subscription["uid"]), subscription)
                candidate_maps[str(subscription["uid"])] = self._collect_candidate_map_from_feed(
                    settings,
                    cookie_state.cookie,
                    options["include_forwarded"],
                    str(subscription["uid"]),
                )
        for folder in folders:
            self._cooperate()
            stats["checked"] += 1
            stats["deduped_files"] += self._dedupe_folder_files(folder["folder_name"])
            if not cookie_state.cookie:
                stats["skipped"] += 1
                continue
            subscription_uid = str(folder.get("subscription_uid") or settings["host_mid"])
            subscription = self.db.get_subscription(subscription_uid)
            options = self._subscription_options(settings, subscription_uid, subscription)
            candidate = candidate_maps.get(subscription_uid, {}).get((str(folder["top_dynamic_id"]), str(folder["source_dynamic_id"])))
            if candidate is None:
                try:
                    detail_item = self.auth.fetch_dynamic_detail(
                        folder["top_dynamic_id"],
                        int(subscription_uid),
                        cookie_state.cookie,
                    )
                    self._sleep_request_jitter(float(settings.get("download_sleep", 0.2)) * 0.45 + 0.08, spread=0.18)
                    candidates = self._collect_candidates(detail_item, options["include_forwarded"])
                    candidate = next(
                        (
                            item
                            for item in candidates
                            if item.top_dynamic_id == str(folder["top_dynamic_id"])
                            and item.source_dynamic_id == str(folder["source_dynamic_id"])
                        ),
                        None,
                    )
                    if candidate is not None:
                        candidate.subscription_uid = subscription_uid
                        candidate.subscription_name = folder.get("subscription_name") or self._subscription_name(subscription_uid)
                        candidate = self._apply_deleted_pair_marks(candidate)
                except Exception:
                    stats["skipped"] += 1
                    continue
            if not self._validation_candidate_needs_repair(folder, candidate, options):
                continue
            if not candidate or (not candidate.pictures and not candidate.live_assets):
                if self.db.has_deleted_pair_marks(folder["top_dynamic_id"], folder["source_dynamic_id"]):
                    continue
                self._archive_validation_gap(folder, "动态内容为空，已归档到待审核")
                stats["review_archived"] += 1
                continue
            if self._candidate_has_selected_media(candidate, options):
                try:
                    self._download_candidate(candidate, settings, cookie_state.cookie, subscription=subscription)
                except ResourceDownloadError as exc:
                    self._queue_candidate_for_review(candidate, self._download_review_reason(exc))
                    stats["review_archived"] += 1
                    continue
            if self._folder_needs_repair(folder["folder_name"], candidate, options):
                self._archive_validation_gap(folder, "动态内容不完整，建议查看原动态或重新拉取")
                stats["review_archived"] += 1
                continue
            stats["repaired_folders"] += 1
        stats["site_deduped_images"] += self._dedupe_synced_site_posts()
        self.cleanup.run()
        return stats

    def _dedupe_synced_site_posts(self) -> int:
        if self.site_syncer is None:
            return 0
        removed = 0
        for post in self.db.list_synced_site_posts():
            self._cooperate()
            count = int(self.site_syncer.dedupe_post_images(int(post["id"])))
            if not count:
                continue
            removed += count
            self.db.update_site_post_counts(int(post["id"]))
            self.site_syncer.mirror_existing_site_post(self.db.get_site_post(int(post["id"])) or post)
        return removed

    def _execute_pull_for_subscription(
        self,
        subscription: dict[str, Any],
        settings: dict[str, Any],
        cookie: str,
        filter_engine: FilterEngine,
        stats: dict[str, Any],
        force_reload: bool,
    ) -> None:
        host_uid = str(subscription["uid"])
        subscription_name = subscription.get("uname") or f"UID {host_uid}"
        options = self._subscription_options(settings, host_uid, subscription)
        subscription_folders = [folder for folder in self.db.list_folders() if str(folder.get("subscription_uid") or "") == host_uid]
        cutoff_ts = 0 if force_reload else max((int(folder.get("pub_ts", 0)) for folder in subscription_folders), default=0)
        self._append_event(
            "开始扫描订阅",
            uid=host_uid,
            subscription_name=subscription_name,
            cutoff_ts=cutoff_ts,
            force_reload=force_reload,
        )
        stats["subscriptions"] += 1
        stale_non_top_pages = 0
        for page_num, items in self._iter_feed_pages(host_uid, cookie):
            self._cooperate()
            self._append_event(
                "扫描分页",
                uid=host_uid,
                subscription_name=subscription_name,
                page=page_num,
                item_count=len(items),
            )
            page_has_recent_non_top = False
            page_has_non_top = False
            for item in items:
                self._cooperate()
                item_is_top = is_top_item(item)
                item_pub_ts = extract_pub_ts(item)
                if not item_is_top:
                    page_has_non_top = True
                    if cutoff_ts == 0 or item_pub_ts == 0 or item_pub_ts >= cutoff_ts:
                        page_has_recent_non_top = True
                for candidate in self._collect_candidates(item, options["include_forwarded"]):
                    self._cooperate()
                    candidate.subscription_uid = host_uid
                    candidate.subscription_name = subscription_name
                    candidate = self._normalize_candidate_media(candidate, options)
                    candidate = self._apply_deleted_pair_marks(candidate)
                    if not self._candidate_has_selected_media(candidate, options):
                        continue
                    self._status = {
                        "running": True,
                        "message": f"正在扫描 {subscription_name} · {candidate.top_dynamic_id}",
                        "mode": "pull",
                        "stats": stats,
                    }
                    if self.db.is_blacklisted(candidate.top_dynamic_id, candidate.source_dynamic_id):
                        continue
                    existing_folder = self.db.get_folder_by_dynamic(candidate.top_dynamic_id, candidate.source_dynamic_id)
                    needs_sync = bool(existing_folder and self._folder_needs_sync(existing_folder["folder_name"], candidate, options))
                    if existing_folder and not needs_sync:
                        continue
                    if cutoff_ts and candidate.pub_ts and candidate.pub_ts <= cutoff_ts and existing_folder and not needs_sync:
                        continue
                    stats["matched"] += 1
                    decision = self.db.get_review_status(candidate.top_dynamic_id, candidate.source_dynamic_id)
                    preview_folder_name = self._folder_preview_name(candidate.pub_ts, candidate.text)
                    if decision == "rejected":
                        continue
                    if decision != "approved":
                        filter_result = filter_engine.evaluate(candidate.source_item)
                        self.db.add_filter_log(
                            candidate.top_dynamic_id,
                            candidate.source_dynamic_id,
                            preview_folder_name,
                            filter_result.decision,
                            filter_result.reasons,
                        )
                        if filter_result.decision == "review":
                            self._append_event(
                                "命中过滤进入待审核",
                                uid=host_uid,
                                subscription_name=subscription_name,
                                dynamic_id=candidate.top_dynamic_id,
                                reasons=filter_result.reasons,
                            )
                            self.db.upsert_review_item(
                                candidate.top_dynamic_id,
                                candidate.source_dynamic_id,
                                preview_folder_name,
                                compact_text(candidate.text)[:120],
                                filter_result.reasons,
                                self._payload_from_candidate(candidate),
                            )
                            stats["review_candidates"] += 1
                            continue
                    try:
                        saved_files = self._download_candidate(candidate, settings, cookie, subscription=subscription)
                    except ResourceDownloadError as exc:
                        reason = self._download_review_reason(exc)
                        self._queue_candidate_for_review(candidate, reason)
                        stats["review_candidates"] += 1
                        self._append_event(
                            "资源损坏进入待审核",
                            uid=host_uid,
                            subscription_name=subscription_name,
                            dynamic_id=candidate.top_dynamic_id,
                            source_dynamic_id=candidate.source_dynamic_id,
                            reason=reason,
                        )
                        continue
                    stats["saved_files"] += saved_files
                    stats["downloaded_candidates"] += 1
                    self._record_added_item(stats, candidate, saved_files, existing_folder is None)
                    self._append_event(
                        "已下载动态",
                        uid=host_uid,
                        subscription_name=subscription_name,
                        dynamic_id=candidate.top_dynamic_id,
                        source_dynamic_id=candidate.source_dynamic_id,
                        pub_ts=candidate.pub_ts,
                        saved_files=saved_files,
                    )
                    self._status = {
                        "running": True,
                        "message": f"已处理 {subscription_name} · {stats['downloaded_candidates']} 条动态",
                        "mode": "pull",
                        "stats": stats,
                    }
            if cutoff_ts and page_num > 1 and page_has_non_top and not page_has_recent_non_top:
                stale_non_top_pages += 1
            else:
                stale_non_top_pages = 0
            if cutoff_ts and stale_non_top_pages >= 2:
                self._append_event(
                    "命中截止时间，停止翻页",
                    uid=host_uid,
                    subscription_name=subscription_name,
                    page=page_num,
                    cutoff_ts=cutoff_ts,
                    stale_pages=stale_non_top_pages,
                )
                break

    def _collect_candidate_map_from_feed(
        self,
        settings: dict[str, Any],
        cookie: str,
        include_forwarded: bool,
        host_uid: str,
    ) -> dict[tuple[str, str], MatchCandidate]:
        matched: dict[tuple[str, str], MatchCandidate] = {}
        for _, items in self._iter_feed_pages(host_uid, cookie):
            self._cooperate()
            for item in items:
                self._cooperate()
                for candidate in self._collect_candidates(item, include_forwarded):
                    candidate.subscription_uid = str(host_uid)
                    candidate.subscription_name = self._subscription_name(str(host_uid))
                    candidate = self._normalize_candidate_media(
                        candidate,
                        {"pull_images": True, "pull_livephoto": True, "include_forwarded": include_forwarded},
                    )
                    matched[(candidate.top_dynamic_id, candidate.source_dynamic_id)] = self._apply_deleted_pair_marks(candidate)
        return matched

    def _collect_candidates(self, item: dict, include_forwarded: bool) -> list[MatchCandidate]:
        merged: dict[tuple[str, str], MatchCandidate] = {}
        for top_item, source_item, pictures in find_nine_pic_blocks(item, include_forwarded=include_forwarded):
            key = (
                str(top_item.get("id_str") or "unknown"),
                str(source_item.get("id_str") or "unknown"),
            )
            candidate = merged.setdefault(
                key,
                MatchCandidate(
                    top_item=top_item,
                    source_item=source_item,
                    top_dynamic_id=key[0],
                    source_dynamic_id=key[1],
                    pub_ts=extract_pub_ts(top_item) or extract_pub_ts(source_item),
                    text=extract_primary_text(top_item) or extract_primary_text(source_item) or "",
                ),
            )
            candidate.pictures = pictures

        for top_item, source_item, assets in find_live_blocks(item, include_forwarded=include_forwarded):
            key = (
                str(top_item.get("id_str") or "unknown"),
                str(source_item.get("id_str") or "unknown"),
            )
            candidate = merged.setdefault(
                key,
                MatchCandidate(
                    top_item=top_item,
                    source_item=source_item,
                    top_dynamic_id=key[0],
                    source_dynamic_id=key[1],
                    pub_ts=extract_pub_ts(top_item) or extract_pub_ts(source_item),
                    text=extract_primary_text(top_item) or extract_primary_text(source_item) or "",
                ),
            )
            candidate.live_assets = assets
        return list(merged.values())

    def _download_candidate(
        self,
        candidate: MatchCandidate,
        settings: dict[str, Any],
        cookie: str,
        subscription: dict[str, Any] | None = None,
    ) -> int:
        existing = self.db.get_folder_by_dynamic(candidate.top_dynamic_id, candidate.source_dynamic_id)
        used_names = {folder["folder_name"] for folder in self.db.list_folders()}
        folder_name = existing["folder_name"] if existing else build_folder_name(candidate.pub_ts, candidate.text, used_names)
        saved_files = 0
        header_uid = str(candidate.subscription_uid or settings["host_mid"])
        options = self._subscription_options(settings, header_uid, subscription)
        candidate = self._normalize_candidate_media(candidate, options)
        candidate = self._apply_deleted_pair_marks(candidate)
        headers = self._build_request_headers(header_uid, cookie, purpose="asset")
        pair_plan = self._pair_plan(candidate)
        created_paths: list[Path] = []

        try:
            pictures_to_download = self._pictures_for_download(candidate, options)
            if pictures_to_download:
                folder = self.storage.image_folder(folder_name)
                folder.mkdir(parents=True, exist_ok=True)
                for index, picture in enumerate(pictures_to_download, start=1):
                    self._cooperate()
                    url = image_url(picture)
                    if not url:
                        continue
                    filename = os.path.basename(urlparse(url).path) or f"{candidate.source_dynamic_id}_{index:02d}.jpg"
                    pair_index = pair_plan["picture_indices"].get(normalized_media_url(url), index)
                    target = folder / self._paired_filename(pair_index, filename)
                    if self._download_if_missing(url, target, headers):
                        saved_files += 1
                        created_paths.append(target)
                    self._sleep_request_jitter(float(settings.get("download_sleep", 0.2)), spread=0.32)

            if options["pull_livephoto"] and candidate.live_assets:
                folder = self.storage.livephoto_folder(folder_name)
                folder.mkdir(parents=True, exist_ok=True)
                for index, asset in enumerate(candidate.live_assets, start=1):
                    self._cooperate()
                    url = asset["live_url"]
                    filename = os.path.basename(urlparse(url).path) or f"{candidate.source_dynamic_id}_{index:02d}.mp4"
                    asset_key = normalized_media_url(url)
                    pair_index = pair_plan["live_indices"].get(asset_key, index)
                    target = folder / self._paired_filename(pair_index, filename)
                    if self._download_if_missing(url, target, headers):
                        saved_files += 1
                        created_paths.append(target)
                    cover_url = asset.get("cover_url")
                    if cover_url:
                        stem = Path(self._paired_filename(pair_index, filename)).stem
                        cover_target = folder / ".source_covers" / f"{stem}.jpg"
                        if self._download_if_missing(cover_url, cover_target, headers):
                            created_paths.append(cover_target)
                    self._sleep_request_jitter(float(settings.get("download_sleep", 0.2)), spread=0.36)
        except ResourceDownloadError:
            self._cleanup_failed_candidate_download(folder_name, created_paths, existing is None)
            raise

        self.indexer.index_folder(
            folder_name=folder_name,
            pub_ts=candidate.pub_ts,
            title=candidate.text or folder_name,
            text_prefix=extract_chinese_prefix(candidate.text),
            top_dynamic_id=candidate.top_dynamic_id,
            source_dynamic_id=candidate.source_dynamic_id,
            subscription_uid=candidate.subscription_uid or str(settings["host_mid"]),
            subscription_name=candidate.subscription_name or self._subscription_name(candidate.subscription_uid or str(settings["host_mid"])),
        )
        return saved_files

    def _folder_needs_sync(self, folder_name: str, candidate: MatchCandidate, options: dict[str, bool]) -> bool:
        candidate = self._normalize_candidate_media(candidate, options)
        assets = self.db.list_assets_for_folder(folder_name)
        image_count = sum(1 for asset in assets if asset["media_type"] == "image")
        live_count = sum(1 for asset in assets if asset["media_type"] == "livephoto")
        required_image_count = self._required_image_count(candidate, options)
        if required_image_count and image_count < required_image_count:
            return True
        if options["pull_livephoto"] and candidate.live_assets and live_count < len(candidate.live_assets):
            return True
        if options["pull_livephoto"] and candidate.live_assets and live_count == 0:
            return True
        if required_image_count and image_count == 0:
            return True
        return False

    def _record_added_item(
        self,
        stats: dict[str, Any],
        candidate: MatchCandidate,
        saved_files: int,
        is_new_folder: bool,
    ) -> None:
        if saved_files <= 0:
            return
        items = stats.setdefault("added_items", [])
        key = (str(candidate.top_dynamic_id), str(candidate.source_dynamic_id))
        for item in items:
            if (str(item.get("top_dynamic_id")), str(item.get("source_dynamic_id"))) == key:
                item["saved_files"] = int(item.get("saved_files") or 0) + int(saved_files)
                item["change_type"] = "new" if item.get("change_type") == "new" or is_new_folder else "updated"
                return
        items.append(
            {
                "top_dynamic_id": candidate.top_dynamic_id,
                "source_dynamic_id": candidate.source_dynamic_id,
                "title": compact_text(candidate.text or "")[:120] or f"动态 {candidate.top_dynamic_id}",
                "subscription_uid": candidate.subscription_uid,
                "subscription_name": candidate.subscription_name or self._subscription_name(candidate.subscription_uid),
                "pub_time": self._folder_pub_time(candidate.pub_ts),
                "image_count": len(candidate.pictures),
                "livephoto_count": len(candidate.live_assets),
                "saved_files": int(saved_files),
                "change_type": "new" if is_new_folder else "updated",
            }
        )

    def _download_if_missing(self, url: str, target: Path, headers: dict[str, str]) -> bool:
        if target.exists() and target.stat().st_size > 0:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(f"{target.suffix}.part")
        last_error: Exception | None = None
        for attempt in range(5):
            self._cooperate()
            if temp_target.exists():
                temp_target.unlink(missing_ok=True)
            response: requests.Response | None = None
            try:
                self._sleep_request_jitter(0.08 + attempt * 0.04, spread=0.18)
                response = requests.get(url, headers=headers, timeout=(20, 180), stream=True)
                response.raise_for_status()
                with temp_target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 512):
                        self._cooperate()
                        if not chunk:
                            continue
                        handle.write(chunk)
                temp_target.replace(target)
                return True
            except (requests.RequestException, IncompleteRead, OSError) as exc:
                last_error = exc
                if attempt >= 4:
                    break
                self._sleep_request_jitter(0.24 + attempt * 0.14, spread=0.4)
            finally:
                if response is not None:
                    response.close()
        temp_target.unlink(missing_ok=True)
        raise ResourceDownloadError(url, str(last_error or "未知错误"))

    def _cleanup_failed_candidate_download(self, folder_name: str, created_paths: list[Path], remove_folder: bool) -> None:
        for path in reversed(created_paths):
            path.unlink(missing_ok=True)
            parent = path.parent
            while parent.name in {".source_covers", ".thumbs"} and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        if remove_folder:
            self.storage.remove_folder_assets(folder_name)

    def _download_review_reason(self, exc: ResourceDownloadError) -> str:
        return f"服务器资源失效，已转入待审核：{exc.url}（{exc.detail}）"

    def _queue_candidate_for_review(self, candidate: MatchCandidate, reason: str) -> None:
        preview_folder_name = self._folder_preview_name(candidate.pub_ts, candidate.text)
        self.db.upsert_review_item(
            candidate.top_dynamic_id,
            candidate.source_dynamic_id,
            preview_folder_name,
            compact_text(candidate.text)[:120] or preview_folder_name,
            [reason],
            self._payload_from_candidate(candidate),
        )

    def _folder_preview_name(self, pub_ts: int, text: str) -> str:
        prefix = extract_chinese_prefix(text) or "日常动态图"
        from app.services.utils import folder_date

        return f"{folder_date(pub_ts)}_{prefix}"

    def _folder_pub_time(self, pub_ts: int) -> str:
        from app.services.utils import format_pub_time

        return format_pub_time(pub_ts)

    def _paired_filename(self, pair_index: int, filename: str) -> str:
        return safe_filename(f"{pair_index:03d}__{filename}")

    def _pair_plan(self, candidate: MatchCandidate) -> dict[str, dict[str, int]]:
        picture_indices: dict[str, int] = {}
        pictures = [picture for picture in candidate.pictures if image_url(picture)]
        for index, picture in enumerate(pictures, start=1):
            picture_indices[normalized_media_url(image_url(picture))] = index

        live_indices: dict[str, int] = {}
        fallback_index = 1
        picture_by_cover = {
            normalized_media_url(image_url(picture)): index
            for index, picture in enumerate(pictures, start=1)
            if image_url(picture)
        }
        for asset in candidate.live_assets:
            cover_key = normalized_media_url(asset.get("cover_url") or "")
            asset_key = normalized_media_url(asset["live_url"])
            pair_index = picture_by_cover.get(cover_key)
            if pair_index is None:
                pair_index = fallback_index
            live_indices[asset_key] = pair_index
            fallback_index = max(fallback_index + 1, pair_index + 1)
        return {"picture_indices": picture_indices, "live_indices": live_indices}

    def _payload_from_candidate(self, candidate: MatchCandidate) -> dict[str, Any]:
        return {
            "top_item": candidate.top_item,
            "source_item": candidate.source_item,
            "top_dynamic_id": candidate.top_dynamic_id,
            "source_dynamic_id": candidate.source_dynamic_id,
            "pub_ts": candidate.pub_ts,
            "text": candidate.text,
            "subscription_uid": candidate.subscription_uid,
            "subscription_name": candidate.subscription_name,
            "pictures": candidate.pictures,
            "live_assets": candidate.live_assets,
        }

    def _candidate_from_payload(self, payload: dict[str, Any]) -> MatchCandidate:
        return MatchCandidate(
            top_item=payload["top_item"],
            source_item=payload["source_item"],
            top_dynamic_id=str(payload["top_dynamic_id"]),
            source_dynamic_id=str(payload["source_dynamic_id"]),
            pub_ts=int(payload["pub_ts"]),
            text=str(payload.get("text", "")),
            subscription_uid=str(payload.get("subscription_uid", "")),
            subscription_name=str(payload.get("subscription_name", "")),
            pictures=list(payload.get("pictures", [])),
            live_assets=list(payload.get("live_assets", [])),
        )

    def _loads_payload(self, raw: str) -> dict[str, Any]:
        import json

        return json.loads(raw)

    def _queue_or_start(self, mode: str, label: str, target, *args) -> bool:
        with self._queue_lock:
            if self._lock.locked():
                queue_id = self._next_queue_id
                self._next_queue_id += 1
                self._queue.append(QueuedTask(queue_id=queue_id, kind=mode, label=label, payload={"args": list(args)}))
                return True
            self._pause_requested = False
            self._cancel_requested = False
            self._acquire(mode=mode, message=f"开始{label}")
            thread = threading.Thread(target=target, args=args, daemon=True)
            thread.start()
            return False

    def _run_next_queued_task(self) -> None:
        with self._queue_lock:
            if self._lock.locked() or not self._queue:
                return
            next_task = self._queue.popleft()
            self._pause_requested = False
            self._cancel_requested = False
            self._acquire(mode=next_task.kind, message=f"开始{next_task.label}")
            if next_task.kind == "pull":
                thread = threading.Thread(target=self._run_pull, daemon=True)
            elif next_task.kind == "subscription-pull":
                uid = str(next_task.payload.get("args", [""])[0])
                thread = threading.Thread(target=self._run_subscription_pull, args=(uid,), daemon=True)
            elif next_task.kind == "subscription-reload":
                uid = str(next_task.payload.get("args", [""])[0])
                thread = threading.Thread(target=self._run_subscription_reload, args=(uid,), daemon=True)
            elif next_task.kind == "review":
                item_id = int(next_task.payload.get("args", [0])[0])
                thread = threading.Thread(target=self._run_review_download, args=(item_id,), daemon=True)
            elif next_task.kind == "validate":
                thread = threading.Thread(target=self._run_validation, daemon=True)
            elif next_task.kind == "index":
                thread = threading.Thread(target=self._run_gallery_index_rebuild, daemon=True)
            elif next_task.kind == "site-sync":
                raw_source_id = next_task.payload.get("args", [None])[0]
                source_id = int(raw_source_id) if raw_source_id is not None else None
                thread = threading.Thread(target=self._run_site_sync, args=(source_id,), daemon=True)
            else:
                self._release()
                return
            thread.start()

    def _cooperate(self) -> None:
        while self._pause_requested and not self._cancel_requested:
            self._status = {**self._status, "running": True, "message": "任务已暂停，等待继续", "paused": True}
            time.sleep(0.25)
        if self._cancel_requested:
            raise RuntimeError("任务已取消")

    def _latest_task_run(self, task_types: list[str]) -> dict[str, Any] | None:
        latest = None
        for task_type in task_types:
            current = self.db.last_task_run(task_type)
            if current and (latest is None or current["id"] > latest["id"]):
                latest = current
        return latest

    def _folder_needs_repair(self, folder_name: str, candidate: MatchCandidate | None, options: dict[str, bool]) -> bool:
        assets = self.db.list_assets_for_folder(folder_name)
        image_count = sum(1 for asset in assets if asset["media_type"] == "image")
        live_count = sum(1 for asset in assets if asset["media_type"] == "livephoto")
        if candidate is not None:
            candidate = self._normalize_candidate_media(candidate, options)
            if self._required_image_count(candidate, options) > image_count:
                return True
            if options["pull_livephoto"] and len(candidate.live_assets) > live_count:
                return True
        if self._folder_has_duplicate_prefixes(self.storage.image_folder(folder_name)):
            return True
        if self._folder_has_duplicate_prefixes(self.storage.livephoto_folder(folder_name)):
            return True
        return False

    def _validation_candidate_needs_repair(self, folder: dict[str, Any], candidate: MatchCandidate | None, options: dict[str, bool]) -> bool:
        if candidate is None:
            return True
        candidate = self._normalize_candidate_media(candidate, options)
        if not candidate.pictures and not candidate.live_assets:
            return True
        assets = self.db.list_assets_for_folder(folder["folder_name"])
        image_count = sum(1 for asset in assets if asset["media_type"] == "image")
        live_count = sum(1 for asset in assets if asset["media_type"] == "livephoto")
        if self._required_image_count(candidate, options) > image_count:
            return True
        if options["pull_livephoto"] and len(candidate.live_assets) > live_count:
            return True
        if self._folder_has_duplicate_prefixes(self.storage.image_folder(folder["folder_name"])):
            return True
        if self._folder_has_duplicate_prefixes(self.storage.livephoto_folder(folder["folder_name"])):
            return True
        return False

    def _archive_validation_gap(self, folder: dict[str, Any], reason: str) -> None:
        payload = {
            "validation_mode": True,
            "top_dynamic_id": str(folder["top_dynamic_id"]),
            "source_dynamic_id": str(folder["source_dynamic_id"]),
            "subscription_uid": str(folder.get("subscription_uid") or ""),
            "subscription_name": str(folder.get("subscription_name") or ""),
            "pub_ts": int(folder.get("pub_ts") or 0),
            "text": folder.get("title") or folder["folder_name"],
            "pictures": [],
            "live_assets": [],
            "top_item": {},
            "source_item": {},
        }
        self.db.upsert_review_item(
            str(folder["top_dynamic_id"]),
            str(folder["source_dynamic_id"]),
            folder["folder_name"],
            compact_text(folder.get("title") or folder["folder_name"])[:120],
            [reason],
            payload,
        )
        self.storage.remove_folder_assets(folder["folder_name"])
        self.db.delete_folder(folder["folder_name"])

    def _folder_has_duplicate_prefixes(self, folder: Path) -> bool:
        if not folder.exists():
            return False
        seen: set[str] = set()
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.name.startswith(".") or "__" not in path.name:
                continue
            prefix = path.name.split("__", 1)[0]
            if prefix in seen:
                return True
            seen.add(prefix)
        return False

    def _dedupe_folder_files(self, folder_name: str) -> int:
        removed = 0
        for folder in (self.storage.image_folder(folder_name), self.storage.livephoto_folder(folder_name)):
            if not folder.exists():
                continue
            buckets: dict[str, list[Path]] = {}
            for path in sorted(folder.iterdir()):
                if not path.is_file() or path.name.startswith(".") or "__" not in path.name:
                    continue
                prefix = path.name.split("__", 1)[0]
                buckets.setdefault(prefix, []).append(path)
            for paths in buckets.values():
                if len(paths) <= 1:
                    continue
                ranked = sorted(paths, key=lambda item: (item.stat().st_size, item.name), reverse=True)
                for duplicate in ranked[1:]:
                    duplicate.unlink(missing_ok=True)
                    removed += 1
        if removed:
            self._reindex_folder(folder_name)
        return removed

    def _reindex_folder(self, folder_name: str) -> None:
        folder = self.db.get_folder(folder_name)
        if not folder:
            return
        self.indexer.index_folder(
            folder_name=folder_name,
            pub_ts=int(folder.get("pub_ts", 0)),
            title=folder.get("title", folder_name),
            text_prefix=folder.get("text_prefix", ""),
            top_dynamic_id=str(folder.get("top_dynamic_id", folder_name)),
            source_dynamic_id=str(folder.get("source_dynamic_id", folder_name)),
            subscription_uid=str(folder.get("subscription_uid") or ""),
            subscription_name=folder.get("subscription_name"),
            review_status=folder.get("review_status", "approved"),
            review_reason=folder.get("review_reason"),
            metadata=loads_json(folder.get("metadata_json"), {}),
            generate_derivatives=False,
        )

    def _needs_library_reindex(self) -> bool:
        db_folders = {folder["folder_name"] for folder in self.db.list_folders()}
        disk_folders = set()
        for root in (self.storage.config.images_dir, self.storage.config.livephoto_dir):
            if not root.exists():
                continue
            disk_folders.update(path.name for path in root.iterdir() if path.is_dir())
        if not disk_folders:
            return False
        if not db_folders:
            return True
        return db_folders != disk_folders

    def _acquire(self, mode: str, message: str) -> bool:
        locked = self._lock.acquire(blocking=False)
        if locked:
            self._event_log = deque(maxlen=120)
            self._status = {"running": True, "message": message, "mode": mode}
            self._append_event("任务开始", mode=mode, status_message=message)
        return locked

    def _release(self) -> None:
        if self._lock.locked():
            self._lock.release()

    def _append_event(self, message: str, **context: Any) -> None:
        payload = {"at": now_iso(), "message": message}
        for key, value in context.items():
            if value is not None and value != "":
                payload[key] = value
        self._event_log.append(payload)

    def _runtime_events(self) -> list[dict[str, Any]]:
        return list(self._event_log)
