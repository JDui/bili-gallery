from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.services.utils import dumps_json, loads_json, now_iso


DEFAULT_SETTINGS = {
    "host_mid": 31968078,
    "pull_images": True,
    "image_min_count": 6,
    "pull_livephoto": True,
    "include_forwarded": True,
    "subscription_policy_migrated": False,
    "image_threshold_default_migrated": False,
    "reload_all_once": False,
    "auto_load_enabled": True,
    "download_sleep": 0.2,
    "scheduler_enabled": False,
    "scheduler_interval_hours": 12,
    "ad_filter_enabled": True,
    "ad_filter_keywords": [
        "推广",
        "广告",
        "合作",
        "恰饭",
        "课程",
        "优惠",
        "抽奖",
        "预约",
        "链接",
    ],
    "long_image_ratio": 3.0,
    "gallery_index_version": 0,
    "gallery_index_rebuilt_at": None,
    "gallery_index_rebuilding": False,
    "auto_gallery_index_check": True,
}
GALLERY_INDEX_VERSION = 1


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        conn.execute("pragma journal_mode = wal")
        conn.execute("pragma synchronous = normal")
        conn.execute("pragma temp_store = memory")
        conn.execute("pragma cache_size = -12000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists settings (
                    key text primary key,
                    value text not null
                );

                create table if not exists auth_state (
                    id integer primary key check (id = 1),
                    cookie text,
                    cookie_json text,
                    user_json text,
                    qr_key text,
                    qr_url text,
                    qr_status text,
                    qr_created_at text
                );

                create table if not exists folders (
                    folder_name text primary key,
                    title text,
                    text_prefix text,
                    pub_ts integer not null default 0,
                    pub_time text not null,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    has_images integer not null default 0,
                    has_livephoto integer not null default 0,
                    status text not null default 'active',
                    review_status text not null default 'approved',
                    review_reason text,
                    metadata_json text,
                    created_at text not null,
                    updated_at text not null,
                    unique(top_dynamic_id, source_dynamic_id)
                );

                create table if not exists assets (
                    id integer primary key autoincrement,
                    folder_name text not null references folders(folder_name) on delete cascade,
                    media_type text not null,
                    pair_index integer not null default 0,
                    filename text not null,
                    rel_path text not null,
                    thumb_rel_path text,
                    cover_rel_path text,
                    reverse_rel_path text,
                    width integer,
                    height integer,
                    status text not null default 'ready',
                    metadata_json text,
                    created_at text not null,
                    updated_at text not null,
                    unique(folder_name, media_type, filename)
                );

                create table if not exists task_runs (
                    id integer primary key autoincrement,
                    task_type text not null,
                    status text not null,
                    message text,
                    details_json text,
                    created_at text not null,
                    finished_at text
                );

                create table if not exists review_items (
                    id integer primary key autoincrement,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    folder_name_candidate text,
                    text_excerpt text,
                    reasons_json text not null,
                    payload_json text not null,
                    status text not null default 'pending',
                    created_at text not null,
                    updated_at text not null,
                    unique(top_dynamic_id, source_dynamic_id)
                );

                create table if not exists filter_logs (
                    id integer primary key autoincrement,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    folder_name_candidate text,
                    decision text not null,
                    reasons_json text not null,
                    created_at text not null
                );

                create table if not exists blacklist_items (
                    id integer primary key autoincrement,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    folder_name text,
                    title text,
                    reason text,
                    created_at text not null,
                    unique(top_dynamic_id, source_dynamic_id)
                );

                create table if not exists deleted_pair_marks (
                    id integer primary key autoincrement,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    folder_name text,
                    pair_index integer not null,
                    reason text,
                    created_at text not null,
                    unique(top_dynamic_id, source_dynamic_id, pair_index)
                );

                create table if not exists trash_items (
                    id integer primary key autoincrement,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    folder_name text not null,
                    title text,
                    folder_json text not null,
                    assets_json text not null,
                    deleted_at text not null,
                    restored_at text,
                    unique(top_dynamic_id, source_dynamic_id)
                );

                create table if not exists subscriptions (
                    uid text primary key,
                    uname text,
                    status text not null default 'active',
                    pull_images integer not null default 1,
                    image_min_count integer not null default 1,
                    pull_livephoto integer not null default 1,
                    include_forwarded integer not null default 1,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists folder_index (
                    folder_name text primary key references folders(folder_name) on delete cascade,
                    title text,
                    text_prefix text,
                    pub_ts integer not null default 0,
                    pub_time text not null,
                    top_dynamic_id text not null,
                    source_dynamic_id text not null,
                    subscription_uid text,
                    subscription_name text,
                    has_images integer not null default 0,
                    has_livephoto integer not null default 0,
                    is_favorite integer not null default 0,
                    review_status text not null default 'approved',
                    review_reason text,
                    image_count integer not null default 0,
                    livephoto_count integer not null default 0,
                    asset_count integer not null default 0,
                    preview_assets_json text not null default '[]',
                    year_key text,
                    month_key text,
                    updated_at text not null
                );

                create table if not exists pair_index (
                    item_key text primary key,
                    folder_name text not null references folders(folder_name) on delete cascade,
                    pair_index integer not null,
                    title text,
                    pub_ts integer not null default 0,
                    pub_time text not null,
                    subscription_uid text,
                    subscription_name text,
                    is_favorite integer not null default 0,
                    has_image integer not null default 0,
                    has_livephoto integer not null default 0,
                    preview_url text,
                    preview_kind text,
                    thumb_url text,
                    display_ratio text,
                    image_json text,
                    livephoto_json text,
                    year_key text,
                    month_key text,
                    updated_at text not null,
                    unique(folder_name, pair_index)
                );

                create index if not exists idx_folders_pub_ts on folders(pub_ts desc);
                create index if not exists idx_folders_review_pub_ts on folders(review_status, pub_ts desc);
                create index if not exists idx_assets_folder on assets(folder_name, media_type, pair_index);
                create index if not exists idx_assets_folder_pair_media on assets(folder_name, pair_index, media_type);
                create index if not exists idx_review_status on review_items(status, updated_at desc);
                create index if not exists idx_filter_logs_created on filter_logs(created_at desc);
                create index if not exists idx_blacklist_items_dynamic on blacklist_items(top_dynamic_id, source_dynamic_id);
                create index if not exists idx_deleted_pair_marks_dynamic on deleted_pair_marks(top_dynamic_id, source_dynamic_id, pair_index);
                create index if not exists idx_trash_items_deleted on trash_items(deleted_at desc);
                create index if not exists idx_subscriptions_status on subscriptions(status, updated_at desc);
                create index if not exists idx_folder_index_pub_ts on folder_index(pub_ts desc, folder_name desc);
                create index if not exists idx_folder_index_subscription_pub_ts on folder_index(subscription_uid, pub_ts desc, folder_name desc);
                create index if not exists idx_folder_index_review_pub_ts on folder_index(review_status, pub_ts desc, folder_name desc);
                create index if not exists idx_folder_index_favorite_pub_ts on folder_index(is_favorite, pub_ts desc, folder_name desc);
                create index if not exists idx_pair_index_pub_ts on pair_index(pub_ts desc, folder_name desc, pair_index asc);
                create index if not exists idx_pair_index_subscription_pub_ts on pair_index(subscription_uid, pub_ts desc, folder_name desc, pair_index asc);
                create index if not exists idx_pair_index_folder_pair on pair_index(folder_name, pair_index asc);
                """
            )
            self._ensure_column(conn, "folders", "subscription_uid", "text")
            self._ensure_column(conn, "folders", "subscription_name", "text")
            self._ensure_column(conn, "folders", "is_favorite", "integer not null default 0")
            conn.execute(
                "create index if not exists idx_folders_subscription_pub_ts on folders(subscription_uid, pub_ts desc)"
            )
            self._ensure_column(conn, "subscriptions", "pull_images", "integer not null default 1")
            self._ensure_column(conn, "subscriptions", "image_min_count", "integer not null default 1")
            self._ensure_column(conn, "subscriptions", "pull_livephoto", "integer not null default 1")
            self._ensure_column(conn, "subscriptions", "include_forwarded", "integer not null default 1")
            self._ensure_default_settings(conn)
            conn.execute("insert or ignore into auth_state(id, qr_status) values (1, 'idle')")
            self._ensure_default_subscription(conn)
            self._migrate_subscription_policies(conn)
            self._migrate_image_threshold_defaults(conn)
            self._backfill_folder_subscriptions(conn)

    def _ensure_default_settings(self, conn: sqlite3.Connection) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "insert or ignore into settings(key, value) values (?, ?)",
                (key, dumps_json(value)),
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        if column in columns:
            return
        conn.execute(f"alter table {table} add column {column} {definition}")

    def _ensure_default_subscription(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("select value from settings where key = 'host_mid'").fetchone()
        host_mid = loads_json(row["value"], DEFAULT_SETTINGS["host_mid"]) if row else DEFAULT_SETTINGS["host_mid"]
        uid = str(host_mid)
        now = now_iso()
        defaults = self._subscription_defaults(conn)
        conn.execute(
            """
            insert into subscriptions(
                uid, uname, status, pull_images, image_min_count, pull_livephoto, include_forwarded, created_at, updated_at
            )
            values (?, ?, 'active', ?, ?, ?, ?, ?, ?)
            on conflict(uid) do update set updated_at = excluded.updated_at
            """,
            (uid, None, defaults["pull_images"], defaults["image_min_count"], defaults["pull_livephoto"], defaults["include_forwarded"], now, now),
        )

    def _subscription_defaults(self, conn: sqlite3.Connection) -> dict[str, int]:
        rows = conn.execute(
            """
            select key, value from settings
            where key in ('pull_images', 'image_min_count', 'pull_livephoto', 'include_forwarded')
            """
        ).fetchall()
        values = {row["key"]: loads_json(row["value"], DEFAULT_SETTINGS.get(row["key"])) for row in rows}
        pull_images_enabled = bool(values.get("pull_images", DEFAULT_SETTINGS["pull_images"]))
        image_min_count = self._normalize_image_threshold(
            values.get("image_min_count", DEFAULT_SETTINGS["image_min_count"]),
            DEFAULT_SETTINGS["image_min_count"],
        )
        return {
            "pull_images": 1 if pull_images_enabled and image_min_count >= 0 else 0,
            "image_min_count": image_min_count if pull_images_enabled else -1,
            "pull_livephoto": 1 if values.get("pull_livephoto", DEFAULT_SETTINGS["pull_livephoto"]) else 0,
            "include_forwarded": 1 if values.get("include_forwarded", DEFAULT_SETTINGS["include_forwarded"]) else 0,
        }

    def _migrate_subscription_policies(self, conn: sqlite3.Connection) -> None:
        marker_row = conn.execute(
            "select value from settings where key = 'subscription_policy_migrated'"
        ).fetchone()
        migrated = loads_json(marker_row["value"], False) if marker_row else False
        if migrated:
            return
        defaults = self._subscription_defaults(conn)
        conn.execute(
            """
            update subscriptions
            set pull_images = ?,
                image_min_count = ?,
                pull_livephoto = ?,
                include_forwarded = ?,
                updated_at = ?
            """,
            (
                defaults["pull_images"],
                defaults["image_min_count"],
                defaults["pull_livephoto"],
                defaults["include_forwarded"],
                now_iso(),
            ),
        )
        conn.execute(
            """
            insert into settings(key, value) values (?, ?)
            on conflict(key) do update set value = excluded.value
            """,
            ("subscription_policy_migrated", dumps_json(True)),
        )

    def _migrate_image_threshold_defaults(self, conn: sqlite3.Connection) -> None:
        marker_row = conn.execute(
            "select value from settings where key = 'image_threshold_default_migrated'"
        ).fetchone()
        migrated = loads_json(marker_row["value"], False) if marker_row else False
        if migrated:
            return
        default_threshold = int(DEFAULT_SETTINGS["image_min_count"])
        current_row = conn.execute(
            "select value from settings where key = 'image_min_count'"
        ).fetchone()
        current_threshold = loads_json(current_row["value"], default_threshold) if current_row else default_threshold
        if int(current_threshold or 0) <= 1:
            conn.execute(
                """
                insert into settings(key, value) values (?, ?)
                on conflict(key) do update set value = excluded.value
                """,
                ("image_min_count", dumps_json(default_threshold)),
            )
        conn.execute(
            """
            update subscriptions
            set image_min_count = ?,
                updated_at = ?
            where image_min_count is null or image_min_count <= 1
            """,
            (default_threshold, now_iso()),
        )
        conn.execute(
            """
            insert into settings(key, value) values (?, ?)
            on conflict(key) do update set value = excluded.value
            """,
            ("image_threshold_default_migrated", dumps_json(True)),
        )

    def _backfill_folder_subscriptions(self, conn: sqlite3.Connection) -> None:
        default_row = conn.execute(
            "select uid, uname from subscriptions order by created_at asc limit 1"
        ).fetchone()
        if not default_row:
            return
        default_uid = str(default_row["uid"])
        default_name = default_row["uname"]
        conn.execute(
            """
            update folders
            set subscription_uid = coalesce(subscription_uid, ?),
                subscription_name = coalesce(subscription_name, ?)
            where subscription_uid is null or subscription_uid = ''
            """,
            (default_uid, default_name),
        )

    def get_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("select key, value from settings").fetchall()
        output = dict(DEFAULT_SETTINGS)
        for row in rows:
            output[row["key"]] = loads_json(row["value"], DEFAULT_SETTINGS.get(row["key"]))
        return output

    def save_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_settings()
        current.update(updates)
        with self.connect() as conn:
            for key, value in current.items():
                conn.execute(
                    """
                    insert into settings(key, value) values (?, ?)
                    on conflict(key) do update set value = excluded.value
                    """,
                    (key, dumps_json(value)),
                )
        return current

    def set_gallery_index_rebuilding(self, rebuilding: bool) -> None:
        self.save_settings({"gallery_index_rebuilding": bool(rebuilding)})

    def mark_gallery_index_rebuilt(self) -> None:
        self.save_settings(
            {
                "gallery_index_version": GALLERY_INDEX_VERSION,
                "gallery_index_rebuilt_at": now_iso(),
                "gallery_index_rebuilding": False,
            }
        )

    def get_auth_state(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("select * from auth_state where id = 1").fetchone()
        if not row:
            return {"qr_status": "idle"}
        return dict(row)

    def update_auth_state(self, **kwargs: Any) -> None:
        if not kwargs:
            return
        assignments = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values())
        with self.connect() as conn:
            conn.execute(f"update auth_state set {assignments} where id = 1", values)

    def get_folder(self, folder_name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from folders where folder_name = ?", (folder_name,)).fetchone()
        return dict(row) if row else None

    def list_subscriptions(self, include_paused: bool = True) -> list[dict[str, Any]]:
        sql = "select * from subscriptions"
        params: tuple[Any, ...] = ()
        if not include_paused:
            sql += " where status = ?"
            params = ("active",)
        sql += " order by updated_at desc, uid asc"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_subscription(self, uid: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from subscriptions where uid = ?", (str(uid),)).fetchone()
        return dict(row) if row else None

    def upsert_subscription(
        self,
        uid: str,
        uname: str | None = None,
        status: str = "active",
        pull_images: bool | None = None,
        image_min_count: int | None = None,
        pull_livephoto: bool | None = None,
        include_forwarded: bool | None = None,
    ) -> dict[str, Any]:
        now = now_iso()
        with self.connect() as conn:
            existing = conn.execute("select * from subscriptions where uid = ?", (str(uid),)).fetchone()
            defaults = self._subscription_defaults(conn)
            normalized_threshold = self._normalize_image_threshold(
                image_min_count
                if image_min_count is not None
                else (existing["image_min_count"] if existing else defaults["image_min_count"]),
                defaults["image_min_count"],
            )
            pull_images_flag = (
                1
                if pull_images
                else 0
                if pull_images is not None
                else int(existing["pull_images"])
                if existing
                else defaults["pull_images"]
            )
            if normalized_threshold < 0:
                pull_images_flag = 0
            payload = {
                "uid": str(uid),
                "uname": uname if uname is not None else (existing["uname"] if existing else None),
                "status": status if status is not None else (existing["status"] if existing else "active"),
                "pull_images": pull_images_flag,
                "image_min_count": normalized_threshold,
                "pull_livephoto": 1 if pull_livephoto else 0 if pull_livephoto is not None else int(existing["pull_livephoto"]) if existing else defaults["pull_livephoto"],
                "include_forwarded": 1 if include_forwarded else 0 if include_forwarded is not None else int(existing["include_forwarded"]) if existing else defaults["include_forwarded"],
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            conn.execute(
                """
                insert into subscriptions(
                    uid, uname, status, pull_images, image_min_count, pull_livephoto, include_forwarded, created_at, updated_at
                )
                values (:uid, :uname, :status, :pull_images, :image_min_count, :pull_livephoto, :include_forwarded, :created_at, :updated_at)
                on conflict(uid) do update set
                    uname = excluded.uname,
                    status = excluded.status,
                    pull_images = excluded.pull_images,
                    image_min_count = excluded.image_min_count,
                    pull_livephoto = excluded.pull_livephoto,
                    include_forwarded = excluded.include_forwarded,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
        return self.get_subscription(uid) or {
            "uid": str(uid),
            "uname": uname,
            "status": status,
            "pull_images": 1 if pull_images and self._normalize_image_threshold(image_min_count, DEFAULT_SETTINGS["image_min_count"]) >= 0 else 0,
            "image_min_count": self._normalize_image_threshold(image_min_count, DEFAULT_SETTINGS["image_min_count"]),
            "pull_livephoto": 1 if pull_livephoto else 0,
            "include_forwarded": 1 if include_forwarded else 0,
        }

    def update_subscription_status(self, uid: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "update subscriptions set status = ?, updated_at = ? where uid = ?",
                (status, now_iso(), str(uid)),
            )

    def update_subscription_settings(self, uid: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_subscription(uid)
        if not current:
            return None
        normalized_threshold = self._normalize_image_threshold(
            updates.get("image_min_count", current.get("image_min_count", DEFAULT_SETTINGS["image_min_count"])),
            current.get("image_min_count", DEFAULT_SETTINGS["image_min_count"]),
        )
        payload = {
            "uid": str(uid),
            "uname": current.get("uname"),
            "status": current.get("status", "active"),
            "pull_images": bool(updates.get("pull_images", current.get("pull_images"))) and normalized_threshold >= 0,
            "image_min_count": normalized_threshold,
            "pull_livephoto": bool(updates.get("pull_livephoto", current.get("pull_livephoto"))),
            "include_forwarded": bool(updates.get("include_forwarded", current.get("include_forwarded"))),
        }
        return self.upsert_subscription(**payload)

    def _normalize_image_threshold(self, value: Any, fallback: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = int(fallback)
        return max(-1, min(12, number))

    def delete_subscription(self, uid: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from subscriptions where uid = ?", (str(uid),))

    def upsert_folder(self, folder: dict[str, Any]) -> None:
        payload = {
            "title": folder.get("title", ""),
            "text_prefix": folder.get("text_prefix", ""),
            "pub_ts": int(folder.get("pub_ts", 0)),
            "pub_time": folder.get("pub_time", ""),
            "top_dynamic_id": str(folder.get("top_dynamic_id", "")),
            "source_dynamic_id": str(folder.get("source_dynamic_id", "")),
            "subscription_uid": str(folder.get("subscription_uid") or ""),
            "subscription_name": folder.get("subscription_name"),
            "has_images": 1 if folder.get("has_images") else 0,
            "has_livephoto": 1 if folder.get("has_livephoto") else 0,
            "is_favorite": 1 if folder.get("is_favorite") else 0,
            "status": folder.get("status", "active"),
            "review_status": folder.get("review_status", "approved"),
            "review_reason": folder.get("review_reason"),
            "metadata_json": dumps_json(folder.get("metadata", {})),
            "updated_at": now_iso(),
        }
        created_at = folder.get("created_at", payload["updated_at"])
        with self.connect() as conn:
            conn.execute(
                """
                insert into folders(
                    folder_name, title, text_prefix, pub_ts, pub_time, top_dynamic_id, source_dynamic_id,
                    subscription_uid, subscription_name, has_images, has_livephoto, is_favorite, status, review_status, review_reason,
                    metadata_json, created_at, updated_at
                )
                values(
                    :folder_name, :title, :text_prefix, :pub_ts, :pub_time, :top_dynamic_id, :source_dynamic_id,
                    :subscription_uid, :subscription_name, :has_images, :has_livephoto, :is_favorite, :status, :review_status, :review_reason,
                    :metadata_json, :created_at, :updated_at
                )
                on conflict(folder_name) do update set
                    title = excluded.title,
                    text_prefix = excluded.text_prefix,
                    pub_ts = excluded.pub_ts,
                    pub_time = excluded.pub_time,
                    top_dynamic_id = excluded.top_dynamic_id,
                    source_dynamic_id = excluded.source_dynamic_id,
                    subscription_uid = excluded.subscription_uid,
                    subscription_name = coalesce(excluded.subscription_name, folders.subscription_name),
                    has_images = excluded.has_images,
                    has_livephoto = excluded.has_livephoto,
                    status = excluded.status,
                    review_status = excluded.review_status,
                    review_reason = excluded.review_reason,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                {"folder_name": folder["folder_name"], "created_at": created_at, **payload},
            )

    def replace_folder_assets(self, folder_name: str, media_type: str, assets: list[dict[str, Any]]) -> None:
        now = now_iso()
        with self.connect() as conn:
            conn.execute(
                "delete from assets where folder_name = ? and media_type = ?",
                (folder_name, media_type),
            )
            for asset in assets:
                conn.execute(
                    """
                    insert into assets(
                        folder_name, media_type, pair_index, filename, rel_path, thumb_rel_path,
                        cover_rel_path, reverse_rel_path, width, height, status, metadata_json,
                        created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        folder_name,
                        media_type,
                        int(asset.get("pair_index", 0)),
                        asset["filename"],
                        asset["rel_path"],
                        asset.get("thumb_rel_path"),
                        asset.get("cover_rel_path"),
                        asset.get("reverse_rel_path"),
                        asset.get("width"),
                        asset.get("height"),
                        asset.get("status", "ready"),
                        dumps_json(asset.get("metadata", {})),
                        now,
                        now,
                    ),
                )

    def get_folder_by_dynamic(self, top_dynamic_id: str, source_dynamic_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select * from folders
                where top_dynamic_id = ? and source_dynamic_id = ?
                limit 1
                """,
                (str(top_dynamic_id), str(source_dynamic_id)),
            ).fetchone()
        return dict(row) if row else None

    def list_folders(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from folders order by pub_ts desc, folder_name desc").fetchall()
        return [dict(row) for row in rows]

    def list_all_assets(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from assets order by folder_name asc, pair_index asc, media_type asc, filename asc"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_assets_for_folder(self, folder_name: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from assets where folder_name = ? order by media_type, pair_index, filename",
                (folder_name,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_folder_favorite(self, folder_name: str, is_favorite: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "update folders set is_favorite = ?, updated_at = ? where folder_name = ?",
                (1 if is_favorite else 0, now_iso(), folder_name),
            )
            conn.execute(
                "update folder_index set is_favorite = ?, updated_at = ? where folder_name = ?",
                (1 if is_favorite else 0, now_iso(), folder_name),
            )
            conn.execute(
                "update pair_index set is_favorite = ?, updated_at = ? where folder_name = ?",
                (1 if is_favorite else 0, now_iso(), folder_name),
            )

    def delete_asset(self, asset_id: int) -> None:
        with self.connect() as conn:
            conn.execute("delete from assets where id = ?", (asset_id,))

    def add_deleted_pair_mark(
        self,
        top_dynamic_id: str,
        source_dynamic_id: str,
        folder_name: str,
        pair_index: int,
        reason: str = "手动删除",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into deleted_pair_marks(
                    top_dynamic_id, source_dynamic_id, folder_name, pair_index, reason, created_at
                )
                values (?, ?, ?, ?, ?, ?)
                on conflict(top_dynamic_id, source_dynamic_id, pair_index) do update set
                    folder_name = excluded.folder_name,
                    reason = excluded.reason
                """,
                (str(top_dynamic_id), str(source_dynamic_id), folder_name, int(pair_index), reason, now_iso()),
            )

    def list_deleted_pair_indices(self, top_dynamic_id: str, source_dynamic_id: str) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select pair_index from deleted_pair_marks
                where top_dynamic_id = ? and source_dynamic_id = ?
                order by pair_index asc
                """,
                (str(top_dynamic_id), str(source_dynamic_id)),
            ).fetchall()
        return {int(row["pair_index"]) for row in rows}

    def has_deleted_pair_marks(self, top_dynamic_id: str, source_dynamic_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select 1 from deleted_pair_marks
                where top_dynamic_id = ? and source_dynamic_id = ?
                limit 1
                """,
                (str(top_dynamic_id), str(source_dynamic_id)),
            ).fetchone()
        return bool(row)

    def clear_deleted_pair_marks(self, top_dynamic_id: str, source_dynamic_id: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "delete from deleted_pair_marks where top_dynamic_id = ? and source_dynamic_id = ?",
                (str(top_dynamic_id), str(source_dynamic_id)),
            )
            return int(cursor.rowcount or 0)

    def delete_folder_if_empty(self, folder_name: str) -> None:
        with self.connect() as conn:
            count = conn.execute(
                "select count(*) from assets where folder_name = ?",
                (folder_name,),
            ).fetchone()[0]
            if count == 0:
                conn.execute("delete from folders where folder_name = ?", (folder_name,))

    def create_task_run(self, task_type: str, status: str, message: str = "", details: dict[str, Any] | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into task_runs(task_type, status, message, details_json, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (task_type, status, message, dumps_json(details or {}), now_iso()),
            )
            return int(cur.lastrowid)

    def finish_task_run(self, task_id: int, status: str, message: str = "", details: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update task_runs
                set status = ?, message = ?, details_json = ?, finished_at = ?
                where id = ?
                """,
                (status, message, dumps_json(details or {}), now_iso(), task_id),
            )

    def last_task_run(self, task_type: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from task_runs where task_type = ? order by id desc limit 1",
                (task_type,),
            ).fetchone()
        return dict(row) if row else None

    def list_task_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from task_runs order by id desc limit ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task_run(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from task_runs where id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def clear_finished_task_runs(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "delete from task_runs where status != 'running'"
            )
            return int(cursor.rowcount or 0)

    def upsert_review_item(
        self,
        top_dynamic_id: str,
        source_dynamic_id: str,
        folder_name_candidate: str,
        text_excerpt: str,
        reasons: list[str],
        payload: dict[str, Any],
        status: str = "pending",
    ) -> None:
        now = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                insert into review_items(
                    top_dynamic_id, source_dynamic_id, folder_name_candidate, text_excerpt,
                    reasons_json, payload_json, status, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(top_dynamic_id, source_dynamic_id) do update set
                    folder_name_candidate = excluded.folder_name_candidate,
                    text_excerpt = excluded.text_excerpt,
                    reasons_json = excluded.reasons_json,
                    payload_json = excluded.payload_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    str(top_dynamic_id),
                    str(source_dynamic_id),
                    folder_name_candidate,
                    text_excerpt,
                    dumps_json(reasons),
                    dumps_json(payload),
                    status,
                    now,
                    now,
                ),
            )

    def list_review_items(self, status: str = "pending") -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from review_items where status = ? order by updated_at desc",
                (status,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_review_item(self, item_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from review_items where id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def set_review_status(self, item_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "update review_items set status = ?, updated_at = ? where id = ?",
                (status, now_iso(), item_id),
            )

    def get_review_status(self, top_dynamic_id: str, source_dynamic_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select status from review_items
                where top_dynamic_id = ? and source_dynamic_id = ?
                limit 1
                """,
                (str(top_dynamic_id), str(source_dynamic_id)),
            ).fetchone()
        return row["status"] if row else None

    def add_blacklist_item(
        self,
        top_dynamic_id: str,
        source_dynamic_id: str,
        folder_name: str,
        title: str,
        reason: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into blacklist_items(
                    top_dynamic_id, source_dynamic_id, folder_name, title, reason, created_at
                )
                values (?, ?, ?, ?, ?, ?)
                on conflict(top_dynamic_id, source_dynamic_id) do update set
                    folder_name = excluded.folder_name,
                    title = excluded.title,
                    reason = excluded.reason
                """,
                (str(top_dynamic_id), str(source_dynamic_id), folder_name, title, reason, now_iso()),
            )

    def delete_blacklist_item(self, top_dynamic_id: str, source_dynamic_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "delete from blacklist_items where top_dynamic_id = ? and source_dynamic_id = ?",
                (str(top_dynamic_id), str(source_dynamic_id)),
            )

    def is_blacklisted(self, top_dynamic_id: str, source_dynamic_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select 1 from blacklist_items
                where top_dynamic_id = ? and source_dynamic_id = ?
                limit 1
                """,
                (str(top_dynamic_id), str(source_dynamic_id)),
            ).fetchone()
        return bool(row)

    def list_blacklist_items(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from blacklist_items order by created_at desc").fetchall()
        return [dict(row) for row in rows]

    def upsert_trash_item(self, folder: dict[str, Any], assets: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into trash_items(
                    top_dynamic_id, source_dynamic_id, folder_name, title, folder_json, assets_json, deleted_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(top_dynamic_id, source_dynamic_id) do update set
                    folder_name = excluded.folder_name,
                    title = excluded.title,
                    folder_json = excluded.folder_json,
                    assets_json = excluded.assets_json,
                    deleted_at = excluded.deleted_at,
                    restored_at = null
                """,
                (
                    str(folder["top_dynamic_id"]),
                    str(folder["source_dynamic_id"]),
                    folder["folder_name"],
                    folder.get("title") or folder["folder_name"],
                    dumps_json(folder),
                    dumps_json(assets),
                    now_iso(),
                ),
            )

    def list_trash_items(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from trash_items where restored_at is null order by deleted_at desc"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_trash_item(self, item_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from trash_items where id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def mark_trash_restored(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "update trash_items set restored_at = ? where id = ?",
                (now_iso(), item_id),
            )

    def delete_folder(self, folder_name: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from folders where folder_name = ?", (folder_name,))

    def add_filter_log(
        self,
        top_dynamic_id: str,
        source_dynamic_id: str,
        folder_name_candidate: str,
        decision: str,
        reasons: list[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into filter_logs(
                    top_dynamic_id, source_dynamic_id, folder_name_candidate, decision, reasons_json, created_at
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(top_dynamic_id),
                    str(source_dynamic_id),
                    folder_name_candidate,
                    decision,
                    dumps_json(reasons),
                    now_iso(),
                ),
            )

    def list_filter_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from filter_logs order by id desc limit ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_filter_logs(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute("delete from filter_logs")
            return int(cursor.rowcount or 0)

    def clear_gallery_indexes(self) -> None:
        with self.connect() as conn:
            conn.execute("delete from pair_index")
            conn.execute("delete from folder_index")

    def replace_gallery_index(
        self,
        folder_name: str,
        folder_index: dict[str, Any],
        pair_indexes: list[dict[str, Any]],
    ) -> None:
        now = now_iso()
        folder_payload = {
            "folder_name": folder_name,
            "title": folder_index.get("title", ""),
            "text_prefix": folder_index.get("text_prefix", ""),
            "pub_ts": int(folder_index.get("pub_ts") or 0),
            "pub_time": folder_index.get("pub_time", ""),
            "top_dynamic_id": str(folder_index.get("top_dynamic_id") or ""),
            "source_dynamic_id": str(folder_index.get("source_dynamic_id") or ""),
            "subscription_uid": str(folder_index.get("subscription_uid") or ""),
            "subscription_name": folder_index.get("subscription_name"),
            "has_images": 1 if folder_index.get("has_images") else 0,
            "has_livephoto": 1 if folder_index.get("has_livephoto") else 0,
            "is_favorite": 1 if folder_index.get("is_favorite") else 0,
            "review_status": folder_index.get("review_status", "approved"),
            "review_reason": folder_index.get("review_reason"),
            "image_count": int(folder_index.get("image_count") or 0),
            "livephoto_count": int(folder_index.get("livephoto_count") or 0),
            "asset_count": int(folder_index.get("asset_count") or 0),
            "preview_assets_json": folder_index.get("preview_assets_json", "[]"),
            "year_key": folder_index.get("year_key"),
            "month_key": folder_index.get("month_key"),
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into folder_index(
                    folder_name, title, text_prefix, pub_ts, pub_time, top_dynamic_id, source_dynamic_id,
                    subscription_uid, subscription_name, has_images, has_livephoto, is_favorite, review_status,
                    review_reason, image_count, livephoto_count, asset_count, preview_assets_json, year_key,
                    month_key, updated_at
                )
                values(
                    :folder_name, :title, :text_prefix, :pub_ts, :pub_time, :top_dynamic_id, :source_dynamic_id,
                    :subscription_uid, :subscription_name, :has_images, :has_livephoto, :is_favorite, :review_status,
                    :review_reason, :image_count, :livephoto_count, :asset_count, :preview_assets_json, :year_key,
                    :month_key, :updated_at
                )
                on conflict(folder_name) do update set
                    title = excluded.title,
                    text_prefix = excluded.text_prefix,
                    pub_ts = excluded.pub_ts,
                    pub_time = excluded.pub_time,
                    top_dynamic_id = excluded.top_dynamic_id,
                    source_dynamic_id = excluded.source_dynamic_id,
                    subscription_uid = excluded.subscription_uid,
                    subscription_name = excluded.subscription_name,
                    has_images = excluded.has_images,
                    has_livephoto = excluded.has_livephoto,
                    is_favorite = excluded.is_favorite,
                    review_status = excluded.review_status,
                    review_reason = excluded.review_reason,
                    image_count = excluded.image_count,
                    livephoto_count = excluded.livephoto_count,
                    asset_count = excluded.asset_count,
                    preview_assets_json = excluded.preview_assets_json,
                    year_key = excluded.year_key,
                    month_key = excluded.month_key,
                    updated_at = excluded.updated_at
                """,
                folder_payload,
            )
            conn.execute("delete from pair_index where folder_name = ?", (folder_name,))
            for row in pair_indexes:
                conn.execute(
                    """
                    insert into pair_index(
                        item_key, folder_name, pair_index, title, pub_ts, pub_time, subscription_uid,
                        subscription_name, is_favorite, has_image, has_livephoto, preview_url, preview_kind,
                        thumb_url, display_ratio, image_json, livephoto_json, year_key, month_key, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["item_key"],
                        folder_name,
                        int(row.get("pair_index") or 0),
                        row.get("title", ""),
                        int(row.get("pub_ts") or 0),
                        row.get("pub_time", ""),
                        str(row.get("subscription_uid") or ""),
                        row.get("subscription_name"),
                        1 if row.get("is_favorite") else 0,
                        1 if row.get("has_image") else 0,
                        1 if row.get("has_livephoto") else 0,
                        row.get("preview_url"),
                        row.get("preview_kind"),
                        row.get("thumb_url"),
                        row.get("display_ratio"),
                        row.get("image_json"),
                        row.get("livephoto_json"),
                        row.get("year_key"),
                        row.get("month_key"),
                        now,
                    ),
                )

    def gallery_index_status(self) -> dict[str, Any]:
        settings = self.get_settings()
        with self.connect() as conn:
            counts = conn.execute(
                """
                select
                    (select count(*) from folders) as folder_rows,
                    (select count(*) from folder_index) as folder_index_rows,
                    (select count(*) from pair_index) as pair_index_rows,
                    (
                        select count(*)
                        from (
                            select folder_name, pair_index
                            from assets
                            group by folder_name, pair_index
                        )
                    ) as asset_pair_rows
                """
            ).fetchone()
        version = int(settings.get("gallery_index_version") or 0)
        stale = (
            version != GALLERY_INDEX_VERSION
            or (counts["folder_rows"] and not counts["folder_index_rows"])
            or int(counts["folder_index_rows"] or 0) != int(counts["folder_rows"] or 0)
            or int(counts["pair_index_rows"] or 0) != int(counts["asset_pair_rows"] or 0)
        )
        return {
            "version": version,
            "current_version": GALLERY_INDEX_VERSION,
            "rebuilt_at": settings.get("gallery_index_rebuilt_at"),
            "rebuilding": bool(settings.get("gallery_index_rebuilding")),
            "folder_rows": int(counts["folder_rows"] or 0),
            "folder_index_rows": int(counts["folder_index_rows"] or 0),
            "pair_index_rows": int(counts["pair_index_rows"] or 0),
            "asset_pair_rows": int(counts["asset_pair_rows"] or 0),
            "stale": stale,
        }

    def gallery_index_needs_rebuild(self) -> bool:
        return bool(self.gallery_index_status().get("stale"))

    def gallery_index_ready(self) -> bool:
        with self.connect() as conn:
            counts = conn.execute(
                """
                select
                    (select count(*) from folders) as folder_rows,
                    (select count(*) from folder_index) as folder_index_rows
                """
            ).fetchone()
        folder_rows = int(counts["folder_rows"] or 0)
        folder_index_rows = int(counts["folder_index_rows"] or 0)
        if folder_rows != folder_index_rows:
            return False
        settings = self.get_settings()
        return folder_rows == 0 or int(settings.get("gallery_index_version") or 0) == GALLERY_INDEX_VERSION

    def query_folder_index(
        self,
        category: str = "all",
        year: str | None = None,
        month: str | None = None,
        start_month: str | None = None,
        end_month: str | None = None,
        subscription_uids: list[str] | None = None,
        page: int = 1,
        page_size: int = 24,
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        where_sql, params = self._gallery_index_where(
            category=category,
            year=year,
            month=month,
            start_month=start_month,
            end_month=end_month,
            subscription_uids=subscription_uids,
            table_alias="folder_index",
            pair_mode=False,
        )
        random_order = sort_order == "random"
        order_direction = "asc" if sort_order == "asc" else "desc"
        offset = max(page - 1, 0) * page_size
        with self.connect() as conn:
            total = int(
                conn.execute(f"select count(*) from folder_index where {where_sql}", params).fetchone()[0]
            )
            if random_order:
                rows = conn.execute(
                    f"""
                    select *
                    from folder_index
                    where {where_sql}
                    order by random()
                    limit ?
                    """,
                    [*params, int(page_size)],
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    select *
                    from folder_index
                    where {where_sql}
                    order by pub_ts {order_direction}, folder_name {order_direction}
                    limit ? offset ?
                    """,
                    [*params, int(page_size), int(offset)],
                ).fetchall()
        return {"total": total, "items": [dict(row) for row in rows]}

    def query_pair_index(
        self,
        category: str = "all",
        year: str | None = None,
        month: str | None = None,
        start_month: str | None = None,
        end_month: str | None = None,
        subscription_uids: list[str] | None = None,
        page: int = 1,
        page_size: int = 24,
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        where_sql, params = self._gallery_index_where(
            category=category,
            year=year,
            month=month,
            start_month=start_month,
            end_month=end_month,
            subscription_uids=subscription_uids,
            table_alias="pair_index",
            pair_mode=True,
        )
        random_order = sort_order == "random"
        order_direction = "asc" if sort_order == "asc" else "desc"
        offset = max(page - 1, 0) * page_size
        with self.connect() as conn:
            total = int(
                conn.execute(f"select count(*) from pair_index where {where_sql}", params).fetchone()[0]
            )
            if random_order:
                rows = conn.execute(
                    f"""
                    select *
                    from pair_index
                    where {where_sql}
                    order by random()
                    limit ?
                    """,
                    [*params, int(page_size)],
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    select *
                    from pair_index
                    where {where_sql}
                    order by pub_ts {order_direction}, folder_name {order_direction}, pair_index asc
                    limit ? offset ?
                    """,
                    [*params, int(page_size), int(offset)],
                ).fetchall()
        return {"total": total, "items": [dict(row) for row in rows]}

    def gallery_meta_from_index(self) -> dict[str, Any]:
        with self.connect() as conn:
            counts_row = conn.execute(
                """
                select
                    count(*) as all_count,
                    sum(case when has_images = 1 then 1 else 0 end) as images_count,
                    sum(case when has_livephoto = 1 then 1 else 0 end) as livephoto_count,
                    sum(case when has_images = 1 and has_livephoto = 1 then 1 else 0 end) as paired_count,
                    sum(case when not (has_images = 1 and has_livephoto = 1) then 1 else 0 end) as unpaired_count,
                    sum(case when is_favorite = 1 then 1 else 0 end) as favorites_count
                from folder_index
                """
            ).fetchone()
            months = conn.execute(
                """
                select distinct year_key, month_key
                from folder_index
                where coalesce(month_key, '') != ''
                order by year_key desc, month_key desc
                """
            ).fetchall()
            subscriptions = conn.execute(
                """
                select subscription_uid as uid,
                       max(subscription_name) as name,
                       count(*) as count
                from folder_index
                where coalesce(subscription_uid, '') != ''
                group by subscription_uid
                order by lower(coalesce(max(subscription_name), subscription_uid)) asc
                """
            ).fetchall()
        years: dict[str, list[str]] = {}
        for row in months:
            year_key = str(row["year_key"] or "未知")
            month_key = str(row["month_key"] or "")
            years.setdefault(year_key, [])
            if month_key and month_key not in years[year_key]:
                years[year_key].append(month_key)
        return {
            "counts": {
                "all": int(counts_row["all_count"] or 0),
                "images": int(counts_row["images_count"] or 0),
                "livephoto": int(counts_row["livephoto_count"] or 0),
                "paired": int(counts_row["paired_count"] or 0),
                "unpaired": int(counts_row["unpaired_count"] or 0),
                "favorites": int(counts_row["favorites_count"] or 0),
            },
            "years": {year: months for year, months in years.items()},
            "subscriptions": [
                {
                    "uid": str(row["uid"]),
                    "name": row["name"] or f"UID {row['uid']}",
                    "count": int(row["count"] or 0),
                }
                for row in subscriptions
            ],
        }

    def subscription_stats_from_index(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select
                    subscription_uid as uid,
                    max(subscription_name) as uname,
                    count(*) as folder_count,
                    sum(case when has_images = 1 then 1 else 0 end) as image_count,
                    sum(case when has_livephoto = 1 then 1 else 0 end) as livephoto_count
                from folder_index
                where coalesce(subscription_uid, '') != ''
                group by subscription_uid
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _gallery_index_where(
        self,
        *,
        category: str,
        year: str | None,
        month: str | None,
        start_month: str | None,
        end_month: str | None,
        subscription_uids: list[str] | None,
        table_alias: str,
        pair_mode: bool,
    ) -> tuple[str, list[Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        column = lambda name: f"{table_alias}.{name}"
        if subscription_uids:
            normalized = [str(uid) for uid in subscription_uids if str(uid).strip()]
            if normalized:
                placeholders = ", ".join("?" for _ in normalized)
                clauses.append(f"{column('subscription_uid')} in ({placeholders})")
                params.extend(normalized)
        if year:
            clauses.append(f"{column('year_key')} = ?")
            params.append(year)
        if month:
            clauses.append(f"{column('month_key')} = ?")
            params.append(month)
        elif start_month or end_month:
            range_start = min(item for item in [start_month, end_month] if item)
            range_end = max(item for item in [start_month, end_month] if item)
            clauses.append(f"{column('month_key')} >= ? and {column('month_key')} <= ?")
            params.extend([range_start, range_end])
        if category == "images":
            clauses.append(f"{column('has_images' if not pair_mode else 'has_image')} = 1")
        elif category == "livephoto":
            clauses.append(f"{column('has_livephoto')} = 1")
        elif category == "paired":
            clauses.append(f"{column('has_livephoto')} = 1")
            clauses.append(f"{column('has_images' if not pair_mode else 'has_image')} = 1")
        elif category == "unpaired":
            clauses.append(
                f"not ({column('has_livephoto')} = 1 and {column('has_images' if not pair_mode else 'has_image')} = 1)"
            )
        elif category == "favorites":
            clauses.append(f"{column('is_favorite')} = 1")
        return " and ".join(clauses), params

    def clear_content_data(self) -> None:
        with self.connect() as conn:
            conn.execute("delete from pair_index")
            conn.execute("delete from folder_index")
            conn.execute("delete from assets")
            conn.execute("delete from folders")
            conn.execute("delete from review_items")
            conn.execute("delete from filter_logs")
            conn.execute("delete from blacklist_items")
            conn.execute("delete from deleted_pair_marks")
            conn.execute("delete from trash_items")
            conn.execute("delete from task_runs")
