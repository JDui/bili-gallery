from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import Database
from app.services.media_indexer import MediaIndexer
from app.services.storage import StorageService
from app.services.thumbnailer import ThumbnailService
from app.services.utils import dumps_json


@dataclass(frozen=True)
class SeedConfig:
    storage_root: Path
    config_dir: Path
    data_dir: Path
    images_dir: Path
    livephoto_dir: Path
    database_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成用于页面审查的示例数据")
    parser.add_argument("--storage-root", required=True, help="示例存储目录")
    return parser.parse_args()


def build_config(storage_root: Path) -> SeedConfig:
    config_dir = storage_root / "config"
    data_dir = storage_root / "data"
    return SeedConfig(
        storage_root=storage_root,
        config_dir=config_dir,
        data_dir=data_dir,
        images_dir=data_dir / "images",
        livephoto_dir=data_dir / "livephoto",
        database_path=config_dir / "app.db",
    )


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def make_image(path: Path, title: str, size: tuple[int, int], palette: tuple[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, palette[0])
    draw = ImageDraw.Draw(image)
    for index in range(10):
        inset = 32 + index * 12
        draw.rounded_rectangle(
            (inset, inset, size[0] - inset, size[1] - inset),
            radius=28,
            outline=palette[1],
            width=3,
        )
    draw.text((56, 56), title, fill="#ffffff")
    image.save(path, quality=92)


def make_video(path: Path, color: str, duration: float = 2.4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ThumbnailService()._resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，可执行审查数据无法生成")
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=960x1200:d={duration}",
        "-vf",
        "fps=12,format=yuv420p",
        str(path),
    ]
    subprocess.run(command, check=True, capture_output=True)


def seed_library(storage: StorageService, indexer: MediaIndexer) -> None:
    folder_a = "20260103_阿巴巴阿巴"
    make_image(storage.image_folder(folder_a) / "01.jpg", "冬日窗边", (1080, 1350), ("#6f9fe6", "#dce8ff"))
    make_image(storage.image_folder(folder_a) / "02.jpg", "静物光影", (1080, 1500), ("#cc8c77", "#f7ddd2"))
    make_video(storage.livephoto_folder(folder_a) / "01.mp4", "#8ab4ff")
    indexer.index_folder(folder_a, 1767369600, "阿巴巴阿巴的冬日记录", "阿巴巴阿巴", "demo-top-1", "demo-src-1")

    folder_b = "20260214_春日海风"
    make_image(storage.image_folder(folder_b) / "01.jpg", "海风", (1080, 1440), ("#78c6b0", "#d7f5ec"))
    make_image(storage.image_folder(folder_b) / "02.jpg", "山路", (1080, 1380), ("#8b77d1", "#ece5ff"))
    indexer.index_folder(folder_b, 1768737600, "春日海风里的照片流", "春日海风", "demo-top-2", "demo-src-2")

    folder_duplicate = "20260220_海风返图"
    storage.image_folder(folder_duplicate).mkdir(parents=True, exist_ok=True)
    shutil.copy2(storage.image_folder(folder_b) / "01.jpg", storage.image_folder(folder_duplicate) / "01.jpg")
    shutil.copy2(storage.image_folder(folder_b) / "02.jpg", storage.image_folder(folder_duplicate) / "02.jpg")
    make_image(storage.image_folder(folder_duplicate) / "03.jpg", "返图", (1080, 1440), ("#7bbbd1", "#e1f4fa"))
    indexer.index_folder(folder_duplicate, 1771545600, "海风返图与补充记录", "海风返图", "demo-top-duplicate", "demo-src-duplicate")

    folder_duplicate_second = "20260225_海风回顾"
    storage.image_folder(folder_duplicate_second).mkdir(parents=True, exist_ok=True)
    shutil.copy2(storage.image_folder(folder_b) / "01.jpg", storage.image_folder(folder_duplicate_second) / "01.jpg")
    shutil.copy2(storage.image_folder(folder_b) / "02.jpg", storage.image_folder(folder_duplicate_second) / "02.jpg")
    indexer.index_folder(
        folder_duplicate_second,
        1771977600,
        "海风照片回顾",
        "海风回顾",
        "demo-top-duplicate-2",
        "demo-src-duplicate-2",
    )

    folder_c = "20260301_设计样片"
    make_video(storage.livephoto_folder(folder_c) / "01.mp4", "#f29cb5")
    indexer.index_folder(folder_c, 1772323200, "设计样片与动效预览", "设计样片", "demo-top-3", "demo-src-3")


def seed_review_data(db: Database) -> None:
    db.upsert_review_item(
        "review-top-1",
        "review-src-1",
        "20260309_推广样例",
        "这是一个命中推广规则的示例动态，用于展示待审核页",
        ["命中文案关键词: 推广", "长图占多数"],
        {
            "top_item": {},
            "source_item": {},
            "top_dynamic_id": "review-top-1",
            "source_dynamic_id": "review-src-1",
            "pub_ts": 1773014400,
            "text": "推广样例",
            "pictures": [],
            "live_assets": [],
        },
        status="pending",
    )
    db.add_filter_log("review-top-1", "review-src-1", "20260309_推广样例", "review", ["命中文案关键词: 推广", "长图占多数"])
    db.add_filter_log("review-top-2", "review-src-2", "20260310_合作展示", "review", ["命中文案关键词: 合作"])
    db.create_task_run("pull", "running", "正在扫描动态 demo-top-2", {"matched": 3, "downloaded_candidates": 1, "saved_files": 4})
    finished_task = db.create_task_run("review", "running", "处理审核项 1", {"item_id": 1})
    db.finish_task_run(finished_task, "success", "审核项下载完成", {"item_id": 1})
    db.upsert_trash_item(
        {
            "folder_name": "20260312_不喜欢样例",
            "title": "不喜欢样例",
            "text_prefix": "不喜欢样例",
            "pub_ts": 1773273600,
            "pub_time": "2026-03-12 12:00:00",
            "top_dynamic_id": "trash-top-1",
            "source_dynamic_id": "trash-src-1",
            "has_images": True,
            "has_livephoto": False,
        },
        [],
    )
    db.add_blacklist_item("trash-top-1", "trash-src-1", "20260312_不喜欢样例", "不喜欢样例", "不喜欢")
    db.update_auth_state(
        cookie="SESSDATA=demo",
        cookie_json=dumps_json({"SESSDATA": "demo"}),
        user_json=dumps_json({"name": "审查演示账号"}),
        qr_status="done",
    )


def main() -> None:
    args = parse_args()
    storage_root = Path(args.storage_root).resolve()
    reset_dir(storage_root)
    config = build_config(storage_root)
    storage = StorageService(config)
    storage.ensure()
    db = Database(config.database_path)
    db.init()
    db.save_settings(
        {
            "host_mid": 31968078,
            "scheduler_enabled": True,
            "scheduler_interval_hours": 6,
            "ad_filter_keywords": ["推广", "广告", "合作", "抽奖"],
        }
    )
    indexer = MediaIndexer(db, storage, ThumbnailService())
    seed_library(storage, indexer)
    seed_review_data(db)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONPATH", str(ROOT_DIR))
    main()
