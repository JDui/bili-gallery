import threading
import time
from pathlib import Path

from app.config import AppConfig
from app.db import Database
from app.services.gallery import GalleryService
from app.services.puller import PullManager
from app.services.site_downloader import MediaDownloader
from app.services.site_parser import PageFetcher, SourceParser, site_request_timeout
from app.services.site_syncer import SiteSyncManager
from app.services.storage import StorageService
from app.services.utils import clean_filename, parse_date
from fastapi.testclient import TestClient


def fixture_url(name: str) -> str:
    return Path(__file__).parent.joinpath("site_fixtures", name).resolve().as_uri()


def make_app(tmp_path: Path) -> tuple[Database, StorageService, SiteSyncManager]:
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
    return db, storage, SiteSyncManager(db, storage)


def html_source() -> dict:
    return {
        "source_type": "html",
        "entry_url": fixture_url("index.html"),
        "max_pages": 1,
        "list_item_selector": ".post-card",
        "detail_link_selector": ".detail-link",
        "title_selector": "h1",
        "date_selector": "time",
        "tag_selector": ".tag",
        "body_selector": ".body",
        "media_selector": ".content img, .content video source",
    }


def create_fixture_source(db: Database) -> dict:
    return db.create_site_source(
        {
            "name": "Fixture",
            "slug": "fixture",
            **html_source(),
            "enabled": True,
        }
    )


def create_skip_source(db: Database, skip_head: int, skip_tail: int) -> dict:
    return db.create_site_source(
        {
            "name": "Skip Fixture",
            "slug": f"skip-fixture-{skip_head}-{skip_tail}",
            "source_type": "html",
            "entry_url": fixture_url("skip_index.html"),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "title_selector": "h1",
            "date_selector": "time",
            "tag_selector": ".tag",
            "body_selector": ".body",
            "media_selector": ".content img, .content video source",
            "skip_head_images": skip_head,
            "skip_tail_images": skip_tail,
            "enabled": True,
        }
    )


def test_site_requests_use_browser_like_headers() -> None:
    fetcher = PageFetcher(user_agent="Custom UA")
    downloader = MediaDownloader(user_agent="Custom UA")
    assert site_request_timeout(300) == (20.0, 300.0)
    assert PageFetcher(timeout=60).timeout == (10.0, 60.0)
    assert MediaDownloader(timeout=300).timeout == (20.0, 300.0)
    for session in (fetcher.session, downloader.session):
        assert session.headers["User-Agent"] == "Custom UA"
        assert session.headers["Accept"] == "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        assert session.headers["Accept-Language"] == "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6"
        assert session.headers["Connection"] == "close"


def test_site_parser_extracts_html_rss_and_paged_preview() -> None:
    parser = SourceParser(PageFetcher())
    posts = parser.discover(html_source())
    assert len(posts) == 2
    assert posts[0].title == "Allowed Spring Post"
    assert posts[0].pub_date == "2026-04-01"
    assert [asset.media_type for asset in posts[0].assets] == ["image", "video"]

    rss_posts = parser.discover({"source_type": "rss", "entry_url": fixture_url("feed.xml")})
    assert len(rss_posts) == 1
    assert rss_posts[0].title == "Feed Post"
    assert rss_posts[0].tags == ["feed"]

    paged = {
        **html_source(),
        "entry_url": fixture_url("paged1.html"),
        "page_url_template": f"file://{Path(__file__).parent.joinpath('site_fixtures').resolve()}/paged{{page}}.html",
        "max_pages": 2,
        "media_selector": ".content img",
    }
    assert [post.title for post in parser.preview(paged, limit=3)] == ["Allowed Spring Post", "Old Post", "Third Post"]


def test_site_sync_downloads_allowed_posts_and_is_idempotent(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)

    first = syncer._sync_source(source)
    second = syncer._sync_source(source)
    posts = db.list_site_posts()
    logs = db.list_site_filter_logs()
    assets = db.list_site_assets(posts[0]["id"])
    gallery = GalleryService(db, storage)
    gallery_items = gallery.get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])
    gallery_detail = gallery.get_folder_detail(gallery_items["items"][0]["folder_name"])

    assert first["posts"] == 1
    assert first["downloaded"] == 2
    assert second["downloaded"] == 0
    assert len(posts) == 1
    assert posts[0]["downloaded_count"] == 2
    assert all(asset["status"] == "ready" for asset in assets)
    assert gallery_items["total"] == 1
    assert gallery_items["items"][0]["subscription_uid"] == f"site:{source['id']}"
    assert gallery_items["items"][0]["subscription_name"] == "Fixture"
    assert gallery_detail and len(gallery_detail["videos"]) == 1
    assert any(log["reason"] == "早于起始日期" for log in logs)


def test_site_sync_uses_main_task_queue_when_busy(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)
    puller = PullManager(db, storage, None, None, None, None)
    puller.attach_site_syncer(syncer)
    syncer.bind_task_queue(puller)

    puller._lock.acquire()
    try:
        result = syncer.start_sync(source["id"])
        assert result["queued"] is True
        status = puller.status()
        assert status["queue"][0]["kind"] == "site-sync"
        assert status["queue"][0]["payload"]["args"] == [source["id"]]
        assert puller.cancel_queued(status["queue"][0]["queue_id"])["ok"] is True
    finally:
        puller._lock.release()


def test_site_favorite_block_and_source_import_export(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)
    syncer._sync_source(source)
    post = db.list_site_posts()[0]

    db.set_site_post_flag(post["id"], "is_favorite", True)
    assert len(db.list_site_posts(category="favorites")) == 1

    db.set_site_post_flag(post["id"], "is_blocked", True)
    assert len(db.list_site_posts(category="all")) == 0
    assert len(db.list_site_posts(category="blocked")) == 1

    exported = db.export_site_sources()
    result = db.import_site_sources(
        {
            "version": 1,
            "sources": [
                {**exported["sources"][0], "name": "Updated Fixture", "skip_head_images": 2},
                {**exported["sources"][0], "name": "Imported Fixture", "slug": "imported-fixture"},
            ],
        }
    )
    assert result["created"] == 1
    assert result["updated"] == 1
    assert db.get_site_source(source["id"])["name"] == "Updated Fixture"


def test_site_sync_skips_head_and_tail_images_but_keeps_video(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    source = create_skip_source(db, 1, 2)

    result = syncer._sync_source(source)
    post = db.list_site_posts()[0]
    assets = db.list_site_assets(post["id"])

    assert result["downloaded"] == 3
    assert [asset["media_type"] for asset in assets] == ["image", "video", "image"]
    assert [asset["url"].rsplit("/", 1)[-1] for asset in assets] == ["img2.jpg", "clip.mp4", "img3.jpg"]


def test_site_sync_downloads_media_with_three_workers(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    db.save_settings({"site_request_sleep": 0})
    source = create_skip_source(db, 0, 0)

    class TrackingDownloader:
        active = 0
        max_active = 0
        lock = threading.Lock()

        def download(self, url: str, target: Path) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.lock:
                self.__class__.active += 1
                self.__class__.max_active = max(self.__class__.max_active, self.__class__.active)
            try:
                time.sleep(0.05)
                target.write_bytes(url.encode("utf-8"))
            finally:
                with self.lock:
                    self.__class__.active -= 1

    monkeypatch.setattr(syncer, "_new_media_downloader", lambda settings: TrackingDownloader())

    result = syncer._sync_source(source)

    assert result["downloaded"] == 6
    assert TrackingDownloader.max_active == 3


def test_site_helpers_parse_date_and_filename() -> None:
    assert parse_date("2026.04.01").isoformat() == "2026-04-01"
    assert clean_filename("https://example.test/a/b/photo.webp?x=1", "Hello / 世界", 2, "image") == "002-hello-世界.webp"


def test_site_api_source_preview_sync_and_post_actions(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    db, storage, syncer = make_app(tmp_path)
    def sync_now(source_id: int | None = None) -> dict:
        source = db.get_site_source(source_id) if source_id else None
        if source:
            syncer._sync_source(source)
        return {"ok": True, "queued": False, "message": "已开始站点同步"}

    monkeypatch.setattr(syncer, "start_sync", sync_now)
    monkeypatch.setattr(app_main, "db", db)
    monkeypatch.setattr(app_main, "storage", storage)
    monkeypatch.setattr(app_main, "site_syncer", syncer)
    monkeypatch.setattr(app_main, "gallery", GalleryService(db, storage))
    client = TestClient(app_main.app)

    source_payload = {
        "name": "Fixture API",
        "slug": "fixture-api",
        **html_source(),
        "enabled": True,
    }
    created = client.post("/api/site-sources", json=source_payload).json()["item"]
    assert created["id"] > 0

    preview = client.post("/api/site-sources/test", json=source_payload).json()["items"]
    assert len(preview) == 2

    export_payload = client.get("/api/site-sources/export").json()
    import_result = client.post(
        "/api/site-sources/import",
        json={"version": 1, "sources": [{**export_payload["sources"][0], "name": "Fixture API Updated"}]},
    ).json()
    assert import_result["updated"] == 1

    assert client.post(f"/api/site-sources/{created['id']}/sync").json()["ok"] is True

    posts = client.get("/api/site-posts").json()["items"]
    assert len(posts) == 1
    post_id = posts[0]["id"]
    assert client.get(f"/api/site-posts/{post_id}").json()["assets"][0]["url_local"].startswith("/storage/")
    gallery_items = client.get(f"/api/gallery/items?subscription_uids=site:{created['id']}").json()["items"]
    assert len(gallery_items) == 1
    assert gallery_items[0]["subscription_uid"] == f"site:{created['id']}"

    favorite = client.post(f"/api/site-posts/{post_id}/favorite", json={"favorite": True}).json()["item"]
    assert favorite["is_favorite"] is True

    blocked = client.post(f"/api/site-posts/{post_id}/block", json={"blocked": True}).json()["item"]
    assert blocked["is_blocked"] is True

    rules = client.put("/api/site-rules", json={"title_block": ["测试"], "use_regex": False}).json()
    assert rules["title_block"] == ["测试"]

    assert client.get("/api/site-filter/logs").json()["items"]
    log_clear = client.post("/api/site-filter/logs/clear").json()
    assert log_clear["ok"] is True
    assert log_clear["removed"] > 0
    assert client.get("/api/site-filter/logs").json()["items"] == []
    db.add_site_filter_log(created["id"], "https://example.test/again", "Again", "allowed", "重新生成")
    clear_result = client.post(f"/api/site-sources/{created['id']}/clear-delete").json()
    assert clear_result["ok"] is True
    assert clear_result["folders"] == 1
    assert db.get_site_source(created["id"]) is None
    assert db.list_site_posts() == []
    assert db.list_site_filter_logs() == []
    assert db.list_folders() == []
    assert not any(storage.config.images_dir.iterdir())
    assert not (storage.config.data_dir / "sites" / "fixture-api").exists()
