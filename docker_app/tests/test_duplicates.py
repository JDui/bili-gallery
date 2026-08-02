from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.db import Database
from app.services.duplicates import DuplicateService
from app.services.storage import StorageService


def make_services(tmp_path: Path) -> tuple[Database, StorageService, DuplicateService]:
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
    return db, storage, DuplicateService(db, storage)


def fingerprint(hash_bits: int, color: str = "8090a0", contrast: int = 64) -> str:
    return f"v1:{hash_bits:064x}:{color}:{contrast:02x}"


def add_folder(db: Database, folder_name: str, pub_ts: int, fingerprints: list[str]) -> None:
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": f"贴文 {folder_name}",
            "text_prefix": "测试重复内容",
            "pub_ts": pub_ts,
            "pub_time": "2026-08-03 00:00:00",
            "top_dynamic_id": f"top-{folder_name}",
            "source_dynamic_id": f"source-{folder_name}",
            "subscription_uid": "42",
            "subscription_name": "测试订阅",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        folder_name,
        "image",
        [
            {
                "pair_index": index,
                "filename": f"{index:03d}.jpg",
                "rel_path": f"data/images/{folder_name}/{index:03d}.jpg",
                "width": 1200,
                "height": 900,
                "duplicate_fingerprint": value,
                "metadata": {"kind": "image"},
            }
            for index, value in enumerate(fingerprints, start=1)
        ],
    )


def test_duplicate_groups_require_persisted_image_threshold(tmp_path: Path) -> None:
    db, _storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    third = int("f0" * 32, 16)
    add_folder(db, "folder-a", 3, [fingerprint(first), fingerprint(second), fingerprint(third)])
    add_folder(db, "folder-b", 2, [fingerprint(first ^ 1), fingerprint(second ^ 3), fingerprint(int("0f" * 32, 16))])
    add_folder(db, "folder-c", 1, [fingerprint(first ^ 2), fingerprint(int("55" * 32, 16)), fingerprint(int("99" * 32, 16))])

    payload = service.list_groups()

    assert payload["image_threshold"] == 2
    assert payload["active_total"] == 1
    assert {item["folder_name"] for item in payload["items"][0]["items"]} == {"folder-a", "folder-b"}
    assert payload["items"][0]["matched_image_count"] == 2

    db.save_settings({"duplicate_image_threshold": 3})
    assert Database(db.db_path).get_settings()["duplicate_image_threshold"] == 3
    assert service.list_groups()["active_total"] == 0


def test_ignored_duplicate_group_stays_hidden(tmp_path: Path) -> None:
    db, storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    add_folder(db, "folder-a", 2, [fingerprint(first), fingerprint(second)])
    add_folder(db, "folder-b", 1, [fingerprint(first ^ 1), fingerprint(second ^ 3)])
    group = service.list_groups()["items"][0]

    result = service.ignore_group(group["signature"])

    assert result["ok"] is True
    assert service.list_groups()["items"] == []
    assert DuplicateService(db, storage).list_groups()["items"] == []
    assert db.get_sidebar_count_cache()["counts"]["duplicates"] == 0


def test_low_contrast_images_with_different_colors_are_not_duplicates(tmp_path: Path) -> None:
    db, _storage, service = make_services(tmp_path)
    flat_hash = 0
    add_folder(
        db,
        "folder-red",
        2,
        [fingerprint(flat_hash, "d03030", 4), fingerprint(flat_hash, "d03030", 4)],
    )
    add_folder(
        db,
        "folder-blue",
        1,
        [fingerprint(flat_hash, "3040d0", 4), fingerprint(flat_hash, "3040d0", 4)],
    )

    assert service.list_groups()["items"] == []
