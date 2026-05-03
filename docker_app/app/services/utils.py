from __future__ import annotations

import json
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    result = name
    for ch in bad:
        result = result.replace(ch, "_")
    return result


def safe_slug(value: str, fallback: str = "item", max_len: int = 80) -> str:
    text = unquote(value or "").strip().lower()
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:max_len].strip("-") or fallback


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "")
    normalized = normalized.replace(".", "-").replace("/", "-")
    candidates = [normalized, normalized[:19], normalized[:10], normalized[:7]]
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m"):
        for candidate in candidates:
            try:
                parsed = datetime.strptime(candidate, fmt)
                return parsed.date()
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError, IndexError):
        return None


def date_key(value: date | str | None) -> str:
    if isinstance(value, date):
        return value.isoformat()
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else "unknown-date"


def guess_extension(url: str, media_type: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix
    return ".mp4" if media_type == "video" else ".jpg"


def clean_filename(url: str, title: str, index: int, media_type: str) -> str:
    ext = guess_extension(url, media_type)
    return f"{index:03d}-{safe_slug(title, 'asset', 48)}{ext}"


def extract_chinese_prefix(text: str, length: int = 5) -> str:
    clean = compact_text(text)
    chars = [ch for ch in clean if "\u4e00" <= ch <= "\u9fff"]
    return "".join(chars[:length])


def folder_date(pub_ts: int) -> str:
    if pub_ts <= 0:
        return "19700101"
    return datetime.fromtimestamp(pub_ts, TIMEZONE).strftime("%Y%m%d")


def parse_legacy_title(folder_name: str) -> str:
    match = re.match(r"^\d{8}(?:_\d{6})?_(.+)$", folder_name)
    if match:
        return match.group(1)
    return folder_name


def build_folder_name(pub_ts: int, text: str, used_names: set[str]) -> str:
    date_part = folder_date(pub_ts)
    prefix = extract_chinese_prefix(text) or "日常动态图"
    candidate = safe_filename(f"{date_part}_{prefix}")
    final_name = candidate
    index = 2
    while final_name in used_names:
        final_name = f"{candidate}_{index}"
        index += 1
    used_names.add(final_name)
    return final_name


def format_pub_time(pub_ts: int) -> str:
    if pub_ts <= 0:
        return "1970-01-01 00:00:00"
    return datetime.fromtimestamp(pub_ts, TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def dumps_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def loads_json(raw: str | None, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def batched(items: Iterable[object], size: int) -> list[list[object]]:
    batch: list[object] = []
    output: list[list[object]] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            output.append(batch)
            batch = []
    if batch:
        output.append(batch)
    return output
