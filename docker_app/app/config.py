from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    app_root: Path
    repo_root: Path
    storage_root: Path
    config_dir: Path
    data_dir: Path
    images_dir: Path
    livephoto_dir: Path
    database_path: Path
    secret_key: str


def load_config() -> AppConfig:
    app_root = Path(__file__).resolve().parent
    repo_root = Path(os.environ.get("APP_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
    storage_root = Path(os.environ.get("APP_STORAGE_ROOT", repo_root / "storage")).resolve()
    config_dir = storage_root / "config"
    data_dir = storage_root / "data"
    images_dir = data_dir / "images"
    livephoto_dir = data_dir / "livephoto"
    database_path = config_dir / "app.db"
    secret_key = os.environ.get("APP_SECRET_KEY", "bili-gallery-dev-secret")
    return AppConfig(
        app_root=app_root,
        repo_root=repo_root,
        storage_root=storage_root,
        config_dir=config_dir,
        data_dir=data_dir,
        images_dir=images_dir,
        livephoto_dir=livephoto_dir,
        database_path=database_path,
        secret_key=secret_key,
    )
