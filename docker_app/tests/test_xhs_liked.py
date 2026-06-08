from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig
from app.db import Database
from app.services.storage import StorageService
from app.services.xiaohongshu import XHS_SUBSCRIPTION_UID, XhsLikedSyncManager


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


def test_xhs_anchor_uses_latest_two_liked_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db, _storage, syncer = make_db(tmp_path)
    fake = FakeClient([{"notes": [note("newest"), note("backup")], "has_more": False}])
    monkeypatch.setattr(syncer, "_client", lambda: fake)

    result = syncer.set_anchor()

    assert result["ok"] is True
    assert db.get_xhs_liked_state()["anchor_note_ids"] == ["newest", "backup"]


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
