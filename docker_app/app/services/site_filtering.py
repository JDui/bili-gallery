from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FilterDecision:
    allowed: bool
    decision: str
    reason: str


class RuleEngine:
    def __init__(self, rules: dict[str, object]) -> None:
        self.rules = rules
        self.use_regex = bool(rules.get("use_regex"))

    def evaluate(self, title: str, tags: list[str]) -> FilterDecision:
        title = title or ""
        tags = [tag or "" for tag in tags]
        if self._match_any(title, self._patterns("title_block")):
            return FilterDecision(False, "blocked", "命中标题黑名单")
        if self._match_tags(tags, self._patterns("tag_block")):
            return FilterDecision(False, "blocked", "命中 tag 黑名单")

        title_allow = self._patterns("title_allow")
        tag_allow = self._patterns("tag_allow")
        if title_allow or tag_allow:
            if self._match_any(title, title_allow) or self._match_tags(tags, tag_allow):
                return FilterDecision(True, "allowed", "命中白名单")
            return FilterDecision(False, "blocked", "未命中白名单")

        return FilterDecision(True, "allowed", "无白名单限制")

    def _patterns(self, key: str) -> list[str]:
        value = self.rules.get(key) or []
        return [str(item).strip() for item in value if str(item).strip()]

    def _match_tags(self, tags: list[str], patterns: list[str]) -> bool:
        return any(self._match_any(tag, patterns) for tag in tags)

    def _match_any(self, text: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            if self.use_regex:
                try:
                    if re.search(pattern, text, flags=re.I):
                        return True
                except re.error:
                    continue
            elif pattern.lower() in text.lower():
                return True
        return False
