from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config
from app.db import Database
from app.services.bilibili import BilibiliAuthService
from app.services.cleanup import CleanupService
from app.services.gallery import GalleryService
from app.services.legacy_import import LegacyImporter
from app.services.media_indexer import MediaIndexer
from app.services.puller import PullManager
from app.services.scheduler import SchedulerService
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import loads_json
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
scheduler = SchedulerService(db, pull_manager)
templates = Jinja2Templates(directory=str(config.app_root / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure()
    db.init()
    scheduler.start()
    pull_manager.start_startup_sync()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title=APP_TITLE, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.app_root / "static")), name="static")
app.mount("/storage", StaticFiles(directory=str(config.storage_root), check_dir=False), name="storage")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": APP_TITLE,
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
        "gallery_index": db.gallery_index_status(),
    }


@app.get("/api/gallery/items")
async def get_gallery_items(
    category: str = "all",
    year: str | None = None,
    month: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    subscription_uids: str | None = None,
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
    return {"ok": True, "favorite": favorite, "message": "已加入收藏" if favorite else "已取消收藏"}


def _subscription_stats() -> list[dict[str, Any]]:
    if db.gallery_index_ready():
        stats_by_uid = {
            str(item["uid"]): {
                "uid": str(item["uid"]),
                "uname": item.get("uname") or f"UID {item['uid']}",
                "folder_count": int(item.get("folder_count") or 0),
                "image_count": int(item.get("image_count") or 0),
                "livephoto_count": int(item.get("livephoto_count") or 0),
            }
            for item in db.subscription_stats_from_index()
        }
    else:
        stats_by_uid: dict[str, dict[str, Any]] = {}
        for folder in db.list_folders():
            uid = str(folder.get("subscription_uid") or "")
            if not uid:
                continue
            entry = stats_by_uid.setdefault(
                uid,
                {
                    "uid": uid,
                    "uname": folder.get("subscription_name") or f"UID {uid}",
                    "folder_count": 0,
                    "image_count": 0,
                    "livephoto_count": 0,
                },
            )
            entry["folder_count"] += 1
            entry["image_count"] += int(bool(folder.get("has_images")))
            entry["livephoto_count"] += int(bool(folder.get("has_livephoto")))
    output = []
    for item in db.list_subscriptions(include_paused=True):
        stat = stats_by_uid.get(str(item["uid"]), {})
        output.append(
            {
                **item,
                "uname": item.get("uname") or stat.get("uname") or f"UID {item['uid']}",
                "folder_count": stat.get("folder_count", 0),
                "image_count": stat.get("image_count", 0),
                "livephoto_count": stat.get("livephoto_count", 0),
            }
        )
    return output


@app.get("/api/subscriptions")
async def get_subscriptions() -> dict[str, Any]:
    return {"items": _subscription_stats()}


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
    db.upsert_subscription(
        uid,
        profile.get("uname"),
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
    item = db.upsert_subscription(
        uid=uid,
        uname=profile.get("uname") or current.get("uname") or f"UID {uid}",
        status=current.get("status", "active"),
        pull_images=bool(current.get("pull_images")),
        image_min_count=int(current.get("image_min_count", 1) or 1),
        pull_livephoto=bool(current.get("pull_livephoto")),
        include_forwarded=bool(current.get("include_forwarded")),
    )
    return {"ok": True, "message": "昵称已刷新", "item": item}


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
        return pull_manager.start_subscription_pull(uid)
    except RuntimeError as exc:
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
    settings = db.save_settings(payload)
    scheduler.reload()
    return settings


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
