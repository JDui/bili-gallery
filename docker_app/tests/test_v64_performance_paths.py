from __future__ import annotations

import inspect
from pathlib import Path

from app.db import Database
from app.services.gallery import GalleryService
from app.services.sidecar import SidecarRunner


class FakeDetailDb:
    def __init__(self) -> None:
        self.get_folder_calls: list[str] = []

    def get_folder(self, folder_name: str) -> dict:
        self.get_folder_calls.append(folder_name)
        return {
            "folder_name": folder_name,
            "title": "Demo",
            "text_prefix": "",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
            "has_images": False,
            "has_livephoto": False,
            "review_status": "approved",
        }

    def list_folders(self) -> list[dict]:
        raise AssertionError("get_folder_detail should not scan all folders")

    def list_assets_for_folder(self, folder_name: str) -> list[dict]:
        return [
            {
                "id": 1,
                "folder_name": folder_name,
                "media_type": "image",
                "pair_index": 1,
                "filename": "001.jpg",
                "rel_path": "data/images/folder-a/001.jpg",
                "thumb_rel_path": "data/images/folder-a/.thumbs/001.webp",
                "small_thumb_rel_path": "data/images/folder-a/.thumbs/small/001.webp",
                "tiny_thumb_rel_path": "data/images/folder-a/.thumbs/tiny/001.webp",
                "cover_rel_path": None,
                "reverse_rel_path": None,
                "width": 16,
                "height": 9,
                "metadata_json": "{}",
            }
        ]

    def site_post_url_from_dynamic_id(self, dynamic_id: str | None) -> str:
        return ""


class FakeStorage:
    def storage_url(self, rel_path: str | None) -> str | None:
        return f"/storage/{rel_path}" if rel_path else None


def test_get_folder_detail_uses_direct_folder_lookup() -> None:
    db = FakeDetailDb()
    detail = GalleryService(db, FakeStorage()).get_folder_detail("folder-a")
    assert db.get_folder_calls == ["folder-a"]
    assert detail is not None
    assert detail["folder"]["folder_name"] == "folder-a"


def test_random_gallery_queries_do_not_use_order_by_random() -> None:
    folder_source = inspect.getsource(Database.query_folder_index).lower()
    pair_source = inspect.getsource(Database.query_pair_index).lower()
    assert "order by random()" not in folder_source
    assert "order by random()" not in pair_source
    assert "random.sample" in folder_source
    assert "random.sample" in pair_source


def test_sidecar_runner_returns_json_and_falls_back(tmp_path: Path, monkeypatch) -> None:
    fake_worker = tmp_path / "media-worker"
    fake_worker.write_text(
        "#!/bin/sh\n"
        "printf '{\"ok\":true,\"width\":16,\"height\":9,\"source\":\"demo\"}'\n",
        encoding="utf-8",
    )
    fake_worker.chmod(0o755)
    monkeypatch.setenv("APP_MEDIA_WORKER_BIN", str(fake_worker))
    runner = SidecarRunner(timeout_seconds=1)
    result = runner.probe_image(tmp_path / "demo.jpg")
    assert result is not None
    assert result["width"] == 16

    fake_worker.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    fallback_runner = SidecarRunner(timeout_seconds=1)
    assert fallback_runner.probe_image(tmp_path / "demo.jpg") is None


def test_sidecar_runner_ignores_missing_binary(monkeypatch) -> None:
    monkeypatch.setenv("APP_MEDIA_WORKER_BIN", "/missing/media-worker")
    runner = SidecarRunner(timeout_seconds=1)
    assert runner.probe_image(Path("/missing/image.jpg")) is None


def test_subscription_stats_sum_index_image_totals(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.init()
    db.upsert_subscription("42", uname="Image Owner", pull_images=True, image_min_count=1, pull_livephoto=True)
    for index, image_count in enumerate((4, 3), start=1):
        folder_name = f"folder-{index}"
        db.upsert_folder(
            {
                "folder_name": folder_name,
                "title": folder_name,
                "text_prefix": folder_name,
                "pub_ts": index,
                "pub_time": "1970-01-01 00:00:01",
                "top_dynamic_id": f"top-{index}",
                "source_dynamic_id": f"src-{index}",
                "subscription_uid": "42",
                "subscription_name": "Image Owner",
                "has_images": True,
                "has_livephoto": index == 1,
            }
        )
        db.replace_gallery_index(
            folder_name,
            {
                "title": folder_name,
                "text_prefix": folder_name,
                "pub_ts": index,
                "pub_time": "1970-01-01 00:00:01",
                "top_dynamic_id": f"top-{index}",
                "source_dynamic_id": f"src-{index}",
                "subscription_uid": "42",
                "subscription_name": "Image Owner",
                "has_images": True,
                "has_livephoto": index == 1,
                "image_count": image_count,
                "livephoto_count": 1 if index == 1 else 0,
                "asset_count": image_count + (1 if index == 1 else 0),
                "preview_assets_json": "[]",
            },
            [],
        )

    stats = db.subscription_stats_from_index()
    owner = next(item for item in stats if item["uid"] == "42")
    assert owner["folder_count"] == 2
    assert owner["image_count"] == 7
    assert owner["livephoto_count"] == 1
    assert owner["asset_count"] == 8


def test_site_source_content_stats_are_aggregated(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.init()
    source = db.create_site_source(
        {
            "name": "Stats Site",
            "slug": "stats-site",
            "source_type": "html",
            "entry_url": "https://example.com/posts",
            "enabled": True,
        }
    )
    first = db.upsert_site_post(source["id"], {"url": "https://example.com/a", "title": "A", "slug": "a"})
    second = db.upsert_site_post(source["id"], {"url": "https://example.com/b", "title": "B", "slug": "b"})
    for index in range(3):
        asset = db.upsert_site_asset(
            first["id"],
            {"url": f"https://example.com/a-{index}.jpg", "media_type": "image", "filename": f"a-{index}.jpg"},
        )
        db.set_site_asset_result(asset["id"], "ready", f"data/sites/a-{index}.jpg")
    for index in range(2):
        asset = db.upsert_site_asset(
            second["id"],
            {"url": f"https://example.com/b-{index}.jpg", "media_type": "image", "filename": f"b-{index}.jpg"},
        )
        db.set_site_asset_result(asset["id"], "ready", f"data/sites/b-{index}.jpg")
    db.update_site_post_counts(first["id"])
    db.update_site_post_counts(second["id"])

    stats = db.site_source_content_stats()
    assert stats[source["id"]]["post_count"] == 2
    assert stats[source["id"]]["asset_count"] == 5
