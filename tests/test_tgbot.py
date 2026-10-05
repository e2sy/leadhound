"""Pocket bot: command parsing, confirm TTL, chat gating, the snipe duel.
Every test runs against a FakeBot transport — no network, ever."""

from __future__ import annotations

import threading

import pytest

from leadhound import db
from leadhound.notify import tgbot


class FakeBot(tgbot.Bot):
    """Records sends instead of hitting the Bot API."""

    def __init__(self) -> None:
        super().__init__("TEST:TOKEN")
        self.sent: list[tuple[str, str, dict | None]] = []

    def send(self, chat: str, text: str, keyboard: dict | None = None) -> bool:
        self.sent.append((chat, text, keyboard))
        return True

    def answer_callback(self, cb_id: str) -> None:
        pass


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()


@pytest.fixture
def seeded():
    uid = db.create_user("pocket@test.dev", "pw")["id"]

    def _job(guid, score, status="pending", bmin=200, bmax=900):
        jid, _ = db.upsert_job(
            {"guid": guid, "source": "remoteok", "title": f"gig {guid}",
             "url": f"https://x.test/{guid}", "body": "react",
             "tags": [], "budget_min": bmin, "budget_max": bmax},
            score, {}, f"draft for {guid}", user_id=uid,
        )
        if status != "pending":
            db.set_status(jid, status)
        return jid

    return {"uid": uid, "mk": _job}


def _deps(seed, fired: list, planned: dict | None = None):
    uid = seed["uid"]
    return {
        "queue": lambda n: [
            tgbot.fmt_queue_line(j)
            for j in db.all_jobs(user_id=uid) if j.status == "pending"
        ][:n],
        "gig": lambda jid: (
            tgbot.fmt_gig_card(j, j.draft)
            if (j := db.get_job(jid)) and j.user_id == uid else None
        ),
        "approve": lambda jid: (
            (db.set_status(jid, "approved"), f"#{jid} approved")[1]
            if (j := db.get_job(jid)) and j.user_id == uid
            else f"no gig #{jid} on your board"
        ),
        "plan": lambda jid, amount: planned or {
            "ok": True, "mode": "api", "amount": amount or 500,
            "detail": "Freelancer.com · live bid",
        },
        "fire": lambda jid, amount: (fired.append((jid, amount)),
                                     {"ok": True, "amount": amount or 500,
                                      "bid_id": 777})[1],
        "stats": lambda: {"kills": 1},
    }


def _bot(seed, deps, chat="4242"):
    b = tgbot.PocketBot(user_id=seed["uid"], token="TEST:TOKEN",
                        chat_id=chat, stop=threading.Event(), deps=deps)
    b.bot = FakeBot()
    return b


# ------------------------------------------------------------------ parsing
def test_parse_command():
    assert tgbot.parse_command("/snipe 42 500") == ("snipe", ["42", "500"])
    assert tgbot.parse_command("/QUEUE 3") == ("queue", ["3"])
    assert tgbot.parse_command("/queue@leadhoundbot 3") == ("queue", ["3"])
    assert tgbot.parse_command("just chatting") == ("", [])
    assert tgbot.parse_command("/") == ("", [])
    assert tgbot.parse_command("") == ("", [])


def test_confirm_store_ttl(monkeypatch):
    store = tgbot.ConfirmStore(ttl=100.0)
    store.put("c1", 42, 500.0)
    assert store.pop("c1") and store.pop("c1") is None  # pop removes
    store.put("c2", 7, None)
    real = tgbot.time.time
    monkeypatch.setattr(tgbot.time, "time", lambda: real() + 1e9)
    assert store.pop("c2") is None  # expired = never asked (fail-safe)


# ------------------------------------------------------------------ commands
def test_queue_lists_pending(seeded):
    seeded["mk"]("a", 90)
    seeded["mk"]("b", 70)
    seeded["mk"]("c", 50, status="sent")  # sniped gigs never clutter the queue
    b = _bot(seeded, _deps(seeded, []))
    text, kb = b._command("queue", [], "4242")
    assert kb is None and "gig a" in text and "gig c" not in text


def test_gig_and_approve(seeded):
    jid = seeded["mk"]("k", 84)
    b = _bot(seeded, _deps(seeded, []))
    text, _ = b._command("gig", [str(jid)], "4242")
    assert "gig k" in text and "draft for k" in text
    text, _ = b._command("approve", [str(jid)], "4242")
    assert "approved" in text
    assert db.get_job(jid).status == "approved"


def test_approve_rejects_foreign_gig(seeded):
    stranger = db.create_user("x@test.dev", "pw")["id"]
    jid, _ = db.upsert_job(
        {"guid": "alien", "source": "remoteok", "title": "alien gig",
         "url": "https://x.test/a", "body": "b", "tags": []},
        99, {}, "d", user_id=stranger,
    )
    b = _bot(seeded, _deps(seeded, []))
    text, _ = b._command("approve", [str(jid)], "4242")
    assert "no gig" in text
    assert db.get_job(jid).status == "pending"


def test_snipe_arms_and_fires(seeded):
    jid = seeded["mk"]("s", 95)
    fired: list = []
    b = _bot(seeded, _deps(seeded, fired))
    text, kb = b._command("snipe", [str(jid), "650"], "4242")
    assert kb is not None and "armed" in text
    text, _ = b._on_callback("4242", "fire"), None
    assert fired == [(jid, 650.0)]


def test_snipe_cancel_never_fires(seeded):
    jid = seeded["mk"]("s2", 95)
    fired: list = []
    b = _bot(seeded, _deps(seeded, fired))
    b._command("snipe", [str(jid)], "4242")
    b._on_callback("4242", "cancel")
    assert fired == []


def test_snipe_kit_mode_skips_confirm(seeded):
    jid = seeded["mk"]("s3", 95)
    fired: list = []
    deps = _deps(seeded, fired, planned={
        "ok": True, "mode": "kit",
        "detail": "open the gig and send the draft",
    })
    b = _bot(seeded, deps)
    text, kb = b._command("snipe", [str(jid)], "4242")
    assert kb is None and "kit" in text and "fired" not in text
    b._on_callback("4242", "fire")  # stale state must not exist
    assert fired == []


def test_snipe_bad_plan_is_honest(seeded):
    jid = seeded["mk"]("s4", 95)
    deps = _deps(seeded, [], planned={"ok": False, "detail": "not linked"})
    b = _bot(seeded, deps)
    text, kb = b._command("snipe", [str(jid)], "4242")
    assert kb is None and "not linked" in text


# ------------------------------------------------------------------ gating
def test_foreign_chat_gets_silence(seeded):
    seeded["mk"]("h", 90)
    b = _bot(seeded, _deps(seeded, []))
    b._handle({"message": {"chat": {"id": 999999}, "text": "/queue"}})
    assert b.bot.sent == []


def test_own_chat_and_callbacks_work(seeded):
    jid = seeded["mk"]("h2", 90)
    b = _bot(seeded, _deps(seeded, []))
    b._handle({"message": {"chat": {"id": 4242}, "text": "/queue"}})
    assert len(b.bot.sent) == 1 and "gig h2" in b.bot.sent[0][1]
    b._command("snipe", [str(jid)], "4242")
    b._handle({"callback_query": {"id": "cb1", "data": "fire",
                                  "message": {"chat": {"id": 4242}}}})
    assert "fired" in b.bot.sent[-1][1]


def test_unknown_command_and_garbage(seeded):
    b = _bot(seeded, _deps(seeded, []))
    text, _ = b._command("nuke", [], "4242")
    assert "/help" in text
    text, _ = b._command("", ["junk"], "4242")
    assert "/help" in text or "pocket sniper" in text


# ------------------------------------------------------------------ /ping /digest
def test_ping_reports_alive(seeded):
    deps = _deps(seeded, [])
    deps["ping"] = lambda: tgbot.compose_ping(2, None)
    b = _bot(seeded, deps)
    b._handle({"message": {"chat": {"id": 4242}, "text": "/ping"}})
    assert len(b.bot.sent) == 1
    assert "alive" in b.bot.sent[0][1] and "armed" in b.bot.sent[0][1]
    assert "last sweep never" in b.bot.sent[0][1]


def test_compose_digest_counts_and_ranks_top_gigs(seeded):
    seeded["mk"]("dg-1", 91)
    seeded["mk"]("dg-2", 84, status="approved")
    seeded["mk"]("dg-3", 70, status="sent")
    text = tgbot.compose_digest(
        db.all_jobs(user_id=seeded["uid"]), db.snipe_stats(seeded["uid"])
    )
    assert "board digest" in text
    assert "2 pending" in text and "1 approved" in text
    assert "gig dg-1" in text  # the best pending gig surfaced


def test_compose_digest_empty_board(seeded):
    text = tgbot.compose_digest([], db.snipe_stats(seeded["uid"]))
    assert "0 pending" in text and "best on the radar" not in text


def test_help_lists_every_command(seeded):
    b = _bot(seeded, _deps(seeded, []))
    text, _ = b._command("help", [], "4242")
    for word in ("/queue", "/gig", "/approve", "/snipe", "/stats", "/digest", "/ping"):
        assert word in text
