"""Demo mode — injects realistic sample gigs so leadhound works with zero network.

This is also the YouTube-demo mode: `leadhound demo && leadhound queue`.
"""

from __future__ import annotations

from datetime import UTC, datetime

DEMO_JOBS = [
    {
        "guid": "demo-001",
        "source": "demo",
        "title": "React Native fitness app with Stripe subscriptions — long-term",
        "url": "https://example.com/gig/rn-fitness",
        "body": (
            "We're a funded startup (12 previous hires, 5.0 rating, payment verified) "
            "looking for a senior mobile dev. Budget: $3,000 - $4,500 fixed. "
            "Stack: React Native, Node.js, PostgreSQL, Stripe. Offline-first is a must. "
            "Ongoing work available for the right person."
        ),
        "tags": ["react native", "stripe", "node.js"],
        "posted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    },
    {
        "guid": "demo-002",
        "source": "demo",
        "title": "Next.js SaaS dashboard + Stripe billing (App Router)",
        "url": "https://example.com/gig/nextjs-saas",
        "body": (
            "Need a production-grade dashboard: Next.js App Router, TypeScript, "
            "PostgreSQL, Stripe billing with webhooks. Budget $2,400 fixed. "
            "Design ready in Figma. Start ASAP."
        ),
        "tags": ["next.js", "typescript", "stripe"],
        "posted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    },
    {
        "guid": "demo-003",
        "source": "demo",
        "title": "WordPress scraper script — small task",
        "url": "https://example.com/gig/wp-scrape",
        "body": "Need a quick script to scrape 200 pages. Budget $50. Python.",
        "tags": ["python", "scraping"],
        "posted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    },
    {
        "guid": "demo-004",
        "source": "demo",
        "title": "NFT game devs wanted — equity only, for exposure",
        "url": "https://example.com/gig/nft-exposure",
        "body": "Building the next big P2E game. Equity only, great for your portfolio. React + WebGL.",
        "tags": ["react", "webgl"],
        "posted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    },
]
