"""Shared fixtures: every test runs against an isolated LEADHOUND_HOME."""

import pathlib
import sys

import pytest

# Allow running pytest without installing the package first
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point ~/.leadhound at a temp dir so tests never touch real user data."""
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / ".leadhound"))
    yield


@pytest.fixture
def profile():
    from leadhound.config import Profile

    return Profile(
        name="Test Sniper",
        headline="Full-stack dev — React, Node, Stripe",
        skills=["react", "typescript", "stripe", "node.js", "python", "next.js"],
        min_hourly=30.0,
        min_fixed_budget=800.0,
        red_flags=["unpaid", "for exposure"],
        highlights=["Shipped 10 apps to production"],
        tone_samples=[],
    )
