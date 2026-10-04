"""Tests for the double-click launcher (leadhound.launch)."""

from __future__ import annotations

import socket

from leadhound import db
from leadhound.config import init_files, is_initialized, load_profile
from leadhound.launch import ensure_first_run_data, find_free_port


def test_find_free_port_returns_bindable_port() -> None:
    port = find_free_port(7900, tries=5)
    assert 7900 <= port < 7905
    # the returned port must actually be bindable (we release before returning,
    # so a quick re-bind check is the best offline assertion we can make)
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


def test_first_run_seeds_demo_gigs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    seeded = ensure_first_run_data()
    assert seeded == 4
    assert is_initialized()
    assert db.stats()["total"] == 4
    # drafts exist — the board is explorable immediately
    jobs = db.all_jobs()
    assert any(j.draft for j in jobs)


def test_second_run_does_not_reseed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    assert ensure_first_run_data() == 4
    assert ensure_first_run_data() == 0  # data already present
    assert db.stats()["total"] == 4


def test_existing_data_is_never_replaced(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    init_files()
    load_profile()  # force profile read path
    db.ensure_db()
    db.upsert_job(
        {"guid": "real-1", "source": "remoteok", "title": "real gig",
         "url": "https://x/1", "body": "", "tags": ""},
        77, {"skills": {"matched": [], "score": 0}}, "",
    )
    assert ensure_first_run_data() == 0
    assert db.stats()["total"] == 1  # untouched


def test_build_state_flags_demo_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    ensure_first_run_data()
    from leadhound.web import build_state

    state = build_state()
    assert state["demo"] is True
    assert all(j["source"] == "demo" for j in state["jobs"])

    db.upsert_job(
        {"guid": "real-2", "source": "remotive", "title": "real",
         "url": "https://x/2", "body": "", "tags": ""},
        50, {"skills": {"matched": [], "score": 0}}, "",
    )
    assert build_state()["demo"] is False


def test_launch_app_serves_dashboard(monkeypatch, tmp_path) -> None:
    """Full double-click path: init + seed + bind + serve, then stop cleanly."""
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    import threading
    import time
    import urllib.request

    from leadhound import web as web_mod
    from leadhound.launch import launch_app

    port = find_free_port(7950, tries=10)
    monkeypatch.setattr("leadhound.launch.find_free_port", lambda *a, **k: port)
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))

    def fake_serve_forever(self, poll_interval=0.5):
        """Serve requests for a bounded window, then let launch_app return."""
        self.timeout = 0.2
        end = time.time() + 8
        while time.time() < end:
            self.handle_request()

    monkeypatch.setattr(web_mod.ThreadingHTTPServer, "serve_forever",
                        fake_serve_forever)

    t = threading.Thread(target=launch_app, daemon=True)
    t.start()

    state = None
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state",
                                        timeout=2) as r:
                state = r.read()
                break
        except OSError:
            time.sleep(0.2)
    assert state is not None, "dashboard did not come up"
    assert b'"demo": true' in state

    for _ in range(20):  # browser auto-open fires on a 0.6s timer
        if opened:
            break
        time.sleep(0.2)
    assert opened and opened[0].startswith("http://127.0.0.1:")

    t.join(timeout=12)
    assert not t.is_alive(), "launch_app did not return"
