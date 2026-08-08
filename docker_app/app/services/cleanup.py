from __future__ import annotations

from pathlib import Path

from app.db import Database
from app.services.storage import StorageService
from app.services.task_priority import TaskPriorityCoordinator


class CleanupService:
    def __init__(
        self,
        db: Database,
        storage: StorageService,
        priority: TaskPriorityCoordinator | None = None,
    ) -> None:
        self.db = db
        self.storage = storage
        self.priority = priority

    def run(self) -> dict[str, int]:
        removed_assets = 0
        removed_files = 0
        folders_to_check: set[str] = set()

        for folder in self.db.list_folders():
            self._background_checkpoint()
            for asset in self.db.list_assets_for_folder(folder["folder_name"]):
                self._background_checkpoint()
                original_path = self.storage.config.storage_root / asset["rel_path"]
                if original_path.exists():
                    continue
                removed_files += self._remove_if_exists(asset.get("thumb_rel_path"))
                removed_files += self._remove_if_exists(asset.get("small_thumb_rel_path"))
                removed_files += self._remove_if_exists(asset.get("tiny_thumb_rel_path"))
                removed_files += self._remove_if_exists(asset.get("cover_rel_path"))
                removed_files += self._remove_if_exists(asset.get("reverse_rel_path"))
                self.db.delete_asset(int(asset["id"]))
                folders_to_check.add(folder["folder_name"])
                removed_assets += 1

        for folder_name in folders_to_check:
            self._background_checkpoint()
            self.db.delete_folder_if_empty(folder_name)
        return {"removed_assets": removed_assets, "removed_files": removed_files}

    def _background_checkpoint(self) -> None:
        if self.priority is not None:
            self.priority.background_checkpoint()

    def _remove_if_exists(self, rel_path: str | None) -> int:
        if not rel_path:
            return 0
        target = self.storage.config.storage_root / rel_path
        if target.exists():
            target.unlink()
            return 1
        return 0
