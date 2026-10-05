"""Telegram pocket-sniper endpoints: per-user settings, secret masking,
test-message honest verdicts. Bot API is always stubbed — no network."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.notify import telegram as tg


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "pocket@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def test_defaults_have_no_token(authed):
    r = authed.get("/api/notify")
    assert r.status_code == 200
    n = r.json()["notify"]
    assert n["has_token"] is False
    assert n["telegram_enabled"] is False
    assert n["push_min_score"] == 70


def test_save_and_mask(authed):
    r = authed.post("/api/notify/telegram",
                    json={"token": "123:SECRET", "chat_id": "42", "enabled": True})
    assert r.status_code == 200
    n = r.json()["notify"]
    assert n["has_token"] is True
    assert n["telegram_chat_id"] == "42"
    assert n["telegram_enabled"] is True
    assert "SECRET" not in r.text  # the token itself never comes back


def test_partial_save_keeps_token(authed):
    authed.post("/api/notify/telegram", json={"token": "123:KEEPME", "chat_id": "42"})
    r = authed.post("/api/notify/telegram", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["notify"]["has_token"] is True
    # second user stays clean (per-user, not global)
    authed.post("/api/auth/register",
                json={"email": "other@test.dev", "password": "hunter2boogaloo"})
    c2 = TestClient(authed.app)
    c2.post("/api/auth/login",
            json={"email": "other@test.dev", "password": "hunter2boogaloo"})
    n2 = c2.get("/api/notify").json()["notify"]
    assert n2["has_token"] is False


def test_push_min_score_clamped(authed):
    r = authed.post("/api/notify/telegram", json={"push_min_score": 9001})
    assert r.json()["notify"]["push_min_score"] == 100


def test_requires_auth():
    config.init_files()
    c = TestClient(create_app(start_poller=False))
    assert c.get("/api/notify").status_code == 401
    assert c.post("/api/notify/telegram", json={}).status_code == 401


def test_test_message_needs_credentials(authed):
    r = authed.post("/api/notify/telegram/test")
    assert r.status_code == 400
    assert "save your bot token" in r.json()["detail"]


def test_test_message_ok(monkeypatch, authed):
    authed.post("/api/notify/telegram", json={"token": "123:OK", "chat_id": "42"})
    seen = {}

    def fake_send(token, chat):
        seen["token"], seen["chat"] = token, chat
        return True, "Telegram accepted the message"

    monkeypatch.setattr(tg, "send_test_message", fake_send)
    r = authed.post("/api/notify/telegram/test")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "detail": "Telegram accepted the message"}
    assert seen == {"token": "123:OK", "chat": "42"}


def test_test_message_surfaces_telegram_verdict(monkeypatch, authed):
    authed.post("/api/notify/telegram", json={"token": "123:BAD", "chat_id": "42"})
    monkeypatch.setattr(tg, "send_test_message",
                        lambda t, c: (False, "Unauthorized"))
    r = authed.post("/api/notify/telegram/test")
    assert r.status_code == 502
    assert r.json()["detail"] == "Unauthorized"


def test_db_seeds_token_from_config_file(authed):
    """pre-0.9 migration: a config.toml [telegram] block seeds a wiped account."""
    from leadhound.db import _conn

    uid = db.user_by_email("pocket@test.dev")["id"]
    c = _conn()
    c.execute("DELETE FROM notify_settings WHERE user_id = ?", (uid,))
    c.commit()
    c.close()
    config.config_path().write_text(
        '[telegram]\nbot_token = "777:SEED"\nchat_id = "9001"\n'
    )
    n = authed.get("/api/notify").json()["notify"]
    assert n["has_token"] is True
    assert n["telegram_chat_id"] == "9001"


def _job(guid: str) -> dict:
    return {
        "guid": guid,
        "source": "remoteok",
        "title": guid,
        "url": f"https://example.com/{guid}",
        "body": "react developer needed",
        "tags": ["react"],
    }


def test_push_min_score_gates_telegram(monkeypatch, authed):
    """Below the bar: stored on the board, silent in the pocket."""
    from leadhound import pipeline
    from leadhound.config import LLMConfig, Profile, TelegramConfig

    sent: list[str] = []
    monkeypatch.setattr(
        pipeline.tg, "send_job_card",
        lambda tok, chat, j, b: sent.append(j.title) or True,
    )
    monkeypatch.setattr(pipeline.tg, "send_draft", lambda tok, chat, j: True)
    fixed = {"skills": {"matched": ["x"]}, "budget": {}, "red_flags": []}
    monkeypatch.setattr(pipeline, "score_job", lambda job, profile: (75, dict(fixed)))
    prof = Profile(name="T", headline="", skills=[], min_hourly=0,
                   min_fixed_budget=0, red_flags=[], highlights=[], tone_samples=[])
    tg = TelegramConfig(enabled=True, bot_token="t", chat_id="c")
    uid = db.user_by_email("pocket@test.dev")["id"]

    pipeline.ingest_jobs([_job("quiet")], profile=prof, llm_cfg=LLMConfig(),
                         min_score=60, tg_cfg=tg, tg_min_score=80, user_id=uid)
    assert sent == []  # 75 < 80: no buzz

    monkeypatch.setattr(pipeline, "score_job", lambda job, profile: (90, dict(fixed)))
    pipeline.ingest_jobs([_job("loud")], profile=prof, llm_cfg=LLMConfig(),
                         min_score=60, tg_cfg=tg, tg_min_score=80, user_id=uid)
    assert sent == ["loud"]  # 90 >= 80: fired

    monkeypatch.setattr(pipeline, "score_job", lambda job, profile: (62, dict(fixed)))
    pipeline.ingest_jobs([_job("loud2")], profile=prof, llm_cfg=LLMConfig(),
                         min_score=60, tg_cfg=tg, tg_min_score=0, user_id=uid)
    assert "loud2" in sent  # bar 0 -> board threshold rules (old behavior)


def test_per_user_isolation_in_pipeline(monkeypatch, authed):
    """user B (no telegram) must never inherit user A's bot."""
    from leadhound import pipeline
    from leadhound.config import LLMConfig, Profile, TelegramConfig

    sent: list[str] = []
    monkeypatch.setattr(
        pipeline.tg, "send_job_card",
        lambda tok, chat, j, b: sent.append((chat, j.title)) or True,
    )
    monkeypatch.setattr(pipeline.tg, "send_draft", lambda tok, chat, j: True)
    fixed = {"skills": {"matched": ["x"]}, "budget": {}, "red_flags": []}
    monkeypatch.setattr(pipeline, "score_job", lambda job, profile: (95, dict(fixed)))
    prof = Profile(name="T", headline="", skills=[], min_hourly=0,
                   min_fixed_budget=0, red_flags=[], highlights=[], tone_samples=[])
    tg = TelegramConfig(enabled=True, bot_token="t", chat_id="c")
    a = db.user_by_email("pocket@test.dev")["id"]
    b = db.create_user("b@test.dev", "pw")["id"]

    pipeline.ingest_jobs([_job("for-a")], profile=prof, llm_cfg=LLMConfig(),
                         min_score=60, tg_cfg=tg, tg_min_score=0, user_id=a)
    pipeline.ingest_jobs([_job("for-b")], profile=prof, llm_cfg=LLMConfig(),
                         min_score=60, tg_cfg=None, tg_min_score=0, user_id=b)
    assert sent == [("c", "for-a")]


def test_cadence_endpoint(authed):
    r = authed.post("/api/notify/cadence",
                    json={"connector": "remoteok", "minutes": 3})
    assert r.status_code == 200
    assert r.json()["minutes"] == 5  # floor
    r = authed.post("/api/notify/cadence",
                    json={"connector": "remoteok", "minutes": 500})
    assert r.json()["minutes"] == 120  # ceiling
    r = authed.post("/api/notify/cadence",
                    json={"connector": "nope", "minutes": 10})
    assert r.status_code == 404
    stored = db.connector_cfg(db.user_by_email("pocket@test.dev")["id"], "remoteok")
    assert stored["settings"]["poll_minutes"] == 120


def test_radar_reports_push_and_cadence(authed):
    authed.post("/api/notify/telegram", json={"token": "1:2", "chat_id": "3",
                                              "enabled": True, "push_min_score": 88})
    authed.post("/api/notify/cadence", json={"connector": "remoteok", "minutes": 9})
    authed.post("/api/connectors/remoteok", json={"enabled": True})
    d = authed.get("/api/radar").json()
    assert d["push"]["telegram_enabled"] is True
    assert d["push"]["push_min_score"] == 88
    assert d["cadence"]["remoteok"] == 9


# ------------------------------------------------------- pocket listener (C5)
class _FakeBot:
    errors = 0


def _fake_spawn(calls):
    def _spawn(*, user_id, token, chat_id, stop, deps):
        calls.append({"user_id": user_id, "token": token, "chat": chat_id})
        return _FakeBot(), threading.Thread(target=lambda: None, daemon=True)
    return _spawn


def test_listen_needs_credentials(authed):
    r = authed.post("/api/notify/telegram/listen", json={"listen": True})
    assert r.status_code == 400
    assert "bot token and chat id" in r.json()["detail"]


def test_listen_start_stop_roundtrip(monkeypatch, authed):
    from leadhound import api
    authed.post("/api/notify/telegram",
                json={"token": "1:ABC", "chat_id": "42", "enabled": True})
    calls: list = []
    monkeypatch.setattr(api.tgbot, "spawn", _fake_spawn(calls))
    r = authed.post("/api/notify/telegram/listen", json={"listen": True})
    assert r.json()["listening"] is True
    assert calls and calls[0]["chat"] == "42"
    n = authed.get("/api/notify").json()["notify"]
    assert n["listen_enabled"] is True and n["listening"] is True
    radar = authed.get("/api/radar").json()["push"]
    assert radar["listener_running"] is True
    r = authed.post("/api/notify/telegram/listen", json={"listen": False})
    assert r.json()["listening"] is False
    assert authed.get("/api/notify").json()["notify"]["listening"] is False


def test_listener_autoarms_on_server_boot(monkeypatch, authed):
    from leadhound import api
    uid = db.user_by_email("pocket@test.dev")["id"]
    db.save_notify_cfg(uid, telegram_token="9:BOOT", telegram_chat_id="7",
                       telegram_enabled=True, listen_enabled=True)
    calls: list = []
    monkeypatch.setattr(api.tgbot, "spawn", _fake_spawn(calls))
    with TestClient(api.create_app(start_poller=True)) as c:
        c.get("/api/health")  # lifespan runs on first request
    assert len(calls) == 1 and calls[0]["user_id"] == uid


def test_listener_not_double_spawned(monkeypatch, authed):
    from leadhound import api
    authed.post("/api/notify/telegram",
                json={"token": "1:ABC", "chat_id": "42"})
    calls: list = []
    monkeypatch.setattr(api.tgbot, "spawn", _fake_spawn(calls))
    authed.post("/api/notify/telegram/listen", json={"listen": True})
    authed.post("/api/notify/telegram/listen", json={"listen": True})  # re-arm
    assert len(calls) == 2  # restart-clean: stop old, spawn new — never two polls


def test_connector_failure_alerts_pocket_once(monkeypatch, authed):
    from leadhound.connectors import REGISTRY, Connector, Field

    authed.post("/api/notify/telegram",
                json={"token": "1:ALERT", "chat_id": "42", "enabled": True})
    alerts: list[str] = []
    monkeypatch.setattr(tg, "send_plain",
                        lambda tok, chat, text: alerts.append(text) or True)

    def boom(settings):
        raise RuntimeError("fiverr cookie died")

    monkeypatch.setitem(REGISTRY, "fiverr", Connector(
        id="fiverr", label="Fiverr", kind="public", blurb="b",
        fields=[Field("cookie", "Cookie")], fetch=boom))
    authed.post("/api/connectors/fiverr", json={"enabled": True})
    r = authed.post("/api/connectors/fiverr/run")
    assert r.status_code == 502
    assert len(alerts) == 1 and "fiverr cookie died" in alerts[0]
    # same failure again -> silence (never cry wolf)
    authed.post("/api/connectors/fiverr/run")
    assert len(alerts) == 1


def test_no_alert_without_telegram(monkeypatch, authed):
    from leadhound.connectors import REGISTRY, Connector, Field

    alerts: list[str] = []
    monkeypatch.setattr(tg, "send_plain",
                        lambda tok, chat, text: alerts.append(text) or True)

    def boom(settings):
        raise RuntimeError("upwork said no")

    monkeypatch.setitem(REGISTRY, "upwork", Connector(
        id="upwork", label="Upwork", kind="public", blurb="b",
        fields=[Field("client_id", "ID")], fetch=boom))
    authed.post("/api/connectors/upwork", json={"enabled": True})
    authed.post("/api/connectors/upwork/run")
    assert alerts == []
