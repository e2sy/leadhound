"""Telegram pocket-sniper endpoints: per-user settings, secret masking,
test-message honest verdicts. Bot API is always stubbed — no network."""

from __future__ import annotations

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
