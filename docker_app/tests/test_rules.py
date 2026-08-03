from __future__ import annotations

from pathlib import Path

from app.db import Database
from app.services.bilibili import BilibiliAuthService
from app.services.cleanup import CleanupService
from app.services.filtering import FilterEngine
from app.services.gallery import GalleryService
from app.services.media_indexer import MediaIndexer
from app.services.puller import PullManager, ResourceDownloadError
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import build_folder_name


class DummyConfig:
    def __init__(self, root: Path) -> None:
        self.storage_root = root
        self.config_dir = root / "config"
        self.data_dir = root / "data"
        self.images_dir = self.data_dir / "images"
        self.livephoto_dir = self.data_dir / "livephoto"
        self.database_path = self.config_dir / "app.db"


class DummyCleanup:
    def run(self) -> dict[str, int]:
        return {"removed_assets": 0, "removed_files": 0}


class DummyIndexer:
    def reindex_library(self) -> None:
        return

    def index_folder(self, **kwargs) -> None:
        return

    def _replace_gallery_index(self, folder: dict, assets: list[dict]) -> None:
        return


class DummyAuth:
    class State:
        cookie = "SESSDATA=test"

    def get_cookie_state(self) -> "DummyAuth.State":
        return self.State()


class DummyLegacyImporter:
    def import_if_needed(self) -> dict[str, object]:
        return {"skipped": True}


class DummyDuplicateService:
    def remove_folders(self, _folder_names: list[str]) -> dict[str, object]:
        return {"active_total": 0}

    def refresh_group(self, _signature: str, _folder_names: list[str]) -> dict[str, object]:
        return {"active_total": 0}


def test_folder_name_prefers_chinese_prefix() -> None:
    used = set()
    folder = build_folder_name(1767139200, "ABC阿巴巴阿巴 world", used)
    assert folder == "20251231_阿巴巴阿巴"


def test_folder_name_falls_back_when_no_chinese() -> None:
    used = set()
    folder = build_folder_name(1767139200, "HELLO-123", used)
    assert folder == "20251231_日常动态图"


def test_folder_name_handles_collision() -> None:
    used = set()
    first = build_folder_name(1767139200, "阿巴巴阿巴", used)
    second = build_folder_name(1767139200, "阿巴巴阿巴", used)
    assert first == "20251231_阿巴巴阿巴"
    assert second == "20251231_阿巴巴阿巴_2"


def test_filter_marks_keyword_or_long_images_for_review() -> None:
    engine = FilterEngine(
        {
            "ad_filter_enabled": True,
            "ad_filter_keywords": ["推广"],
            "long_image_ratio": 3.0,
        }
    )
    item = {
        "modules": {
            "module_dynamic": {
                "desc": {"text": "这是一个推广动态"},
                "major": {
                    "draw": {
                        "items": [
                            {"src": "https://a", "width": 800, "height": 4000},
                            {"src": "https://b", "width": 800, "height": 3200},
                            {"src": "https://c", "width": 800, "height": 900},
                        ]
                    }
                },
            }
        }
    }
    result = engine.evaluate(item)
    assert result.decision == "review"
    assert len(result.reasons) == 2


def test_cleanup_removes_orphan_thumb_and_asset(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    db.upsert_folder(
        {
            "folder_name": "20250101_测试",
            "title": "测试",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "1",
            "source_dynamic_id": "1",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    thumb = config.storage_root / "data/images/20250101_测试/.thumbs/1.webp"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"thumb")
    db.replace_folder_assets(
        "20250101_测试",
        "image",
        [
            {
                "pair_index": 1,
                "filename": "1.jpg",
                "rel_path": "data/images/20250101_测试/1.jpg",
                "thumb_rel_path": "data/images/20250101_测试/.thumbs/1.webp",
            }
        ],
    )
    cleanup = CleanupService(db, storage)
    result = cleanup.run()
    assert result["removed_assets"] == 1
    assert result["removed_files"] == 1
    assert not thumb.exists()
    assert db.list_folders() == []


def test_stream_download_writes_file_by_chunks(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())

    class FakeResponse:
        def raise_for_status(self) -> None:
            return

        def iter_content(self, chunk_size: int):
            assert chunk_size == 1024 * 512
            yield b"hello "
            yield b"world"

        def close(self) -> None:
            return

    def fake_get(url, headers, timeout, stream):
        assert stream is True
        return FakeResponse()

    monkeypatch.setattr("app.services.puller.requests.get", fake_get)
    target = tmp_path / "data" / "images" / "demo" / "file.jpg"
    changed = manager._download_if_missing("https://example.com/file.jpg", target, {"User-Agent": "x"})
    assert changed is True
    assert target.read_bytes() == b"hello world"


def test_review_download_failure_restores_pending_status(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    db.upsert_review_item(
        "top-1",
        "src-1",
        "20250101_测试",
        "测试动态",
        ["命中文案关键词: 推广"],
        {
            "top_item": {},
            "source_item": {},
            "top_dynamic_id": "top-1",
            "source_dynamic_id": "src-1",
            "pub_ts": 1,
            "text": "测试动态",
            "pictures": [],
            "live_assets": [],
        },
    )
    review_item = db.list_review_items()[0]

    def fake_download(candidate, settings, cookie):
        raise RuntimeError("download failed")

    monkeypatch.setattr(manager, "_download_candidate", fake_download)
    manager._run_review_download(int(review_item["id"]))
    assert db.get_review_item(int(review_item["id"]))["status"] == "pending"


def test_pull_download_failure_moves_candidate_to_review_and_continues(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    subscription = db.upsert_subscription("42", uname="测试UP", pull_images=True, image_min_count=1, pull_livephoto=False)
    settings = db.get_settings()
    stats = {
        "subscriptions": 0,
        "matched": 0,
        "downloaded_candidates": 0,
        "review_candidates": 0,
        "saved_files": 0,
        "force_reload": False,
        "added_items": [],
    }
    candidate = manager._candidate_from_payload(
        {
            "top_item": {"id_str": "top-1"},
            "source_item": {"id_str": "src-1"},
            "top_dynamic_id": "top-1",
            "source_dynamic_id": "src-1",
            "pub_ts": 1,
            "text": "测试动态",
            "subscription_uid": "42",
            "subscription_name": "测试UP",
            "pictures": [{"src": "https://example.com/a.jpg"}],
            "live_assets": [],
        }
    )

    monkeypatch.setattr(manager, "_iter_feed_pages", lambda host_uid, cookie: iter([(1, [{"id_str": "top-1"}])]))
    monkeypatch.setattr(manager, "_collect_candidates", lambda item, include_forwarded: [candidate])

    def fake_download(*args, **kwargs):
        raise ResourceDownloadError("https://example.com/a.jpg", "404 Client Error")

    monkeypatch.setattr(manager, "_download_candidate", fake_download)
    manager._execute_pull_for_subscription(subscription, settings, "SESSDATA=test", FilterEngine(settings), stats, False)

    review_items = db.list_review_items()
    assert len(review_items) == 1
    assert review_items[0]["top_dynamic_id"] == "top-1"
    assert "服务器资源失效" in review_items[0]["reasons_json"]
    assert stats["review_candidates"] == 1
    assert stats["downloaded_candidates"] == 0


def test_thumbnail_service_uses_bundled_ffmpeg_when_system_binary_missing(monkeypatch) -> None:
    service = ThumbnailService()
    monkeypatch.setattr("app.services.thumbnailer.shutil.which", lambda name: None)
    monkeypatch.setattr("app.services.thumbnailer.bundled_ffmpeg_exe", lambda: "/tmp/fake-ffmpeg")
    assert service._resolve_ffmpeg() == "/tmp/fake-ffmpeg"


def test_index_template_uses_local_alpine_bundle() -> None:
    root = Path(__file__).resolve().parents[1]
    template = root / "app" / "templates" / "index.html"
    bundle = root / "app" / "static" / "vendor" / "alpinejs.min.js"
    html = template.read_text(encoding="utf-8")

    assert bundle.exists()
    assert bundle.stat().st_size > 0
    assert '/static/vendor/alpinejs.min.js?v={{ app_version }}' in html
    assert "cdn.jsdelivr.net/npm/alpinejs" not in html


def test_qr_login_start_uses_browser_headers_and_saves_state(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    auth = BilibiliAuthService(db)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "url": "https://example.com/scan",
                    "qrcode_key": "qr-demo",
                },
            }

    class FakeSession:
        def __init__(self) -> None:
            self.headers = {}

        def get(self, url: str, timeout: int):
            assert "User-Agent" in self.headers
            assert self.headers["Referer"] == "https://passport.bilibili.com/login"
            assert url.endswith("/qrcode/generate")
            assert timeout == 20
            return FakeResponse()

    monkeypatch.setattr("app.services.bilibili.requests.Session", FakeSession)
    payload = auth.start_qr_login()
    state = db.get_auth_state()
    assert payload["status"] == "pending"
    assert payload["qr_key"] == "qr-demo"
    assert payload["image_data_url"].startswith("data:image/png;base64,")
    assert state["qr_key"] == "qr-demo"
    assert state["qr_status"] == "pending"


def test_gallery_indexes_rebuild_and_query_are_stable(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    indexer = MediaIndexer(db, storage, ThumbnailService())
    gallery = GalleryService(db, storage)

    db.upsert_folder(
        {
            "folder_name": "20250102_第二条",
            "title": "第二条动态",
            "text_prefix": "第二条",
            "pub_ts": 20,
            "pub_time": "1970-01-01 00:00:20",
            "top_dynamic_id": "top-2",
            "source_dynamic_id": "src-2",
            "subscription_uid": "200",
            "subscription_name": "UP-B",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        "20250102_第二条",
        "image",
        [
            {
                "pair_index": 1,
                "filename": "001__a.jpg",
                "rel_path": "data/images/20250102_第二条/001__a.jpg",
                "thumb_rel_path": "data/images/20250102_第二条/.thumbs/001__a.webp",
                "width": 800,
                "height": 600,
            },
            {
                "pair_index": 2,
                "filename": "002__b.jpg",
                "rel_path": "data/images/20250102_第二条/002__b.jpg",
                "thumb_rel_path": "data/images/20250102_第二条/.thumbs/002__b.webp",
                "width": 600,
                "height": 800,
            },
        ],
    )
    db.upsert_folder(
        {
            "folder_name": "20250101_第一条",
            "title": "第一条动态",
            "text_prefix": "第一条",
            "pub_ts": 10,
            "pub_time": "1970-01-01 00:00:10",
            "top_dynamic_id": "top-1",
            "source_dynamic_id": "src-1",
            "subscription_uid": "100",
            "subscription_name": "UP-A",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        "20250101_第一条",
        "image",
        [
            {
                "pair_index": 1,
                "filename": "001__c.jpg",
                "rel_path": "data/images/20250101_第一条/001__c.jpg",
                "thumb_rel_path": "data/images/20250101_第一条/.thumbs/001__c.webp",
                "width": 1024,
                "height": 768,
            }
        ],
    )

    assert db.gallery_index_ready() is False
    indexer.rebuild_gallery_indexes()
    assert db.gallery_index_ready() is True

    folders = gallery.get_gallery_items(view_mode="folder", sort_order="desc", page_size=10)
    assert [item["folder_name"] for item in folders["items"]] == ["20250102_第二条", "20250101_第一条"]
    assert folders["cache_hit"] is False

    cached_folders = gallery.get_gallery_items(view_mode="folder", sort_order="desc", page_size=10)
    assert cached_folders["cache_hit"] is True
    assert [item["folder_name"] for item in cached_folders["items"]] == ["20250102_第二条", "20250101_第一条"]

    db.set_folder_favorite("20250102_第二条", True)
    refreshed_folders = gallery.get_gallery_items(view_mode="folder", sort_order="desc", page_size=10)
    assert refreshed_folders["cache_hit"] is False
    assert refreshed_folders["items"][0]["is_favorite"] is True

    pairs = gallery.get_gallery_items(view_mode="pair", sort_order="desc", page_size=10)
    assert [item["item_key"] for item in pairs["items"]] == [
        "20250102_第二条::1",
        "20250102_第二条::2",
        "20250101_第一条::1",
    ]


def test_gallery_source_kind_filters_up_and_site_sources(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    indexer = MediaIndexer(db, storage, ThumbnailService())
    gallery = GalleryService(db, storage)

    folders = [
        {
            "folder_name": "20250103_UP收藏",
            "title": "UP收藏",
            "text_prefix": "UP收藏",
            "pub_ts": 30,
            "pub_time": "1970-01-01 00:00:30",
            "top_dynamic_id": "top-up",
            "source_dynamic_id": "src-up",
            "subscription_uid": "300",
            "subscription_name": "UP-C",
            "has_images": True,
            "has_livephoto": False,
            "is_favorite": True,
        },
        {
            "folder_name": "20250102_站点图片",
            "title": "站点图片",
            "text_prefix": "站点图",
            "pub_ts": 20,
            "pub_time": "1970-01-01 00:00:20",
            "top_dynamic_id": "top-site",
            "source_dynamic_id": "src-site",
            "subscription_uid": "site:9",
            "subscription_name": "站点来源",
            "has_images": True,
            "has_livephoto": False,
        },
        {
            "folder_name": "20250101_旧数据",
            "title": "旧数据",
            "text_prefix": "旧数据",
            "pub_ts": 10,
            "pub_time": "1970-01-01 00:00:10",
            "top_dynamic_id": "top-legacy",
            "source_dynamic_id": "src-legacy",
            "has_images": True,
            "has_livephoto": False,
        },
    ]
    for folder in folders:
        db.upsert_folder(folder)
        db.replace_folder_assets(
            folder["folder_name"],
            "image",
            [
                {
                    "pair_index": 1,
                    "filename": "001__source.jpg",
                    "rel_path": f"data/images/{folder['folder_name']}/001__source.jpg",
                    "thumb_rel_path": f"data/images/{folder['folder_name']}/.thumbs/001__source.webp",
                    "width": 800,
                    "height": 600,
                }
            ],
        )

    fallback_site = gallery.get_gallery_items(source_kind="site", page_size=10)
    fallback_up = gallery.get_gallery_items(source_kind="up", page_size=10)
    assert [item["folder_name"] for item in fallback_site["items"]] == ["20250102_站点图片"]
    assert [item["folder_name"] for item in fallback_up["items"]] == ["20250103_UP收藏", "20250101_旧数据"]
    assert gallery.get_gallery_items(source_kind="invalid", page_size=10)["total"] == 3

    indexer.rebuild_gallery_indexes()

    assert gallery.get_gallery_items(source_kind="all", page_size=10)["total"] == 3
    site_folders = gallery.get_gallery_items(source_kind="site", page_size=10)
    up_folders = gallery.get_gallery_items(source_kind="up", page_size=10)
    favorite_up = gallery.get_gallery_items(category="favorites", source_kind="up", page_size=10)
    site_pairs = gallery.get_gallery_items(source_kind="site", view_mode="pair", page_size=10)
    precise_subscription = gallery.get_gallery_items(
        source_kind="up",
        subscription_uids=["site:9"],
        page_size=10,
    )

    assert [item["folder_name"] for item in site_folders["items"]] == ["20250102_站点图片"]
    assert [item["folder_name"] for item in up_folders["items"]] == ["20250103_UP收藏", "20250101_旧数据"]
    assert [item["folder_name"] for item in favorite_up["items"]] == ["20250103_UP收藏"]
    assert [item["folder_name"] for item in site_pairs["items"]] == ["20250102_站点图片"]
    assert [item["folder_name"] for item in precise_subscription["items"]] == ["20250102_站点图片"]


def test_gallery_index_favorite_and_meta_follow_index_rows(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    indexer = MediaIndexer(db, storage, ThumbnailService())
    gallery = GalleryService(db, storage)

    db.upsert_folder(
        {
            "folder_name": "20250103_收藏测试",
            "title": "收藏测试",
            "text_prefix": "收藏测",
            "pub_ts": 30,
            "pub_time": "1970-01-01 00:00:30",
            "top_dynamic_id": "top-3",
            "source_dynamic_id": "src-3",
            "subscription_uid": "300",
            "subscription_name": "UP-C",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        "20250103_收藏测试",
        "image",
        [
            {
                "pair_index": 1,
                "filename": "001__fav.jpg",
                "rel_path": "data/images/20250103_收藏测试/001__fav.jpg",
                "thumb_rel_path": "data/images/20250103_收藏测试/.thumbs/001__fav.webp",
                "width": 900,
                "height": 900,
            }
        ],
    )
    indexer.rebuild_gallery_indexes()
    db.set_folder_favorite("20250103_收藏测试", True)

    favorites = gallery.get_gallery_items(category="favorites", view_mode="folder", page_size=10)
    assert favorites["total"] == 1
    assert favorites["items"][0]["is_favorite"] is True

    pair_view = gallery.get_gallery_items(category="favorites", view_mode="pair", page_size=10)
    assert pair_view["total"] == 1
    assert pair_view["items"][0]["is_favorite"] is True

    meta = gallery.get_gallery_meta()
    assert meta["counts"]["favorites"] == 1


def test_qr_poll_persists_cookie_from_poll_response(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    db.update_auth_state(qr_key="qr-demo", qr_status="pending")
    auth = BilibiliAuthService(db)

    class FakeResponse:
        cookies = {"SESSDATA": "sess-from-poll"}

        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "code": 0,
                    "url": "https://passport.bilibili.com/crossDomain?bili_jct=csrf-token&DedeUserID=123",
                    "message": "0",
                },
            }

    class FakeSession:
        def __init__(self) -> None:
            self.headers = {}

        def get(self, url: str, params=None, timeout: int = 20):
            assert url.endswith("/qrcode/poll")
            assert params == {"qrcode_key": "qr-demo"}
            return FakeResponse()

    monkeypatch.setattr("app.services.bilibili.requests.Session", FakeSession)
    monkeypatch.setattr(auth, "check_cookie", lambda: {"ok": True, "message": "Cookie 有效"})
    monkeypatch.setattr(auth, "_exchange_login", lambda login_url: {})

    payload = auth.poll_qr_login()
    state = db.get_auth_state()

    assert payload["status"] == "done"
    assert state["qr_status"] == "done"
    assert state["cookie"]
    assert "SESSDATA=sess-from-poll" in state["cookie"]
    assert "bili_jct=csrf-token" in state["cookie"]
    assert "DedeUserID=123" in state["cookie"]


def test_gallery_card_uses_internal_assets_for_collage(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    folder = config.images_dir / "20250101_测试"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1, 4):
        path = folder / f"{index:02d}.jpg"
        path.write_bytes(b"fake-image")
    db.upsert_folder(
        {
            "folder_name": "20250101_测试",
            "title": "测试动态",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        "20250101_测试",
        "image",
        [
            {
                "pair_index": index,
                "filename": f"{index:02d}.jpg",
                "rel_path": f"data/images/20250101_测试/{index:02d}.jpg",
                "thumb_rel_path": f"data/images/20250101_测试/.thumbs/{index:02d}.webp",
            }
            for index in range(1, 4)
        ],
    )

    service = GalleryService(db, storage)
    card = service.get_gallery_items()["items"][0]

    assert len(card["preview_tiles"]) == 3
    assert card["asset_count"] == 3


def test_gallery_pair_view_flattens_assets_for_image_mode(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    folder_name = "20250101_测试"
    folder = config.images_dir / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1, 3):
        path = folder / f"{index:02d}.jpg"
        path.write_bytes(b"fake-image")
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": "测试动态",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
            "has_images": True,
            "has_livephoto": True,
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
            },
            {
                "pair_index": 2,
                "filename": "02.jpg",
                "rel_path": f"data/images/{folder_name}/02.jpg",
                "thumb_rel_path": f"data/images/{folder_name}/.thumbs/02.webp",
            },
        ],
    )
    db.replace_folder_assets(
        folder_name,
        "livephoto",
        [
            {
                "pair_index": 1,
                "filename": "01.mp4",
                "rel_path": f"data/livephoto/{folder_name}/01.mp4",
                "cover_rel_path": f"data/livephoto/{folder_name}/.thumbs/01.webp",
                "reverse_rel_path": f"data/livephoto/{folder_name}/.thumbs/01-reverse.mp4",
            }
        ],
    )

    service = GalleryService(db, storage)
    result = service.get_gallery_items(view_mode="pair")

    assert result["view_mode"] == "pair"
    assert len(result["items"]) == 2
    assert result["items"][0]["item_key"] == f"{folder_name}::1"
    assert result["items"][0]["has_livephoto"] is True
    assert result["items"][1]["has_images"] is True


def test_full_reload_setting_is_consumed_after_pull(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    db.save_settings({"reload_all_once": True})
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())

    monkeypatch.setattr(
        manager,
        "_execute_pull_subscription_with_retry",
        lambda subscription, settings, cookie, filter_engine, stats, force_reload: None,
    )

    stats = manager._execute_pull()

    assert stats["force_reload"] is True
    assert db.get_settings()["reload_all_once"] is False


def test_move_to_trash_blacklists_and_removes_folder(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    folder_name = "20250101_测试"
    image_folder = config.images_dir / folder_name
    image_folder.mkdir(parents=True, exist_ok=True)
    (image_folder / "01.jpg").write_bytes(b"image")
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": "测试动态",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
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
            }
        ],
    )
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())

    result = manager.move_to_trash(folder_name)

    assert result["ok"] is True
    assert result["sidebar_counts"]["counts"]["all"] == 0
    assert result["sidebar_counts"]["counts"]["trash"] == 1
    assert db.is_blacklisted("top", "src") is True
    assert db.list_trash_items()[0]["folder_name"] == folder_name
    assert not image_folder.exists()
    assert db.list_folders() == []


def test_delete_pair_refreshes_sidebar_count_cache(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    folder_name = "20250101_测试"
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": "测试动态",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        folder_name,
        "image",
        [
            {"pair_index": 1, "filename": "01.jpg", "rel_path": f"data/images/{folder_name}/01.jpg"},
        ],
    )
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())

    result = manager.delete_pair(folder_name, 1)
    cached = db.get_sidebar_count_cache()["counts"]

    assert result["ok"] is True
    assert result["remove_empty_folder"] is True
    assert result["sidebar_counts"]["counts"]["all"] == 0
    assert cached["all"] == 0


def test_cleanup_duplicate_pairs_keeps_post_when_all_images_are_removed(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    folder_name = "20250101_保留贴文"
    db.upsert_folder(
        {
            "folder_name": folder_name,
            "title": "保留贴文",
            "text_prefix": "测试",
            "pub_ts": 1,
            "pub_time": "1970-01-01 00:00:01",
            "top_dynamic_id": "top",
            "source_dynamic_id": "src",
            "has_images": True,
            "has_livephoto": False,
        }
    )
    db.replace_folder_assets(
        folder_name,
        "image",
        [
            {"pair_index": 1, "filename": "01.jpg", "rel_path": f"data/images/{folder_name}/01.jpg"},
        ],
    )
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())

    result = manager.cleanup_duplicate_pairs([{"folder_name": folder_name, "pair_index": 1}])

    assert result["removed"] == [{"folder_name": folder_name, "pair_index": 1}]
    assert db.get_folder(folder_name) is not None
    assert db.list_assets_for_folder(folder_name) == []
    assert db.get_folder(folder_name)["has_images"] == 0


def test_duplicate_deletions_enqueue_independently_while_another_task_is_running(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    manager.attach_duplicate_service(DummyDuplicateService())
    manager._lock.acquire()
    try:
        trash_result = manager.start_duplicate_trash("group-a", "folder-a")
        cleanup_result = manager.start_duplicate_cleanup(
            "group-b",
            ["folder-b", "folder-c"],
            [{"folder_name": "folder-c", "pair_index": 1}],
        )
        queue = manager.status()["queue"]
    finally:
        manager._lock.release()

    assert trash_result["queued"] is True
    assert cleanup_result["queued"] is True
    assert [item["kind"] for item in queue] == ["duplicate-trash", "duplicate-cleanup"]
    assert queue[0]["payload"]["args"] == ["group-a", "folder-a"]
    assert queue[1]["payload"]["args"][0] == "group-b"


def test_startup_sync_reuses_persistent_storage_stats_cache(tmp_path: Path, monkeypatch) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    cached_stats = {
        "image_bytes": 1024,
        "thumbnail_bytes": 256,
        "trash_bytes": 0,
        "image_files": 10,
        "thumbnail_files": 20,
        "trash_files": 0,
        "updated_at": "2026-08-04T00:00:00+08:00",
    }
    db.set_storage_stats_cache(cached_stats)
    monkeypatch.setattr(db, "list_folders", lambda: [{"folder_name": "cached-folder"}])
    monkeypatch.setattr(db, "gallery_index_needs_rebuild", lambda: False)
    monkeypatch.setattr(db, "gallery_index_status", lambda: {"stale": False})

    def fail_if_scanned(_trash_items) -> dict[str, int]:
        raise AssertionError("启动时不应再次扫描存储目录")

    monkeypatch.setattr(storage, "storage_usage_stats", fail_if_scanned)
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    manager._lock.acquire()

    manager._run_startup_sync()

    assert manager.status()["running"] is False
    assert manager.status()["stats"]["storage_stats"] == cached_stats


def test_reject_review_moves_item_to_trash_and_blacklist(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    db.upsert_review_item(
        "top-2",
        "src-2",
        "20250101_测试动态",
        "测试动态",
        ["命中推广关键词"],
        {
            "top_item": {},
            "source_item": {},
            "top_dynamic_id": "top-2",
            "source_dynamic_id": "src-2",
            "pub_ts": 1,
            "text": "测试动态",
            "pictures": [{"src": "https://i0.hdslb.com/a.jpg"}],
            "live_assets": [{"live_url": "https://i0.hdslb.com/a.mp4"}],
        },
    )
    review_item = db.list_review_items()[0]

    result = manager.reject_review_item(int(review_item["id"]))

    assert result["ok"] is True
    assert db.get_review_item(int(review_item["id"]))["status"] == "rejected"
    trash_item = db.list_trash_items()[0]
    assert trash_item["folder_name"] == "20250101_测试动态"
    assert db.is_blacklisted("top-2", "src-2") is True


def test_pair_plan_prefers_cover_match_for_livephoto(tmp_path: Path) -> None:
    config = DummyConfig(tmp_path)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    manager = PullManager(db, storage, DummyIndexer(), DummyCleanup(), DummyAuth(), DummyLegacyImporter())
    candidate = manager._candidate_from_payload(
        {
            "top_item": {},
            "source_item": {},
            "top_dynamic_id": "top-3",
            "source_dynamic_id": "src-3",
            "pub_ts": 1,
            "text": "测试动态",
            "pictures": [
                {"src": "https://img.example.com/1.jpg?x=1"},
                {"src": "https://img.example.com/2.jpg?x=1"},
            ],
            "live_assets": [
                {
                    "live_url": "https://video.example.com/a.mp4?token=1",
                    "cover_url": "https://img.example.com/2.jpg?token=2",
                },
                {
                    "live_url": "https://video.example.com/b.mp4?token=1",
                    "cover_url": "",
                },
            ],
        }
    )

    pair_plan = manager._pair_plan(candidate)

    assert pair_plan["picture_indices"]["https://img.example.com/1.jpg"] == 1
    assert pair_plan["picture_indices"]["https://img.example.com/2.jpg"] == 2
    assert pair_plan["live_indices"]["https://video.example.com/a.mp4"] == 2
    assert pair_plan["live_indices"]["https://video.example.com/b.mp4"] == 3
