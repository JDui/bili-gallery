from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def list_names(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name for path in root.iterdir() if path.is_dir()}


def list_media(root: Path, folder_name: str, suffixes: set[str]) -> list[dict]:
    if not root.exists():
        return []
    output = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in suffixes:
            continue
        output.append(
            {
                "folder_name": folder_name,
                "filename": path.name,
                "rel_path": str(path),
                "bytes": path.stat().st_size,
            }
        )
    return output


def scan(args: argparse.Namespace) -> None:
    images_dir = Path(args.images_dir)
    livephoto_dir = Path(args.livephoto_dir)
    names = sorted(list_names(images_dir) | list_names(livephoto_dir))
    folders = []
    missing = []
    for folder_name in names:
        image_folder = images_dir / folder_name
        livephoto_folder = livephoto_dir / folder_name
        images = list_media(image_folder, folder_name, IMAGE_SUFFIXES)
        livephotos = list_media(livephoto_folder, folder_name, VIDEO_SUFFIXES)
        if not image_folder.exists():
            missing.append(f"images/{folder_name}")
        if not livephoto_folder.exists():
            missing.append(f"livephoto/{folder_name}")
        folders.append({"folder_name": folder_name, "images": images, "livephotos": livephotos})
    print_json({"ok": True, "folders": folders, "missing": missing, "orphan_files": []})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--images-dir", required=True)
    scan_parser.add_argument("--livephoto-dir", required=True)
    scan_parser.set_defaults(func=scan)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as error:
        print_json({"ok": False, "error": str(error)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
