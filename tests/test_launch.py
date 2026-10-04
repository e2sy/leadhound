"""Tests for the double-click launcher (leadhound.launch).

The launcher no longer seeds demo gigs — the empty board offers real
fetching and an explicit sample-data button instead.
"""

from __future__ import annotations

import socket

from leadhound import db
from leadhound.config import is_initialized
from leadhound.launch import find_free_port, launch_app


def test_find_free_port_returns_bindable_port() -> None:
    port = find_free_port(7900, tries=5)
    assert 7900 <= port < 7905
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_free_port_skips_occupied_port(monkeypatch) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]
    try:
        port = find_free_port(taken, tries=5)
        assert port != taken
    finally:
        blocker.close()


def test_launch_inits_without_demo_data(monkeypatch, tmp_path) -> None:
    """First run: init happens, board starts EMPTY (no fake gigs)."""
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    served: list[tuple] = []
    import leadhound.web as web_mod

    monkeypatch.setattr(web_mod, "serve",
                        lambda host, port, open_browser: served.append((host, port)))
    launch_app()
    assert served, "launch_app must hand off to the server"
    host, port = served[0]
    assert host == "127.0.0.1"
    assert 7800 <= port < 7810
    assert is_initialized()
    assert db.stats()["total"] == 0  # no demo seeding — the board is honestly empty
    assert db.users_count() == 0  # accounts are created in the browser


def test_launch_second_run_uses_existing_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    import leadhound.web as web_mod

    calls: list[int] = []
    monkeypatch.setattr(web_mod, "serve",
                        lambda host, port, open_browser: calls.append(port))
    launch_app()
    launch_app()
    assert len(calls) == 2
    assert db.stats()["total"] == 0
