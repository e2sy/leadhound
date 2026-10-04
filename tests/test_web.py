"""Web dashboard tests — real HTTP round-trips against an ephemeral local server."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from leadhound import config, db
from leadhound.web import build_state, make_handler


def _seed(guid: str, score: int, title: str, status: str = "pending",
          outcome: str | None = None) -> int:
    db.upsert_job(
        {
            "guid": guid,
            "source": "remoteok",
            "title": title,
            "url": f"https://example.com/{guid}",
            "body": "We need a react developer with stripe experience.",
            "tags": ["react", "stripe"],
        },
        score,
        {
            "budget": {"hourly": 60, "fixed_min": None, "note": "above your minimum"},
            "skills": {"matched": ["react", "stripe"]},
            "red_flags": [] if score > 50 else ["unpaid test gig"],
        },
        f"Draft for {title}.",
    )
    jid = next(j.id for j in db.all_jobs() if j.guid == guid)
    if status != "pending":
        db.set_status(jid, status)
    if outcome:
        db.set_outcome(jid, outcome)
    return jid


@pytest.fixture
def server():
    config.init_files()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler())
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()


def _get(base: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read()


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestState:
    def test_build_state_shape(self):
        config.init_files()
        _seed("s1", 90, "Hot gig")
        _seed("s2", 40, "Cold gig", status="rejected")
        st = build_state()
        assert set(st) == {"stats", "calibration", "jobs", "demo"}
        assert st["demo"] is False  # real sources, not demo data
        assert st["stats"]["total"] == 2
        assert st["jobs"][0]["title"] == "Hot gig"  # best first
        j = st["jobs"][0]
        assert j["matched"] == ["react", "stripe"]
        assert j["draft"] == "Draft for Hot gig."
        assert isinstance(j["tags"], list)

    def test_body_preview_truncated(self):
        config.init_files()
        db.upsert_job(
            {"guid": "long", "source": "x", "title": "Long", "url": "https://e.com",
             "body": "x" * 5000, "tags": []},
            50, {}, "",
        )
        j = build_state()["jobs"][0]
        assert len(j["body"]) <= 401 and j["body"].endswith("…")


class TestHTTP:
    def test_root_serves_html(self, server):
        code, raw = _get(server, "/")
        assert code == 200
        assert b"LEADHOUND" in raw and b"api/state" in raw

    def test_api_state(self, server):
        _seed("w1", 85, "Nice gig")
        code, raw = _get(server, "/api/state")
        d = json.loads(raw)
        assert code == 200
        assert d["stats"]["total"] == 1
        assert d["jobs"][0]["title"] == "Nice gig"

    def test_api_state_no_jobs_ok(self, server):
        code, raw = _get(server, "/api/state")
        d = json.loads(raw)
        assert code == 200 and d["jobs"] == []

    def test_unknown_path_404(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            _get(server, "/nope")
        assert e.value.code == 404

    def test_favicon_204(self, server):
        code, _ = _get(server, "/favicon.ico")
        assert code == 204


class TestMutations:
    def test_status_transition(self, server):
        jid = _seed("m1", 77, "Move me")
        code, d = _post(server, "/api/status", {"id": jid, "status": "approved"})
        assert code == 200 and d["ok"] is True
        assert db.get_job(jid).status == "approved"

    def test_status_rejects_bad_status(self, server):
        jid = _seed("m2", 60, "Bad status")
        code, d = _post(server, "/api/status", {"id": jid, "status": "won"})
        assert code == 400 and d["ok"] is False

    def test_status_rejects_unknown_job(self, server):
        code, _ = _post(server, "/api/status", {"id": 9999, "status": "sent"})
        assert code == 404

    def test_draft_edit(self, server):
        jid = _seed("m3", 70, "Edit draft")
        code, _ = _post(server, "/api/draft", {"id": jid, "text": "Rewritten!"})
        assert code == 200 and db.get_job(jid).draft == "Rewritten!"

    def test_outcome_set_and_clear(self, server):
        jid = _seed("m4", 88, "Outcome me", status="sent")
        code, _ = _post(server, "/api/outcome", {"id": jid, "outcome": "won"})
        assert code == 200 and db.get_job(jid).outcome == "won"
        code, _ = _post(server, "/api/outcome", {"id": jid, "outcome": "none"})
        assert code == 200 and db.get_job(jid).outcome is None

    def test_outcome_rejects_bad_value(self, server):
        jid = _seed("m5", 66, "Bad outcome", status="sent")
        code, _ = _post(server, "/api/outcome", {"id": jid, "outcome": "yolo"})
        assert code == 400

    def test_invalid_json_body(self, server):
        req = urllib.request.Request(
            server + "/api/status", data=b"not json",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 400

    def test_post_unknown_path_404(self, server):
        code, _ = _post(server, "/api/whatever", {"x": 1})
        assert code == 404
