from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from starlette.responses import Response

from app.config import AppConfig
from app.db import Database
from app.services.storage import StorageService
from app.services.xiaohongshu import (
    XHS_BROWSER_LOGIN_URL,
    XHS_SUBSCRIPTION_UID,
    XHS_VERIFICATION_MESSAGE,
    XhsAuthService,
    XhsLikedSyncManager,
    XhsVerificationRequiredError,
    load_xhs_cookies_from_chrome,
    normalize_xhs_cookie_items,
)


class DummyAuth:
    def get_cookie_state(self):
        class State:
            cookie_json = {"a1": "test"}
            user = {"user_id": "u1", "nickname": "tester"}

        return State()

    def check_cookie(self):
        return {"ok": True}


class DummyIndexer:
    pass


class FakeClient:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get_liked_notes(self, cursor: str = "", num: int = 30):
        index = self.calls
        self.calls += 1
        return self.pages[index] if index < len(self.pages) else {"notes": [], "has_more": False, "cursor": ""}


class VerificationClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get_liked_notes(self, cursor: str = "", num: int = 30):
        raise XhsVerificationRequiredError(XHS_VERIFICATION_MESSAGE)


class LogoutTrackingAuth(DummyAuth):
    logged_out = False

    def logout(self):
        self.logged_out = True


def make_db(tmp_path: Path) -> tuple[Database, StorageService, XhsLikedSyncManager]:
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
    return db, storage, XhsLikedSyncManager(db, storage, DummyIndexer(), DummyAuth())


def note(note_id: str) -> dict:
    return {"note_id": note_id, "note_card": {"note_id": note_id, "display_title": note_id}}


def make_chrome_cookie_db(user_data_dir: Path, profile: str = "Default") -> Path:
    db_path = user_data_dir / profile / "Network" / "Cookies"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            create table cookies (
                host_key text,
                name text,
                value text,
                encrypted_value blob,
                last_access_utc integer,
                expires_utc integer,
                creation_utc integer
            )
            """
        )
        rows = [
            (".xiaohongshu.com", "a1", "chrome-a1", b"", 3, 0, 1),
            (".xiaohongshu.com", "webId", "chrome-webid", b"", 3, 0, 1),
            (".xiaohongshu.com", "web_session", "chrome-session", b"", 3, 0, 1),
            (".xiaohongshu.com", "version", "1", b"", 3, 0, 1),
            (".example.com", "a1", "ignored", b"", 3, 0, 1),
        ]
        conn.executemany("insert into cookies values (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_xhs_anchor_uses_latest_two_liked_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db, _storage, syncer = make_db(tmp_path)
    fake = FakeClient([{"notes": [note("newest"), note("backup")], "has_more": False}])
    monkeypatch.setattr(syncer, "_client", lambda: fake)

    result = syncer.set_anchor()

    assert result["ok"] is True
    assert db.get_xhs_liked_state()["anchor_note_ids"] == ["newest", "backup"]


def test_xhs_cookie_check_clears_login_after_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _storage, _syncer = make_db(tmp_path)
    db.update_xhs_auth_state(cookie_json='{"a1":"old-a1"}', user_json='{"user_id":"u1"}')

    class FailingCheckClient:
        cookies = {"a1": "old-a1"}

        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_self_info(self):
            raise XhsVerificationRequiredError(XHS_VERIFICATION_MESSAGE)

    monkeypatch.setattr("app.services.xiaohongshu.XhsApiClient", FailingCheckClient)

    result = XhsAuthService(db).check_cookie()

    assert result == {"ok": False, "message": XHS_VERIFICATION_MESSAGE, "requires_login": True}
    state = db.get_xhs_auth_state()
    assert state["cookie_json"] is None
    assert state["user_json"] is None


def test_xhs_cookie_import_saves_browser_cookie_and_checks_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _storage, _syncer = make_db(tmp_path)

    class SuccessfulCheckClient:
        def __init__(self, cookies, *args, **kwargs):
            self.cookies = dict(cookies)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_self_info(self):
            return {"user_id": "u1", "nickname": "tester", "guest": False}

    monkeypatch.setattr("app.services.xiaohongshu.XhsApiClient", SuccessfulCheckClient)

    result = XhsAuthService(db).import_cookie_text(
        "Cookie: a1=browser-a1; webId=browser-webid; web_session=session-value; Path=/; Secure"
    )

    state = db.get_xhs_auth_state()
    saved_cookies = json.loads(state["cookie_json"])
    assert result["ok"] is True
    assert state["qr_status"] == "imported"
    assert saved_cookies["a1"] == "browser-a1"
    assert saved_cookies["web_session"] == "session-value"
    assert "Path" not in saved_cookies


def test_xhs_cookie_import_rejects_document_cookie_without_session(tmp_path: Path) -> None:
    db, _storage, _syncer = make_db(tmp_path)

    with pytest.raises(RuntimeError, match="缺少 web_session"):
        XhsAuthService(db).import_cookie_text("a1=browser-a1; webId=browser-webid; gid=browser-gid")


def test_xhs_browser_login_opens_system_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db, _storage, _syncer = make_db(tmp_path)
    auth = XhsAuthService(db)
    opened_urls: list[str] = []

    def fake_open(url: str) -> bool:
        opened_urls.append(url)
        return True

    monkeypatch.setattr("app.services.xiaohongshu._open_system_browser", fake_open)

    result = auth.start_browser_login()
    state = db.get_xhs_auth_state()

    assert result["status"] == "browser_pending"
    assert result["url"] == XHS_BROWSER_LOGIN_URL
    assert result["opened"] is True
    assert opened_urls == [XHS_BROWSER_LOGIN_URL]
    assert state["qr_url"] == XHS_BROWSER_LOGIN_URL
    assert state["qr_status"] == "browser_pending"


def test_xhs_loads_cookie_from_chrome_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_data_dir = tmp_path / "Chrome"
    make_chrome_cookie_db(user_data_dir)
    monkeypatch.setenv("XHS_CHROME_USER_DATA_DIR", str(user_data_dir))

    cookies, profile = load_xhs_cookies_from_chrome()

    assert profile == "Default"
    assert cookies["a1"] == "chrome-a1"
    assert cookies["webId"] == "chrome-webid"
    assert cookies["web_session"] == "chrome-session"
    assert "version" not in cookies


def test_xhs_cookie_normalize_encodes_non_ascii_values() -> None:
    cookies = normalize_xhs_cookie_items({"nickname": "小红书用户", "version": "1", "bad name": "ignored"})
    response = Response("ok")

    response.set_cookie("nickname", cookies["nickname"])

    assert cookies["nickname"] == "%E5%B0%8F%E7%BA%A2%E4%B9%A6%E7%94%A8%E6%88%B7"
    assert "version" not in cookies
    assert "bad name" not in cookies


def test_xhs_browser_login_status_checks_captured_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_data_dir = tmp_path / "Chrome"
    make_chrome_cookie_db(user_data_dir)
    monkeypatch.setenv("XHS_CHROME_USER_DATA_DIR", str(user_data_dir))
    monkeypatch.setattr("app.services.xiaohongshu._open_system_browser", lambda url: True)
    db, _storage, _syncer = make_db(tmp_path)
    auth = XhsAuthService(db)
    auth.start_browser_login()

    class SuccessfulCheckClient:
        def __init__(self, cookies, *args, **kwargs):
            self.cookies = dict(cookies)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_self_info(self):
            return {"user_id": "u1", "nickname": "tester", "guest": False}

    monkeypatch.setattr("app.services.xiaohongshu.XhsApiClient", SuccessfulCheckClient)

    result = auth.browser_login_status()

    assert result["status"] == "done"
    assert result["ok"] is True
    assert result["uid"] == "u1"
    assert result["profile"] == "Default"
    saved_cookies = json.loads(db.get_xhs_auth_state()["cookie_json"])
    assert saved_cookies["web_session"] == "chrome-session"


def test_xhs_anchor_marks_auth_required_after_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, storage, _syncer = make_db(tmp_path)
    auth = LogoutTrackingAuth()
    syncer = XhsLikedSyncManager(db, storage, DummyIndexer(), auth)
    monkeypatch.setattr(syncer, "_client", lambda: VerificationClient())

    with pytest.raises(XhsVerificationRequiredError):
        syncer.set_anchor()

    state = db.get_xhs_liked_state()
    assert auth.logged_out is True
    assert state["last_status"] == "auth_required"
    assert state["last_message"] == XHS_VERIFICATION_MESSAGE


def test_xhs_incremental_stops_at_existing_anchor_and_resets_to_latest_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _storage, syncer = make_db(tmp_path)
    db.update_xhs_liked_state(anchor_note_ids=["old-main", "old-backup"], anchor_set_at="2026-01-01")
    fake = FakeClient([{"notes": [note("n1"), note("n2"), note("old-backup")], "has_more": False}])
    processed: list[str] = []
    monkeypatch.setattr(syncer, "_client", lambda: fake)
    monkeypatch.setattr(syncer, "_process_card", lambda _client, card, cooperate=None: processed.append(card["note_id"]) or {"downloaded": 0})

    stats = syncer.execute_pull()

    assert stats["new"] == 2
    assert processed == ["n1", "n2"]
    assert db.get_xhs_liked_state()["anchor_note_ids"] == ["n1", "n2"]


def test_xhs_incremental_keeps_old_anchor_when_anchor_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _storage, syncer = make_db(tmp_path)
    db.update_xhs_liked_state(anchor_note_ids=["old-main", "old-backup"], anchor_set_at="2026-01-01")
    fake = FakeClient([{"notes": [note("n1"), note("n2")], "has_more": False}])
    monkeypatch.setattr(syncer, "_client", lambda: fake)

    with pytest.raises(RuntimeError, match="旧锚点"):
        syncer.execute_pull()

    state = db.get_xhs_liked_state()
    assert state["anchor_note_ids"] == ["old-main", "old-backup"]
    assert state["last_status"] == "failed"


def test_gallery_source_kind_xhs_matches_only_xhs_subscription(tmp_path: Path) -> None:
    db, _storage, _syncer = make_db(tmp_path)
    for folder_name, uid in [
        ("xhs-folder", XHS_SUBSCRIPTION_UID),
        ("site-folder", "site:1"),
        ("up-folder", "12345"),
    ]:
        db.upsert_folder(
            {
                "folder_name": folder_name,
                "title": folder_name,
                "pub_ts": 1,
                "pub_time": "1970-01-01 00:00:01",
                "top_dynamic_id": folder_name,
                "source_dynamic_id": folder_name,
                "subscription_uid": uid,
                "subscription_name": uid,
                "has_images": True,
                "has_livephoto": False,
            }
        )
        db.replace_gallery_index(
            folder_name,
            {
                "title": folder_name,
                "pub_ts": 1,
                "pub_time": "1970-01-01 00:00:01",
                "top_dynamic_id": folder_name,
                "source_dynamic_id": folder_name,
                "subscription_uid": uid,
                "subscription_name": uid,
                "has_images": True,
                "image_count": 1,
                "asset_count": 1,
            },
            [],
        )

    assert [item["folder_name"] for item in db.query_folder_index(source_kind="xhs")["items"]] == ["xhs-folder"]
    assert [item["folder_name"] for item in db.query_folder_index(source_kind="site")["items"]] == ["site-folder"]
    assert [item["folder_name"] for item in db.query_folder_index(source_kind="up")["items"]] == ["up-folder"]
