#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

BASE_DIR = pathlib.Path(__file__).resolve().parent
PARENT_DIR = BASE_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from bili_9pics_downloader import (  # noqa: E402
    STATE_BEGIN,
    STATE_END,
    build_folder_base,
    build_headers,
    compact_text,
    extract_picture_nodes,
    extract_primary_text,
    extract_pub_ts,
    folder_pub_ts,
    format_pub_time,
    iter_space_pages,
    load_cookie_from_env,
    load_cookie_from_chrome,
    record_key,
    safe_filename,
    TIMEZONE,
)


def resolve_cookie(profile: str) -> str:
    env_cookie = load_cookie_from_env()
    if env_cookie:
        print("[AUTH] use cookie from env")
        return env_cookie

    print(f"[AUTH] load cookie from Chrome profile={profile}")
    return load_cookie_from_chrome(profile=profile)


def live_url(pic: dict) -> str:
    url = (pic.get("live_url") or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url.replace("http://", "https://")


def extract_live_assets(item: dict) -> List[dict]:
    assets = []
    for pic in extract_picture_nodes(item):
        url = live_url(pic)
        if url:
            assets.append(
                {
                    "live_url": url,
                    "cover_url": (pic.get("url") or pic.get("src") or pic.get("img_src") or "").strip(),
                }
            )
    return assets


def find_live_blocks(item: dict, include_forwarded: bool) -> List[Tuple[dict, dict, List[dict]]]:
    blocks: List[Tuple[dict, dict, List[dict]]] = []
    assets = extract_live_assets(item)
    if assets:
        blocks.append((item, item, assets))

    if include_forwarded:
        orig = item.get("orig")
        if isinstance(orig, dict):
            orig_assets = extract_live_assets(orig)
            if orig_assets:
                blocks.append((item, orig, orig_assets))

    return blocks


def load_md_records(md_path: pathlib.Path) -> Dict[str, dict]:
    if not md_path.exists():
        return {}

    text = md_path.read_text(encoding="utf-8")
    start = text.find(STATE_BEGIN)
    end = text.find(STATE_END)
    if start == -1 or end == -1 or end <= start:
        return {}

    payload = text[start + len(STATE_BEGIN):end].strip()
    if not payload:
        return {}

    try:
        items = json.loads(payload)
    except json.JSONDecodeError:
        return {}

    records = {}
    for item in items:
        key = record_key(str(item["top_dynamic_id"]), str(item["source_dynamic_id"]))
        records[key] = item
    return records


def load_processed_urls(urls_txt: pathlib.Path) -> Set[str]:
    if not urls_txt.exists():
        return set()
    return {line.strip() for line in urls_txt.read_text(encoding="utf-8").splitlines() if line.strip()}


def count_files(folder: pathlib.Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for path in folder.iterdir() if path.is_file())


def refresh_record_status(record: dict, out_root: pathlib.Path) -> None:
    folder = out_root / record["folder_name"]
    file_count = count_files(folder)
    record["file_count"] = file_count
    record["status"] = "complete" if file_count >= int(record["live_count"]) else "partial"


def write_downloads_md(md_path: pathlib.Path, out_root: pathlib.Path, records: Dict[str, dict]) -> None:
    ordered = sorted(
        records.values(),
        key=lambda item: (int(item.get("pub_ts", 0)), item["top_dynamic_id"], item["source_dynamic_id"]),
        reverse=True,
    )
    for record in ordered:
        refresh_record_status(record, out_root)

    total_files = sum(int(record.get("file_count", 0)) for record in ordered)
    now_text = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# 粽子淞 Live Photo 动态下载记录",
        "",
        f"- 更新时间：{now_text}",
        f"- 已记录动态：{len(ordered)}",
        f"- 已保存文件：{total_files}",
        "",
        "| 发布时间 | 前5字 | Live 数 | 已有文件 | 状态 | 顶层动态ID | 源动态ID | 目录 |",
        "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]

    for record in ordered:
        lines.append(
            "| {pub_time} | {text_prefix} | {live_count} | {file_count} | {status} | "
            "{top_dynamic_id} | {source_dynamic_id} | downloaded/{folder_name} |".format(
                pub_time=record["pub_time"],
                text_prefix=record["text_prefix"].replace("|", "/"),
                live_count=record["live_count"],
                file_count=record.get("file_count", 0),
                status=record.get("status", "partial"),
                top_dynamic_id=record["top_dynamic_id"],
                source_dynamic_id=record["source_dynamic_id"],
                folder_name=record["folder_name"],
            )
        )

    lines.extend(
        [
            "",
            STATE_BEGIN,
            json.dumps(ordered, ensure_ascii=False, indent=2),
            STATE_END,
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def latest_local_pub_ts(records: Dict[str, dict], out_root: pathlib.Path) -> int:
    latest = 0
    for record in records.values():
        try:
            latest = max(latest, int(record.get("pub_ts") or 0))
        except (TypeError, ValueError):
            continue

    if not out_root.exists():
        return latest

    for path in out_root.iterdir():
        if path.is_dir():
            latest = max(latest, folder_pub_ts(path.name))
    return latest


def short_title(text: str) -> str:
    clean = compact_text(text)
    chars: List[str] = []
    for ch in clean:
        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            chars.append(ch)
        elif ch in {" ", "-", "_"}:
            chars.append("_")
        if len(chars) >= 5:
            break

    title = "".join(chars).strip("_")
    return title or "无文案"


def make_unique_folder_name(base_name: str, used_names: Set[str]) -> str:
    candidate = base_name
    index = 2
    while candidate in used_names:
        candidate = f"{base_name}_{index}"
        index += 1
    used_names.add(candidate)
    return candidate


def build_record(
    top_item: dict,
    source_item: dict,
    live_count: int,
    used_folder_names: Set[str],
    existing_record: Optional[dict] = None,
) -> dict:
    top_id = str(top_item.get("id_str") or "unknown")
    source_id = str(source_item.get("id_str") or "unknown")
    pub_ts = extract_pub_ts(top_item) or extract_pub_ts(source_item)
    text = extract_primary_text(top_item) or extract_primary_text(source_item) or "无文案"

    folder_name = existing_record["folder_name"] if existing_record else ""
    if not folder_name:
        folder_name = make_unique_folder_name(build_folder_base(pub_ts, text), used_folder_names)
    else:
        used_folder_names.add(folder_name)

    return {
        "top_dynamic_id": top_id,
        "source_dynamic_id": source_id,
        "pub_ts": pub_ts,
        "pub_time": format_pub_time(pub_ts),
        "text_prefix": short_title(text),
        "live_count": live_count,
        "folder_name": folder_name,
        "file_count": int(existing_record.get("file_count", 0)) if existing_record else 0,
        "status": existing_record.get("status", "partial") if existing_record else "partial",
    }


def basename_from_live_url(url: str, source_dynamic_id: str, index: int) -> str:
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path)
    if basename:
        return safe_filename(basename)
    return f"{source_dynamic_id}_{index:02d}.mp4"


def download_file(url: str, out_path: pathlib.Path, headers: Dict[str, str]) -> None:
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all Live Photo assets from Bilibili dynamics."
    )
    parser.add_argument("--host-mid", type=int, default=31968078, help="Bilibili UID")
    parser.add_argument("--out-root", default="downloaded", help="Output directory under LivePhoto")
    parser.add_argument("--chrome-profile", default="Default", help="Chrome profile name")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between file downloads")
    parser.add_argument(
        "--skip-forwarded",
        action="store_true",
        help="Ignore forwarded dynamics whose original content contains Live Photo assets",
    )
    args = parser.parse_args()

    cookie = resolve_cookie(profile=args.chrome_profile)
    headers = build_headers(host_mid=args.host_mid, cookie=cookie)

    out_root = BASE_DIR / args.out_root
    out_root.mkdir(parents=True, exist_ok=True)

    downloads_md = BASE_DIR / "downloads_livephoto.md"
    urls_txt = BASE_DIR / "urls_livephoto.txt"

    records = load_md_records(downloads_md)
    used_folder_names = {record["folder_name"] for record in records.values() if record.get("folder_name")}
    used_folder_names.update(path.name for path in out_root.iterdir() if path.is_dir())

    processed_urls = load_processed_urls(urls_txt)
    write_downloads_md(downloads_md, out_root, records)

    has_existing_downloads = any(path.is_dir() for path in out_root.iterdir())
    incremental_cutoff_ts = latest_local_pub_ts(records, out_root) if has_existing_downloads else 0
    if incremental_cutoff_ts > 0:
        print(f"[INCREMENTAL] cutoff={format_pub_time(incremental_cutoff_ts)}")

    matched_dynamics = 0
    collected_urls = 0
    downloaded_files = 0
    reached_old_items = False

    for page_num, items in iter_space_pages(args.host_mid, headers=headers):
        page_has_newer_items = False

        for item in items:
            item_pub_ts = extract_pub_ts(item)
            if incremental_cutoff_ts == 0 or item_pub_ts == 0 or item_pub_ts > incremental_cutoff_ts:
                page_has_newer_items = True

            matches = find_live_blocks(item, include_forwarded=not args.skip_forwarded)
            if not matches:
                continue

            for top_item, source_item, assets in matches:
                top_pub_ts = extract_pub_ts(top_item) or extract_pub_ts(source_item)
                if incremental_cutoff_ts > 0 and top_pub_ts > 0 and top_pub_ts <= incremental_cutoff_ts:
                    continue

                matched_dynamics += 1
                top_id = str(top_item.get("id_str") or "unknown")
                source_id = str(source_item.get("id_str") or "unknown")
                key = record_key(top_id, source_id)

                record = build_record(
                    top_item,
                    source_item,
                    len(assets),
                    used_folder_names,
                    existing_record=records.get(key),
                )
                records[key] = record

                dynamic_dir = out_root / record["folder_name"]
                dynamic_dir.mkdir(parents=True, exist_ok=True)
                print(
                    f"[MATCH] top={record['top_dynamic_id']} source={record['source_dynamic_id']} "
                    f"folder={record['folder_name']}"
                )

                for index, asset in enumerate(assets, start=1):
                    url = asset["live_url"]
                    if url not in processed_urls:
                        with urls_txt.open("a", encoding="utf-8") as f:
                            f.write(url + "\n")
                        processed_urls.add(url)
                        collected_urls += 1

                    out_path = dynamic_dir / basename_from_live_url(url, record["source_dynamic_id"], index)
                    if out_path.exists() and out_path.stat().st_size > 0:
                        continue

                    try:
                        download_file(url, out_path, headers=headers)
                        downloaded_files += 1
                        print(f"[SAVE] {record['folder_name']} -> {out_path.name}")
                    except Exception as exc:
                        print(f"[FAIL] {record['folder_name']} {url} err={exc}")
                    time.sleep(args.sleep)

                refresh_record_status(record, out_root)
                write_downloads_md(downloads_md, out_root, records)

        if incremental_cutoff_ts > 0 and not page_has_newer_items and page_num > 1:
            print(f"[STOP] reached cutoff page with no newer items after {format_pub_time(incremental_cutoff_ts)}")
            reached_old_items = True
            break

    write_downloads_md(downloads_md, out_root, records)

    print()
    print(f"Matched dynamics: {matched_dynamics}")
    print(f"New URL collected: {collected_urls}")
    print(f"Files saved this run: {downloaded_files}")
    print(f"Reached cutoff: {reached_old_items}")
    print(f"Output folder: {out_root.resolve()}")
    print(f"URL list: {urls_txt.resolve()}")
    print(f"Record file: {downloads_md.resolve()}")


if __name__ == "__main__":
    main()
