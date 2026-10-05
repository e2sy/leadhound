"""Per-user notify settings: roundtrip, partial update, seeding, isolation."""

from __future__ import annotations

import pytest

from leadhound import db
from leadhound.config import config_path


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()


def _uid(email: str = "sniper@test.dev") -> int:
    return db.create_user(email, "pw")["id"]


def test_defaults_when_no_row() -> None:
    cfg = db.notify_cfg(_uid())
    assert cfg["telegram_token"] == ""
    assert cfg["telegram_chat_id"] == ""
    assert cfg["telegram_enabled"] == 0
    assert cfg["listen_enabled"] == 0
    assert cfg["push_min_score"] == 70


def test_roundtrip_and_partial_update() -> None:
    uid = _uid()
    db.save_notify_cfg(
        uid,
        telegram_token="12345:AAAA",
        telegram_chat_id="424242",
        telegram_enabled=True,
        push_min_score=80,
    )
    cfg = db.notify_cfg(uid)
    assert cfg["telegram_token"] == "12345:AAAA"
    assert cfg["telegram_chat_id"] == "424242"
    assert cfg["telegram_enabled"] == 1
    assert cfg["push_min_score"] == 80

    # partial: flipping listen on must not touch the token or threshold
    db.save_notify_cfg(uid, listen_enabled=True)
    cfg = db.notify_cfg(uid)
    assert cfg["listen_enabled"] == 1
    assert cfg["telegram_token"] == "12345:AAAA"
    assert cfg["push_min_score"] == 80


def test_push_min_score_clamped() -> None:
    uid = _uid()
    db.save_notify_cfg(uid, push_min_score=500)
    assert db.notify_cfg(uid)["push_min_score"] == 100
    db.save_notify_cfg(uid, push_min_score=-3)
    assert db.notify_cfg(uid)["push_min_score"] == 0


def test_user_isolation() -> None:
    a, b = _uid("a@test.dev"), _uid("b@test.dev")
    db.save_notify_cfg(a, telegram_token="AAA", telegram_chat_id="1")
    db.save_notify_cfg(b, telegram_token="BBB", telegram_chat_id="2")
    assert db.notify_cfg(a)["telegram_token"] == "AAA"
    assert db.notify_cfg(b)["telegram_token"] == "BBB"


def test_seeds_once_from_config_file() -> None:
    uid = _uid()
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(
        "[telegram]\nenabled = true\nbot_token = \"777:SEED\"\nchat_id = \"9001\"\n"
    )
    cfg = db.notify_cfg(uid)
    assert cfg["telegram_token"] == "777:SEED"
    assert cfg["telegram_chat_id"] == "9001"
    assert cfg["telegram_enabled"] == 1

    # after the seed, a user edit wins — the file never overwrites it again
    db.save_notify_cfg(uid, telegram_token="777:MINE")
    cfg = db.notify_cfg(uid)
    assert cfg["telegram_token"] == "777:MINE"


def test_saved_row_blocks_seeding() -> None:
    uid = _uid()
    db.save_notify_cfg(uid, telegram_token="999:MINE", telegram_chat_id="7")
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(
        "[telegram]\nbot_token = \"888:SEED\"\nchat_id = \"9002\"\n"
    )
    cfg = db.notify_cfg(uid)
    assert cfg["telegram_token"] == "999:MINE"
    assert cfg["telegram_chat_id"] == "7"
