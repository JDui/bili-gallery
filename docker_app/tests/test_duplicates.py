from __future__ import annotations

from pathlib import Path

import pytest

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


def add_folder(
    db: Database,
    folder_name: str,
    pub_ts: int,
    fingerprints: list[str],
    width: int = 1200,
    height: int = 900,
) -> None:
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
                "width": width,
                "height": height,
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
    ratios = {item["folder_name"]: item["duplicate_ratio"] for item in payload["items"][0]["items"]}
    assert ratios == {"folder-a": 67, "folder-b": 67}

    restarted_service = DuplicateService(db, _storage)
    restarted_service._build_groups = lambda _threshold: (_ for _ in ()).throw(AssertionError("不应重新全局检测"))
    assert restarted_service.list_groups()["active_total"] == 1
    db.set_folder_favorite("folder-a", True)
    assert restarted_service.list_groups()["active_total"] == 1
    with pytest.raises(AssertionError, match="不应重新全局检测"):
        restarted_service.list_groups(force=True)

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


def test_removing_duplicate_folders_updates_cache_without_global_rescan(tmp_path: Path) -> None:
    db, _storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    shared = [fingerprint(first), fingerprint(second)]
    add_folder(db, "high-resolution", 3, shared, width=2400, height=1800)
    add_folder(db, "more-images", 2, [*shared, fingerprint(int("f0" * 32, 16))])
    add_folder(db, "earlier", 1, shared)

    group = service.list_groups()["items"][0]
    tags = {item["folder_name"]: item["feature_tags"] for item in group["items"]}
    assert "更高分辨率" in tags["high-resolution"]
    assert "更多图片" in tags["more-images"]
    assert "更早发布" in tags["earlier"]

    db.delete_folder("high-resolution")
    service._build_groups = lambda _threshold: (_ for _ in ()).throw(AssertionError("不应重新全局检测"))
    payload = service.remove_folders(["high-resolution"])

    assert payload["active_total"] == 1
    assert {item["folder_name"] for item in payload["items"][0]["items"]} == {"more-images", "earlier"}
    assert service.get_group(group["signature"])["post_count"] == 2

    db.delete_folder("more-images")
    payload = service.remove_folders(["more-images"])

    assert payload["active_total"] == 0
    assert payload["items"] == []
    assert db.get_sidebar_count_cache()["counts"]["duplicates"] == 0

    restarted_service = DuplicateService(db, _storage)
    restarted_service._build_groups = lambda _threshold: (_ for _ in ()).throw(AssertionError("不应重新全局检测"))
    assert restarted_service.list_groups()["items"] == []


def test_cleanup_plan_only_selects_lower_resolution_duplicates(tmp_path: Path) -> None:
    db, storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    shared = [fingerprint(first), fingerprint(second)]
    add_folder(db, "high-resolution", 2, shared, width=2400, height=1800)
    add_folder(db, "low-resolution", 1, shared, width=1200, height=900)

    group = service.list_groups()["items"][0]
    assert group["cleanup_candidate_count"] == 2
    assert {item["duplicate_ratio"] for item in group["items"]} == {100}

    restarted = DuplicateService(db, storage)
    restarted._build_groups = lambda _threshold: (_ for _ in ()).throw(AssertionError("不应重新全局检测"))
    plan = restarted.cleanup_plan(group["signature"])

    assert plan["folder_names"] == ["high-resolution", "low-resolution"]
    assert {
        (target["folder_name"], target["pair_index"])
        for target in plan["targets"]
    } == {("low-resolution", 1), ("low-resolution", 2)}


def test_refresh_group_after_cleanup_only_rechecks_affected_folders(tmp_path: Path) -> None:
    db, _storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    shared = [fingerprint(first), fingerprint(second)]
    add_folder(db, "high-resolution", 2, shared, width=2400, height=1800)
    add_folder(db, "low-resolution", 1, shared, width=1200, height=900)
    group = service.list_groups()["items"][0]
    plan = service.cleanup_plan(group["signature"])
    for target in plan["targets"]:
        for asset in db.list_assets_for_folder(target["folder_name"]):
            if int(asset["pair_index"]) == int(target["pair_index"]):
                db.delete_asset(int(asset["id"]))

    original_build = service._build_groups
    calls = []

    def scoped_build(threshold: int, folder_names: set[str] | None = None) -> list[dict]:
        calls.append(folder_names)
        return original_build(threshold, folder_names=folder_names)

    service._build_groups = scoped_build
    payload = service.refresh_group(group["signature"], plan["folder_names"])

    assert calls == [{"high-resolution", "low-resolution"}]
    assert payload["items"] == []
    assert db.get_folder("high-resolution") is not None
    assert db.get_folder("low-resolution") is not None


def test_equal_resolution_duplicates_have_no_cleanup_targets(tmp_path: Path) -> None:
    db, _storage, service = make_services(tmp_path)
    first = int("a5" * 32, 16)
    second = int("3c" * 32, 16)
    shared = [fingerprint(first), fingerprint(second)]
    add_folder(db, "first", 2, shared)
    add_folder(db, "second", 1, shared)

    group = service.list_groups()["items"][0]

    assert group["cleanup_candidate_count"] == 0
    assert service.cleanup_plan(group["signature"])["targets"] == []
