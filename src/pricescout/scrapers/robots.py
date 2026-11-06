"""Minimal robots.txt parser following RFC 9309.

Why not `urllib.robotparser`? It does not understand the `*` and `$` wildcards that most
large shops use (e.g. MediaMarkt's `Disallow: *de/list/*_*`), so it would silently ignore them.

Rules (RFC 9309):
- Pick the group whose user-agent token matches our product token; otherwise the `*` group.
- The rule with the longest matching path wins; on a tie, Allow beats Disallow.
- No matching rule means the URL is allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    body = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.compile(body + ("$" if anchored else ""))


class RobotsTxt:
    def __init__(self, text: str):
        self.groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (s.strip() for s in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:  # consecutive UA lines share a group
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue  # e.g. Sitemap lines before any group
            if key in ("allow", "disallow") and value:
                current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass

    def _group_for(self, user_agent: str) -> _Group | None:
        token = user_agent.split("/")[0].strip().lower()
        specific = [g for g in self.groups if any(a != "*" and a in token for a in g.agents)]
        if specific:
            return specific[0]
        return next((g for g in self.groups if "*" in g.agents), None)

    def can_fetch(self, user_agent: str, url: str) -> bool:
        group = self._group_for(user_agent)
        if group is None:
            return True
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: tuple[int, bool] | None = None  # (pattern length, allow)
        for allow, pattern in group.rules:
            if _pattern_to_regex(pattern).match(path):
                candidate = (len(pattern), allow)
                if best is None or candidate > best:  # longer wins; tie -> True (allow) wins
                    best = candidate
        return True if best is None else best[1]

    def crawl_delay(self, user_agent: str) -> float | None:
        group = self._group_for(user_agent)
        return group.crawl_delay if group else None
