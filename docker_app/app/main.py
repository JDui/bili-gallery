from __future__ import annotations

from contextlib import asynccontextmanager
import random
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests

from app.config import load_config
from app.db import Database
from app.services.bilibili import BilibiliAuthService
from app.services.cleanup import CleanupService
from app.services.gallery import GalleryService
from app.services.legacy_import import LegacyImporter
from app.services.media_indexer import MediaIndexer
from app.services.puller import PullManager
from app.services.scheduler import SchedulerService
from app.services.site_syncer import SiteSyncManager
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import format_pub_time, loads_json
from app.version import APP_NAME, APP_TITLE, APP_VERSION

config = load_config()
storage = StorageService(config)
db = Database(config.database_path)
thumbnailer = ThumbnailService()
indexer = MediaIndexer(db, storage, thumbnailer)
cleanup = CleanupService(db, storage)
auth = BilibiliAuthService(db)
gallery = GalleryService(db, storage)
legacy_importer = LegacyImporter(db, storage, indexer, config.repo_root)
pull_manager = PullManager(db, storage, indexer, cleanup, auth, legacy_importer)
site_syncer = SiteSyncManager(db, storage, indexer)
pull_manager.attach_site_syncer(site_syncer)
site_syncer.bind_task_queue(pull_manager)
scheduler = SchedulerService(db, pull_manager, site_syncer)
templates = Jinja2Templates(directory=str(config.app_root / "templates"))
AVATAR_REFRESH_INITIAL_DELAY_RANGE = (2.0, 5.0)
AVATAR_REFRESH_BETWEEN_DELAY_RANGE = (6.0, 14.0)
AVATAR_REFRESH_LONG_PAUSE_EVERY = 8
AVATAR_REFRESH_LONG_PAUSE_RANGE = (35.0, 75.0)
AVATAR_REFRESH_RISK_BACKOFF_RANGE = (90.0, 180.0)
AVATAR_REFRESH_RISK_KEYWORDS = ("验证码", "风控", "安全", "captcha", "-352", "412")
AVATAR_CACHE_MAX_BYTES = 5 * 1024 * 1024
_icon_reset_lock = threading.Lock()


class CacheControlStaticFiles(StaticFiles):
    def __init__(self, *args: Any, cache_control: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        if response.status_code in {200, 304}:
            response.headers.setdefault("Cache-Control", self.cache_control)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure()
    db.init()
    thumbnailer.apply_settings(db.get_settings())
    scheduler.start()
    pull_manager.start_startup_sync()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title=APP_TITLE, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount(
    "/static",
    CacheControlStaticFiles(
        directory=str(config.app_root / "static"),
        cache_control="public, max-age=31536000, immutable",
    ),
    name="static",
)
app.mount(
    "/storage",
    CacheControlStaticFiles(
        directory=str(config.storage_root),
        check_dir=False,
        cache_control="public, max-age=900",
    ),
    name="storage",
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = db.get_settings()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": settings.get("app_title") or APP_TITLE,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
        },
    )


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "app": app.title,
        "status": pull_manager.status(),
        "site_status": site_syncer.status(),
        "site_stats": db.site_stats(),
        "sidebar_counts": db.get_sidebar_count_cache(),
        "gallery_index": db.gallery_index_status(),
    }


@app.get("/api/sidebar-counts")
async def sidebar_counts() -> dict[str, Any]:
    return db.get_sidebar_count_cache()


@app.post("/api/sidebar-counts/refresh")
async def refresh_sidebar_counts(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    keys = payload.get("keys")
    if keys is not None and not isinstance(keys, list):
        raise HTTPException(status_code=400, detail="keys 必须是数组")
    return db.refresh_sidebar_count_cache([str(key) for key in keys] if keys else None)


@app.get("/api/gallery/items")
async def get_gallery_items(
    category: str = "all",
    year: str | None = None,
    month: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    subscription_uids: str | None = None,
    source_kind: str = "all",
    search_query: str | None = None,
    view_mode: str = "folder",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 24,
) -> dict[str, Any]:
    return gallery.get_gallery_items(
        category=category,
        year=year,
        month=month,
        start_month=start_month,
        end_month=end_month,
        subscription_uids=[item for item in (subscription_uids or "").split(",") if item],
        source_kind=source_kind,
        search_query=search_query,
        page=page,
        page_size=page_size,
        view_mode=view_mode,
        sort_order=sort_order,
    )


@app.get("/api/gallery/meta")
async def get_gallery_meta() -> dict[str, Any]:
    return gallery.get_gallery_meta()


@app.get("/api/gallery/folders/{folder_name}")
async def get_folder_detail(folder_name: str) -> dict[str, Any]:
    detail = gallery.get_folder_detail(folder_name)
    if detail is None:
        raise HTTPException(status_code=404, detail="动态不存在")
    return detail


@app.post("/api/gallery/folders/{folder_name}/favorite")
async def toggle_favorite(folder_name: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    folder = next((item for item in db.list_folders() if item["folder_name"] == folder_name), None)
    if not folder:
        raise HTTPException(status_code=404, detail="动态不存在")
    favorite = bool(payload.get("favorite", not bool(folder.get("is_favorite"))))
    db.set_folder_favorite(folder_name, favorite)
    sidebar_counts = db.refresh_sidebar_count_cache(["all", "favorites", "livephoto"])
    return {"ok": True, "favorite": favorite, "message": "已加入收藏" if favorite else "已取消收藏", "sidebar_counts": sidebar_counts}


@app.get("/api/site-sources")
async def list_site_sources() -> dict[str, Any]:
    stats_by_source = db.site_source_content_stats()
    return {
        "items": [
            {
                **source,
                **stats_by_source.get(int(source["id"]), {"post_count": 0, "asset_count": 0}),
            }
            for source in db.list_site_sources()
        ]
    }


@app.get("/api/site-sources/export")
async def export_site_sources() -> JSONResponse:
    return JSONResponse(
        db.export_site_sources(),
        headers={"Content-Disposition": 'attachment; filename="site-sources.json"'},
    )


@app.post("/api/site-sources/import")
async def import_site_sources(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        result = db.import_site_sources(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/site-sources/suggest")
async def suggest_site_source(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not payload.get("entry_url"):
        raise HTTPException(status_code=400, detail="请输入入口 URL")
    try:
        return {"ok": True, "suggestion": site_syncer.suggest_source(payload)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/site-sources")
async def create_site_source(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not payload.get("entry_url"):
        raise HTTPException(status_code=400, detail="请输入入口 URL")
    try:
        return {"ok": True, "message": "站点来源已保存", "item": db.create_site_source(payload)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/site-sources/{source_id}")
async def update_site_source(source_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        item = db.update_site_source(source_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="站点来源不存在")
    return {"ok": True, "message": "站点来源已更新", "item": item}


@app.delete("/api/site-sources/{source_id}")
async def delete_site_source(source_id: int) -> dict[str, Any]:
    if not db.delete_site_source(source_id):
        raise HTTPException(status_code=404, detail="站点来源不存在")
    return {"ok": True, "message": "站点来源已删除"}


@app.post("/api/site-sources/{source_id}/clear-delete")
async def clear_delete_site_source(source_id: int) -> dict[str, Any]:
    source = db.get_site_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="站点来源不存在")
    folders = db.list_site_gallery_folders(source_id)
    result = db.clear_site_source_and_gallery(source_id)
    removed_files = 0
    for folder in folders:
        removed_files += storage.remove_folder_assets(folder["folder_name"])
    removed_files += storage.remove_site_source_assets(source.get("slug") or source.get("name") or str(source_id))
    storage_stats = pull_manager.refresh_storage_stats_cache()
    return {
        "ok": True,
        "message": f"已清空并删除站点，移除 {result['posts']} 条贴文和 {result['folders']} 个图库项目",
        "removed_files": removed_files,
        "storage_stats": storage_stats,
        **result,
    }


@app.post("/api/site-sources/{source_id}/sync")
async def sync_site_source(source_id: int) -> dict[str, Any]:
    if not db.get_site_source(source_id):
        raise HTTPException(status_code=404, detail="站点来源不存在")
    return site_syncer.start_sync(source_id)


@app.post("/api/site-sources/{source_id}/validate")
async def validate_site_source(source_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    if not db.get_site_source(source_id):
        raise HTTPException(status_code=404, detail="站点来源不存在")
    max_pages = payload.get("max_pages")
    try:
        max_pages = max(1, int(max_pages)) if max_pages else None
    except (TypeError, ValueError):
        max_pages = None
    if max_pages:
        return site_syncer.start_full_validation(source_id, max_pages=max_pages)
    return site_syncer.start_full_validation(source_id)


@app.post("/api/site-sources/{source_id}/refresh-icon")
async def refresh_site_source_icon(source_id: int) -> dict[str, Any]:
    try:
        item = site_syncer.refresh_site_icon(source_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    message = "站点图标已刷新" if item.get("icon_url") else "未能获取站点图标，已回退默认样式"
    return {"ok": True, "message": message, "item": item}


@app.post("/api/site-sources/test")
async def test_site_source(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return {"ok": True, "items": site_syncer.test_source(payload)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/site-sync")
async def sync_all_site_sources() -> dict[str, Any]:
    return site_syncer.start_sync()


@app.get("/api/site-posts")
async def list_site_posts(category: str = "all", source_id: int | None = None, q: str = "") -> dict[str, Any]:
    return {"items": db.list_site_posts(category=category, source_id=source_id, q=q)}


@app.get("/api/site-posts/{post_id}")
async def get_site_post(post_id: int) -> dict[str, Any]:
    item = db.get_site_post(post_id)
    if not item:
        raise HTTPException(status_code=404, detail="站点贴文不存在")
    assets = db.list_site_assets(post_id)
    for asset in assets:
        asset["url_local"] = f"/storage/{asset['rel_path']}" if asset.get("rel_path") else None
    return {"item": item, "assets": assets}


@app.post("/api/site-posts/{post_id}/favorite")
async def toggle_site_post_favorite(post_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    current = db.get_site_post(post_id)
    if not current:
        raise HTTPException(status_code=404, detail="站点贴文不存在")
    value = bool(payload.get("favorite", not current.get("is_favorite")))
    return {"ok": True, "item": db.set_site_post_flag(post_id, "is_favorite", value)}


@app.post("/api/site-posts/{post_id}/block")
async def toggle_site_post_block(post_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    current = db.get_site_post(post_id)
    if not current:
        raise HTTPException(status_code=404, detail="站点贴文不存在")
    value = bool(payload.get("blocked", not current.get("is_blocked")))
    db.set_site_post_flag(post_id, "is_blocked", value)
    db.set_site_post_status(post_id, "blocked" if value else "ready", "手动屏蔽" if value else None)
    if value:
        for folder_name in db.delete_site_gallery_post(current["source_id"], post_id):
            storage.remove_folder_assets(folder_name)
        pull_manager.refresh_storage_stats_cache()
    return {"ok": True, "item": db.get_site_post(post_id)}


@app.get("/api/site-rules")
async def get_site_rules() -> dict[str, Any]:
    return db.get_site_rules()


@app.put("/api/site-rules")
async def save_site_rules(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return db.save_site_rules(payload)


@app.get("/api/site-filter/logs")
async def site_filter_logs(limit: int = 200) -> dict[str, Any]:
    return {"items": db.list_site_filter_logs(limit=limit)}


@app.post("/api/site-filter/logs/clear")
async def clear_site_filter_logs() -> dict[str, Any]:
    removed = db.clear_site_filter_logs()
    return {"ok": True, "message": f"已清理 {removed} 条站点过滤日志", "removed": removed}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _latest_subscription_pull_at() -> str | None:
    latest_at: str | None = None
    for task_type in ("pull", "site-sync"):
        task = db.last_task_run(task_type)
        if not task:
            continue
        candidate = str(task.get("finished_at") or task.get("created_at") or "")
        if candidate and (latest_at is None or candidate > latest_at):
            latest_at = candidate
    return latest_at


def _latest_content_fields(*stats: dict[str, Any]) -> dict[str, Any]:
    latest_ts = 0
    latest_at = ""
    for stat in stats:
        if not stat:
            continue
        candidate_ts = _safe_int(stat.get("latest_content_ts"))
        candidate_at = str(stat.get("latest_content_at") or "")
        if candidate_ts > latest_ts:
            latest_ts = candidate_ts
            latest_at = candidate_at or format_pub_time(candidate_ts)
            continue
        if not latest_ts and candidate_at and candidate_at > latest_at:
            latest_at = candidate_at
    return {
        "latest_content_at": latest_at or None,
        "latest_content_ts": latest_ts,
    }


def _subscription_stats() -> list[dict[str, Any]]:
    if db.gallery_index_ready():
        stats_by_uid = {
            str(item["uid"]): {
                "uid": str(item["uid"]),
                "uname": item.get("uname") or f"UID {item['uid']}",
                "folder_count": int(item.get("folder_count") or 0),
                "image_count": int(item.get("image_count") or 0),
                "livephoto_count": int(item.get("livephoto_count") or 0),
                "asset_count": int(item.get("asset_count") or 0),
                "latest_content_ts": int(item.get("latest_content_ts") or 0),
                "latest_content_at": item.get("latest_content_at"),
            }
            for item in db.subscription_stats_from_index()
        }
    else:
        stats_by_uid: dict[str, dict[str, Any]] = {}
        assets_by_folder: dict[str, dict[str, int]] = {}
        for asset in db.list_all_assets():
            folder_stats = assets_by_folder.setdefault(str(asset.get("folder_name") or ""), {"image_count": 0, "livephoto_count": 0, "asset_count": 0})
            folder_stats["asset_count"] += 1
            if asset.get("media_type") == "image":
                folder_stats["image_count"] += 1
            if asset.get("media_type") == "livephoto":
                folder_stats["livephoto_count"] += 1
        for folder in db.list_folders():
            uid = str(folder.get("subscription_uid") or "")
            if not uid:
                continue
            folder_assets = assets_by_folder.get(str(folder.get("folder_name") or ""), {})
            entry = stats_by_uid.setdefault(
                uid,
                {
                    "uid": uid,
                    "uname": folder.get("subscription_name") or f"UID {uid}",
                    "folder_count": 0,
                    "image_count": 0,
                    "livephoto_count": 0,
                    "asset_count": 0,
                    "latest_content_ts": 0,
                    "latest_content_at": None,
                },
            )
            entry["folder_count"] += 1
            entry["image_count"] += int(folder_assets.get("image_count") or int(bool(folder.get("has_images"))))
            entry["livephoto_count"] += int(folder_assets.get("livephoto_count") or int(bool(folder.get("has_livephoto"))))
            entry["asset_count"] += int(folder_assets.get("asset_count") or 0)
            folder_pub_ts = _safe_int(folder.get("pub_ts"))
            if folder_pub_ts >= _safe_int(entry.get("latest_content_ts")):
                entry["latest_content_ts"] = folder_pub_ts
                entry["latest_content_at"] = folder.get("pub_time") or (format_pub_time(folder_pub_ts) if folder_pub_ts else None)
    site_stats_by_uid = {
        db.site_subscription_uid(source_id): stat
        for source_id, stat in db.site_source_content_stats().items()
    }
    output = []
    for item in db.list_subscriptions(include_paused=True):
        stat = stats_by_uid.get(str(item["uid"]), {})
        site_stat = site_stats_by_uid.get(str(item["uid"]), {})
        image_total = int(stat.get("image_count") or 0)
        latest_content = _latest_content_fields(stat, site_stat)
        output.append(
            {
                **item,
                "uname": item.get("uname") or stat.get("uname") or f"UID {item['uid']}",
                "icon_url": item.get("avatar_url"),
                "icon_tiny_url": item.get("avatar_tiny_url"),
                "folder_count": stat.get("folder_count", 0),
                "image_count": stat.get("image_count", 0),
                "image_total": image_total,
                "livephoto_count": stat.get("livephoto_count", 0),
                "asset_count": stat.get("asset_count", 0),
                **latest_content,
                "is_site": str(item["uid"]).startswith("site:"),
            }
        )
    existing_uids = {str(item["uid"]) for item in output}
    for source in db.list_site_sources():
        uid = db.site_subscription_uid(source["id"])
        if uid in existing_uids:
            continue
        stat = stats_by_uid.get(uid, {})
        site_stat = site_stats_by_uid.get(uid, {})
        image_total = int(stat.get("image_count") or 0) or int(site_stat.get("asset_count") or 0)
        latest_content = _latest_content_fields(stat, site_stat)
        output.append(
            {
                "uid": uid,
                "uname": source.get("name") or stat.get("uname") or stat.get("name") or uid,
                "status": "active",
                "pull_images": 1,
                "image_min_count": 1,
                "pull_livephoto": 0,
                "include_forwarded": 0,
                "created_at": source.get("created_at"),
                "updated_at": source.get("updated_at"),
                "icon_url": source.get("icon_url"),
                "icon_tiny_url": source.get("icon_tiny_url"),
                "source_id": source.get("id"),
                "source_type": source.get("source_type"),
                "entry_url": source.get("entry_url"),
                "folder_count": stat.get("folder_count", 0) or site_stat.get("post_count", 0),
                "post_count": site_stat.get("post_count", 0),
                "image_count": stat.get("image_count", 0),
                "image_total": image_total,
                "livephoto_count": stat.get("livephoto_count", 0),
                "asset_count": stat.get("asset_count", 0) or site_stat.get("asset_count", 0),
                **latest_content,
                "is_site": True,
            }
        )
        existing_uids.add(uid)
    for uid, stat in sorted(stats_by_uid.items(), key=lambda item: str(item[1].get("uname") or item[0]).lower()):
        if not uid.startswith("site:") or uid in existing_uids:
            continue
        site_stat = site_stats_by_uid.get(uid, {})
        image_total = int(stat.get("image_count") or 0) or int(site_stat.get("asset_count") or 0)
        latest_content = _latest_content_fields(stat, site_stat)
        output.append(
            {
                "uid": uid,
                "uname": stat.get("uname") or stat.get("name") or uid,
                "status": "active",
                "pull_images": 1,
                "image_min_count": 1,
                "pull_livephoto": 0,
                "include_forwarded": 0,
                "icon_url": None,
                "icon_tiny_url": None,
                "folder_count": stat.get("folder_count", 0) or site_stat.get("post_count", 0),
                "post_count": site_stat.get("post_count", 0),
                "image_count": stat.get("image_count", 0),
                "image_total": image_total,
                "livephoto_count": stat.get("livephoto_count", 0),
                "asset_count": stat.get("asset_count", 0) or site_stat.get("asset_count", 0),
                **latest_content,
                "is_site": True,
            }
        )
    return output


def _refresh_subscription_icon_item(current: dict[str, Any], cookie: str | None) -> tuple[dict[str, Any], bool, str | None]:
    uid = str(current["uid"])
    try:
        profile = auth.fetch_up_profile(uid, cookie)
    except RuntimeError as exc:
        item = db.set_subscription_icon(uid, None) or current
        return item, False, str(exc)

    avatar_url = profile.get("face") or None
    if avatar_url:
        avatar_url, avatar_tiny_url = _cache_subscription_avatar(uid, avatar_url, cookie)
        item = db.upsert_subscription(
            uid=uid,
            uname=profile.get("uname") or current.get("uname") or f"UID {uid}",
            avatar_url=avatar_url,
            avatar_tiny_url=avatar_tiny_url,
            status=current.get("status", "active"),
            pull_images=bool(current.get("pull_images")),
            image_min_count=int(current.get("image_min_count", 1) or 1),
            pull_livephoto=bool(current.get("pull_livephoto")),
            include_forwarded=bool(current.get("include_forwarded")),
        )
        return item, True, None

    if profile.get("uname"):
        db.upsert_subscription(
            uid=uid,
            uname=profile.get("uname") or current.get("uname") or f"UID {uid}",
            avatar_url=current.get("avatar_url"),
            avatar_tiny_url=current.get("avatar_tiny_url"),
            status=current.get("status", "active"),
            pull_images=bool(current.get("pull_images")),
            image_min_count=int(current.get("image_min_count", 1) or 1),
            pull_livephoto=bool(current.get("pull_livephoto")),
            include_forwarded=bool(current.get("include_forwarded")),
        )
    item = db.set_subscription_icon(uid, None) or db.get_subscription(uid) or current
    return item, False, "未能获取 UP 主头像"


def _cache_subscription_avatar(uid: str, avatar_url: str | None, cookie: str | None = None) -> tuple[str | None, str | None]:
    if not avatar_url or not _looks_like_bilibili_avatar_url(avatar_url):
        return avatar_url, None
    parsed = urlparse(avatar_url)
    extension = _avatar_extension(parsed.path)
    target_dir = storage.config.data_dir / "avatars" / "up"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uid}{extension}"
    tiny_target = target_dir / "tiny" / f"{uid}.webp"
    tmp_target = target.with_suffix(f"{target.suffix}.tmp")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://space.bilibili.com/{uid}/",
        "Connection": "close",
    }
    if cookie:
        headers["Cookie"] = cookie
    response = None
    try:
        response = requests.get(avatar_url, headers=headers, timeout=(8, 30), stream=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and not content_type.startswith("image/"):
            return avatar_url, None
        total = 0
        with tmp_target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > AVATAR_CACHE_MAX_BYTES:
                    tmp_target.unlink(missing_ok=True)
                    return avatar_url, None
                file.write(chunk)
        if total <= 0:
            tmp_target.unlink(missing_ok=True)
            return avatar_url, None
        tmp_target.replace(target)
        avatar_tiny_url = _ensure_tiny_storage_image(target, tiny_target)
        return storage.storage_url(storage.relative_to_storage(target)), avatar_tiny_url
    except Exception:
        tmp_target.unlink(missing_ok=True)
        return avatar_url, None
    finally:
        if response is not None:
            response.close()


def _ensure_tiny_storage_image(source: Path, target: Path) -> str | None:
    if not source.exists():
        return None
    try:
        thumbnailer.ensure_tiny_image_thumbnail(source, target)
    except Exception:
        return None
    if not target.exists():
        return None
    return storage.storage_url(storage.relative_to_storage(target))


def _looks_like_bilibili_avatar_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not parsed.scheme.startswith("http"):
        return str(url).startswith("/storage/")
    if not host.endswith(("hdslb.com", "bilivideo.com", "bilibili.com")):
        return False
    if path.endswith((".ico", ".svg")):
        return False
    if any(marker in path for marker in ("favicon", "logo", "webicon", "apple-touch-icon")):
        return False
    return any(
        marker in path
        for marker in (
            "/bfs/face/",
            "/images/member/noface",
            "/bfs/garb/item/",
            "/bfs/baselabs/",
            "/bfs/activity-plat/static/",
        )
    )


def _avatar_extension(path: str) -> str:
    clean_path = str(path or "").split("@", 1)[0].lower()
    match = re.search(r"\.(jpg|jpeg|png|webp|gif|avif)$", clean_path)
    if not match:
        return ".jpg"
    ext = match.group(1)
    return ".jpg" if ext == "jpeg" else f".{ext}"


def _sleep_before_avatar_refresh(index: int, previous_error: str | None = None) -> float:
    delay_range = AVATAR_REFRESH_INITIAL_DELAY_RANGE if index <= 0 else AVATAR_REFRESH_BETWEEN_DELAY_RANGE
    delay = random.uniform(*delay_range)
    if index > 0 and index % AVATAR_REFRESH_LONG_PAUSE_EVERY == 0:
        delay += random.uniform(*AVATAR_REFRESH_LONG_PAUSE_RANGE)
    if previous_error and _looks_like_avatar_refresh_risk(previous_error):
        delay += random.uniform(*AVATAR_REFRESH_RISK_BACKOFF_RANGE)
    time.sleep(delay)
    return delay


def _looks_like_avatar_refresh_risk(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(keyword.lower() in text for keyword in AVATAR_REFRESH_RISK_KEYWORDS)


@app.get("/api/subscriptions")
async def get_subscriptions() -> dict[str, Any]:
    return {"items": _subscription_stats(), "latest_pull_at": _latest_subscription_pull_at()}


@app.post("/api/subscriptions")
async def add_subscription(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    uid = str(payload.get("uid") or "").strip()
    if not uid.isdigit():
        raise HTTPException(status_code=400, detail="请输入有效的 UID")
    cookie = auth.get_cookie_state().cookie
    try:
        profile = auth.fetch_up_profile(uid, cookie)
    except RuntimeError:
        profile = {"uid": uid, "uname": f"UID {uid}"}
    current = db.get_settings()
    avatar_url, avatar_tiny_url = _cache_subscription_avatar(uid, profile.get("face"), cookie)
    db.upsert_subscription(
        uid,
        profile.get("uname"),
        avatar_url=avatar_url,
        avatar_tiny_url=avatar_tiny_url,
        status="active",
        pull_images=bool(current.get("pull_images", True)),
        image_min_count=int(current.get("image_min_count", 1) or 1),
        pull_livephoto=bool(current.get("pull_livephoto", True)),
        include_forwarded=bool(current.get("include_forwarded", True)),
    )
    if not current.get("host_mid"):
        db.save_settings({"host_mid": int(uid)})
    return {"ok": True, "message": "订阅已添加", "item": db.get_subscription(uid)}


@app.put("/api/subscriptions/{uid}")
async def update_subscription(uid: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    item = db.update_subscription_settings(
        uid,
        {
            "pull_images": payload.get("pull_images"),
            "image_min_count": payload.get("image_min_count"),
            "pull_livephoto": payload.get("pull_livephoto"),
            "include_forwarded": payload.get("include_forwarded"),
        },
    )
    if not item:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"ok": True, "message": "订阅抓取策略已更新", "item": item}


@app.post("/api/subscriptions/{uid}/refresh-profile")
async def refresh_subscription_profile(uid: str) -> dict[str, Any]:
    current = db.get_subscription(uid)
    if not current:
        raise HTTPException(status_code=404, detail="订阅不存在")
    cookie = auth.get_cookie_state().cookie
    try:
        profile = auth.fetch_up_profile(uid, cookie)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    avatar_url, avatar_tiny_url = _cache_subscription_avatar(uid, profile.get("face"), cookie)
    item = db.upsert_subscription(
        uid=uid,
        uname=profile.get("uname") or current.get("uname") or f"UID {uid}",
        avatar_url=avatar_url or current.get("avatar_url"),
        avatar_tiny_url=avatar_tiny_url or current.get("avatar_tiny_url"),
        status=current.get("status", "active"),
        pull_images=bool(current.get("pull_images")),
        image_min_count=int(current.get("image_min_count", 1) or 1),
        pull_livephoto=bool(current.get("pull_livephoto")),
        include_forwarded=bool(current.get("include_forwarded")),
    )
    return {"ok": True, "message": "昵称已刷新", "item": item}


@app.post("/api/subscriptions/{uid}/refresh-icon")
async def refresh_subscription_icon(uid: str) -> dict[str, Any]:
    current = db.get_subscription(uid)
    if not current:
        raise HTTPException(status_code=404, detail="订阅不存在")
    cookie = auth.get_cookie_state().cookie
    item, found, _error = _refresh_subscription_icon_item(current, cookie)
    message = "头像已刷新" if found else "未能获取 UP 主头像，已回退默认样式"
    return {"ok": True, "message": message, "item": item}


@app.post("/api/subscriptions/{uid}/toggle")
async def toggle_subscription(uid: str) -> dict[str, Any]:
    try:
        return pull_manager.toggle_subscription(uid)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/subscriptions/{uid}/reload")
async def reload_subscription(uid: str) -> dict[str, Any]:
    try:
        return pull_manager.start_subscription_reload(uid)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/subscriptions/{uid}/pull")
async def pull_subscription(uid: str) -> dict[str, Any]:
    try:
        if uid.startswith("site:"):
            source_id = int(uid.split(":", 1)[1])
            if not db.get_site_source(source_id):
                raise RuntimeError("站点来源不存在")
            return site_syncer.start_sync(source_id)
        return pull_manager.start_subscription_pull(uid)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/subscriptions/{uid}")
async def delete_subscription(uid: str) -> dict[str, Any]:
    try:
        return pull_manager.unsubscribe_and_delete(uid)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/pull/run")
async def run_pull() -> dict[str, Any]:
    try:
        return pull_manager.start_pull()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/pull/reload-all")
async def run_reload_all() -> dict[str, Any]:
    try:
        return pull_manager.start_reload_all()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/pull/status")
async def pull_status() -> dict[str, Any]:
    return pull_manager.status()


@app.get("/api/tasks/runs")
async def task_runs(limit: int = 50) -> dict[str, Any]:
    items = []
    for item in db.list_task_runs(limit=limit):
        items.append(
            {
                **item,
                "details": loads_json(item["details_json"], {}),
            }
        )
    return {"items": items, "current": pull_manager.status(), "queue": pull_manager.status().get("queue", [])}


@app.get("/api/tasks/{task_id}")
async def task_run_detail(task_id: int) -> dict[str, Any]:
    item = db.get_task_run(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "item": {
            **item,
            "details": loads_json(item["details_json"], {}),
        }
    }


@app.post("/api/tasks/pause")
async def pause_task() -> dict[str, Any]:
    try:
        return pull_manager.pause_current()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/resume")
async def resume_task() -> dict[str, Any]:
    try:
        return pull_manager.resume_current()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/cancel")
async def cancel_task() -> dict[str, Any]:
    try:
        return pull_manager.cancel_current()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/queue/{queue_id}/cancel")
async def cancel_queued_task(queue_id: int) -> dict[str, Any]:
    try:
        return pull_manager.cancel_queued(queue_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: int) -> dict[str, Any]:
    try:
        return pull_manager.retry_task_run(task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/clear-finished")
async def clear_finished_tasks() -> dict[str, Any]:
    removed = db.clear_finished_task_runs()
    return {"ok": True, "message": f"已清理 {removed} 条已结束任务日志", "removed": removed}


@app.get("/api/review/items")
async def review_items(status: str = "pending") -> dict[str, Any]:
    items = []
    for item in db.list_review_items(status=status):
        items.append(
            {
                **item,
                "reasons": loads_json(item["reasons_json"], []),
                "payload": loads_json(item["payload_json"], {}),
            }
        )
    return {"items": items}


@app.post("/api/review/{item_id}/approve")
async def approve_review(item_id: int) -> dict[str, Any]:
    if not db.get_review_item(item_id):
        raise HTTPException(status_code=404, detail="待审核项不存在")
    try:
        return pull_manager.start_review_approval(item_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/review/{item_id}/reject")
async def reject_review(item_id: int) -> dict[str, Any]:
    if not db.get_review_item(item_id):
        raise HTTPException(status_code=404, detail="待审核项不存在")
    try:
        return pull_manager.reject_review_item(item_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/filter/logs")
async def filter_logs(limit: int = 200) -> dict[str, Any]:
    items = []
    for item in db.list_filter_logs(limit=limit):
        items.append(
            {
                **item,
                "reasons": loads_json(item["reasons_json"], []),
            }
        )
    return {"items": items}


@app.post("/api/filter/logs/clear")
async def clear_filter_logs() -> dict[str, Any]:
    removed = db.clear_filter_logs()
    return {"ok": True, "message": f"已清理 {removed} 条过滤日志", "removed": removed}


@app.get("/api/trash/items")
async def trash_items() -> dict[str, Any]:
    items = []
    for item in db.list_trash_items():
        folder = loads_json(item["folder_json"], {})
        if not folder.get("original_url"):
            metadata = loads_json(folder.get("metadata_json"), {})
            folder["original_url"] = metadata.get("site_post_url") or db.site_post_url_from_dynamic_id(folder.get("source_dynamic_id"))
        subscription_uid = str(folder.get("subscription_uid") or "")
        subscription_name = str(folder.get("subscription_name") or "").strip()
        if subscription_uid and not subscription_name:
            subscription = db.get_subscription(subscription_uid)
            if subscription:
                subscription_name = str(subscription.get("uname") or "").strip()
        items.append(
            {
                **item,
                "folder": folder,
                "subscription_uid": subscription_uid,
                "subscription_name": subscription_name,
            }
        )
    return {"items": items}


@app.post("/api/gallery/folders/{folder_name}/trash")
async def trash_folder(folder_name: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    reason = str(payload.get("reason") or "不喜欢")
    try:
        return pull_manager.move_to_trash(folder_name, reason=reason)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/gallery/folders/{folder_name}/pairs/{pair_index}/delete")
async def delete_folder_pair(folder_name: str, pair_index: int) -> dict[str, Any]:
    try:
        return pull_manager.delete_pair(folder_name, pair_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/trash/{item_id}/restore")
async def restore_trash(item_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    repull_now = bool(payload.get("repull_now"))
    try:
        return pull_manager.restore_from_trash(item_id, repull_now=repull_now)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    settings = db.get_settings()
    settings["auth"] = auth.check_cookie()
    return settings


@app.put("/api/settings")
async def update_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    payload = {key: value for key, value in payload.items() if key not in {"auth"}}
    settings = db.save_settings(payload)
    thumbnailer.apply_settings(settings)
    scheduler.reload()
    return settings


@app.get("/api/settings/storage-stats")
async def get_storage_stats() -> dict[str, Any]:
    return {"ok": True, "stats": pull_manager.storage_stats()}


@app.post("/api/settings/storage-stats/refresh")
async def refresh_storage_stats() -> dict[str, Any]:
    return {"ok": True, "stats": pull_manager.refresh_storage_stats_cache()}


@app.post("/api/settings/storage-cleanup")
async def cleanup_storage_trash() -> dict[str, Any]:
    try:
        return pull_manager.start_storage_cleanup()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/clear-data")
async def clear_data() -> dict[str, Any]:
    try:
        return pull_manager.clear_all_content()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/validate-content")
async def validate_content() -> dict[str, Any]:
    try:
        return pull_manager.start_validation()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/rebuild-gallery-index")
async def rebuild_gallery_index() -> dict[str, Any]:
    try:
        return pull_manager.start_gallery_index_rebuild()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/rebuild-thumbnails/{level}")
async def rebuild_thumbnails(level: str) -> dict[str, Any]:
    try:
        return pull_manager.start_thumbnail_rebuild(level)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _execute_reset_all_icons(cookie: str | None) -> dict[str, Any]:
    summary = {
        "subscriptions": {"total": 0, "updated": 0, "fallback": 0, "failed": 0},
        "sites": {"total": 0, "updated": 0, "fallback": 0, "failed": 0},
        "errors": [],
    }

    previous_avatar_error: str | None = None
    for index, subscription in enumerate(db.list_subscriptions(include_paused=True)):
        summary["subscriptions"]["total"] += 1
        waited = _sleep_before_avatar_refresh(index, previous_avatar_error)
        summary["subscriptions"]["wait_seconds"] = round(float(summary["subscriptions"].get("wait_seconds", 0)) + waited, 2)
        item, found, error = _refresh_subscription_icon_item(subscription, cookie)
        previous_avatar_error = error
        if found and item.get("avatar_url"):
            summary["subscriptions"]["updated"] += 1
        else:
            summary["subscriptions"]["fallback"] += 1
        if error and error != "未能获取 UP 主头像":
            summary["subscriptions"]["failed"] += 1
            summary["errors"].append({"kind": "subscription", "uid": subscription.get("uid"), "message": error})

    for source in db.list_site_sources():
        summary["sites"]["total"] += 1
        try:
            item = site_syncer.refresh_site_icon(int(source["id"]))
        except RuntimeError as exc:
            summary["sites"]["failed"] += 1
            summary["errors"].append({"kind": "site", "id": source.get("id"), "message": str(exc)})
            continue
        if item.get("icon_url"):
            summary["sites"]["updated"] += 1
        else:
            summary["sites"]["fallback"] += 1

    db.refresh_sidebar_count_cache(["subscriptions", "sites"])
    message = (
        f"图标重置完成：UP {summary['subscriptions']['updated']}/{summary['subscriptions']['total']}，"
        f"站点 {summary['sites']['updated']}/{summary['sites']['total']}。"
    )
    if summary["subscriptions"]["fallback"] or summary["sites"]["fallback"]:
        message += " 无法获取图像的项目已回退默认样式。"
    if summary["subscriptions"]["failed"] or summary["sites"]["failed"]:
        message += " 部分项目请求失败，详情已记录。"
    return {"message": message, "result": summary}


def _run_reset_all_icons_task(task_id: int, cookie: str | None) -> None:
    try:
        details = _execute_reset_all_icons(cookie)
        db.finish_task_run(task_id, "success", details["message"], details)
    except Exception as exc:
        db.finish_task_run(task_id, "failed", str(exc), {"error": str(exc)})
    finally:
        _icon_reset_lock.release()


@app.post("/api/settings/reset-icons")
async def reset_all_icons() -> dict[str, Any]:
    if not _icon_reset_lock.acquire(blocking=False):
        return {"ok": True, "queued": True, "message": "已有图标重置任务正在运行"}
    cookie = auth.get_cookie_state().cookie
    task_id = db.create_task_run("icons", "running", "开始重置所有图标")
    thread = threading.Thread(target=_run_reset_all_icons_task, args=(task_id, cookie), daemon=True)
    thread.start()
    return {"ok": True, "queued": False, "message": "图标重置任务已提交，可在任务队列中查看进度"}


@app.post("/api/auth/qr/start")
async def start_qr() -> dict[str, Any]:
    try:
        return auth.start_qr_login()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/auth/qr/status")
async def poll_qr() -> dict[str, Any]:
    try:
        return auth.poll_qr_login()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/auth/check")
async def check_auth() -> dict[str, Any]:
    return auth.check_cookie()


@app.post("/api/auth/logout")
async def logout() -> dict[str, Any]:
    auth.logout()
    return {"ok": True, "message": "已退出登录"}
