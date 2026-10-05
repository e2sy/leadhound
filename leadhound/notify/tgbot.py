"""The pocket sniper — a two-way Telegram bot per listening account.

Your gigs live in your pocket now:

    /queue           top pending gigs, best score first
    /gig 42          the full card + the drafted proposal
    /approve 42      move it to approved
    /snipe 42 500    Freelancer live-fire (amount optional) — asks before firing
    /stats           the scoreboard, pocket-sized
    /digest          board summary + the three best gigs
    /ping            is the radar alive?
    /help            what you just read

Design rules, learned the hard way:
- every handler is user-scoped and chat-scoped: a stray /queue from any
  other chat gets silence, never your data;
- firing asks first — the confirm state lives in memory with a 5-minute
  TTL, so a restart can never leave a half-armed bid around;
- handlers never talk to the Bot API directly; they return (text,
  keyboard) and the transport sends. That keeps every decision testable
  with zero network.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests

API = "https://api.telegram.org/bot{token}/{method}"
CONFIRM_TTL = 300.0  # a pending Fire prompt dies after 5 minutes


# ------------------------------------------------------------------ pure bits
def parse_command(text: str) -> tuple[str, list[str]]:
    """/snipe 42 500 -> ('snipe', ['42', '500']); junk -> ('', [])."""
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return "", []
    parts = stripped[1:].split()
    if not parts:
        return "", []
    return parts[0].lower().split("@", 1)[0], parts[1:]  # /cmd@bot -> cmd


@dataclass
class Confirm:
    """A /snipe waiting for the user's thumb: which gig, how much, when."""

    job_id: int
    amount: float | None
    ts: float


class ConfirmStore:
    """chat -> pending snipe. TTL-guarded: stale confirms self-destruct."""

    def __init__(self, ttl: float = CONFIRM_TTL) -> None:
        self.ttl = ttl
        self._d: dict[str, Confirm] = {}
        self._lock = threading.Lock()

    def put(self, chat: str, job_id: int, amount: float | None) -> None:
        with self._lock:
            self._d[chat] = Confirm(job_id=job_id, amount=amount, ts=time.time())

    def pop(self, chat: str) -> Confirm | None:
        with self._lock:
            c = self._d.pop(chat, None)
        if c and time.time() - c.ts > self.ttl:
            return None  # expired — treat as never asked (fail-safe)
        return c


def _money(job) -> str:
    if job.hourly:
        return f"${job.hourly:g}/hr"
    if job.budget_max and job.budget_min:
        return f"${job.budget_min:,.0f}-{job.budget_max:,.0f}"
    if job.budget_max:
        return f"to ${job.budget_max:,.0f}"
    if job.budget_min:
        return f"from ${job.budget_min:,.0f}"
    return "budget not stated"


def fmt_queue_line(j) -> str:
    money = _money(j)
    return f"{j.id} · {j.score}/100 · {money} · {j.title[:70]}"


def fmt_gig_card(j, draft: str) -> str:
    money = _money(j)
    head = (
        f"🎯 <b>{j.score}/100</b> — {j.title}\n"
        f"<b>source:</b> {j.source} · <b>money:</b> {money} · "
        f"<b>status:</b> {j.status}\n"
        f'<a href="{j.url}">open gig ↗</a>\n'
    )
    tail = f"\n<i>{draft[:2800]}</i>" if draft else "\n<i>(no draft yet)</i>"
    return head + tail


def compose_ping(armed: int, last_run: str | None) -> str:
    """Pure /ping text — the api layer feeds it db numbers."""
    when = str(last_run or "never")[:16]
    return f"🐺 alive — {armed} source(s) armed · last sweep {when}"


def compose_digest(jobs: list, stats: dict) -> str:
    """Pure /digest text: counts, scoreboard, and the three best pending
    gigs. jobs = the user's Job rows, stats = db.snipe_stats() output."""
    pend = sorted(
        (j for j in jobs if j.status == "pending"),
        key=lambda j: (-j.score, -j.id),
    )
    appr = sum(1 for j in jobs if j.status == "approved")
    lines = [
        "🐺 <b>board digest</b>",
        f"🎯 {len(pend)} pending · ✅ {appr} approved · "
        f"🔥 {stats.get('sniped', 0)} sniped",
        f"↩ {stats.get('reply_rate', '—')}% replies · "
        f"🏆 {stats.get('wins', 0)}W / {stats.get('losses', 0)}L",
    ]
    if pend:
        lines.append("")
        lines.append("<b>best on the radar</b>")
        lines += [fmt_queue_line(j) for j in pend[:3]]
    return "\n".join(lines)


# ------------------------------------------------------------------ transport
class Bot:
    """One bot token = one transport. sendMessage is serialized at ~1/s per
    Telegram's per-chat limit; 429s are honored once, then dropped."""

    def __init__(self, token: str) -> None:
        self.token = token
        self._lock = threading.Lock()
        self._last_send = 0.0

    def _call(self, method: str, payload: dict, timeout: float) -> dict | None:
        try:
            r = requests.post(API.format(token=self.token, method=method),
                              json=payload, timeout=timeout)
        except Exception:
            return None
        if r.status_code == 429:
            try:
                pause = float(r.json().get("parameters", {}).get("retry_after", 1))
                time.sleep(min(15.0, max(0.5, pause)))
            except Exception:
                time.sleep(1.0)
            return None
        try:
            data = r.json()
        except Exception:
            return None
        return data if data.get("ok") else None

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict]:
        data = self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout,
             "allowed_updates": ["message", "callback_query"]},
            timeout=float(timeout) + 10,
        )
        return data.get("result") or [] if data else []

    def send(self, chat: str, text: str, keyboard: dict | None = None) -> bool:
        payload: dict = {
            "chat_id": chat,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = keyboard
        with self._lock:  # per-chat politeness
            wait = 1.05 - (time.time() - self._last_send)
            if wait > 0:
                time.sleep(wait)
            self._last_send = time.time()
        return self._call("sendMessage", payload, timeout=20) is not None

    def answer_callback(self, cb_id: str) -> None:
        self._call("answerCallbackQuery", {"callback_query_id": cb_id}, timeout=10)


def fire_keyboard() -> dict:
    return {"inline_keyboard": [[
        {"text": "🔥 Fire", "callback_data": "fire"},
        {"text": "Cancel", "callback_data": "cancel"},
    ]]}


# ------------------------------------------------------------------ the bot
class PocketBot:
    """Long-poll loop for one account's bot. deps carries the app-side
    callables (queue/gig/approve/plan/fire/stats) so this module never
    imports the web stack — dependency injection keeps tests honest."""

    def __init__(self, *, user_id: int, token: str, chat_id: str,
                 stop: threading.Event, deps: dict) -> None:
        self.user_id = user_id
        self.chat_id = str(chat_id)
        self.bot = Bot(token)
        self.stop = stop
        self.deps = deps
        self.confirms = ConfirmStore()
        self.errors = 0  # consecutive getUpdates failures — radar reads this
        self._thread: threading.Thread | None = None

    # ---- loop
    def run(self) -> None:
        offset = 0
        while not self.stop.is_set():
            updates = self.bot.get_updates(offset)
            if updates is None or updates == []:
                self.errors += 1 if not updates else 0
                self.stop.wait(2.0)
                continue
            self.errors = 0
            for upd in updates:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                try:
                    self._handle(upd)
                except Exception:  # noqa: S112 — one bad update must never kill the loop
                    continue  # one bad update must never kill the loop

    # ---- dispatch
    def _handle(self, upd: dict) -> None:
        cb = upd.get("callback_query")
        if cb:
            chat = str(((cb.get("message") or {}).get("chat") or {}).get("id") or "")
            if chat == self.chat_id:
                self._on_callback(chat, str(cb.get("data") or ""))
                self.bot.answer_callback(str(cb.get("id") or ""))
            return
        msg = upd.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id") or "")
        if chat != self.chat_id:
            return  # not your board — silence, always
        cmd, args = parse_command(str(msg.get("text") or ""))
        text, kb = self._command(cmd, args, chat)
        if text:
            self.bot.send(chat, text, kb)

    # ---- commands
    def _command(self, cmd: str, args: list[str], chat: str) -> tuple[str, dict | None]:
        if cmd in ("", "start", "help"):
            return self._help(), None
        if cmd == "queue":
            return self._queue(args), None
        if cmd == "gig":
            return self._gig(args), None
        if cmd == "approve":
            return self._approve(args), None
        if cmd == "snipe":
            return self._snipe(args, chat)
        if cmd == "stats":
            return str(self.deps["stats"]()), None
        if cmd == "ping":
            return str(self.deps["ping"]()), None
        if cmd == "digest":
            return str(self.deps["digest"]()), None
        return (
            "unknown command — /help lists the arsenal", None
        )

    def _help(self) -> str:
        return (
            "🐺 <b>pocket sniper</b>\n"
            "/queue [n] — best pending gigs\n"
            "/gig &lt;id&gt; — full card + proposal\n"
            "/approve &lt;id&gt; — move to approved\n"
            "/snipe &lt;id&gt; [amount] — Freelancer live-fire (asks first)\n"
            "/stats — the scoreboard\n"
            "/digest — board summary + the three best gigs\n"
            "/ping — is the radar alive?\n"
            "/help — this card"
        ).replace("&lt;", "<").replace("&gt;", ">")

    def _queue(self, args: list[str]) -> str:
        try:
            n = max(1, min(10, int(args[0]))) if args else 5
        except ValueError:
            n = 5
        lines = self.deps["queue"](n)
        if not lines:
            return "board is clear — no pending gigs above your score bar."
        return "🎯 <b>top gigs</b>\n" + "\n".join(lines)

    def _gig(self, args: list[str]) -> str:
        if not args:
            return "which gig? /gig &lt;id&gt;".replace("&lt;", "<").replace("&gt;", ">")
        try:
            jid = int(args[0])
        except ValueError:
            return "that id isn't a number — /queue shows ids"
        card = self.deps["gig"](jid)
        return card or f"no gig #{jid} on your board"

    def _approve(self, args: list[str]) -> str:
        if not args:
            return "which gig? /approve &lt;id&gt;".replace("&lt;", "<").replace("&gt;", ">")
        try:
            jid = int(args[0])
        except ValueError:
            return "that id isn't a number"
        return str(self.deps["approve"](jid))

    def _snipe(self, args: list[str], chat: str) -> tuple[str, dict | None]:
        if not args:
            return "usage: /snipe &lt;id&gt; [amount]".replace("&lt;", "<").replace("&gt;", ">"), None
        try:
            jid = int(args[0])
        except ValueError:
            return "that id isn't a number", None
        amount: float | None = None
        if len(args) > 1:
            try:
                amount = float(args[1].replace("$", "").replace(",", ""))
            except ValueError:
                return "amount should be a number, like /snipe 42 500", None
        plan = self.deps["plan"](jid, amount)
        if not plan.get("ok"):
            return f"can't snipe #{jid}: {plan.get('detail', 'unknown')}", None
        if plan.get("mode") != "api":
            return (
                f"#{jid} — this source has no bidding API, the kit is the weapon:\n"
                f"{plan.get('detail', '')}"
            ), None
        self.confirms.put(chat, jid, plan.get("amount"))
        return (
            f"🔫 <b>armed</b> — gig #{jid}\n"
            f"bid ${plan.get('amount'):g} · {plan.get('detail', '')}\n"
            "fire for real?"
        ), fire_keyboard()

    # ---- callbacks
    def _on_callback(self, chat: str, data: str) -> None:
        if data == "cancel":
            self.confirms.pop(chat)
            self.bot.send(chat, "standing down — nothing fired")
            return
        if data == "fire":
            c = self.confirms.pop(chat)
            if not c:
                self.bot.send(chat, "that confirm expired — /snipe again")
                return
            result = self.deps["fire"](c.job_id, c.amount)
            if result.get("ok"):
                self.bot.send(
                    chat,
                    f"🔥 <b>fired</b> — gig #{c.job_id}\n"
                    f"bid ${result.get('amount'):g} · bid id {result.get('bid_id')}\n"
                    "the board now shows it as sniped.",
                )
            else:
                self.bot.send(chat, f"misfire: {result.get('detail', 'unknown')}")


def spawn(*, user_id: int, token: str, chat_id: str,
          stop: threading.Event, deps: dict) -> tuple[PocketBot, threading.Thread]:
    """Build the bot and start its thread (daemon — dies with the process)."""
    bot = PocketBot(user_id=user_id, token=token, chat_id=chat_id,
                    stop=stop, deps=deps)
    thread = threading.Thread(
        target=bot.run, name=f"pocket-bot-u{user_id}", daemon=True
    )
    thread.start()
    return bot, thread
