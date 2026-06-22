from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FilterDecision:
    allowed: bool
    decision: str
    reason: str


class RuleEngine:
    VALID_MODES = {"blacklist", "whitelist", "both"}

    def __init__(self, rules: dict[str, object]) -> None:
        self.rules = rules
        self.use_regex = bool(rules.get("use_regex"))
        mode = str(rules.get("mode") or "blacklist").strip().lower()
        self.mode = mode if mode in self.VALID_MODES else "blacklist"

    def evaluate(self, title: str, tags: list[str]) -> FilterDecision:
        title = title or ""
        tags = [tag or "" for tag in tags]
        allow_match = self._match_rule_group(title, tags, "allow")
        block_match = self._match_rule_group(title, tags, "block")
        allow_configured = self._group_has_patterns("allow")
        block_configured = self._group_has_patterns("block")

        if self.mode == "blacklist":
            if block_match:
                return FilterDecision(False, "blocked", "命中站点黑名单")
            return FilterDecision(True, "allowed", "未命中站点黑名单" if block_configured else "无黑名单限制")

        if self.mode == "whitelist":
            if not allow_configured:
                return FilterDecision(True, "allowed", "无白名单限制")
            if allow_match:
                return FilterDecision(True, "allowed", "命中站点白名单")
            return FilterDecision(False, "blocked", "未命中站点白名单")

        if allow_configured and not allow_match:
            return FilterDecision(False, "blocked", "未命中站点白名单")
        if block_match:
            return FilterDecision(False, "blocked", "命中站点黑名单")
        if allow_configured and block_configured:
            return FilterDecision(True, "allowed", "命中白名单且未命中黑名单")
        if allow_configured:
            return FilterDecision(True, "allowed", "命中站点白名单")
        return FilterDecision(True, "allowed", "未命中站点黑名单" if block_configured else "无黑白名单限制")

    def _group_has_patterns(self, group: str) -> bool:
        if group == "allow":
            return bool(self._allow_keyword_patterns() or self._patterns("title_allow") or self._patterns("tag_allow"))
        return bool(self._block_keyword_patterns() or self._patterns("title_block") or self._patterns("tag_block"))

    def _match_rule_group(self, title: str, tags: list[str], group: str) -> bool:
        if group == "allow":
            shared = self._allow_keyword_patterns()
            return (
                self._match_title_or_tags(title, tags, shared)
                or self._match_any(title, self._patterns("title_allow"))
                or self._match_tags(tags, self._patterns("tag_allow"))
            )
        shared = self._block_keyword_patterns()
        return (
            self._match_title_or_tags(title, tags, shared)
            or self._match_any(title, self._patterns("title_block"))
            or self._match_tags(tags, self._patterns("tag_block"))
        )

    def _allow_keyword_patterns(self) -> list[str]:
        patterns = self._patterns("allow_keywords")
        if self.mode == "whitelist":
            patterns.extend(self._patterns("keywords"))
        elif self.mode == "both" and not patterns and not self._patterns("title_allow") and not self._patterns("tag_allow"):
            patterns.extend(self._patterns("keywords"))
        return patterns

    def _block_keyword_patterns(self) -> list[str]:
        patterns = self._patterns("block_keywords")
        if self.mode == "blacklist":
            patterns.extend(self._patterns("keywords"))
        return patterns

    def _patterns(self, key: str) -> list[str]:
        value = self.rules.get(key) or []
        return [str(item).strip() for item in value if str(item).strip()]

    def _match_title_or_tags(self, title: str, tags: list[str], patterns: list[str]) -> bool:
        return self._match_any(title, patterns) or self._match_tags(tags, patterns)

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
