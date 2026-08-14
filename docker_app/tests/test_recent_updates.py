from pathlib import Path

from app.config import AppConfig
from app.db import Database
from app.services.gallery import GalleryService
from app.services.storage import StorageService
from fastapi.testclient import TestClient


def make_services(tmp_path: Path) -> tuple[Database, StorageService, GalleryService]:
    config = AppConfig(
        app_root=tmp_path,
        repo_root=tmp_path,
        storage_root=tmp_path / "storage",
        config_dir=tmp_path / "storage" / "config",
        data_dir=tmp_path / "storage" / "data",
        images_dir=tmp_path / "storage" / "data" / "images",
        livephoto_dir=tmp_path / "storage" / "data" / "livephoto",
        database_path=tmp_path / "storage" / "config" / "app.db",
        secret_key="test-secret",
    )
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    return db, storage, GalleryService(db, storage)


def add_folder(
    db: Database,
    folder_name: str,
    top_dynamic_id: str,
    source_dynamic_id: str,
    subscription_uid: str = "123",
    subscription_name: str = "测试 UP",
) -> None:
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": f"完整动态 {folder_name}",
            "text_prefix": "五字标题",
            "pub_ts": 1,
            "pub_time": "2026-08-15 10:00:00",
            "top_dynamic_id": top_dynamic_id,
            "source_dynamic_id": source_dynamic_id,
            "subscription_uid": subscription_uid,
            "subscription_name": subscription_name,
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        folder_name,
        "image",
        [
            {
                "pair_index": 1,
                "filename": "01.jpg",
                "rel_path": f"data/images/{folder_name}/01.jpg",
                "thumb_rel_path": f"data/images/{folder_name}/.thumbs/01.webp",
            }
        ],
    )


def add_pull_task(db: Database, message: str, added_items: list[dict]) -> int:
    task_id = db.create_task_run("pull", "running", message)
    db.finish_task_run(task_id, "success", message, {"added_items": added_items})
    return task_id


def test_recent_updates_groups_successful_pull_items_and_filters_deleted_content(tmp_path: Path) -> None:
    db, _storage, gallery = make_services(tmp_path)
    add_folder(db, "new-folder", "top-new", "source-new")
    add_folder(db, "old-folder", "top-old", "source-old")
    add_folder(
        db,
        "site-folder",
        "site:7:post-1",
        "site:7:post-1",
        subscription_uid="site:7",
        subscription_name="测试站点",
    )

    old_task = add_pull_task(
        db,
        "自动拉取完成",
        [{"top_dynamic_id": "top-old", "source_dynamic_id": "source-old"}],
    )
    new_task = add_pull_task(
        db,
        "手动拉取完成",
        [
            {"top_dynamic_id": "top-new", "source_dynamic_id": "source-new"},
            {"top_dynamic_id": "missing", "source_dynamic_id": "missing"},
        ],
    )
    failed_task = db.create_task_run("pull", "running", "拉取失败")
    db.finish_task_run(
        failed_task,
        "failed",
        "拉取失败",
        {"added_items": [{"top_dynamic_id": "top-old", "source_dynamic_id": "source-old"}]},
    )
    site_task = db.create_task_run("site-sync", "running", "站点同步")
    db.finish_task_run(
        site_task,
        "success",
        "站点同步完成",
        {
            "added_items": [
                {
                    "top_dynamic_id": "site:7:post-1",
                    "source_dynamic_id": "site:7:post-1",
                }
            ]
        },
    )
    failed_site_task = db.create_task_run("site-sync", "running", "站点同步失败")
    db.finish_task_run(
        failed_site_task,
        "failed",
        "站点同步失败",
        {
            "added_items": [
                {
                    "top_dynamic_id": "site:7:post-1",
                    "source_dynamic_id": "site:7:post-1",
                }
            ]
        },
    )

    payload = gallery.get_recent_updates()

    assert [group["task_id"] for group in payload["groups"]] == [site_task, new_task, old_task]
    assert [group["task_type"] for group in payload["groups"]] == ["site-sync", "pull", "pull"]
    assert payload["total_groups"] == 3
    assert payload["total_items"] == 3
    site_card = payload["groups"][0]["items"][0]
    assert site_card["folder_name"] == "site-folder"
    assert site_card["subscription_uid"] == "site:7"
    card = payload["groups"][1]["items"][0]
    assert card["folder_name"] == "new-folder"
    assert card["title"] == "完整动态 new-folder"
    assert card["text_prefix"] == "五字标题"
    assert card["subscription_name"] == "测试 UP"
    assert card["image_count"] == 1

    db.delete_folder("site-folder")
    after_site_delete = gallery.get_recent_updates()
    assert [group["task_id"] for group in after_site_delete["groups"]] == [new_task, old_task]
    assert after_site_delete["total_items"] == 2

    db.delete_folder("new-folder")
    after_new_delete = gallery.get_recent_updates()
    assert [group["task_id"] for group in after_new_delete["groups"]] == [old_task]
    assert after_new_delete["total_items"] == 1

    db.delete_folder("old-folder")
    assert gallery.get_recent_updates() == {"groups": [], "total_groups": 0, "total_items": 0}


def test_recent_updates_api_clamps_limit_and_returns_groups(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    db, _storage, gallery = make_services(tmp_path)
    add_folder(db, "api-folder", "top-api", "source-api")
    task_id = add_pull_task(
        db,
        "拉取完成",
        [{"top_dynamic_id": "top-api", "source_dynamic_id": "source-api"}],
    )
    monkeypatch.setattr(app_main, "gallery", gallery)

    payload = TestClient(app_main.app).get("/api/gallery/recent-updates?limit=999").json()

    assert payload["total_groups"] == 1
    assert payload["groups"][0]["task_id"] == task_id
