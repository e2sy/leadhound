"""The connector registry — every job source leadhound can hunt, in one place.

Built-in sources:
  * zero-config (public, ToS-friendly): remoteok, remotive, weworkremotely,
    hackernews, freelancer
  * bring-your-own: upwork (OAuth2 app keys), fiverr (session cookie, beta),
    rss (any RSS/Atom job feed URL)
  * account link (no gigs — arms the sniper): freelancer_account links the
    user's own Freelancer.com account via official OAuth so 🎯 snipe can
    place real bids with their credentials
"""

from __future__ import annotations

from ..watchers import hn as _hn
from ..watchers import rss as _rss
from . import fiverr, freelancer, freelancer_account, reddit, rss_custom, upwork
from .base import Connector, Field


def _simple(fn):
    """Adapt a zero-argument watcher to the (settings) -> (jobs, None) shape."""
    return lambda settings: (fn(), None)


def _wwr_fetch(settings):
    """WeWorkRemotely adapter — passes the preset channel through."""
    return _rss.weworkremotely(settings or {}), None


def _remotive_fetch(settings):
    """Remotive adapter — passes the preset channel through."""
    return _rss.remotive(settings or {}), None


REGISTRY: dict[str, Connector] = {
    c.id: c
    for c in [
        Connector(
            id="remoteok",
            min_poll=2,
            label="RemoteOK",
            kind="public",
            blurb="Remote dev jobs, public API. Works out of the box.",
            fetch=_simple(_rss.remoteok),
        ),
        Connector(
            id="remotive",
            min_poll=2,
            label="Remotive",
            kind="public",
            blurb="Remote software-dev gigs via Remotive's public API — starter packs switch its channel.",
            fetch=_remotive_fetch,
        ),
        Connector(
            id="weworkremotely",
            min_poll=2,
            label="WeWorkRemotely",
            kind="public",
            blurb="The remote RSS feeds — starter packs pick the category channel.",
            fetch=_wwr_fetch,
        ),
        Connector(
            id="hackernews",
            min_poll=2,
            label="Hacker News",
            kind="public",
            blurb="The monthly 'Freelancer? Seeking freelancer?' thread.",
            fetch=_simple(_hn.fetch),
        ),
        Connector(
            id="reddit",
            min_poll=5,
            label="Reddit [Hiring] posts",
            kind="public",
            blurb=(
                "[Hiring] posts from freelance subreddits (r/forhire, r/hiring, "
                "r/jobbit) via Reddit's public JSON — polite 5-minute cadence. "
                "Edit the subreddit list to match your niche."
            ),
            fields=[
                Field(
                    "subreddits",
                    "Subreddits (comma-separated)",
                    placeholder="forhire,hiring,jobbit",
                    hint="max 5 · only [Hiring] posts count, [For Hire] is skipped",
                ),
            ],
            fetch=reddit.fetch,
        ),
        Connector(
            id="freelancer",
            label="Freelancer.com",
            kind="public",
            blurb=(
                "Live search over Freelancer.com's public API — real budgets, "
                "no login. Optional: paste your app's webhook signing secret "
                "and new projects hit the board in seconds, not next poll."
            ),
            fields=[
                Field("query", "Search keywords", placeholder="react nextjs"),
                Field(
                    "webhook_secret",
                    "Webhook signing secret",
                    placeholder="secret from the freelancer developer portal",
                    secret=True,
                    hint="developers.freelancer.com → your app → webhook secret; "
                         "point the webhook at POST {your leadhound}/webhook/freelancer",
                ),
            ],
            fetch=freelancer.fetch,
        ),
        Connector(
            id="freelancer_account",
            label="Freelancer.com account (snipe)",
            kind="keys",
            blurb=(
                "Links YOUR Freelancer.com account via official OAuth so the "
                "🎯 snipe button places real bids with your credentials. "
                "Gig hunting stays on the Freelancer.com source card — this "
                "link never fetches gigs, it fires shots."
            ),
            fields=[
                Field("client_id", "OAuth client id", placeholder="freelancer app client id"),
                Field("client_secret", "OAuth client secret", secret=True),
            ],
            setup_url="https://www.freelancer.com/developers/applications",
            fetch=freelancer_account.fetch,
        ),
        Connector(
            id="upwork",
            label="Upwork",
            kind="keys",
            blurb=(
                "Official OAuth2: create a free dev app, paste the keys, "
                "connect once — leadhound refreshes the token forever."
            ),
            fields=[
                Field("client_id", "OAuth client id", placeholder="upwork app client id"),
                Field("client_secret", "OAuth client secret", secret=True),
                Field("query", "Search keywords", placeholder="react native"),
            ],
            setup_url="https://www.upwork.com/developer/applications",
            fetch=upwork.fetch,
        ),
        Connector(
            id="fiverr",
            label="Fiverr (beta)",
            kind="cookie",
            blurb=(
                "Unofficial: polls buyer requests with your session cookie. "
                "Paste a fresh cookie if Fiverr logs you out."
            ),
            fields=[
                Field(
                    "cookie",
                    "Fiverr session cookie",
                    placeholder="cookie header from your logged-in browser",
                    secret=True,
                    hint="DevTools → Network → any fiverr.com request → Cookie header",
                ),
            ],
            fetch=fiverr.fetch,
        ),
        Connector(
            id="rss",
            min_poll=2,
            label="Custom RSS / Atom feed",
            kind="feed",
            blurb="Any job feed URL — niche boards, Upwork/Fiverr mirrors, agency feeds.",
            fields=[
                Field("url", "Feed URL", placeholder="https://example.com/jobs.rss"),
            ],
            fetch=rss_custom.fetch,
        ),
    ]
}


def all_connectors() -> list[Connector]:
    return list(REGISTRY.values())


def get(connector_id: str) -> Connector | None:
    return REGISTRY.get(connector_id)
