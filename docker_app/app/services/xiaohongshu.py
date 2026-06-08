from __future__ import annotations

import base64
import io
import json
import random
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import qrcode
import requests

from app.db import Database
from app.services.media_indexer import MediaIndexer
from app.services.site_downloader import MediaDownloader
from app.services.storage import StorageService
from app.services.utils import TIMEZONE, clean_filename, dumps_json, now_iso, safe_slug

try:
    from xhshow import CryptoConfig, SessionManager, Xhshow
except Exception:  # pragma: no cover - exercised only when dependency is missing at runtime.
    CryptoConfig = None  # type: ignore[assignment]
    SessionManager = None  # type: ignore[assignment]
    Xhshow = None  # type: ignore[assignment]


XHS_HOME = "https://www.xiaohongshu.com"
XHS_API = "https://edith.xiaohongshu.com"
XHS_APP_ID = "xhs-pc-web"
XHS_SDK_VERSION = "4.2.6"
XHS_PLATFORM = "macOS"
XHS_CHROME_VERSION = "145"
XHS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/{XHS_CHROME_VERSION}.0.0.0 Safari/537.36"
)
XHS_SUBSCRIPTION_UID = "xhs:likes"
XHS_SUBSCRIPTION_NAME = "小红书赞过"
XHS_PAGE_SIZE = 30
XHS_MAX_INCREMENTAL_PAGES = 20
QR_WAITING = 0
QR_SCANNED = 1
QR_CONFIRMED = 2


@dataclass
class XhsCookieState:
    cookie_json: dict[str, str]
    user: dict[str, Any]

    @property
    def cookie_header(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in self.cookie_json.items() if value)


def _generate_a1() -> str:
    prefix = "".join(random.choices("0123456789abcdef", k=24))
    timestamp = str(int(time.time() * 1000))
    suffix = "".join(random.choices("0123456789abcdef", k=15))
    return prefix + timestamp + suffix


def _generate_webid() -> str:
    return "".join(random.choices("0123456789abcdef", k=32))


def _json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


def _pub_ts(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return 0
        try:
            number = float(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y.%m.%d"):
                try:
                    return int(datetime.strptime(text, fmt).replace(tzinfo=TIMEZONE).timestamp())
                except ValueError:
                    continue
            return 0
    if number > 10_000_000_000:
        number = number / 1000
    return int(number)


def _pub_time(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


class XhsApiClient:
    def __init__(
        self,
        cookies: dict[str, str],
        timeout: float = 30.0,
        request_delay: float = 0.4,
    ) -> None:
        if Xhshow is None or CryptoConfig is None or SessionManager is None:
            raise RuntimeError("缺少 xhshow 依赖，请重新安装 requirements.txt")
        self.cookies = dict(cookies)
        self.timeout = timeout
        self.request_delay = max(float(request_delay or 0), 0)
        self._last_request_at = 0.0
        config = CryptoConfig().with_overrides(
            PUBLIC_USERAGENT=XHS_USER_AGENT,
            SIGNATURE_DATA_TEMPLATE={
                "x0": XHS_SDK_VERSION,
                "x1": XHS_APP_ID,
                "x2": XHS_PLATFORM,
                "x3": "",
                "x4": "",
            },
            SIGNATURE_XSCOMMON_TEMPLATE={
                "s0": 5,
                "s1": "",
                "x0": "1",
                "x1": XHS_SDK_VERSION,
                "x2": XHS_PLATFORM,
                "x3": XHS_APP_ID,
                "x4": "4.86.0",
                "x5": "",
                "x6": "",
                "x7": "",
                "x8": "",
                "x9": -596800761,
                "x10": 0,
                "x11": "normal",
            },
        )
        self.signer = Xhshow(config)
        self.sign_session = SessionManager(config)
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "XhsApiClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def login_activate(self) -> dict[str, Any]:
        return self.post("/api/sns/web/v1/login/activate", {})

    def create_qr_login(self) -> dict[str, Any]:
        return self.post("/api/sns/web/v1/login/qrcode/create", {"qr_type": 1})

    def check_qr_status(self, qr_id: str, code: str) -> dict[str, Any]:
        return self.post(
            "/api/qrcode/userinfo",
            {"qrId": qr_id, "code": code},
            header_overrides={"service-tag": "webcn"},
        )

    def complete_qr_login(self, qr_id: str, code: str) -> dict[str, Any]:
        return self.get("/api/sns/web/v1/login/qrcode/status", {"qr_id": qr_id, "code": code})

    def get_self_info(self) -> dict[str, Any]:
        return self.get("/api/sns/web/v2/user/me")

    def get_liked_notes(self, cursor: str = "", num: int = XHS_PAGE_SIZE) -> dict[str, Any]:
        return self.get("/api/sns/web/v1/note/like/page", {"cursor": cursor, "num": int(num)})

    def get_note_detail(self, note_id: str, xsec_token: str = "", xsec_source: str = "pc_feed") -> dict[str, Any]:
        return self.post(
            "/api/sns/web/v1/feed",
            {
                "source_note_id": note_id,
                "image_formats": ["jpg", "webp", "avif"],
                "extra": {"need_body_topic": "1"},
                "xsec_source": xsec_source or "pc_feed",
                "xsec_token": xsec_token or "",
            },
        )

    def get(self, uri: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = self._signed_headers("GET", uri, params=params)
        url = XHS_API + self.signer.build_url(uri, params)
        return self._request("GET", url, headers=headers)

    def post(
        self,
        uri: str,
        payload: dict[str, Any],
        header_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = self._signed_headers("POST", uri, payload=payload)
        if header_overrides:
            headers.update(header_overrides)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return self._request("POST", XHS_API + uri, headers=headers, data=body)

    def _signed_headers(
        self,
        method: str,
        uri: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        sign_headers = self.signer.sign_headers(
            method,
            uri,
            self.cookies,
            params=params if method.upper() == "GET" else None,
            payload=payload if method.upper() == "POST" else None,
            session=self.sign_session,
        )
        return {**self._base_headers(), **sign_headers}

    def _base_headers(self) -> dict[str, str]:
        return {
            "user-agent": XHS_USER_AGENT,
            "content-type": "application/json;charset=UTF-8",
            "cookie": self._cookie_header(),
            "origin": XHS_HOME,
            "referer": f"{XHS_HOME}/",
            "sec-ch-ua": f'"Not:A-Brand";v="99", "Google Chrome";v="{XHS_CHROME_VERSION}", "Chromium";v="{XHS_CHROME_VERSION}"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "dnt": "1",
        }

    def _cookie_header(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in self.cookies.items() if value)

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if self.request_delay:
            elapsed = time.time() - self._last_request_at
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed + random.uniform(0.05, 0.2))
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        self._last_request_at = time.time()
        for key, value in response.cookies.items():
            if value:
                self.cookies[key] = value
        if response.status_code in {461, 471}:
            raise RuntimeError("小红书触发验证，请稍后重试或重新扫码登录")
        response.raise_for_status()
        payload = response.json()
        if payload.get("success"):
            data = payload.get("data")
            return data if isinstance(data, dict) else {"data": data}
        code = payload.get("code")
        if code == -100:
            raise RuntimeError("小红书登录已失效，请重新扫码登录")
        raise RuntimeError(payload.get("msg") or payload.get("message") or f"小红书接口失败: {payload}")


class XhsAuthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_cookie_state(self) -> XhsCookieState:
        state = self.db.get_xhs_auth_state()
        return XhsCookieState(
            cookie_json=_json_loads(state.get("cookie_json"), {}),
            user=_json_loads(state.get("user_json"), {}),
        )

    def start_qr_login(self) -> dict[str, Any]:
        cookies = {"a1": _generate_a1(), "webId": _generate_webid()}
        with XhsApiClient(cookies, request_delay=0) as client:
            try:
                data = client.login_activate()
                self._apply_login_cookies(client.cookies, data)
            except Exception:
                pass
            qr_data = client.create_qr_login()
            qr_id = str(qr_data.get("qr_id") or "")
            code = str(qr_data.get("code") or "")
            qr_url = str(qr_data.get("url") or "")
            if not qr_id or not code or not qr_url:
                raise RuntimeError("小红书二维码创建失败")
            self.db.update_xhs_auth_state(
                cookie_json=dumps_json(client.cookies),
                user_json=None,
                qr_id=qr_id,
                qr_code=code,
                qr_url=qr_url,
                qr_status="pending",
                qr_created_at=now_iso(),
            )
        return {
            "qr_id": qr_id,
            "qr_url": qr_url,
            "image_data_url": self._render_qr_data_url(qr_url),
            "status": "pending",
            "message": "请使用小红书客户端扫码登录",
        }

    def poll_qr_login(self) -> dict[str, Any]:
        state = self.db.get_xhs_auth_state()
        qr_id = str(state.get("qr_id") or "")
        code = str(state.get("qr_code") or "")
        if not qr_id or not code:
            return {"status": "idle", "message": "暂无小红书二维码会话"}
        cookies = _json_loads(state.get("cookie_json"), {})
        with XhsApiClient(cookies, request_delay=0) as client:
            data = client.check_qr_status(qr_id, code)
            code_status = int(data.get("codeStatus", -1))
            if code_status == QR_WAITING:
                self.db.update_xhs_auth_state(qr_status="pending", cookie_json=dumps_json(client.cookies))
                return {"status": "pending", "message": "等待扫码"}
            if code_status == QR_SCANNED:
                self.db.update_xhs_auth_state(qr_status="scanned", cookie_json=dumps_json(client.cookies))
                return {"status": "scanned", "message": "已扫码，等待确认"}
            if code_status != QR_CONFIRMED:
                self.db.update_xhs_auth_state(qr_status="pending", cookie_json=dumps_json(client.cookies))
                return {"status": "pending", "message": data.get("msg") or "等待确认"}
            completion = client.complete_qr_login(qr_id, code)
            self._apply_login_cookies(client.cookies, completion)
            user = self._check_cookie_with_client(client)
            self.db.update_xhs_auth_state(
                cookie_json=dumps_json(client.cookies),
                user_json=dumps_json(user.get("user", {})),
                qr_id=None,
                qr_code=None,
                qr_url=None,
                qr_status="done",
            )
        return {"status": "done", "message": "小红书登录成功", **user}

    def check_cookie(self) -> dict[str, Any]:
        state = self.get_cookie_state()
        if not state.cookie_json.get("a1"):
            return {"ok": False, "message": "小红书未登录"}
        try:
            with XhsApiClient(state.cookie_json, request_delay=0) as client:
                result = self._check_cookie_with_client(client)
                self.db.update_xhs_auth_state(
                    cookie_json=dumps_json(client.cookies),
                    user_json=dumps_json(result.get("user", {})),
                )
                return result
        except Exception as exc:
            return {"ok": False, "message": f"小红书 Cookie 检查失败: {exc}"}

    def logout(self) -> None:
        self.db.update_xhs_auth_state(
            cookie_json=None,
            user_json=None,
            qr_id=None,
            qr_code=None,
            qr_url=None,
            qr_status="idle",
            qr_created_at=None,
        )

    def _check_cookie_with_client(self, client: XhsApiClient) -> dict[str, Any]:
        info = client.get_self_info()
        user_id = str(info.get("user_id") or info.get("userid") or "")
        nickname = str(info.get("nickname") or info.get("name") or "")
        guest = bool(info.get("guest", False))
        if guest or not user_id:
            return {"ok": False, "message": "小红书 Cookie 无效或仍是游客态", "user": info}
        return {"ok": True, "message": "小红书 Cookie 有效", "uid": user_id, "uname": nickname, "user": info}

    def _apply_login_cookies(self, cookies: dict[str, str], payload: dict[str, Any]) -> None:
        login_info = payload.get("login_info") if isinstance(payload.get("login_info"), dict) else {}
        session = payload.get("session") or login_info.get("session")
        secure_session = payload.get("secure_session") or login_info.get("secure_session")
        if session:
            cookies["web_session"] = str(session)
        if secure_session:
            cookies["web_session_sec"] = str(secure_session)

    def _render_qr_data_url(self, qr_url: str) -> str:
        image = qrcode.make(qr_url)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class XhsLikedSyncManager:
    def __init__(
        self,
        db: Database,
        storage: StorageService,
        indexer: MediaIndexer,
        auth: XhsAuthService,
    ) -> None:
        self.db = db
        self.storage = storage
        self.indexer = indexer
        self.auth = auth

    def status(self) -> dict[str, Any]:
        cookie_state = self.auth.get_cookie_state()
        user = cookie_state.user or {}
        return {
            **self.db.get_xhs_liked_state(),
            "stats": self.db.xhs_stats(),
            "auth": {
                "ok": bool(cookie_state.cookie_json.get("a1") and user),
                "uid": user.get("user_id") or user.get("userid") or "",
                "uname": user.get("nickname") or user.get("name") or "",
                "message": "小红书已登录" if cookie_state.cookie_json.get("a1") else "小红书未登录",
            },
        }

    def set_anchor(self, cooperate=None) -> dict[str, Any]:
        with self._client() as client:
            if cooperate:
                cooperate()
            cards = self._liked_cards(client.get_liked_notes(num=2))
            anchors = [card["note_id"] for card in cards[:2] if card.get("note_id")]
            if len(anchors) < 1:
                raise RuntimeError("未获取到小红书赞过笔记，无法设置锚点")
            state = self.db.update_xhs_liked_state(
                anchor_note_ids=anchors,
                anchor_set_at=now_iso(),
                last_status="anchor",
                last_message=f"已设置 {len(anchors)} 个锚点",
                last_stats={"anchors": len(anchors)},
            )
        return {"ok": True, "message": f"已设置 {len(anchors)} 个小红书赞过锚点", "state": state}

    def execute_pull(self, cooperate=None) -> dict[str, Any]:
        state = self.db.get_xhs_liked_state()
        old_anchors = {str(item) for item in state.get("anchor_note_ids") or [] if str(item).strip()}
        if not old_anchors:
            raise RuntimeError("请先设置小红书赞过锚点")
        stats = {"discovered": 0, "new": 0, "downloaded": 0, "skipped": 0, "errors": 0}
        new_cards: list[dict[str, Any]] = []
        latest_anchor_candidates: list[str] = []
        cursor = ""
        found_anchor = False
        with self._client() as client:
            for _page in range(XHS_MAX_INCREMENTAL_PAGES):
                if cooperate:
                    cooperate()
                page = client.get_liked_notes(cursor=cursor, num=XHS_PAGE_SIZE)
                cards = self._liked_cards(page)
                if not cards:
                    break
                for card in cards:
                    note_id = str(card.get("note_id") or "")
                    if note_id and len(latest_anchor_candidates) < 2:
                        latest_anchor_candidates.append(note_id)
                    if note_id in old_anchors:
                        found_anchor = True
                        break
                    new_cards.append(card)
                if found_anchor:
                    break
                cursor = str(page.get("cursor") or "")
                if not page.get("has_more") or not cursor:
                    break
            stats["discovered"] = len(new_cards)
            if not found_anchor:
                self.db.update_xhs_liked_state(
                    last_sync_at=now_iso(),
                    last_status="failed",
                    last_message="未在翻页范围内遇到旧锚点，锚点未更新",
                    last_stats=stats,
                )
                raise RuntimeError("未在翻页范围内遇到旧锚点，锚点未更新")
            for card in new_cards:
                try:
                    if cooperate:
                        cooperate()
                    result = self._process_card(client, card, cooperate=cooperate)
                    stats["new"] += 1
                    stats["downloaded"] += int(result.get("downloaded") or 0)
                except Exception as exc:
                    stats["errors"] += 1
                    note_id = str(card.get("note_id") or "")
                    if note_id:
                        self.db.update_xhs_note_counts(note_id, status="failed", error=str(exc))
                    self.db.update_xhs_liked_state(
                        last_sync_at=now_iso(),
                        last_status="failed",
                        last_message=f"小红书赞过拉取失败: {exc}",
                        last_stats=stats,
                    )
                    raise
        self.db.update_xhs_liked_state(
            anchor_note_ids=latest_anchor_candidates[:2] or list(old_anchors)[:2],
            anchor_set_at=now_iso(),
            last_sync_at=now_iso(),
            last_status="success",
            last_message=f"小红书赞过拉取完成，新增 {stats['new']} 条",
            last_stats=stats,
        )
        return stats

    def _client(self) -> XhsApiClient:
        state = self.auth.get_cookie_state()
        if not state.cookie_json.get("a1"):
            raise RuntimeError("小红书未登录，请先扫码登录")
        return XhsApiClient(state.cookie_json)

    def _liked_cards(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        raw_notes = page.get("notes") or page.get("items") or page.get("list") or []
        cards = []
        for raw in raw_notes if isinstance(raw_notes, list) else []:
            card = self._normalize_card(raw)
            if card.get("note_id"):
                cards.append(card)
        return cards

    def _normalize_card(self, raw: dict[str, Any]) -> dict[str, Any]:
        note_card = raw.get("note_card") if isinstance(raw.get("note_card"), dict) else raw
        note_id = str(raw.get("note_id") or note_card.get("note_id") or note_card.get("id") or "").strip()
        user = note_card.get("user") if isinstance(note_card.get("user"), dict) else {}
        return {
            "note_id": note_id,
            "title": str(note_card.get("display_title") or note_card.get("title") or raw.get("title") or ""),
            "excerpt": str(note_card.get("desc") or note_card.get("description") or ""),
            "author_name": str(user.get("nickname") or raw.get("nickname") or ""),
            "author_id": str(user.get("user_id") or user.get("id") or ""),
            "liked_at": raw.get("liked_time") or raw.get("time") or raw.get("timestamp"),
            "xsec_token": str(raw.get("xsec_token") or note_card.get("xsec_token") or ""),
            "xsec_source": str(raw.get("xsec_source") or note_card.get("xsec_source") or "pc_user_liked"),
            "raw": raw,
        }

    def _process_card(self, client: XhsApiClient, card: dict[str, Any], cooperate=None) -> dict[str, int]:
        note_id = str(card["note_id"])
        detail = client.get_note_detail(note_id, card.get("xsec_token") or "", card.get("xsec_source") or "pc_user_liked")
        note = self._normalize_detail(card, detail)
        assets = self._note_assets(note, detail)
        note["asset_count"] = len(assets)
        self.db.upsert_xhs_note(note)
        post_folder = self.storage.xhs_note_folder(note_id, note.get("pub_time")[:10] if note.get("pub_time") else None, note.get("title"))
        downloaded = 0
        for index, asset in enumerate(assets, start=1):
            if cooperate:
                cooperate()
            filename = clean_filename(asset["url"], note.get("title") or note_id, index, asset["media_type"])
            db_asset = self.db.upsert_xhs_note_asset(note_id, {**asset, "filename": filename})
            target = post_folder / filename
            if db_asset.get("status") == "ready" and target.exists() and target.stat().st_size > 0:
                downloaded += 1
                continue
            try:
                MediaDownloader(user_agent=XHS_USER_AGENT).download(asset["url"], target)
                self.db.set_xhs_note_asset_result(int(db_asset["id"]), "ready", self.storage.relative_to_storage(target))
                downloaded += 1
            except Exception as exc:
                self.db.set_xhs_note_asset_result(int(db_asset["id"]), "failed", error=str(exc))
                raise
        self.db.update_xhs_note_counts(note_id, status="ready", error=None)
        folder_name = self._mirror_to_gallery(note, post_folder)
        self.db.upsert_xhs_note({**note, "folder_name": folder_name, "downloaded_count": downloaded, "status": "ready"})
        return {"downloaded": downloaded}

    def _normalize_detail(self, card: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        item = detail.get("items", [detail])[0] if isinstance(detail.get("items"), list) and detail.get("items") else detail
        note_card = item.get("note_card") if isinstance(item.get("note_card"), dict) else item
        user = note_card.get("user") if isinstance(note_card.get("user"), dict) else {}
        ts = _pub_ts(note_card.get("time") or note_card.get("last_update_time") or card.get("liked_at"))
        note_id = str(card["note_id"])
        return {
            "note_id": note_id,
            "url": f"{XHS_HOME}/explore/{note_id}",
            "title": str(note_card.get("title") or note_card.get("display_title") or card.get("title") or "小红书笔记"),
            "excerpt": str(note_card.get("desc") or card.get("excerpt") or ""),
            "author_name": str(user.get("nickname") or card.get("author_name") or ""),
            "author_id": str(user.get("user_id") or card.get("author_id") or ""),
            "liked_at": card.get("liked_at"),
            "pub_ts": ts,
            "pub_time": _pub_time(ts),
            "xsec_token": card.get("xsec_token") or "",
            "xsec_source": card.get("xsec_source") or "",
            "raw": detail,
            "status": "discovered",
        }

    def _note_assets(self, note: dict[str, Any], detail: dict[str, Any]) -> list[dict[str, str]]:
        item = detail.get("items", [detail])[0] if isinstance(detail.get("items"), list) and detail.get("items") else detail
        note_card = item.get("note_card") if isinstance(item.get("note_card"), dict) else item
        assets: list[dict[str, str]] = []
        image_list = note_card.get("image_list") if isinstance(note_card.get("image_list"), list) else []
        for image in image_list:
            url = self._best_image_url(image)
            if url:
                assets.append({"url": url, "media_type": "image"})
        video = note_card.get("video") if isinstance(note_card.get("video"), dict) else {}
        video_url = self._best_video_url(video)
        if video_url:
            assets.append({"url": video_url, "media_type": "video"})
        return assets

    def _best_image_url(self, image: dict[str, Any]) -> str:
        for key in ("url_default", "url_pre", "url", "trace_id"):
            value = image.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        info_list = image.get("info_list") if isinstance(image.get("info_list"), list) else []
        for info in info_list:
            url = info.get("url") if isinstance(info, dict) else ""
            if isinstance(url, str) and url.startswith("http"):
                return url
        return ""

    def _best_video_url(self, video: dict[str, Any]) -> str:
        media = video.get("media") if isinstance(video.get("media"), dict) else video
        stream = media.get("stream") if isinstance(media.get("stream"), dict) else {}
        candidates = []
        for key in ("h264", "h265", "av1"):
            candidates.extend(stream.get(key) if isinstance(stream.get(key), list) else [])
        for item in candidates:
            master_url = item.get("master_url") if isinstance(item, dict) else ""
            backup_urls = item.get("backup_urls") if isinstance(item, dict) and isinstance(item.get("backup_urls"), list) else []
            for url in [master_url, *backup_urls]:
                if isinstance(url, str) and url.startswith("http"):
                    return url
        return ""

    def _mirror_to_gallery(self, note: dict[str, Any], post_folder: Path) -> str:
        ready_assets = self.db.list_xhs_note_assets(note["note_id"])
        images = [asset for asset in ready_assets if asset.get("status") == "ready" and asset.get("media_type") == "image"]
        videos = [asset for asset in ready_assets if asset.get("status") == "ready" and asset.get("media_type") == "video"]
        folder_name = f"xhs_{note['note_id']}_{safe_slug(note.get('title') or 'note', 'note', 48)}"
        image_folder = self.storage.image_folder(folder_name)
        image_folder.mkdir(parents=True, exist_ok=True)
        for existing in image_folder.iterdir():
            if existing.is_file() and not existing.name.startswith("."):
                existing.unlink(missing_ok=True)
        for index, asset in enumerate(images, start=1):
            source_path = self.storage.resolve_storage_path(asset.get("rel_path"))
            if not source_path or not source_path.exists():
                continue
            target = image_folder / f"{index:03d}__{asset['filename']}"
            shutil.copy2(source_path, target)
        if images:
            self.indexer.index_folder(
                folder_name=folder_name,
                pub_ts=int(note.get("pub_ts") or 0),
                title=note.get("title") or folder_name,
                text_prefix=note.get("excerpt") or "",
                top_dynamic_id=f"xhs:{note['note_id']}",
                source_dynamic_id=f"xhs:{note['note_id']}",
                subscription_uid=XHS_SUBSCRIPTION_UID,
                subscription_name=XHS_SUBSCRIPTION_NAME,
                metadata={"source": "xhs", "original_url": note.get("url"), "xhs_note_id": note["note_id"]},
            )
        else:
            self.db.upsert_folder(
                {
                    "folder_name": folder_name,
                    "title": note.get("title") or folder_name,
                    "text_prefix": note.get("excerpt") or "",
                    "pub_ts": int(note.get("pub_ts") or 0),
                    "pub_time": note.get("pub_time") or "",
                    "top_dynamic_id": f"xhs:{note['note_id']}",
                    "source_dynamic_id": f"xhs:{note['note_id']}",
                    "subscription_uid": XHS_SUBSCRIPTION_UID,
                    "subscription_name": XHS_SUBSCRIPTION_NAME,
                    "has_images": False,
                    "has_livephoto": False,
                    "metadata": {"source": "xhs", "original_url": note.get("url"), "xhs_note_id": note["note_id"]},
                }
            )
            self.indexer.refresh_gallery_index(folder_name)
        video_assets = []
        for index, asset in enumerate(videos, start=1):
            if asset.get("rel_path"):
                video_assets.append(
                    {
                        "pair_index": index,
                        "filename": asset["filename"],
                        "rel_path": asset["rel_path"],
                        "metadata": {"kind": "xhs-video"},
                    }
                )
        self.db.replace_folder_assets(folder_name, "video", video_assets)
        self.indexer.refresh_gallery_index(folder_name)
        return folder_name
