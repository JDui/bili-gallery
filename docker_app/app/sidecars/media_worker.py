from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def resize_to_short_edge(image: Image.Image, short_edge: int) -> Image.Image:
    width, height = image.size
    current_short = max(1, min(width, height))
    if current_short <= short_edge:
        return image
    scale = short_edge / current_short
    target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def save_webp(image: Image.Image, target: Path, short_edge: int, quality: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    resized = resize_to_short_edge(image, short_edge)
    resized.save(target, format="WEBP", quality=quality, method=6)


def probe_image(args: argparse.Namespace) -> None:
    source = Path(args.source)
    with Image.open(source) as image:
        width, height = image.size
    print_json({"ok": True, "source": str(source), "width": width, "height": height})


def derive_image(args: argparse.Namespace) -> None:
    source = Path(args.source)
    thumb = Path(args.thumb)
    small = Path(args.small)
    tiny = Path(args.tiny)
    with Image.open(source) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        width, height = normalized.size
        save_webp(normalized, thumb, 576, 68)
        save_webp(normalized, small, 258, 42)
        save_webp(normalized, tiny, 9, 28)
    print_json(
        {
            "ok": True,
            "source": str(source),
            "width": width,
            "height": height,
            "thumb": str(thumb),
            "small": str(small),
            "tiny": str(tiny),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe-image")
    probe.add_argument("--source", required=True)
    probe.set_defaults(func=probe_image)
    derive = subparsers.add_parser("derive-image")
    derive.add_argument("--source", required=True)
    derive.add_argument("--thumb", required=True)
    derive.add_argument("--small", required=True)
    derive.add_argument("--tiny", required=True)
    derive.set_defaults(func=derive_image)
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
