import threading
import time
from types import SimpleNamespace
from pathlib import Path

from app.config import AppConfig
from app.db import Database
from app.services.cleanup import CleanupService
from app.services.gallery import GalleryService
from app.services.media_indexer import MediaIndexer
from app.services.puller import PullManager
from app.services.site_downloader import MediaDownloader
from app.services.site_parser import PageFetcher, SourceParser, site_request_timeout
from app.services.site_syncer import SiteSyncManager
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import clean_filename, parse_date
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw


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


def create_duplicate_source(db: Database, tmp_path: Path) -> dict:
    site_dir = tmp_path / "fixture-site"
    site_dir.mkdir()
    same = Image.new("RGB", (32, 32), (220, 220, 220))
    draw = ImageDraw.Draw(same)
    draw.rectangle((4, 4, 18, 18), fill=(40, 40, 40))
    draw.rectangle((20, 20, 28, 28), fill=(120, 120, 120))
    same.save(site_dir / "same-a.jpg")
    same.save(site_dir / "same-b.jpg")
    unique = Image.new("RGB", (32, 32), (220, 220, 220))
    draw = ImageDraw.Draw(unique)
    draw.rectangle((14, 4, 28, 18), fill=(40, 40, 40))
    draw.rectangle((4, 20, 12, 28), fill=(120, 120, 120))
    unique.save(site_dir / "unique.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <article class="post-card"><a class="detail-link" href="post.html">Post</a></article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Duplicate Images Post</h1>
          <time datetime="2026-04-02">2026.04.02</time>
          <p class="body">Duplicate image cleanup.</p>
          <img src="same-a.jpg">
          <img src="same-b.jpg">
          <img src="unique.jpg">
        </article>
        """,
        encoding="utf-8",
    )
    return db.create_site_source(
        {
            "name": "Duplicate Fixture",
            "slug": "duplicate-fixture",
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "title_selector": "h1",
            "date_selector": "time",
            "body_selector": ".body",
            "media_selector": ".content img",
            "enabled": True,
        }
    )


def create_single_image_source(db: Database, tmp_path: Path) -> dict:
    site_dir = tmp_path / "single-image-site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <article class="post-card"><a class="detail-link" href="post.html">Post</a></article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Single Image Post</h1>
          <time datetime="2026-04-06">2026.04.06</time>
          <p class="body">Single image retry fixture.</p>
          <img src="retry.jpg">
        </article>
        """,
        encoding="utf-8",
    )
    return db.create_site_source(
        {
            "name": "Single Image Fixture",
            "slug": "single-image-fixture",
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "title_selector": "h1",
            "date_selector": "time",
            "body_selector": ".body",
            "media_selector": ".content img",
            "enabled": True,
        }
    )


def create_incremental_source(db: Database, tmp_path: Path) -> dict:
    site_dir = tmp_path / "incremental-site"
    site_dir.mkdir()
    for name, color in (("older.jpg", (180, 20, 20)), ("newer.jpg", (20, 180, 20))):
        Image.new("RGB", (32, 32), color).save(site_dir / name)
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <article class="post-card"><a class="detail-link" href="newer.html">Newer</a></article>
        <article class="post-card"><a class="detail-link" href="older.html">Older</a></article>
        """,
        encoding="utf-8",
    )
    (site_dir / "newer.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Newer Same Day</h1>
          <time datetime="2026-04-05">2026.04.05</time>
          <p class="body">Newer same-day post.</p>
          <img src="newer.jpg">
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "older.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Older Previous Day</h1>
          <time datetime="2026-04-04">2026.04.04</time>
          <p class="body">Older previous-day post.</p>
          <img src="older.jpg">
        </article>
        """,
        encoding="utf-8",
    )
    return db.create_site_source(
        {
            "name": "Incremental Fixture",
            "slug": "incremental-fixture",
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "title_selector": "h1",
            "date_selector": "time",
            "body_selector": ".body",
            "media_selector": ".content img",
            "enabled": True,
        }
    )


def test_site_requests_use_browser_like_headers() -> None:
    fetcher = PageFetcher(user_agent="Custom UA")
    downloader = MediaDownloader(user_agent="Custom UA")
    proxied_fetcher = PageFetcher(user_agent="Custom UA", proxies={"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})
    proxied_downloader = MediaDownloader(user_agent="Custom UA", proxies={"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})
    assert site_request_timeout(300) == (20.0, 300.0)
    assert PageFetcher(timeout=60).timeout == (10.0, 60.0)
    assert MediaDownloader(timeout=300).timeout == (20.0, 300.0)
    for session in (fetcher.session, downloader.session):
        assert session.headers["User-Agent"] == "Custom UA"
        assert session.headers["Accept"] == "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        assert session.headers["Accept-Language"] == "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6"
        assert session.headers["Connection"] == "close"
    assert proxied_fetcher.session.proxies["http"] == "http://127.0.0.1:7890"
    assert proxied_downloader.session.proxies["https"] == "http://127.0.0.1:7890"


def test_gallery_thumbnails_use_576_and_258_short_edge_and_rebuild_cleans_old_derivatives(tmp_path: Path) -> None:
    db, storage, _syncer = make_app(tmp_path)
    image_folder = storage.image_folder("thumb-demo")
    image_folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1600, 1200), (180, 20, 20)).save(image_folder / "001__demo.jpg")
    indexer = MediaIndexer(db, storage, ThumbnailService())
    indexer.index_folder("thumb-demo", 1, "Thumb Demo", "", "top", "source")
    old_marker = image_folder / ".thumbs" / "old-720.webp"
    old_small_marker = image_folder / ".thumbs" / "small" / "old-360.webp"
    old_marker.write_bytes(b"old")
    old_small_marker.write_bytes(b"old")

    indexer.rebuild_gallery_indexes()
    asset = db.list_assets_for_folder("thumb-demo")[0]
    thumb = storage.resolve_storage_path(asset["thumb_rel_path"])
    small = storage.resolve_storage_path(asset["small_thumb_rel_path"])

    assert not old_marker.exists()
    assert not old_small_marker.exists()
    with Image.open(thumb) as image:
        assert min(image.size) == 576
    with Image.open(small) as image:
        assert min(image.size) == 258
    Image.new("RGB", (640, 480), (20, 20, 180)).save(thumb, format="WEBP")
    Image.new("RGB", (320, 240), (20, 20, 180)).save(small, format="WEBP")
    indexer.refresh_gallery_index("thumb-demo")
    with Image.open(thumb) as image:
        assert min(image.size) == 576
    with Image.open(small) as image:
        assert min(image.size) == 258
    detail = GalleryService(db, storage).get_folder_detail("thumb-demo")
    assert "/.thumbs/small/" in detail["pairs"][0]["preview_url"]


def test_site_sync_uses_configured_page_timeout(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    db.save_settings({"site_request_timeout": 480})
    source = create_fixture_source(db)
    captured: list[int] = []

    class CaptureFetcher(PageFetcher):
        def __init__(self, timeout: int = 300, user_agent: str = "", proxies=None) -> None:
            captured.append(timeout)
            super().__init__(timeout=timeout, user_agent=user_agent, proxies=proxies)

    monkeypatch.setattr("app.services.site_syncer.PageFetcher", CaptureFetcher)

    syncer.test_source(source)
    syncer._sync_source(source)

    assert captured == [480, 480]


def test_site_sync_uses_configured_proxy_for_page_and_media(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    db.save_settings({"site_proxy_enabled": True, "site_proxy_host": "127.0.0.1", "site_proxy_port": 7890})
    source = create_fixture_source(db)
    captured_fetcher: list[dict[str, str]] = []
    captured_downloader: list[dict[str, str]] = []

    class CaptureFetcher(PageFetcher):
        def __init__(self, timeout: int = 300, user_agent: str = "", proxies=None) -> None:
            super().__init__(timeout=timeout, user_agent=user_agent, proxies=proxies)
            captured_fetcher.append(dict(self.session.proxies))

    class CaptureDownloader(MediaDownloader):
        def __init__(self, timeout: int = 300, user_agent: str = "", proxies=None) -> None:
            super().__init__(timeout=timeout, user_agent=user_agent, proxies=proxies)
            captured_downloader.append(dict(self.session.proxies))

    monkeypatch.setattr("app.services.site_syncer.PageFetcher", CaptureFetcher)
    monkeypatch.setattr("app.services.site_syncer.MediaDownloader", CaptureDownloader)

    syncer._sync_source(source)

    assert captured_fetcher[0]["http"] == "http://127.0.0.1:7890"
    assert captured_downloader[0]["https"] == "http://127.0.0.1:7890"


def test_site_sync_records_source_errors_without_failing_entire_task(tmp_path: Path, monkeypatch) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)

    def fail_source(_source, cooperate=None):
        raise TimeoutError("读取超时")

    monkeypatch.setattr(syncer, "_sync_source", fail_source)

    result = syncer.execute_sync(source["id"])
    logs = db.list_site_filter_logs()

    assert result["sources"] == 1
    assert result["errors"] == 1
    assert logs[0]["decision"] == "error"
    assert "读取超时" in logs[0]["reason"]


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
    assert gallery_detail["folder"]["original_url"] == fixture_url("post1.html")
    assert gallery_detail and len(gallery_detail["videos"]) == 1
    assert any(log["reason"] == "早于起始日期" for log in logs)


def test_site_sync_dedupes_images_with_same_content(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_duplicate_source(db, tmp_path)

    result = syncer._sync_source(source)
    post = db.list_site_posts()[0]
    assets = db.list_site_assets(post["id"])
    gallery = GalleryService(db, storage)
    gallery_items = gallery.get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])
    detail = gallery.get_folder_detail(gallery_items["items"][0]["folder_name"])

    assert result["downloaded"] == 3
    assert post["asset_count"] == 2
    assert post["downloaded_count"] == 2
    assert [asset["status"] for asset in assets] == ["ready", "duplicate", "ready"]
    assert assets[1]["error"] == "重复图片"
    assert detail["folder"]["original_url"] == assets[0]["url"].rsplit("/", 1)[0] + "/post.html"
    assert len(detail["images"]) == 2


def test_site_sync_does_not_redownload_duplicate_assets(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    source = create_duplicate_source(db, tmp_path)
    syncer._sync_source(source)

    class FailingDownloader:
        def download(self, url: str, target: Path) -> None:
            raise AssertionError(f"unexpected download: {url}")

    monkeypatch.setattr(syncer, "_new_media_downloader", lambda settings: FailingDownloader())

    result = syncer._sync_source(source)
    post = db.list_site_posts()[0]
    assets = db.list_site_assets(post["id"])

    assert result["downloaded"] == 0
    assert [asset["status"] for asset in assets] == ["ready", "duplicate", "ready"]


def test_site_sync_retries_media_download_until_fifth_attempt(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    source = create_single_image_source(db, tmp_path)
    attempts = {"count": 0}

    class FlakyDownloader:
        def download(self, url: str, target: Path) -> None:
            attempts["count"] += 1
            if attempts["count"] < 5:
                raise OSError("temporary failure")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"ok")

    monkeypatch.setattr(syncer, "_new_media_downloader", lambda settings: FlakyDownloader())
    monkeypatch.setattr("app.services.site_syncer.time.sleep", lambda seconds: None)

    result = syncer._sync_source(source)
    post = db.list_site_posts()[0]
    asset = db.list_site_assets(post["id"])[0]

    assert attempts["count"] == 5
    assert result["downloaded"] == 1
    assert result["errors"] == 0
    assert asset["status"] == "ready"


def test_site_sync_records_failed_media_after_five_attempts(tmp_path: Path, monkeypatch) -> None:
    db, _storage, syncer = make_app(tmp_path)
    source = create_single_image_source(db, tmp_path)
    attempts = {"count": 0}

    class BrokenDownloader:
        def download(self, url: str, target: Path) -> None:
            attempts["count"] += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.with_suffix(f"{target.suffix}.part").write_bytes(b"partial")
            raise OSError("permanent failure")

    monkeypatch.setattr(syncer, "_new_media_downloader", lambda settings: BrokenDownloader())
    monkeypatch.setattr("app.services.site_syncer.time.sleep", lambda seconds: None)

    result = syncer._sync_source(source)
    post = db.list_site_posts()[0]
    asset = db.list_site_assets(post["id"])[0]
    target = _site_asset_target(storage=_storage, asset=asset)
    logs = db.list_site_filter_logs()

    assert attempts["count"] == 5
    assert result["downloaded"] == 0
    assert result["errors"] == 1
    assert asset["status"] == "failed"
    assert "permanent failure" in asset["error"]
    assert any(log["decision"] == "download-error" and "permanent failure" in log["reason"] for log in logs)
    assert not target.exists()


def _site_asset_target(storage: StorageService, asset: dict) -> Path:
    rel_path = asset.get("rel_path")
    if rel_path:
        resolved = storage.resolve_storage_path(rel_path)
        if resolved:
            return resolved
    post = asset["filename"]
    candidates = list(storage.config.data_dir.glob(f"sites/**/{post}"))
    return candidates[0] if candidates else storage.config.data_dir / post


def test_site_sync_skips_older_than_latest_but_repairs_same_day_missing_media(tmp_path: Path, monkeypatch) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_incremental_source(db, tmp_path)
    first = syncer._sync_source(source)
    assert first["downloaded"] == 2

    newer_post = next(post for post in db.list_site_posts(source_id=source["id"]) if post["title"] == "Newer Same Day")
    newer_asset = db.list_site_assets(newer_post["id"])[0]
    newer_target = storage.resolve_storage_path(newer_asset["rel_path"])
    assert newer_target and newer_target.exists()
    newer_target.unlink()
    downloaded_urls: list[str] = []

    class CaptureDownloader:
        def download(self, url: str, target: Path) -> None:
            downloaded_urls.append(url)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"repaired")

    monkeypatch.setattr(syncer, "_new_media_downloader", lambda settings: CaptureDownloader())

    second = syncer._sync_source(source)
    logs = db.list_site_filter_logs()

    assert second["downloaded"] == 1
    assert second["skipped"] == 1
    assert len(downloaded_urls) == 1
    assert downloaded_urls[0].endswith("/newer.jpg")
    assert any(log["decision"] == "skipped" and log["reason"] == "早于本地最新时间" for log in logs)


def test_site_full_validation_clears_and_resyncs_source(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_duplicate_source(db, tmp_path)
    syncer._sync_source(source)
    post = db.list_site_posts()[0]
    folder_name = GalleryService(db, storage).get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])["items"][0]["folder_name"]
    assert db.list_site_assets(post["id"])
    assert storage.image_folder(folder_name).exists()

    result = syncer.execute_full_validation(source["id"])
    posts = db.list_site_posts()
    detail = GalleryService(db, storage).get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])

    assert result["cleared_posts"] == 1
    assert result["cleared_assets"] == 3
    assert result["downloaded"] == 3
    assert len(posts) == 1
    assert posts[0]["downloaded_count"] == 2
    assert detail["total"] == 1


def test_site_full_validation_records_empty_result_details_and_logs(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "empty-site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("<!doctype html><main>empty</main>", encoding="utf-8")
    source = db.create_site_source(
        {
            "name": "Empty Fixture",
            "slug": "empty-fixture",
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "media_selector": ".content img",
            "enabled": True,
        }
    )

    result = syncer.execute_full_validation(source["id"])
    logs = db.list_site_filter_logs()
    decisions = {log["decision"] for log in logs}

    assert result["discovered"] == 0
    assert result["posts"] == 0
    assert result["validation_mode"] is True
    assert result["source"]["entry_url"] == source["entry_url"]
    assert {"validation-start", "validation-cleared", "empty", "validation-empty", "validation-complete"}.issubset(decisions)


def test_validation_dedupes_historical_site_posts_and_refreshes_gallery(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_duplicate_source(db, tmp_path)
    syncer._sync_source(source)
    post = db.list_site_posts()[0]
    assets = db.list_site_assets(post["id"])
    duplicate = assets[1]
    duplicate_path = storage.resolve_storage_path(duplicate["rel_path"])
    kept_path = storage.resolve_storage_path(assets[0]["rel_path"])
    duplicate_path.parent.mkdir(parents=True, exist_ok=True)
    duplicate_path.write_bytes(kept_path.read_bytes())
    db.set_site_asset_result(duplicate["id"], "ready", duplicate["rel_path"])
    db.update_site_post_counts(post["id"])
    syncer.mirror_existing_site_post(db.get_site_post(post["id"]))
    folder_name = GalleryService(db, storage).get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])["items"][0]["folder_name"]
    assert len(GalleryService(db, storage).get_folder_detail(folder_name)["images"]) == 3

    class FakeAuth:
        def get_cookie_state(self):
            return SimpleNamespace(cookie=None)

    puller = PullManager(db, storage, None, CleanupService(db, storage), FakeAuth(), None)
    puller.attach_site_syncer(syncer)

    stats = puller._execute_validation()

    assert stats["site_deduped_images"] == 1
    assert db.get_site_post(post["id"])["downloaded_count"] == 2
    assert len(GalleryService(db, storage).get_folder_detail(folder_name)["images"]) == 2


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
    monkeypatch.setattr(syncer, "start_full_validation", sync_now)
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
    assert client.post(f"/api/subscriptions/site:{created['id']}/pull").json()["ok"] is True
    assert client.post(f"/api/site-sources/{created['id']}/validate").json()["ok"] is True

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
