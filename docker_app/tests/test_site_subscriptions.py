import threading
import time
import sqlite3
from types import SimpleNamespace
from pathlib import Path

from app.config import AppConfig
from app.db import Database, DEFAULT_SETTINGS
from app.services.cleanup import CleanupService
from app.services.gallery import GalleryService
from app.services.bilibili import BilibiliAuthService
from app.services.media_indexer import MediaIndexer
from app.services.puller import PullManager
from app.services.site_downloader import MediaDownloader
from app.services.site_parser import PageFetcher, SourceParser, site_request_timeout
from app.services.site_filtering import RuleEngine
from app.services.scheduler import SchedulerService
from app.services.site_syncer import SiteSyncManager
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import clean_filename, dumps_json, parse_date
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


def create_rule_guard_source(db: Database, tmp_path: Path) -> dict:
    site_dir = tmp_path / "rule-guard-site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <article class="post-card"><a class="detail-link" href="blocked.html">Blocked</a></article>
        <article class="post-card"><a class="detail-link" href="nodate.html">No Date</a></article>
        """,
        encoding="utf-8",
    )
    (site_dir / "blocked.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Other Post</h1>
          <time datetime="2026-04-06">2026.04.06</time>
          <a class="tag">daily</a>
          <p class="body">This post should miss the allow list.</p>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "nodate.html").write_text(
        """
        <!doctype html>
        <article class="content">
          <h1>Allowed Without Date</h1>
          <a class="tag">spring</a>
          <p class="body">This post should be skipped because it has no date.</p>
        </article>
        """,
        encoding="utf-8",
    )
    return db.create_site_source(
        {
            "name": "Rule Guard Fixture",
            "slug": "rule-guard-fixture",
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".post-card",
            "detail_link_selector": ".detail-link",
            "title_selector": "h1",
            "date_selector": "time",
            "tag_selector": ".tag",
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


def test_site_scheduler_settings_migrate_from_legacy_global_scheduler(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table settings (key text primary key, value text not null)")
        conn.execute("insert into settings(key, value) values (?, ?)", ("scheduler_enabled", dumps_json(True)))
        conn.execute("insert into settings(key, value) values (?, ?)", ("scheduler_interval_hours", dumps_json(5)))

    db = Database(db_path)
    db.init()
    settings = db.get_settings()

    assert settings["site_scheduler_enabled"] is True
    assert settings["site_scheduler_interval_hours"] == 5


def test_scheduler_registers_up_and_site_jobs_independently(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    db.save_settings(
        {
            "scheduler_enabled": True,
            "scheduler_interval_hours": 2,
            "site_scheduler_enabled": True,
            "site_scheduler_interval_hours": 7,
        }
    )
    pull_calls = {"count": 0}
    site_calls = {"count": 0}

    class PullStub:
        def start_pull(self) -> None:
            pull_calls["count"] += 1

    class SiteStub:
        def start_sync(self) -> None:
            site_calls["count"] += 1

    service = SchedulerService(db, PullStub(), SiteStub())
    service.reload()
    jobs = {job.id: job for job in service.scheduler.get_jobs()}

    assert set(jobs) == {"scheduled-pull", "scheduled-site-sync"}
    assert int(jobs["scheduled-pull"].trigger.interval.total_seconds()) == 2 * 3600
    assert int(jobs["scheduled-site-sync"].trigger.interval.total_seconds()) == 7 * 3600

    service.start_scheduled_pull()
    assert pull_calls["count"] == 1
    assert site_calls["count"] == 0

    service.start_scheduled_site_sync()
    assert pull_calls["count"] == 1
    assert site_calls["count"] == 1


def test_new_databases_keep_site_scheduler_disabled_by_default(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    settings = db.get_settings()

    assert settings["site_scheduler_enabled"] == DEFAULT_SETTINGS["site_scheduler_enabled"]
    assert settings["site_scheduler_interval_hours"] == DEFAULT_SETTINGS["site_scheduler_interval_hours"]


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


def test_site_source_suggestion_detects_blog_list_structure(tmp_path: Path) -> None:
    site_dir = tmp_path / "blog-list-site"
    (site_dir / "page").mkdir(parents=True)
    Image.new("RGB", (32, 32), (20, 80, 160)).save(site_dir / "image.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>Example Blog | Archive</title></head>
          <body>
            <div class="post-list cf" role="article">
              <a href="post.html">
                <section class="entry-content">
                  <span class="date updated">2026.06.19</span>
                  <span class="cat-name">daily</span>
                  <h2 class="entry-title">Example Blog Post</h2>
                </section>
              </a>
            </div>
            <div class="post-list cf" role="article">
              <a href="post2.html">
                <section class="entry-content">
                  <span class="date updated">2026.06.18</span>
                  <span class="cat-name">daily</span>
                  <h2 class="entry-title">Second Blog Post</h2>
                </section>
              </a>
            </div>
            <a href="page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article class="post">
          <h1>Example Blog Post</h1>
          <time datetime="2026-06-19">2026.06.19</time>
          <span class="cat-name">daily</span>
          <div class="entry-content"><img data-src="image.jpg" src="data:image/svg+xml,placeholder"></div>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article class="post">
          <h1>Second Blog Post</h1>
          <time datetime="2026-06-18">2026.06.18</time>
        </article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=1)

    assert suggestion["name"] == "Example Blog"
    assert suggestion["list_item_selector"] == ".post-list"
    assert suggestion["page_url_template"].endswith("/page/{page}")
    assert posts[0].title == "Example Blog Post"
    assert posts[0].pub_date == "2026-06-19"
    assert posts[0].assets[0].url.endswith("/image.jpg")


def test_site_source_suggestion_detects_content_post_structure(tmp_path: Path) -> None:
    site_dir = tmp_path / "content-post-site"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), (120, 40, 160)).save(site_dir / "image.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>Content Post Site | Archive</title></head>
          <body>
            <article class="content-post post hentry">
              <div class="site-images"><a href="post.html"><img src="image.jpg"></a></div>
              <h2 class="post-title"><a href="post.html">Sample Image Set</a></h2>
              <div class="post-date">2026年6月23日(火) 21:39</div>
              <div class="post-categories"><a>sample</a></div>
            </article>
            <article class="content-post post hentry">
              <div class="site-images"><a href="post2.html"><img src="image.jpg"></a></div>
              <h2 class="post-title"><a href="post2.html">Second Image Set</a></h2>
              <div class="post-date">2026年6月22日(月) 10:20</div>
              <div class="post-categories"><a>daily</a></div>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article class="post">
          <h1>Sample Image Set</h1>
          <div class="post-date">2026年6月23日(火) 21:39</div>
          <div class="post-categories"><a>sample</a></div>
          <div class="post-page-content"><p>detail text</p><img src="image.jpg"></div>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article class="post">
          <h1>Second Image Set</h1>
          <div class="post-date">2026年6月22日(月) 10:20</div>
        </article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=1)

    assert suggestion["list_item_selector"] == ".content-post"
    assert suggestion["preview"][0]["pub_date"] == "2026-06-23"
    assert posts[0].title == "Sample Image Set"
    assert posts[0].pub_date == "2026-06-23"
    assert posts[0].tags == ["sample"]
    assert posts[0].assets[0].url.endswith("/image.jpg")


def test_site_parser_fallback_handles_entry_meta_json_ld_and_self_closing_images(tmp_path: Path, monkeypatch) -> None:
    from app.services import site_parser

    site_dir = tmp_path / "wordpress-style-site"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), (90, 120, 160)).save(site_dir / "image.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>WordPress Style</title></head>
          <body>
            <article class="hentry">
              <h1 class="entry-title"><a href="post.html">List Title</a></h1>
              <div class="entry-meta">2026-05-22｜この記事のカテゴリ</div>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <html>
          <head>
            <title>Detail Title - Site</title>
            <script type="application/ld+json">{"datePublished":"2026-05-22T07:15:00+00:00"}</script>
          </head>
          <body>
            <h1 class="site-title"></h1>
            <article class="hentry">
              <h1 class="entry-title">Detail Title</h1>
              <div class="entry-content"><img src="image.jpg" /></div>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(site_parser, "BeautifulSoup", None)

    parser = SourceParser(PageFetcher())
    posts = parser.discover(
        {
            "source_type": "html",
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "max_pages": 1,
            "list_item_selector": ".hentry",
            "detail_link_selector": "a",
            "title_selector": "h1",
            "date_selector": site_parser.DEFAULT_DATE_SELECTOR,
            "body_selector": "article",
            "media_selector": ".entry-content img",
        }
    )

    assert len(posts) == 1
    assert posts[0].title == "Detail Title"
    assert posts[0].pub_date == "2026-05-22"
    assert posts[0].assets[0].url.endswith("/image.jpg")


def test_site_parser_handles_misskon_style_lazy_images_and_schema_dates(tmp_path: Path) -> None:
    site_dir = tmp_path / "misskon-style-site"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), (30, 90, 150)).save(site_dir / "cover.webp")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>MissKon Style - Archive</title></head>
          <body>
            <article class="post hentry">
              <a href="post.html"><img class="lazy" data-src="cover.webp" src="data:image/svg+xml,placeholder"></a>
              <h2><a href="post.html">Lazy Gallery Post</a></h2>
              <span>Comments 0 Views 1 2 3</span>
            </article>
            <article class="post hentry">
              <a href="post2.html"><img class="lazy" data-src="cover.webp" src="data:image/svg+xml,placeholder"></a>
              <h2><a href="post2.html">Second Lazy Gallery Post</a></h2>
            </article>
            <a href="page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <html>
          <head>
            <script type="application/ld+json">
              {"@type":"Article","datePublished":"2026-07-03T12:00:26+08:00"}
            </script>
          </head>
          <body>
            <article class="post hentry">
              <h1>Lazy Gallery Post</h1>
              <div class="content">
                <img class="aligncenter lazy" data-src="cover.webp" src="data:image/svg+xml,placeholder">
              </div>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article class="post hentry"><h1>Second Lazy Gallery Post</h1></article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=1)

    assert suggestion["list_item_selector"] in {"article", ".hentry", ".post"}
    assert suggestion["page_url_template"].endswith("/page/{page}")
    assert posts[0].title == "Lazy Gallery Post"
    assert posts[0].pub_date == "2026-07-03"
    assert posts[0].assets[0].url.endswith("/cover.webp")


def test_site_parser_handles_cosheji_style_post_items_and_update_dates(tmp_path: Path) -> None:
    site_dir = tmp_path / "cosheji-style-site"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), (150, 90, 30)).save(site_dir / "cover.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>COS合集社-高质量COSPLAY写真图集分享 -</title></head>
          <body>
            <article class="post-item">
              <a href="collection.html">柒柒要乖哦COS写真合集 [80套][持续更新]</a>
              <time datetime="2026-07-03T08:00:00+08:00">16 小时前</time>
              <span>2 1 4.7K</span>
            </article>
            <article class="post-item">
              <a href="collection2.html">星澜是澜澜COS写真合集 [60套][持续更新]</a>
              <time datetime="2026-07-02T12:00:00+08:00">2 天前</time>
            </article>
            <a href="page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "collection.html").write_text(
        """
        <!doctype html>
        <html>
          <body>
            <article>
              <h1>柒柒要乖哦COS写真合集 [80套][持续更新]</h1>
              <div class="entry-content">
                <p>资源目录 2026.07.03更新 No.080-雨天邂逅 [178P1V-2.25GB]</p>
                <img src="cover.jpg">
              </div>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "collection2.html").write_text(
        """
        <!doctype html>
        <article><h1>星澜是澜澜COS写真合集 [60套][持续更新]</h1></article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=1)

    assert suggestion["name"] == "COS合集社"
    assert suggestion["list_item_selector"] == ".post-item"
    assert suggestion["preview"][0]["pub_date"] == "2026-07-03"
    assert suggestion["page_url_template"].endswith("/page/{page}")
    assert posts[0].title == "柒柒要乖哦COS写真合集 [80套][持续更新]"
    assert posts[0].pub_date == "2026-07-03"
    assert posts[0].assets[0].url.endswith("/cover.jpg")


def test_site_parser_handles_foamgirl_style_cards_external_ads_and_asset_dates(tmp_path: Path) -> None:
    site_dir = tmp_path / "foamgirl-style-site"
    site_dir.mkdir(parents=True)
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>FoamGirl-Share sexy asian girl photos</title></head>
          <body>
            <nav>
              <ul>
                <li><a href="index.html">Home</a></li>
                <li><a href="chinese.html">Chinese</a></li>
                <li><a href="korea.html">Korea</a></li>
                <li><a href="japan.html">Japan</a></li>
              </ul>
            </nav>
            <div class="item">
              <a href="post.html"><img src="thumb.jpg" alt="Bomi (보미): Oil Play at Hotel"></a>
            </div>
            <div class="item">
              <a href="https://u36.net/shorts"><img src="ad.gif" alt="External video ad"></a>
            </div>
            <div class="item">
              <a href="post2.html"><img src="thumb2.jpg" alt="[LE] LERB-112B: Lenti"></a>
            </div>
            <a href="page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>Bomi (보미): Oil Play at Hotel (89 photos)</h1>
          <div class="content">
            <img src="wp-content/uploads/2025/09/11/001.jpg">
            <img src="wp-content/uploads/2025/09/11/002.jpg">
          </div>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>[LE] LERB-112B: Lenti (49 photos)</h1>
          <div class="content"><img src="wp-content/uploads/2025/09/11/101.jpg"></div>
        </article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=3)

    assert suggestion["name"] == "FoamGirl"
    assert suggestion["list_item_selector"] == ".item"
    assert suggestion["preview"][0]["title"] == "Bomi (보미): Oil Play at Hotel"
    assert suggestion["page_url_template"].endswith("/page/{page}")
    assert [post.title for post in posts] == [
        "Bomi (보미): Oil Play at Hotel (89 photos)",
        "[LE] LERB-112B: Lenti (49 photos)",
    ]
    assert posts[0].pub_date == "2025-09-11"
    assert len(posts[0].assets) == 2


def test_site_parser_handles_foamgirl_category_list_items(tmp_path: Path) -> None:
    site_dir = tmp_path / "foamgirl-category-site"
    site_dir.mkdir(parents=True)
    (site_dir / "cosplay.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>Cosplay - FoamGirl</title></head>
          <body>
            <nav>
              <ul>
                <li><a href="index.html">Home</a></li>
                <li><a href="chinese.html">Chinese</a></li>
                <li><a href="cosplay.html">Cosplay</a></li>
              </ul>
            </nav>
            <ul class="update_area_lists">
              <li class="i_list list_n1 lms-one cxudy-list-formatimage">
                <a href="post.html" class="thumb-srcbox">
                  <img class="waitpic" src="placeholder.gif" data-original="wp-content/uploads/2026/07/02/cover.webp" alt="Cosplay Hokunaimeko - 2B">
                </a>
                <div class="case_info">
                  <a class="meta-title" href="post.html">Cosplay Hokunaimeko - 2B</a>
                  <div class="meta-post">2 days ago</div>
                </div>
              </li>
              <li class="i_list list_n1 lms-one cxudy-list-formatimage">
                <a href="post2.html" class="thumb-srcbox">
                  <img class="waitpic" src="placeholder.gif" data-original="wp-content/uploads/2026/07/01/cover2.webp" alt="Cosplay Quan - Tora">
                </a>
                <div class="case_info">
                  <a class="meta-title" href="post2.html">Cosplay Quan - Tora</a>
                  <div class="meta-post">3 days ago</div>
                </div>
              </li>
            </ul>
            <a href="cosplay/page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>Cosplay Hokunaimeko - 2B</h1>
          <div class="content"><img src="wp-content/uploads/2026/07/02/001.jpg"></div>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>Cosplay Quan - Tora</h1>
          <div class="content"><img src="wp-content/uploads/2026/07/01/001.jpg"></div>
        </article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "cosplay.html").resolve().as_uri())
    preview = parser.preview(suggestion, limit=2)
    posts = parser.discover(suggestion, limit=2)

    assert suggestion["list_item_selector"] in {".i_list", ".update_area_lists li", ".cxudy-list-formatimage"}
    assert suggestion["preview"][0]["title"] == "Cosplay Hokunaimeko - 2B"
    assert suggestion["preview"][0]["pub_date"] == "2026-07-02"
    assert suggestion["page_url_template"].endswith("/cosplay/page/{page}")
    assert [post.pub_date for post in preview] == ["2026-07-02", "2026-07-01"]
    assert [post.pub_date for post in posts] == ["2026-07-02", "2026-07-01"]
    assert [post.title for post in posts] == ["Cosplay Hokunaimeko - 2B", "Cosplay Quan - Tora"]


def test_site_parser_handles_hotgirlpix_style_articles(tmp_path: Path) -> None:
    site_dir = tmp_path / "hotgirlpix-style-site"
    site_dir.mkdir(parents=True)
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><title>Hot Girl Pix - Sexy models, hot girls, Asian girls, Western girls</title></head>
          <body>
            <article>
              <h2><a href="post.html">Roxy Model</a></h2>
              <span class="post-date">Date: 2026-07-02</span>
              <img class="postFeaturedImage" src="cover.jpg" alt="Roxy Model Cover Photo">
            </article>
            <article>
              <h2><a href="post2.html">Mizuki Takanashi</a></h2>
              <span class="post-date">Date: 2026-07-01</span>
              <img class="postFeaturedImage" src="cover2.jpg" alt="Mizuki Cover Photo">
            </article>
            <a href="page/2">2</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>Roxy Model</h1>
          <span class="post-date">Date: 2026-07-02</span>
          <div class="content">
            <img src="files/2026/04/04/17/001.jpg">
            <img src="files/2026/04/04/17/002.jpg">
          </div>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post2.html").write_text(
        """
        <!doctype html>
        <article><h1>Mizuki Takanashi</h1><span class="post-date">Date: 2026-07-01</span></article>
        """,
        encoding="utf-8",
    )

    parser = SourceParser(PageFetcher())
    suggestion = parser.suggest((site_dir / "index.html").resolve().as_uri())
    posts = parser.discover(suggestion, limit=1)

    assert suggestion["name"] == "Hot Girl Pix"
    assert suggestion["list_item_selector"] == "article"
    assert suggestion["preview"][0]["pub_date"] == "2026-07-02"
    assert suggestion["page_url_template"].endswith("/page/{page}")
    assert posts[0].title == "Roxy Model"
    assert posts[0].pub_date == "2026-07-02"
    assert len(posts[0].assets) == 2


def test_site_parser_stops_when_later_paged_html_is_missing(tmp_path: Path) -> None:
    site_dir = tmp_path / "paged-missing"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), (40, 80, 120)).save(site_dir / "image.jpg")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <article class="post-card">
          <a class="detail-link" href="post.html">Only Post</a>
        </article>
        """,
        encoding="utf-8",
    )
    (site_dir / "post.html").write_text(
        """
        <!doctype html>
        <article>
          <h1>Only Post</h1>
          <time datetime="2026-06-23">2026-06-23</time>
          <div class="content"><img src="image.jpg"></div>
        </article>
        """,
        encoding="utf-8",
    )
    parser = SourceParser(PageFetcher())
    source = {
        "source_type": "html",
        "entry_url": (site_dir / "index.html").resolve().as_uri(),
        "page_url_template": (site_dir / "missing-{page}.html").resolve().as_uri(),
        "max_pages": 20,
        "list_item_selector": ".post-card",
        "detail_link_selector": ".detail-link",
        "title_selector": "h1",
        "date_selector": "time",
        "tag_selector": "",
        "body_selector": ".content",
        "media_selector": ".content img",
    }

    posts = parser.discover(source)

    assert [post.title for post in posts] == ["Only Post"]


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


def test_site_sync_stores_rule_matched_posts_with_date_fallback(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    db.save_site_rules({"mode": "whitelist", "allow_keywords": ["spring"], "use_regex": False})
    source = create_rule_guard_source(db, tmp_path)

    result = syncer._sync_source(source)
    logs = db.list_site_filter_logs()
    posts = db.list_site_posts(source_id=source["id"])

    assert result["discovered"] == 2
    assert result["posts"] == 1
    assert result["blocked"] == 1
    assert result["skipped"] == 0
    assert result["no_media"] == 1
    assert len(posts) == 1
    assert posts[0]["title"] == "Allowed Without Date"
    assert parse_date(posts[0]["pub_date"]) is not None
    assert db.list_site_posts(category="blocked", source_id=source["id"]) == []
    assert any(log["reason"] == "未命中站点白名单" for log in logs)
    assert any(log["decision"] == "date-fallback" and "同步日期" in log["reason"] for log in logs)


def test_site_sync_skips_posts_that_are_still_in_trash(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)
    syncer._sync_source(source)
    folder = db.list_folders()[0]
    assets = db.list_assets_for_folder(folder["folder_name"])

    db.upsert_trash_item(folder, assets)
    storage.remove_folder_assets(folder["folder_name"])
    db.delete_folder(folder["folder_name"])
    result = syncer._sync_source(source)

    assert result["skipped"] >= 1
    assert db.list_folders() == []
    assert any(log["reason"] == "仍在内容垃圾桶" for log in db.list_site_filter_logs())


def test_site_rule_engine_mode_keywords_match_title_or_tags() -> None:
    blacklist = RuleEngine({"mode": "blacklist", "keywords": ["photo"], "use_regex": False})
    whitelist = RuleEngine({"mode": "whitelist", "keywords": ["spring"], "use_regex": False})
    both = RuleEngine(
        {
            "mode": "both",
            "allow_keywords": ["spring"],
            "block_keywords": ["ad"],
            "use_regex": False,
        }
    )

    assert blacklist.evaluate("Clean Post", ["photo"]).allowed is False
    assert blacklist.evaluate("Clean Post", ["daily"]).allowed is True
    assert whitelist.evaluate("Spring Update", ["daily"]).allowed is True
    assert whitelist.evaluate("Clean Post", ["daily"]).allowed is False
    assert both.evaluate("Spring Update", ["daily"]).allowed is True
    assert both.evaluate("Spring Ad", ["daily"]).allowed is False
    assert both.evaluate("Clean Post", ["daily"]).allowed is False
    assert both.evaluate("Clean Post", ["spring"]).allowed is True


def test_site_sync_removes_gallery_when_rules_start_blocking(tmp_path: Path) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)

    syncer._sync_source(source)
    gallery = GalleryService(db, storage)
    gallery_items = gallery.get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])
    folder_name = gallery_items["items"][0]["folder_name"]
    assert gallery_items["total"] == 1
    assert storage.image_folder(folder_name).exists()

    db.save_site_rules({"mode": "blacklist", "block_keywords": ["Spring"], "use_regex": False})
    result = syncer._sync_source(source)

    assert result["blocked"] == 1
    assert len(db.list_site_posts(category="blocked", source_id=source["id"])) == 1
    assert gallery.get_gallery_items(category="all", subscription_uids=[f"site:{source['id']}"])["total"] == 0
    assert not storage.image_folder(folder_name).exists()


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


def test_site_sources_sort_by_created_time_and_keep_proxy_setting(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    older = create_fixture_source(db)
    newer = db.create_site_source(
        {
            "name": "Newer Fixture",
            "slug": "newer-fixture",
            **html_source(),
            "entry_url": fixture_url("skip_index.html"),
            "enabled": True,
        }
    )

    assert [item["id"] for item in db.list_site_sources()[:2]] == [newer["id"], older["id"]]
    assert bool(older["use_proxy"]) is True

    updated = db.update_site_source(older["id"], {"name": "Older Updated", "use_proxy": False})

    assert updated and bool(updated["use_proxy"]) is False
    assert [item["id"] for item in db.list_site_sources()[:2]] == [newer["id"], older["id"]]


def test_site_proxy_can_be_disabled_per_source(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    db.save_settings({"site_proxy_enabled": True, "site_proxy_host": "127.0.0.1", "site_proxy_port": 7890})
    source = create_fixture_source(db)

    enabled_settings = syncer._settings_for_source(db.get_settings(), source)
    disabled_settings = syncer._settings_for_source(db.get_settings(), {**source, "use_proxy": 0})

    assert syncer._site_proxies(enabled_settings) == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
    assert syncer._site_proxies(disabled_settings) is None


def test_bilibili_space_page_fallback_extracts_avatar(tmp_path: Path, monkeypatch) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    monkeypatch.setattr(service, "_sleep_jitter", lambda *_args: None)

    class FakeResponse:
        text = """
        <!doctype html>
        <html>
          <head>
            <title>测试UP的个人空间-哔哩哔哩</title>
            <meta itemprop="image" content="//i0.hdslb.com/bfs/face/avatar-test.jpg">
          </head>
        </html>
        """

        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    profile = service._fetch_up_profile_from_space_page("123", FakeSession())

    assert profile == {
        "uid": "123",
        "uname": "测试UP",
        "face": "https://i0.hdslb.com/bfs/face/avatar-test.jpg",
    }


def test_bilibili_space_page_fallback_ignores_site_icon(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    text = """
    <!doctype html>
    <html>
      <head>
        <meta itemprop="image" content="https://www.bilibili.com/favicon.ico">
        <meta property="og:image" content="//static.hdslb.com/images/base/logo.png">
      </head>
    </html>
    """

    assert service._extract_space_face(text) is None


def test_bilibili_space_page_fallback_prefers_real_avatar_over_site_icon(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    text = r"""
    <!doctype html>
    <html>
      <head><meta itemprop="image" content="https://www.bilibili.com/favicon.ico"></head>
      <body>
        <script>
          window.__INITIAL_STATE__ = {"face":"//i1.hdslb.com/bfs/face/real-avatar.jpg"};
        </script>
      </body>
    </html>
    """

    assert service._extract_space_face(text) == "https://i1.hdslb.com/bfs/face/real-avatar.jpg"


def test_bilibili_space_page_fallback_extracts_dynamic_avatar(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    text = r"""
    <!doctype html>
    <html>
      <body>
        <script>
          window.__INITIAL_STATE__ = {
            "layers":[
              {"bfs_style":"widget-layer-avatar","url":"//i0.hdslb.com/bfs/garb/item/dynamic-avatar.webp"}
            ]
          };
        </script>
      </body>
    </html>
    """

    assert service._extract_space_face(text) == "https://i0.hdslb.com/bfs/garb/item/dynamic-avatar.webp"


def test_bilibili_space_page_fallback_extracts_baselabs_avatar(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    text = r"""
    <!doctype html>
    <html>
      <head>
        <link rel="preload" as="image" href="//i1.hdslb.com/bfs/baselabs/static-avatar.png">
      </head>
    </html>
    """

    assert service._extract_space_face(text) == "https://i1.hdslb.com/bfs/baselabs/static-avatar.png"


def test_bilibili_dynamic_feed_prefers_complete_static_avatar(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    profile = service._extract_dynamic_feed_profile(
        {
            "items": [
                {
                    "modules": {
                        "module_author": {
                            "mid": 848008,
                            "name": "-MyMy麦麦-",
                            "face": "https://i1.hdslb.com/bfs/baselabs/static-avatar.png",
                            "avatar": {
                                "layers": [
                                    {
                                        "layers": [
                                            {
                                                "resource": {
                                                    "res_animation": {
                                                        "webp_src": {
                                                            "remote": {
                                                                "url": "https://i0.hdslb.com/bfs/baselabs/animated-avatar.webp",
                                                                "bfs_style": "widget-layer-avatar",
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                ],
                                "fallback_layers": {
                                    "layers": [
                                        {
                                            "resource": {
                                                "res_image": {
                                                    "image_src": {
                                                        "remote": {
                                                            "url": "https://i1.hdslb.com/bfs/baselabs/static-avatar.png",
                                                            "bfs_style": "widget-layer-avatar",
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    ]
                                },
                            },
                        }
                    }
                }
            ]
        },
        "848008",
    )

    assert profile == {
        "uid": "848008",
        "uname": "-MyMy麦麦-",
        "face": "https://i1.hdslb.com/bfs/baselabs/static-avatar.png",
    }


def test_bilibili_dynamic_feed_retries_with_light_headers(tmp_path: Path) -> None:
    db, _storage, _syncer = make_app(tmp_path)
    service = BilibiliAuthService(db)
    service._sleep_jitter = lambda *_args: None

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeSession:
        def __init__(self) -> None:
            self.headers = {"Cookie": "SESSDATA=test", "Sec-CH-UA": '"Chromium"'}
            self.calls: list[dict[str, str]] = []

        def get(self, *_args, **_kwargs):
            self.calls.append(dict(self.headers))
            if len(self.calls) == 1:
                return FakeResponse({"code": -352, "message": "-352"})
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "modules": {
                                    "module_author": {
                                        "mid": 848008,
                                        "name": "-MyMy麦麦-",
                                        "avatar": {
                                            "fallback_layers": {
                                                "layers": [
                                                    {
                                                        "resource": {
                                                            "res_image": {
                                                                "image_src": {
                                                                    "remote": {
                                                                        "url": "https://i1.hdslb.com/bfs/baselabs/static-avatar.png"
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                ]
                                            }
                                        },
                                    }
                                }
                            }
                        ]
                    },
                }
            )

    session = FakeSession()
    profile = service._fetch_up_profile_from_dynamic_feed("848008", session)

    assert profile == {
        "uid": "848008",
        "uname": "-MyMy麦麦-",
        "face": "https://i1.hdslb.com/bfs/baselabs/static-avatar.png",
    }
    assert len(session.calls) == 2
    assert "Sec-CH-UA" not in session.calls[1]
    assert session.headers == {"Cookie": "SESSDATA=test", "Sec-CH-UA": '"Chromium"'}


def test_site_icon_refresh_discovers_html_link_icon(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "icon-site"
    site_dir.mkdir()
    (site_dir / "logo.png").write_bytes(b"fake png")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head><link rel="icon" href="logo.png"></head>
          <body><article class="post-card"><a class="detail-link" href="post.html">Post</a></article></body>
        </html>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "Icon Fixture",
            "slug": "icon-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "enabled": True,
        }
    )

    item = syncer.refresh_site_icon(source["id"])

    assert item["icon_url"] == (site_dir / "logo.png").resolve().as_uri()


def test_site_icon_refresh_fallback_parser_discovers_shortcut_icon(tmp_path: Path, monkeypatch) -> None:
    from app.services import site_parser

    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "shortcut-icon-site"
    site_dir.mkdir()
    (site_dir / "site.ico").write_bytes(b"fake ico")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html><head><link rel="shortcut icon" href="site.ico" /></head><body></body></html>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "Shortcut Icon Fixture",
            "slug": "shortcut-icon-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "enabled": True,
        }
    )
    monkeypatch.setattr(site_parser, "BeautifulSoup", None)

    item = syncer.refresh_site_icon(source["id"])

    assert item["icon_url"] == (site_dir / "site.ico").resolve().as_uri()


def test_site_icon_refresh_discovers_rss_image(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "rss-icon-site"
    site_dir.mkdir()
    (site_dir / "feed-logo.png").write_bytes(b"fake png")
    (site_dir / "feed.xml").write_text(
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>RSS Icon Fixture</title>
            <link>https://example.test/</link>
            <image><url>feed-logo.png</url></image>
          </channel>
        </rss>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "RSS Icon Fixture",
            "slug": "rss-icon-fixture",
            "source_type": "rss",
            "entry_url": (site_dir / "feed.xml").resolve().as_uri(),
            "enabled": True,
        }
    )

    item = syncer.refresh_site_icon(source["id"])

    assert item["icon_url"] == (site_dir / "feed-logo.png").resolve().as_uri()


def test_site_icon_refresh_caches_remote_icon_in_local_storage(tmp_path: Path, monkeypatch) -> None:
    db, storage, syncer = make_app(tmp_path)
    source = create_fixture_source(db)
    remote_icon_url = "https://img.example.test/favicon"
    sessions = []

    class FakeResponse:
        headers = {"content-type": "image/png"}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            yield b"remote-site-icon"

        def close(self) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.headers = {}
            self.proxies = {}
            self.calls = []
            sessions.append(self)

        def get(self, url: str, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return FakeResponse()

        def close(self) -> None:
            return None

    icon_dir = storage.config.data_dir / "avatars" / "sites"
    icon_dir.mkdir(parents=True)
    stale_icon = icon_dir / f"{source['id']}.ico"
    stale_icon.write_bytes(b"stale-icon")

    monkeypatch.setattr(syncer, "discover_site_icon", lambda _source: remote_icon_url)
    monkeypatch.setattr("app.services.site_syncer.requests.Session", FakeSession)

    item = syncer.refresh_site_icon(source["id"])

    cached_icon = icon_dir / f"{source['id']}.png"
    assert item["icon_url"] == f"/storage/data/avatars/sites/{source['id']}.png"
    assert cached_icon.read_bytes() == b"remote-site-icon"
    assert not stale_icon.exists()
    assert sessions[0].calls[0]["url"] == remote_icon_url
    assert sessions[0].calls[0]["stream"] is True
    assert sessions[0].headers["Referer"] == source["entry_url"]


def test_site_icon_refresh_discovers_web_manifest_icon(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "manifest-icon-site"
    site_dir.mkdir()
    (site_dir / "manifest-icon.png").write_bytes(b"manifest icon")
    (site_dir / "site.webmanifest").write_text(
        '{"icons":[{"src":"manifest-icon.png","sizes":"192x192","type":"image/png"}]}',
        encoding="utf-8",
    )
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html><head><link rel="manifest" href="site.webmanifest"></head><body></body></html>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "Manifest Icon Fixture",
            "slug": "manifest-icon-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "enabled": True,
        }
    )

    item = syncer.refresh_site_icon(source["id"])

    assert item["icon_url"] == (site_dir / "manifest-icon.png").resolve().as_uri()


def test_site_icon_refresh_discovers_json_ld_and_lazy_logo(tmp_path: Path) -> None:
    db, _storage, syncer = make_app(tmp_path)
    site_dir = tmp_path / "structured-logo-site"
    site_dir.mkdir()
    (site_dir / "structured-logo.svg").write_text("<svg></svg>", encoding="utf-8")
    (site_dir / "lazy-logo.png").write_bytes(b"lazy logo")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html>
          <head>
            <script type="application/ld+json">
              {"@type":"Organization","logo":{"url":"structured-logo.svg"}}
            </script>
          </head>
          <body><img class="site-logo" data-lazy-src="lazy-logo.png" alt="site logo"></body>
        </html>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "Structured Logo Fixture",
            "slug": "structured-logo-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "enabled": True,
        }
    )

    item = syncer.refresh_site_icon(source["id"])

    assert item["icon_url"] == (site_dir / "structured-logo.svg").resolve().as_uri()


def test_reset_all_icons_refreshes_up_and_site_icons(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    db, _storage, syncer = make_app(tmp_path)
    db.upsert_subscription("123", "旧名称", avatar_url="https://example.test/old.jpg")
    subscription_total = len(db.list_subscriptions(include_paused=True))
    site_dir = tmp_path / "reset-icon-site"
    site_dir.mkdir()
    (site_dir / "site-logo.png").write_bytes(b"fake png")
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <html><head><link rel="icon" href="site-logo.png"></head><body></body></html>
        """,
        encoding="utf-8",
    )
    source = db.create_site_source(
        {
            "name": "Reset Icon Fixture",
            "slug": "reset-icon-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "icon_url": "https://example.test/old-site.png",
            "enabled": True,
        }
    )

    class FakeAuth:
        def get_cookie_state(self):
            return SimpleNamespace(cookie=None)

        def fetch_up_profile(self, uid: str, _cookie: str | None = None) -> dict:
            return {"uid": uid, "uname": "新名称", "face": "https://example.test/new.jpg"}

    monkeypatch.setattr(app_main, "db", db)
    monkeypatch.setattr(app_main, "site_syncer", syncer)
    monkeypatch.setattr(app_main, "auth", FakeAuth())
    monkeypatch.setattr(app_main, "_sleep_before_avatar_refresh", lambda _index, _previous_error=None: 0)
    client = TestClient(app_main.app)

    result = client.post("/api/settings/reset-icons").json()

    assert result["ok"] is True
    assert result["result"]["subscriptions"]["updated"] == subscription_total
    assert result["result"]["sites"]["updated"] == 1
    assert db.get_subscription("123")["avatar_url"] == "https://example.test/new.jpg"
    assert db.get_subscription("123")["uname"] == "新名称"
    assert db.get_site_source(source["id"])["icon_url"] == (site_dir / "site-logo.png").resolve().as_uri()


def test_reset_all_icons_clears_stale_icons_when_missing(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    db, _storage, syncer = make_app(tmp_path)
    db.upsert_subscription("123", "旧名称", avatar_url="https://example.test/old.jpg")
    site_dir = tmp_path / "missing-icon-site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("<!doctype html><html><body>No icon</body></html>", encoding="utf-8")
    source = db.create_site_source(
        {
            "name": "Missing Icon Fixture",
            "slug": "missing-icon-fixture",
            **html_source(),
            "entry_url": (site_dir / "index.html").resolve().as_uri(),
            "icon_url": "https://example.test/old-site.png",
            "enabled": True,
        }
    )

    class FakeAuth:
        def get_cookie_state(self):
            return SimpleNamespace(cookie=None)

        def fetch_up_profile(self, uid: str, _cookie: str | None = None) -> dict:
            return {"uid": uid, "uname": f"UID {uid}", "face": None}

    monkeypatch.setattr(app_main, "db", db)
    monkeypatch.setattr(app_main, "site_syncer", syncer)
    monkeypatch.setattr(app_main, "auth", FakeAuth())
    monkeypatch.setattr(app_main, "_sleep_before_avatar_refresh", lambda _index, _previous_error=None: 0)
    client = TestClient(app_main.app)

    result = client.post("/api/settings/reset-icons").json()

    assert result["ok"] is True
    assert result["result"]["subscriptions"]["fallback"] >= 1
    assert result["result"]["sites"]["fallback"] == 1
    assert db.get_subscription("123")["avatar_url"] is None
    assert db.get_site_source(source["id"])["icon_url"] is None


def test_subscription_avatar_cache_uses_local_storage(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    _db, storage, _syncer = make_app(tmp_path)

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            yield b"avatar-bytes"

        def close(self) -> None:
            return None

    monkeypatch.setattr(app_main, "storage", storage)
    monkeypatch.setattr(app_main.requests, "get", lambda *_args, **_kwargs: FakeResponse())

    cached_url = app_main._cache_subscription_avatar("123", "https://i0.hdslb.com/bfs/face/avatar-test.jpg")

    assert cached_url == "/storage/data/avatars/up/123.jpg"
    assert (storage.config.data_dir / "avatars" / "up" / "123.jpg").read_bytes() == b"avatar-bytes"


def test_subscription_avatar_cache_accepts_dynamic_avatar(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    _db, storage, _syncer = make_app(tmp_path)

    class FakeResponse:
        headers = {"content-type": "image/webp"}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            yield b"dynamic-avatar-bytes"

        def close(self) -> None:
            return None

    monkeypatch.setattr(app_main, "storage", storage)
    monkeypatch.setattr(app_main.requests, "get", lambda *_args, **_kwargs: FakeResponse())

    cached_url = app_main._cache_subscription_avatar(
        "123",
        "https://i0.hdslb.com/bfs/garb/item/dynamic-avatar.webp",
    )

    assert cached_url == "/storage/data/avatars/up/123.webp"
    assert (storage.config.data_dir / "avatars" / "up" / "123.webp").read_bytes() == b"dynamic-avatar-bytes"


def test_subscription_avatar_cache_accepts_activity_dynamic_avatar(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    _db, storage, _syncer = make_app(tmp_path)

    class FakeResponse:
        headers = {"content-type": "image/gif"}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            yield b"activity-avatar-bytes"

        def close(self) -> None:
            return None

    monkeypatch.setattr(app_main, "storage", storage)
    monkeypatch.setattr(app_main.requests, "get", lambda *_args, **_kwargs: FakeResponse())

    cached_url = app_main._cache_subscription_avatar(
        "123",
        "https://i0.hdslb.com/bfs/activity-plat/static/20220506/example/activity-avatar.gif",
    )

    assert cached_url == "/storage/data/avatars/up/123.gif"
    assert (storage.config.data_dir / "avatars" / "up" / "123.gif").read_bytes() == b"activity-avatar-bytes"


def test_subscription_avatar_cache_rejects_site_icon(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    _db, storage, _syncer = make_app(tmp_path)
    called = False

    def fake_get(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("site icons should not be downloaded as avatars")

    monkeypatch.setattr(app_main, "storage", storage)
    monkeypatch.setattr(app_main.requests, "get", fake_get)

    url = app_main._cache_subscription_avatar("123", "https://www.bilibili.com/favicon.ico")

    assert url == "https://www.bilibili.com/favicon.ico"
    assert called is False


def test_reset_all_icons_throttles_subscription_avatar_refresh(tmp_path: Path, monkeypatch) -> None:
    from app import main as app_main

    db, _storage, syncer = make_app(tmp_path)
    db.upsert_subscription("123", "First")
    db.upsert_subscription("456", "Second")
    sleep_calls = []

    class FakeAuth:
        def get_cookie_state(self):
            return SimpleNamespace(cookie=None)

        def fetch_up_profile(self, uid: str, _cookie: str | None = None) -> dict:
            if uid == "123":
                raise RuntimeError("验证码校验")
            return {"uid": uid, "uname": f"UID {uid}", "face": f"https://i0.hdslb.com/bfs/face/{uid}.jpg"}

    def fake_sleep(index: int, previous_error: str | None = None) -> float:
        sleep_calls.append((index, previous_error))
        return 1.25

    monkeypatch.setattr(app_main, "db", db)
    monkeypatch.setattr(app_main, "site_syncer", syncer)
    monkeypatch.setattr(app_main, "auth", FakeAuth())
    monkeypatch.setattr(app_main, "_sleep_before_avatar_refresh", fake_sleep)
    client = TestClient(app_main.app)

    result = client.post("/api/settings/reset-icons").json()

    assert result["ok"] is True
    assert len(sleep_calls) == len(db.list_subscriptions(include_paused=True))
    assert sleep_calls[0] == (0, None)
    assert any(error == "验证码校验" for _index, error in sleep_calls[1:])
    assert result["result"]["subscriptions"]["wait_seconds"] == 1.25 * len(sleep_calls)


def test_avatar_refresh_risk_detection() -> None:
    from app import main as app_main

    assert app_main._looks_like_avatar_refresh_risk("验证码校验") is True
    assert app_main._looks_like_avatar_refresh_risk("HTTP 412") is True
    assert app_main._looks_like_avatar_refresh_risk("普通网络错误") is False


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
    assert parse_date("2026年6月23日(火) 21:39").isoformat() == "2026-06-23"
    assert parse_date("20260522").isoformat() == "2026-05-22"
    assert parse_date("22/05/2026").isoformat() == "2026-05-22"
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

    settings = client.get("/api/settings").json()
    assert settings["review_source_open_mode"] == "browser"
    saved_settings = client.put("/api/settings", json={**settings, "review_source_open_mode": "popup"}).json()
    assert saved_settings["review_source_open_mode"] == "popup"

    sidebar_counts = client.post("/api/sidebar-counts/refresh", json={"keys": ["sites"]}).json()["counts"]
    assert sidebar_counts["sites"] == 1

    suggestion = client.post("/api/site-sources/suggest", json={"entry_url": fixture_url("index.html")}).json()["suggestion"]
    assert suggestion["list_item_selector"] == ".post-card"

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
    assert client.get(f"/api/gallery/items?subscription_uids=site:{created['id']}").json()["items"] == []

    rules = client.put(
        "/api/site-rules",
        json={"mode": "both", "allow_keywords": ["测试"], "block_keywords": ["广告"], "use_regex": False},
    ).json()
    assert rules["mode"] == "both"
    assert rules["allow_keywords"] == ["测试"]
    assert rules["block_keywords"] == ["广告"]

    assert client.get("/api/site-filter/logs").json()["items"]
    log_clear = client.post("/api/site-filter/logs/clear").json()
    assert log_clear["ok"] is True
    assert log_clear["removed"] > 0
    assert client.get("/api/site-filter/logs").json()["items"] == []
    db.add_site_filter_log(created["id"], "https://example.test/again", "Again", "allowed", "重新生成")
    clear_result = client.post(f"/api/site-sources/{created['id']}/clear-delete").json()
    assert clear_result["ok"] is True
    assert clear_result["folders"] == 0
    assert db.get_site_source(created["id"]) is None
    assert db.list_site_posts() == []
    assert db.list_site_filter_logs() == []
    assert db.list_folders() == []
    assert not any(storage.config.images_dir.iterdir())
    assert not (storage.config.data_dir / "sites" / "fixture-api").exists()
