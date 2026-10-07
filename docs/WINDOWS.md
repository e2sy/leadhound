# 🪟 leadhound on Windows — from download to first real gig

Every command below was verified against the full flow (init → demo → board →
97 real gigs fetched from RemoteOK in seconds). Pick **Path A** if you don't
want Python at all, or **Path B** if you live in a terminal.

---

## Path A — the .exe (no Python needed)

1. Grab `leadhound-windows-x64.exe` from the
   [latest release](https://github.com/e2sy/leadhound/releases/latest).
2. Double-click it. The binary self-sets-up and **opens your browser** at the
   dashboard automatically.
3. Windows SmartScreen will flag it (unsigned binary — normal for open source):
   click **More info → Run anyway**.
4. **Create your account** (email + password, stored in local SQLite only) →
   open **🔗 accounts** → switch on **RemoteOK** or **Freelancer.com** (zero
   setup) → hit **⚡ fetch gigs**.
5. Real gigs land on the board, scored and drafted. The radar re-polls every
   few minutes while the app runs.

That's the whole app. Everything below is the same flow with more control.

## Path B — pip (daily-driver setup)

Open **PowerShell** (Win key → type `powershell`):

```powershell
# 1. Python 3.11+ from python.org — on the first installer screen tick
#    "Add python.exe to PATH". Then check:
py --version          # or: python --version

# 2. Install
pip install leadhound    # or: pipx install leadhound

# 3. Bootstrap — creates C:\Users\<you>\.leadhound\ with config + profile
leadhound init

# 4. Launch the dashboard
leadhound web
```

Your browser opens at `http://127.0.0.1:7800` → create your account → 🔗
accounts → enable sources → ⚡ fetch gigs.

> Already have Python but `pip` won't run? Use `py -m pip install leadhound`
> and `py -m leadhound.cli` as a fallback for every command below.

## 🧪 Test it offline first (30 seconds, zero network)

```powershell
leadhound init      # skip if you already ran it
leadhound demo      # injects 4 sample gigs, including 2 red-flag traps
leadhound queue     # review: traps score 18 and 0 — the scope works
leadhound digest    # your morning briefing
leadhound doctor    # pre-flight: profile, config, db, feed reachability
leadhound export --format csv | more   # your pipeline as spreadsheet rows
```

Expected: the React Native demo gig scores **90**, the "NFT for exposure"
trap scores **0**. If you approve one and mark it won, the scoreboard and
win-memory learn from it:

```powershell
leadhound mark 1 won     # id 1 = the first queue row
```

## 🌐 Test it live (2 minutes)

1. `leadhound web` → log in.
2. **🔗 accounts** tab → toggle **RemoteOK** on → **⚡ save & test** (the probe
   should print a green state).
3. **⚡ fetch gigs** — a fresh RemoteOK poll brings in ~100 real gigs, every
   one scored against `profile.toml` and drafted.
4. Open a high-scoring card → **✎ draft** → **🎯 snipe** for the snipe kit
   (copies the proposal + opens the gig page in your browser).
5. Leave the dashboard open — the radar keeps re-polling each source on its
   own cadence, and the 🔔 bell pings when new gigs land.

## 📱 Pocket sniper on your phone (optional, 3 minutes)

1. Telegram → [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Message your bot once (anything), then open in your browser:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id`.
3. Dashboard → **🔗 accounts → 📱 telegram pocket sniper** → paste both →
   **save** → **📨 send test message** → **🎧 arm listener** for the two-way bot
   (`/queue`, `/gig <id>`, `/approve <id>`, `/snipe <id>`, `/stats`).

## 📂 Where everything lives on Windows

| Thing | Location |
|---|---|
| Config + sniper profile | `C:\Users\<you>\.leadhound\config.toml` · `profile.toml` |
| Database (all gigs, drafts, accounts) | `C:\Users\<you>\.leadhound\data\leadhound.db` |
| Edit a config | `notepad $env:USERPROFILE\.leadhound\profile.toml` |
| The exe's data dir | same `.leadhound` folder in your user profile |

## 🔧 Windows-specific troubleshooting

| Symptom | Fix |
|---|---|
| `'leadhound' is not recognized` | Scripts dir not on PATH — run `py -m pip install leadhound` again, or use `py -m leadhound.cli <cmd>` |
| SmartScreen blocks the exe | More info → **Run anyway** (unsigned open-source binary) |
| Port 7800 already in use | `leadhound web --port 7810` |
| Dashboard unreachable from your phone | It binds `127.0.0.1` by design — run `leadhound web --host 0.0.0.0` and accept the Windows Firewall prompt once |
| `pip` refuses / no matching version | You're on Python < 3.11 — install the latest from python.org with *Add to PATH* ticked |
| Weird `PermissionError` on the db | You ran two leadhound instances at once — close the extra console/exe window |
| Antivirus deletes the exe | Restore it and add an exclusion; the Binaries workflow builds it deterministically from the release tag |

## ✅ Honest limits (same on every OS)

- **Freelancer.com gig cards** are the one **live-fire** surface (real bid via
  their official API, only when you click 🎯 snipe).
- Everything else is the **snipe kit**: leadhound drafts + copies + opens the
  gig; **you** paste and send in your own logged-in browser. Upwork's API and
  Fiverr simply don't allow third-party auto-apply — no tool can do it honestly.
- Your data never leaves your machine except to the feeds/APIs you enable.
