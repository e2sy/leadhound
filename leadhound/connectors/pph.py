"""PeoplePerHour connector — their public projects RSS feed.

Bot protection may block datacenter IPs; when that happens the error
path says so plainly (see board_rss.fetch_feed).
"""

from __future__ import annotations

from .board_rss import fetch_feed

FEED_URL = "https://www.peopleperhour.com/feed"


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    return fetch_feed(FEED_URL, "peopleperhour")
