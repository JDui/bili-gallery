#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import error, request


SCRIPT_PATH = Path(__file__).resolve()
APP_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[2]
sys.path.insert(0, str(APP_ROOT))

from app.services.xiaohongshu import (  # noqa: E402
    format_xhs_cookie_header,
    has_xhs_session_cookie,
    load_xhs_cookies_from_chrome,
)


def import_cookie(app_url: str, cookie_header: str) -> dict:
    endpoint = app_url.rstrip("/") + "/api/xhs/auth/cookie/import"
    payload = json.dumps({"cookie_text": cookie_header}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"detail": body}
        message = payload.get("detail") or payload.get("message") or body
        raise RuntimeError(f"导入失败: {message}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="从宿主机 Chrome 读取小红书 Cookie 并导入 ZZS Web 服务")
    parser.add_argument("--app", default="http://localhost:7860", help="ZZS Web 服务地址")
    args = parser.parse_args()

    cookies, profile = load_xhs_cookies_from_chrome()
    if not has_xhs_session_cookie(cookies):
        raise RuntimeError(f"已读取 Chrome Profile {profile}，但缺少 web_session 登录态 Cookie")

    result = import_cookie(args.app, format_xhs_cookie_header(cookies))
    if not result.get("ok"):
        raise RuntimeError(result.get("message") or "小红书 Cookie 导入后校验失败")

    print(f"已从 Chrome Profile {profile} 导入小红书 Cookie：{result.get('uname') or result.get('uid') or '已登录'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
