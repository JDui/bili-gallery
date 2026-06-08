from __future__ import annotations

import random
from math import ceil

from app.db import Database
from app.services.storage import StorageService
from app.services.utils import loads_json


class GalleryService:
    def __init__(self, db: Database, storage: StorageService) -> None:
        self.db = db
        self.storage = storage

    def get_gallery_items(
        self,
        category: str = "all",
        year: str | None = None,
        month: str | None = None,
        start_month: str | None = None,
        end_month: str | None = None,
        subscription_uids: list[str] | None = None,
        source_kind: str = "all",
        page: int = 1,
        page_size: int = 24,
        view_mode: str = "folder",
        sort_order: str = "desc",
    ) -> dict:
        source_kind = self._normalize_source_kind(source_kind)
        if not self.db.gallery_index_ready():
            return self._fallback_gallery_items(
                category=category,
                year=year,
                month=month,
                start_month=start_month,
                end_month=end_month,
                subscription_uids=subscription_uids,
                source_kind=source_kind,
                page=page,
                page_size=page_size,
                view_mode=view_mode,
                sort_order=sort_order,
            )
        if view_mode == "pair":
            result = self.db.query_pair_index(
                category=category,
                year=year,
                month=month,
                start_month=start_month,
                end_month=end_month,
                subscription_uids=subscription_uids,
                source_kind=source_kind,
                page=page,
                page_size=page_size,
                sort_order=sort_order,
            )
            items = [self._pair_card(item) for item in result["items"]]
        else:
            result = self.db.query_folder_index(
                category=category,
                year=year,
                month=month,
                start_month=start_month,
                end_month=end_month,
                subscription_uids=subscription_uids,
                source_kind=source_kind,
                page=page,
                page_size=page_size,
                sort_order=sort_order,
            )
            items = [self._folder_card_from_index(item) for item in result["items"]]
        total = int(result["total"])
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 1,
            "view_mode": view_mode,
            "sort_order": sort_order,
        }

    def get_gallery_meta(self) -> dict:
        if not self.db.gallery_index_ready():
            return self._fallback_gallery_meta()
        return self.db.gallery_meta_from_index()

    def get_folder_detail(self, folder_name: str) -> dict | None:
        folders = {folder["folder_name"]: folder for folder in self.db.list_folders()}
        folder = folders.get(folder_name)
        if not folder:
            return None
        assets = self.db.list_assets_for_folder(folder_name)
        images = [self._asset_json(asset) for asset in assets if asset["media_type"] == "image"]
        livephotos = [self._asset_json(asset) for asset in assets if asset["media_type"] == "livephoto"]
        videos = [self._asset_json(asset) for asset in assets if asset["media_type"] == "video"]
        pair_map: dict[int, dict] = {}
        for image in images:
            pair_map.setdefault(image["pair_index"], {})["image"] = image
        for livephoto in livephotos:
            pair_map.setdefault(livephoto["pair_index"], {})["livephoto"] = livephoto
        pairs = []
        for pair_index in sorted(pair_map):
            entry = pair_map[pair_index]
            image = entry.get("image")
            livephoto = entry.get("livephoto")
            preview_asset = image or livephoto or {}
            pairs.append(
                {
                    "pair_index": pair_index,
                    "image": image,
                    "livephoto": livephoto,
                    "preview_url": (
                        (image or {}).get("small_thumb_url")
                        or (image or {}).get("thumb_url")
                        or (image or {}).get("url")
                        or (livephoto or {}).get("small_thumb_url")
                        or (livephoto or {}).get("thumb_url")
                        or (livephoto or {}).get("cover_url")
                        or (livephoto or {}).get("url")
                    ),
                    "preview_kind": "paired" if image and livephoto else ("livephoto" if livephoto and not image else "image"),
                    "complete": bool(image and livephoto),
                    "display_ratio": self._display_ratio(preview_asset),
                }
            )
        return {
            "folder": self._folder_card_from_folder(folder),
            "pairs": pairs,
            "images": images,
            "livephotos": livephotos,
            "videos": videos,
        }

    def _folder_card_from_index(self, item: dict) -> dict:
        image_count = int(item.get("image_count") or 0)
        livephoto_count = int(item.get("livephoto_count") or 0)
        return {
            "folder_name": item["folder_name"],
            "title": item.get("title") or item["folder_name"],
            "text_prefix": item.get("text_prefix") or "",
            "pub_time": item.get("pub_time"),
            "pub_ts": int(item.get("pub_ts") or 0),
            "top_dynamic_id": item.get("top_dynamic_id"),
            "source_dynamic_id": item.get("source_dynamic_id"),
            "original_url": self._original_url(item),
            "subscription_uid": str(item.get("subscription_uid") or ""),
            "subscription_name": item.get("subscription_name") or "",
            "year_key": item.get("year_key") or "",
            "month_key": item.get("month_key") or "",
            "has_images": bool(item.get("has_images")),
            "has_livephoto": bool(item.get("has_livephoto")),
            "is_favorite": bool(item.get("is_favorite")),
            "review_status": item.get("review_status"),
            "review_reason": item.get("review_reason"),
            "preview_tiles": loads_json(item.get("preview_assets_json"), []),
            "image_count": image_count,
            "livephoto_count": livephoto_count,
            "asset_count": image_count,
        }

    def _folder_card_from_folder(self, folder: dict) -> dict:
        assets = self.db.list_assets_for_folder(folder["folder_name"])
        if not assets:
            return {}
        image_assets = [asset for asset in assets if asset["media_type"] == "image"]
        preview_assets = image_assets or assets
        image_count = len(image_assets)
        livephoto_count = sum(1 for asset in assets if asset["media_type"] == "livephoto")
        return {
            "folder_name": folder["folder_name"],
            "title": folder.get("title") or folder["folder_name"],
            "text_prefix": folder.get("text_prefix") or "",
            "pub_time": folder.get("pub_time"),
            "pub_ts": int(folder.get("pub_ts") or 0),
            "top_dynamic_id": folder.get("top_dynamic_id"),
            "source_dynamic_id": folder.get("source_dynamic_id"),
            "original_url": self._original_url(folder),
            "subscription_uid": str(folder.get("subscription_uid") or ""),
            "subscription_name": folder.get("subscription_name") or "",
            "year_key": (folder.get("pub_time") or "")[:4],
            "month_key": (folder.get("pub_time") or "")[:7],
            "has_images": bool(folder["has_images"]),
            "has_livephoto": bool(folder["has_livephoto"]),
            "is_favorite": bool(folder.get("is_favorite")),
            "review_status": folder.get("review_status"),
            "review_reason": folder.get("review_reason"),
            "preview_tiles": [self._asset_json(asset) for asset in preview_assets[:4]],
            "image_count": image_count,
            "livephoto_count": livephoto_count,
            "asset_count": image_count,
        }

    def _pair_card(self, item: dict) -> dict:
        image = loads_json(item.get("image_json"), None)
        livephoto = loads_json(item.get("livephoto_json"), None)
        return {
            "item_key": item["item_key"],
            "folder_name": item["folder_name"],
            "pair_index": int(item.get("pair_index") or 0),
            "title": item.get("title") or item["folder_name"],
            "pub_time": item.get("pub_time"),
            "pub_ts": int(item.get("pub_ts") or 0),
            "subscription_uid": str(item.get("subscription_uid") or ""),
            "subscription_name": item.get("subscription_name") or "",
            "original_url": self._original_url(item),
            "is_favorite": bool(item.get("is_favorite")),
            "year_key": item.get("year_key") or "",
            "month_key": item.get("month_key") or "",
            "has_images": bool(item.get("has_image")),
            "has_livephoto": bool(item.get("has_livephoto")),
            "preview_url": item.get("preview_url"),
            "preview_kind": item.get("preview_kind"),
            "thumb_url": item.get("thumb_url"),
            "small_thumb_url": (
                (image or {}).get("small_thumb_url")
                or (livephoto or {}).get("small_thumb_url")
                or item.get("thumb_url")
            ),
            "image": image,
            "livephoto": livephoto,
            "display_ratio": item.get("display_ratio"),
            "width": (image or livephoto or {}).get("width"),
            "height": (image or livephoto or {}).get("height"),
        }

    def _asset_json(self, asset: dict | None) -> dict | None:
        if not asset:
            return None
        metadata = loads_json(asset.get("metadata_json"), {})
        return {
            "id": asset["id"],
            "media_type": asset["media_type"],
            "pair_index": asset["pair_index"],
            "filename": asset["filename"],
            "url": self.storage.storage_url(asset["rel_path"]),
            "thumb_url": self.storage.storage_url(asset.get("thumb_rel_path")),
            "small_thumb_url": self.storage.storage_url(asset.get("small_thumb_rel_path")),
            "cover_url": self.storage.storage_url(asset.get("cover_rel_path")),
            "reverse_url": self.storage.storage_url(asset.get("reverse_rel_path")),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "metadata": metadata,
        }

    def _display_ratio(self, asset: dict) -> str:
        width = float(asset.get("width") or 1)
        height = float(asset.get("height") or 1)
        if width <= 0 or height <= 0:
            return "1 / 1"
        ratio = max(1 / 3, min(3, width / height))
        return f"{ratio:.4f} / 1"

    def _original_url(self, item: dict) -> str:
        metadata = loads_json(item.get("metadata_json"), {})
        url = str(metadata.get("site_post_url") or metadata.get("original_url") or "").strip()
        if url:
            return url
        return self.db.site_post_url_from_dynamic_id(item.get("source_dynamic_id"))

    def _fallback_gallery_items(
        self,
        category: str,
        year: str | None,
        month: str | None,
        start_month: str | None,
        end_month: str | None,
        subscription_uids: list[str] | None,
        source_kind: str,
        page: int,
        page_size: int,
        view_mode: str,
        sort_order: str,
    ) -> dict:
        folders = self.db.list_folders()
        filtered = [
            folder
            for folder in folders
            if self._match(folder, category, year, month, start_month, end_month, subscription_uids, source_kind)
        ]
        if view_mode == "pair":
            items = self._fallback_pair_items(filtered, category, sort_order=sort_order)
        else:
            items = [item for item in (self._folder_card_from_folder(folder) for folder in filtered) if item]
            if sort_order == "random":
                random.shuffle(items)
            else:
                reverse = sort_order != "asc"
                items.sort(
                    key=lambda item: (
                        int(item.get("pub_ts") or 0),
                        str(item.get("folder_name") or item.get("item_key") or ""),
                        int(item.get("pair_index") or 0),
                    ),
                    reverse=reverse,
                )
        total = len(items)
        start = max(page - 1, 0) * page_size
        page_items = items[start:start + page_size]
        return {
            "items": page_items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 1,
            "view_mode": view_mode,
            "sort_order": sort_order,
        }

    def _fallback_gallery_meta(self) -> dict:
        folders = self.db.list_folders()
        years: dict[str, list[str]] = {}
        counts = {"all": 0, "images": 0, "livephoto": 0, "paired": 0, "unpaired": 0, "favorites": 0}
        subscriptions: dict[str, dict] = {}
        for folder in folders:
            pub_time = folder.get("pub_time", "")
            year = pub_time[:4] if pub_time else "未知"
            month = pub_time[:7] if pub_time else "未知"
            counts["all"] += 1
            if folder["has_images"]:
                counts["images"] += 1
            if folder["has_livephoto"]:
                counts["livephoto"] += 1
            if folder["has_images"] and folder["has_livephoto"]:
                counts["paired"] += 1
            if not folder["has_images"] or not folder["has_livephoto"]:
                counts["unpaired"] += 1
            if folder.get("is_favorite"):
                counts["favorites"] += 1
            subscription_uid = str(folder.get("subscription_uid") or "")
            if subscription_uid:
                bucket = subscriptions.setdefault(
                    subscription_uid,
                    {
                        "uid": subscription_uid,
                        "name": folder.get("subscription_name") or f"UID {subscription_uid}",
                        "count": 0,
                    },
                )
                bucket["count"] += 1
            years.setdefault(year, [])
            if month not in years[year]:
                years[year].append(month)
        return {
            "counts": counts,
            "years": {year: sorted(months, reverse=True) for year, months in sorted(years.items(), reverse=True)},
            "subscriptions": sorted(subscriptions.values(), key=lambda item: item["name"]),
        }

    def _fallback_pair_items(self, folders: list[dict], category: str, sort_order: str = "desc") -> list[dict]:
        output: list[dict] = []
        if sort_order == "random":
            sorted_folders = list(folders)
            random.shuffle(sorted_folders)
        else:
            reverse = sort_order != "asc"
            sorted_folders = sorted(
                folders,
                key=lambda folder: (int(folder.get("pub_ts") or 0), str(folder.get("folder_name") or "")),
                reverse=reverse,
            )
        for folder in sorted_folders:
            detail = self.get_folder_detail(folder["folder_name"])
            if not detail:
                continue
            for pair in detail["pairs"]:
                if not self._match_pair(pair, category):
                    continue
                preview = pair.get("image") or pair.get("livephoto") or {}
                output.append(
                    {
                        "item_key": f"{folder['folder_name']}::{pair['pair_index']}",
                        "folder_name": folder["folder_name"],
                        "pair_index": pair["pair_index"],
                        "title": folder.get("title") or folder["folder_name"],
                        "pub_time": folder.get("pub_time"),
                        "pub_ts": int(folder.get("pub_ts") or 0),
                        "subscription_uid": str(folder.get("subscription_uid") or ""),
                        "subscription_name": folder.get("subscription_name") or "",
                        "is_favorite": bool(folder.get("is_favorite")),
                        "year_key": (folder.get("pub_time") or "")[:4],
                        "month_key": (folder.get("pub_time") or "")[:7],
                        "has_images": bool(pair.get("image")),
                        "has_livephoto": bool(pair.get("livephoto")),
                        "preview_url": pair.get("preview_url"),
                        "preview_kind": pair.get("preview_kind"),
                        "thumb_url": preview.get("thumb_url") or preview.get("cover_url") or preview.get("url"),
                        "small_thumb_url": preview.get("small_thumb_url") or preview.get("thumb_url") or preview.get("cover_url") or preview.get("url"),
                        "image": pair.get("image"),
                        "livephoto": pair.get("livephoto"),
                        "display_ratio": pair.get("display_ratio"),
                        "width": preview.get("width"),
                        "height": preview.get("height"),
                    }
                )
        if sort_order == "random":
            random.shuffle(output)
        return output

    def _match(
        self,
        folder: dict,
        category: str,
        year: str | None,
        month: str | None,
        start_month: str | None,
        end_month: str | None,
        subscription_uids: list[str] | None,
        source_kind: str,
    ) -> bool:
        pub_time = folder.get("pub_time", "")
        month_key = pub_time[:7] if pub_time else ""
        if subscription_uids:
            if str(folder.get("subscription_uid") or "") not in {str(uid) for uid in subscription_uids}:
                return False
        elif not self._match_source_kind(folder.get("subscription_uid"), source_kind):
            return False
        if year and pub_time[:4] != year:
            return False
        if month and pub_time[:7] != month:
            return False
        if start_month or end_month:
            if not month_key:
                return False
            range_start = min(filter(None, [start_month, end_month]))
            range_end = max(filter(None, [start_month, end_month]))
            if month_key < range_start or month_key > range_end:
                return False
        if category == "all":
            return True
        if category == "images":
            return bool(folder["has_images"])
        if category == "livephoto":
            return bool(folder["has_livephoto"])
        if category == "paired":
            return bool(folder["has_images"] and folder["has_livephoto"])
        if category == "unpaired":
            return not (folder["has_images"] and folder["has_livephoto"])
        if category == "favorites":
            return bool(folder.get("is_favorite"))
        if category == "recent":
            return True
        return True

    def _normalize_source_kind(self, source_kind: str | None) -> str:
        if source_kind in {"up", "site", "xhs"}:
            return str(source_kind)
        return "all"

    def _match_source_kind(self, subscription_uid: object, source_kind: str) -> bool:
        uid = str(subscription_uid or "")
        if source_kind == "xhs":
            return uid.startswith("xhs:")
        if source_kind == "site":
            return uid.startswith("site:")
        if source_kind == "up":
            return not uid.startswith("site:") and not uid.startswith("xhs:")
        return True

    def _match_pair(self, pair: dict, category: str) -> bool:
        has_image = bool(pair.get("image"))
        has_livephoto = bool(pair.get("livephoto"))
        if category == "all":
            return True
        if category == "images":
            return has_image
        if category == "livephoto":
            return has_livephoto
        if category == "paired":
            return has_image and has_livephoto
        if category == "unpaired":
            return not (has_image and has_livephoto)
        return True
