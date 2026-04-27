from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.legacy_bridge import extract_picture_nodes, extract_primary_text


@dataclass
class FilterDecision:
    decision: str
    reasons: list[str]


class FilterEngine:
    def __init__(self, settings: dict[str, object]) -> None:
        self.enabled = bool(settings.get("ad_filter_enabled", True))
        self.keywords = [str(item).strip() for item in settings.get("ad_filter_keywords", []) if str(item).strip()]
        self.long_image_ratio = float(settings.get("long_image_ratio", 3.0))

    def evaluate(self, source_item: dict) -> FilterDecision:
        if not self.enabled:
            return FilterDecision(decision="allow", reasons=[])

        reasons: list[str] = []
        text = extract_primary_text(source_item)
        matched_keywords = [keyword for keyword in self.keywords if keyword and keyword in text]
        if matched_keywords:
            reasons.append(f"命中文案关键词: {', '.join(matched_keywords)}")

        picture_nodes = extract_picture_nodes(source_item)
        long_images = [node for node in picture_nodes if self._is_long_image(node)]
        if picture_nodes and len(long_images) * 2 > len(picture_nodes):
            reasons.append(
                f"长图占多数: {len(long_images)}/{len(picture_nodes)}，阈值 {self.long_image_ratio:.1f}"
            )

        if reasons:
            return FilterDecision(decision="review", reasons=reasons)
        return FilterDecision(decision="allow", reasons=[])

    def _is_long_image(self, picture_node: dict) -> bool:
        width = self._extract_number(picture_node, ["width", "img_width", "x"])
        height = self._extract_number(picture_node, ["height", "img_height", "y"])
        if not width or not height:
            return False
        return height / max(width, 1) >= self.long_image_ratio

    @staticmethod
    def _extract_number(payload: dict, keys: Iterable[str]) -> int:
        for key in keys:
            value = payload.get(key)
            try:
                if value:
                    return int(value)
            except (TypeError, ValueError):
                continue
        return 0
