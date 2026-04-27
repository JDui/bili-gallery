from __future__ import annotations

import shutil
from pathlib import Path

from app.config import AppConfig


class StorageService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def ensure(self) -> None:
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        self.config.images_dir.mkdir(parents=True, exist_ok=True)
        self.config.livephoto_dir.mkdir(parents=True, exist_ok=True)

    def image_folder(self, folder_name: str) -> Path:
        return self.config.images_dir / folder_name

    def livephoto_folder(self, folder_name: str) -> Path:
        return self.config.livephoto_dir / folder_name

    def remove_folder_assets(self, folder_name: str) -> int:
        removed = 0
        for folder in (self.image_folder(folder_name), self.livephoto_folder(folder_name)):
            if folder.exists():
                shutil.rmtree(folder)
                removed += 1
        return removed

    def resolve_storage_path(self, rel_path: str | None) -> Path | None:
        if not rel_path:
            return None
        return self.config.storage_root / rel_path

    def remove_asset_files(self, asset: dict) -> int:
        removed = 0
        for key in ("rel_path", "thumb_rel_path", "cover_rel_path", "reverse_rel_path"):
            path = self.resolve_storage_path(asset.get(key))
            if path and path.exists():
                path.unlink(missing_ok=True)
                removed += 1
        if asset.get("media_type") == "livephoto":
            live_folder = self.livephoto_folder(asset["folder_name"])
            source_cover = live_folder / ".source_covers" / f"{Path(asset['filename']).stem}.jpg"
            if source_cover.exists():
                source_cover.unlink(missing_ok=True)
                removed += 1
        return removed

    def clear_library_data(self) -> dict[str, int]:
        removed = {"images": 0, "livephoto": 0}
        for key, folder in (("images", self.config.images_dir), ("livephoto", self.config.livephoto_dir)):
            if folder.exists():
                children = list(folder.iterdir())
                removed[key] = len(children)
                shutil.rmtree(folder)
            folder.mkdir(parents=True, exist_ok=True)
        return removed

    def relative_to_storage(self, path: Path) -> str:
        return path.resolve().relative_to(self.config.storage_root.resolve()).as_posix()

    def storage_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return f"/storage/{path}"
