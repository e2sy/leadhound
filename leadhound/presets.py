"""Starter packs — one-click bundles of niche job feed channels.

Every channel here was verified against the live source before shipping.
A pack arms a whole niche in one click: it switches the matching sources
ON and points each one at the right feed channel (stored as the
connector's `preset` setting). It never wipes other settings (queries,
cookies, keys stay untouched).
"""

from __future__ import annotations

# Feed channels per connector. weworkremotely values are category slugs
# (some 301-redirect to renamed feeds — feedparser follows, same as the
# default freelance feed has always done). remotive values are their
# documented public-API categories.
CHANNELS: dict[str, dict[str, str]] = {
    "weworkremotely": {
        "freelance": "remote-freelance-jobs",
        "programming": "remote-programming-jobs",
        "design": "remote-design-jobs",
        "marketing": "remote-marketing-jobs",
        "support": "remote-customer-support-jobs",
    },
    "remotive": {
        "software-dev": "software-dev",
        "design": "design",
        "marketing": "marketing",
        "customer-support": "customer-support",
        "sales": "sales",
        "product": "product",
    },
}

# The one-click niche bundles shown in the dashboard.
PACKS: dict[str, dict] = {
    "dev": {
        "label": "💻 dev",
        "blurb": "programming + software-dev feeds on WeWorkRemotely and Remotive",
        "targets": [
            {"connector": "weworkremotely", "preset": "programming"},
            {"connector": "remotive", "preset": "software-dev"},
        ],
    },
    "design": {
        "label": "🎨 design",
        "blurb": "design channels on WeWorkRemotely and Remotive",
        "targets": [
            {"connector": "weworkremotely", "preset": "design"},
            {"connector": "remotive", "preset": "design"},
        ],
    },
    "marketing": {
        "label": "📣 marketing",
        "blurb": "marketing + sales channels on both sources",
        "targets": [
            {"connector": "weworkremotely", "preset": "marketing"},
            {"connector": "remotive", "preset": "marketing"},
        ],
    },
    "support": {
        "label": "🎧 support",
        "blurb": "customer-support channels on both sources",
        "targets": [
            {"connector": "weworkremotely", "preset": "support"},
            {"connector": "remotive", "preset": "customer-support"},
        ],
    },
    "product": {
        "label": "🧭 product",
        "blurb": "Remotive product channel — WWR has no product feed",
        "targets": [
            {"connector": "remotive", "preset": "product"},
        ],
    },
    "freelance": {
        "label": "🐺 freelance firehose",
        "blurb": "the original mix — WWR freelance gigs + Remotive software-dev",
        "targets": [
            {"connector": "weworkremotely", "preset": "freelance"},
            {"connector": "remotive", "preset": "software-dev"},
        ],
    },
}


def pack(key: str) -> dict | None:
    return PACKS.get(key)


def channel(connector_id: str, preset: str | None) -> str | None:
    """The channel slug a connector should fetch, or None to keep defaults."""
    if not preset:
        return None
    return CHANNELS.get(connector_id, {}).get(preset)


def validate() -> list[str]:
    """Sanity-check the registry (used by tests and doctor)."""
    problems: list[str] = []
    for pk, p in PACKS.items():
        if not p.get("targets"):
            problems.append(f"pack {pk}: no targets")
        for t in p["targets"]:
            cid, ch = t.get("connector"), t.get("preset")
            if ch not in CHANNELS.get(cid, {}):
                problems.append(f"pack {pk}: {ch!r} is not a channel of {cid!r}")
    return problems
