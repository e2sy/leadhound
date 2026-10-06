"""Connector protocol.

A connector turns one job site into leadhound's normalized job dicts:

    {guid, source, title, url, body, tags, posted_at,
     budget_min?, budget_max?, hourly?}

`fetch(settings)` returns `(jobs, updated_settings)` — connectors that rotate
credentials (Upwork refresh tokens) hand back the new settings to persist.

Honesty rule: a connector that can't reach or parse its site raises with a
human message — it never returns fake data. That's what demo mode is for.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Field:
    name: str
    label: str
    placeholder: str = ""
    secret: bool = False
    hint: str = ""


@dataclass
class Connector:
    id: str
    label: str
    kind: str  # "public" | "keys" | "cookie" | "feed"
    blurb: str
    fields: list[Field] = field(default_factory=list)
    fetch: Callable[[dict], tuple[list[dict], dict | None]] | None = None
    setup_url: str = ""  # where the user gets credentials, when kind != public
    min_poll: int = 5    # politeness floor (minutes): cheap public feeds ride the fast lane

    @property
    def needs_setup(self) -> bool:
        return self.kind != "public" and len(self.fields) > 0
