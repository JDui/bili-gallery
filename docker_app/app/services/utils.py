from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

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
