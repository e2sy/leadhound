"""Embedded single-page app served by leadhound.api.

Vanilla HTML/CSS/JS — no CDN, no build step, works fully offline.
v4: the sniper — 🎯 snipe button on every gig card with a fire dialog
(Freelancer.com live-fire real bids via the linked account, honest snipe
kit everywhere else), sniped column with audit badges, snipe stats chips,
and the Freelancer.com account-link card with OAuth wizard.
v5: dark/light theme toggle, PWA install support, saved filter presets
and the ✨ improve-draft button in the proposal editor.
All user-controlled strings are HTML-escaped with esc() before insertion.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0d1117">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<title>🐺 leadhound — snipe console</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2129; --line:#21262d;
    --txt:#e6edf3; --dim:#8b949e; --blue:#58a6ff; --green:#3fb950;
    --red:#f85149; --amber:#e3b341; --cyan:#39c5cf;
    --headbg:rgba(13,17,23,.92);
  }
  html[data-theme="light"]{
    --bg:#f6f8fa; --panel:#ffffff; --panel2:#eef1f6; --line:#d9dee7;
    --txt:#1f2630; --dim:#5c6675; --blue:#0b62c4; --green:#148a3a;
    --red:#c9352e; --amber:#9a6a00; --cyan:#0c7c86;
    --headbg:rgba(246,248,250,.92);
  }
  *{box-sizing:border-box; margin:0; padding:0}
  body{background:var(--bg); color:var(--txt);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  a{color:var(--blue); text-decoration:none}
  a:hover{text-decoration:underline}
  button{background:var(--panel2); border:1px solid var(--line); color:var(--txt);
         border-radius:8px; padding:5px 10px; cursor:pointer; font-size:12.5px}
  button:hover{border-color:var(--blue); color:var(--blue)}
  button.on{border-color:var(--green); color:var(--green)}
  button.primary{background:#238636; border-color:#2ea043; color:#fff; font-weight:700}
  button.primary:hover{background:#2ea043; color:#fff}
  button.danger:hover{border-color:var(--red); color:var(--red)}
  input,select,textarea{background:var(--panel2); border:1px solid var(--line); color:var(--txt);
         border-radius:8px; padding:6px 10px; outline:none}
  input:focus,textarea:focus,select:focus{border-color:var(--blue)}

  header{position:sticky; top:0; z-index:10; background:var(--headbg);
         backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
         padding:10px 16px; display:flex; flex-wrap:wrap; gap:10px; align-items:center;}
  .brand{font-weight:800; font-size:17px; letter-spacing:.5px; white-space:nowrap}
  .brand .wolf{filter:drop-shadow(0 0 6px rgba(88,166,255,.8))}
  .chips{display:flex; flex-wrap:wrap; gap:6px; flex:1}
  .chip{display:inline-block; padding:1px 8px; border-radius:999px; font-size:11.5px;
        border:1px solid var(--line); background:var(--panel2); color:var(--dim); white-space:nowrap}
  .chip.green{color:var(--green); border-color:rgba(63,185,80,.35)}
  .chip.red{color:var(--red); border-color:rgba(248,81,73,.35)}
  .chip.amber{color:var(--amber); border-color:rgba(227,179,65,.35)}
  .chip.blue{color:var(--blue); border-color:rgba(88,166,255,.35)}
  .chip.cyan{color:var(--cyan); border-color:rgba(57,197,207,.35)}
  .spacer{flex:1}
  input#q{width:200px}
  #userbox{display:flex; gap:6px; align-items:center}
  #userbox .who{font-size:12px; color:var(--dim); max-width:160px; overflow:hidden;
                text-overflow:ellipsis; white-space:nowrap}

  .hintbar{padding:6px 16px; font-size:12px; color:var(--dim); border-bottom:1px solid var(--line)}
  .hintbar b{color:var(--amber)}

  #app[hidden]{display:none}
  #board{display:grid; grid-template-columns:repeat(4,1fr); gap:12px; padding:14px 16px 40px}
  .col{background:var(--panel); border:1px solid var(--line); border-radius:12px;
       min-height:200px; display:flex; flex-direction:column}
  .col h2{font-size:12.5px; text-transform:uppercase; letter-spacing:1px; color:var(--dim);
          padding:10px 12px; border-bottom:1px solid var(--line); display:flex; gap:8px; align-items:center}
  .col h2 .n{background:var(--panel2); border:1px solid var(--line); border-radius:999px;
             padding:0 7px; font-size:11px; color:var(--txt)}
  .cards{padding:10px; display:flex; flex-direction:column; gap:10px; overflow-y:auto; max-height:calc(100vh - 170px)}

  .card{background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:10px}
  .card.hot{border-color:rgba(63,185,80,.4)}
  .card.cold{opacity:.62}
  .row{display:flex; gap:8px; align-items:flex-start}
  .ring{flex:0 0 auto; width:44px; height:44px; border-radius:50%; display:flex;
        align-items:center; justify-content:center; font-weight:800; font-size:14px;
        border:3px solid var(--dim); background:var(--bg)}
  .ttl{font-weight:600; line-height:1.3}
  .ttl a{color:var(--txt)}
  .ttl a:hover{color:var(--blue)}
  .meta{margin-top:4px; display:flex; flex-wrap:wrap; gap:5px}
  .skills{margin-top:7px; display:flex; flex-wrap:wrap; gap:5px}
  .intel{margin-top:7px; font-size:12px; color:var(--cyan)}
  .prev{margin-top:7px; font-size:12px; color:var(--dim);
        display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden}
  .acts{margin-top:9px; display:flex; flex-wrap:wrap; gap:6px; align-items:center}
  .acts select{padding:4px 6px; font-size:12px}
  .obadge{font-size:11.5px; padding:1px 8px; border-radius:999px; border:1px solid}
  .o-won{color:var(--green); border-color:var(--green)}
  .o-replied{color:var(--amber); border-color:var(--amber)}
  .o-interview{color:var(--cyan); border-color:var(--cyan)}
  .o-lost{color:var(--red); border-color:var(--red)}

  details.draft{margin-top:8px; border-top:1px dashed var(--line); padding-top:8px}
  details.draft summary{cursor:pointer; font-size:12.5px; color:var(--blue); user-select:none}
  textarea{width:100%; min-height:130px; margin-top:7px;
           font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; resize:vertical}
  .draftbtns{display:flex; gap:6px; margin-top:6px}
  .empty{color:var(--dim); font-size:12.5px; text-align:center; padding:22px 8px}

  /* ---------------- hero (empty board) ---------------- */
  #hero{max-width:560px; margin:8vh auto; text-align:center; padding:28px 22px;
        background:var(--panel); border:1px solid var(--line); border-radius:16px}
  #hero .wolf{font-size:44px; filter:drop-shadow(0 0 12px rgba(88,166,255,.7))}
  #hero h1{font-size:20px; margin:10px 0 6px}
  #hero p{color:var(--dim); font-size:13px; margin-bottom:18px}
  #hero ol.check{list-style:none; text-align:left; display:flex; flex-direction:column; gap:10px;
                 margin:14px auto 4px; max-width:440px}
  #hero ol.check li{display:flex; align-items:center; gap:10px; background:var(--panel2);
                    border:1px solid var(--line); border-radius:10px; padding:10px 12px}
  #hero ol.check .tick{width:24px; height:24px; border-radius:50%; border:1px solid var(--line);
                       display:flex; align-items:center; justify-content:center;
                       font-size:12px; color:var(--dim); flex:none}
  #hero ol.check .lbl{font-size:13px}
  #hero ol.check .lbl small{display:block; color:var(--dim); font-size:11px}
  #hero ol.check li.done{border-color:rgba(63,185,80,.45)}
  #hero ol.check li.done .tick{border-color:var(--green); color:var(--green)}
  #hero ol.check li.done .tick b{display:none}
  #hero ol.check li.done .tick::after{content:"✓"}
  #hero ol.check li.done .lbl{color:var(--dim)}
  #hero ol.check .grow{flex:1}
  #hero .fine{margin-top:16px; font-size:11.5px; color:var(--dim)}
  #hero .explore{margin-top:8px; font-size:11.5px; color:var(--dim)}

  /* ---------------- auth gate ---------------- */
  #authview{position:fixed; inset:0; z-index:40; display:flex; align-items:center;
            justify-content:center; background:
            radial-gradient(1200px 500px at 50% -10%, rgba(88,166,255,.12), transparent), var(--bg)}
  #authview[hidden]{display:none}
  .authcard{width:340px; background:var(--panel); border:1px solid var(--line);
            border-radius:16px; padding:26px 24px; box-shadow:0 20px 60px rgba(0,0,0,.55)}
  .authcard .logo{text-align:center; font-size:34px; filter:drop-shadow(0 0 10px rgba(88,166,255,.7))}
  .authcard h1{text-align:center; font-size:19px; margin:8px 0 2px}
  .authcard .sub{text-align:center; color:var(--dim); font-size:12px; margin-bottom:16px}
  .authtabs{display:flex; gap:6px; margin-bottom:14px}
  .authtabs button{flex:1}
  .authtabs button.sel{border-color:var(--blue); color:var(--blue); font-weight:700}
  .authcard label{display:block; font-size:11.5px; color:var(--dim); margin:8px 0 3px}
  .authcard input{width:100%}
  .authcard .wide{width:100%; margin-top:14px; padding:8px}
  #autherr{color:var(--red); font-size:12px; margin-top:10px; min-height:16px}
  .authfine{margin-top:12px; font-size:11px; color:var(--dim); text-align:center}

  /* ---------------- view tabs + accounts hub ---------------- */
  .vtabs{display:flex; gap:4px}
  .vtabs button{border-radius:8px}
  .vtabs button.sel{border-color:var(--blue); color:var(--blue)}
  #accountsView{max-width:1240px; margin:0 auto; padding:14px 18px 30px}
  .ahead{display:flex; align-items:flex-end; gap:14px; margin:6px 2px 14px}
  .ahead h2{font-size:17px}
  .asub{font-size:12px; color:var(--dim); margin-top:3px}
  .asub b{color:var(--txt)}
  .agrid{display:grid; grid-template-columns:repeat(auto-fill, minmax(350px, 1fr));
         gap:12px}
  .conn .badge{margin-left:auto; font-size:10.5px; padding:2px 8px; border-radius:999px;
               border:1px solid var(--line); white-space:nowrap}
  .badge.ok{color:var(--green); border-color:rgba(63,185,80,.45); background:rgba(63,185,80,.08)}
  .badge.err{color:var(--red); border-color:rgba(248,81,73,.45); background:rgba(248,81,73,.08)}
  .badge.warn{color:var(--amber); border-color:rgba(227,179,65,.45); background:rgba(227,179,65,.07)}
  .badge.off{color:var(--dim)}
  .wiz{margin-top:9px; font-size:12px; border:1px dashed var(--line); border-radius:9px;
       padding:7px 10px}
  .wiz summary{cursor:pointer; color:var(--blue); font-size:11.5px}
  .wiz ol{margin:8px 0 4px 18px; display:flex; flex-direction:column; gap:5px}
  .wiz code{background:var(--bg); border:1px solid var(--line); border-radius:6px;
            padding:1px 6px; font-size:11px; word-break:break-all}
  .wiz .warn{margin-top:7px; color:var(--amber); font-size:11px}
  .afoot{margin-top:16px; font-size:11px; color:var(--dim); text-align:center}
  .conn{background:var(--panel2); border:1px solid var(--line); border-radius:12px; padding:12px; margin-bottom:10px}
  .conn.on{border-color:rgba(63,185,80,.4)}
  .connhead{display:flex; align-items:center; gap:8px}
  .connhead b{font-size:14px}
  .kchip{font-size:10.5px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); color:var(--dim)}
  .kchip.public{color:var(--green); border-color:rgba(63,185,80,.4)}
  .kchip.keys{color:var(--amber); border-color:rgba(227,179,65,.4)}
  .kchip.cookie{color:var(--amber); border-color:rgba(227,179,65,.4)}
  .kchip.feed{color:var(--cyan); border-color:rgba(57,197,207,.4)}
  .switch{margin-left:auto; display:flex; align-items:center; gap:6px; font-size:11px; color:var(--dim)}
  .conn .blurb{font-size:12px; color:var(--dim); margin-top:5px}
  .conn .fields{margin-top:9px; display:flex; flex-direction:column; gap:7px}
  .conn .fields label{display:block; font-size:11px; color:var(--dim); margin-bottom:2px}
  .conn .fields input{width:100%; font-size:12px}
  .conn .hint{font-size:10.5px; color:var(--dim); margin-top:2px}
  .connacts{display:flex; gap:6px; margin-top:9px; flex-wrap:wrap; align-items:center}
  .cstat{margin-top:8px; font-size:11.5px; color:var(--dim)}
  .cstat.err{color:var(--red)}

  #toasts{position:fixed; right:14px; bottom:14px; display:flex; flex-direction:column; gap:8px; z-index:50}
  .toast{background:var(--panel); border:1px solid var(--green); color:var(--txt);
         border-radius:10px; padding:8px 14px; font-size:13px; box-shadow:0 6px 24px rgba(0,0,0,.5)}
  .toast.err{border-color:var(--red)}

  /* ---------------- snipe dialog ---------------- */
  button.snipebtn{border-color:rgba(227,179,65,.55); color:var(--amber); font-weight:600}
  button.snipebtn:hover{background:rgba(227,179,65,.12); color:var(--amber)}
  #snipeModal{position:fixed; inset:0; z-index:45; background:rgba(0,0,0,.62);
              display:flex; align-items:center; justify-content:center}
  #snipeModal[hidden]{display:none}
  .sbox{width:540px; max-width:94vw; max-height:88vh; overflow-y:auto; background:var(--panel);
        border:1px solid var(--line); border-radius:14px; padding:16px 18px;
        box-shadow:0 20px 60px rgba(0,0,0,.6)}
  .sbox h3{font-size:15px; margin-bottom:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
  .ssub{font-size:11.5px; color:var(--dim); margin-bottom:8px}
  .smode{font-size:12px; margin:8px 0; color:var(--dim); border:1px dashed var(--line);
         border-radius:9px; padding:8px 10px}
  .smode b{color:var(--amber)}
  .smode.fire{border-color:rgba(248,81,73,.4)}
  .smode.fire b{color:var(--red)}
  .sbox label{display:block; font-size:11px; color:var(--dim); margin:8px 0 3px}
  .sbox input{width:140px}
  .srow{display:flex; gap:14px; flex-wrap:wrap}
  .sbtns{display:flex; gap:8px; margin-top:14px}
  .sbtns[hidden]{display:none}
  #sApiFields[hidden]{display:none}
  .sbtns .primary{padding:6px 14px}
  button.fire{background:#b62324; border-color:#da3633; color:#fff; font-weight:700}
  button.fire:hover{background:#da3633; color:#fff}
  .snote{margin-top:9px; font-size:11px; color:var(--dim)}
  .schip{font-size:11px; padding:1px 8px; border-radius:999px; border:1px solid var(--amber); color:var(--amber)}
  .card.selk{border-color:var(--blue); box-shadow:0 0 0 1px var(--blue), 0 4px 18px rgba(88,166,255,.18)}
  #keyHelp{position:fixed; inset:0; z-index:60; background:rgba(0,0,0,.62);
           display:flex; align-items:center; justify-content:center}
  #keyHelp[hidden]{display:none}
  .kbox{width:430px; max-width:92vw; background:var(--panel); border:1px solid var(--line);
        border-radius:14px; padding:18px 20px; box-shadow:0 20px 60px rgba(0,0,0,.6)}
  .kbox h3{font-size:15px; margin-bottom:10px}
  .krow{display:flex; gap:10px; padding:4px 0; font-size:12.5px; color:var(--dim); align-items:baseline}
  .krow b{color:var(--txt); width:150px; flex:none}
  kbd{background:var(--bg); border:1px solid var(--line); border-bottom-width:2px;
      border-radius:6px; padding:0 6px; font:11.5px ui-monospace,monospace; color:var(--txt)}
  .dtabs{display:flex; gap:4px; margin-top:7px}
  .dtabs button{font-size:11px; padding:3px 9px; border-radius:7px}
  .dtabs button.sel{border-color:var(--blue); color:var(--blue); font-weight:700}
  .svar label{display:block; font-size:11px; color:var(--dim); margin:8px 0 3px}
  .svchips{display:flex; gap:6px; flex-wrap:wrap}
  .svchips button.sel{border-color:var(--amber); color:var(--amber); font-weight:700}

  /* ---------------- stats tab ---------------- */
  #statsView{max-width:1100px; margin:0 auto; padding:14px 18px 30px}
  .scards{display:grid; grid-template-columns:repeat(auto-fill, minmax(170px,1fr)); gap:10px; margin-bottom:16px}
  .scard{background:var(--panel2); border:1px solid var(--line); border-radius:12px; padding:12px 14px}
  .scard .k{font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.6px}
  .scard .v{font-size:22px; font-weight:800; margin-top:2px}
  .scard .s{font-size:11px; color:var(--dim); margin-top:2px}
  .scard.hot{border-color:rgba(63,185,80,.4)}
  .spanel{background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:14px}
  .spanel h3{font-size:12.5px; margin-bottom:8px; color:var(--dim); text-transform:uppercase; letter-spacing:.8px}
  .brow{display:flex; align-items:center; gap:8px; padding:5px 0; font-size:12.5px}
  .brow .bl{width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
  .brow .btrack{flex:1; height:10px; background:var(--bg); border:1px solid var(--line); border-radius:999px; overflow:hidden}
  .brow .bfill{display:block; height:100%; background:var(--blue); border-radius:999px}
  .brow .bfill.g{background:var(--green)}
  .brow .bn{width:190px; text-align:right; color:var(--dim); font-size:11.5px; white-space:nowrap}
  .sline{font-size:12.5px; color:var(--dim); padding:4px 0}
  .sline b{color:var(--txt)}

  @media (max-width:920px){
    #board{grid-template-columns:repeat(4, minmax(270px, 1fr)); overflow-x:auto}
    .cards{max-height:none}
    input#q{width:140px}
  }
</style>
</head>
<body>

<div id="authview" hidden>
  <div class="authcard">
    <div class="logo">🐺</div>
    <h1>LEADHOUND</h1>
    <div class="sub">your gig sniper — local-first, your data stays here</div>
    <div class="authtabs">
      <button id="tabLogin" class="sel" onclick="authTab('login')">log in</button>
      <button id="tabReg" onclick="authTab('register')">create account</button>
    </div>
    <label for="aemail">email</label>
    <input id="aemail" type="email" autocomplete="username" placeholder="you@studio.dev">
    <label for="apass">password</label>
    <input id="apass" type="password" autocomplete="current-password" placeholder="min 8 characters"
           onkeydown="if(event.key==='Enter')submitAuth()">
    <button id="authbtn" class="primary wide" onclick="submitAuth()">log in</button>
    <div id="autherr"></div>
    <div class="authfine">accounts live in your local SQLite — no cloud, no tracking.</div>
  </div>
</div>

<div id="app" hidden>
  <header>
    <div class="brand"><span class="wolf">🐺</span> LEADHOUND</div>
    <div class="chips" id="chips"></div>
    <div class="spacer"></div>
    <input id="q" placeholder="search gigs…" oninput="S.q=this.value; render()">
    <nav class="vtabs">
      <button id="tabBoard" class="sel" onclick="showView('board')">▦ board</button>
      <button id="tabStats" onclick="showView('stats')">📊 stats</button>
      <button id="tabAccts" onclick="showView('accounts')">🔗 accounts <span id="connN" class="chip blue">0</span></button>
    </nav>
    <button id="autoBtn" class="on" onclick="toggleAuto()" title="auto-refresh every 8s">⟳ auto</button>
    <button onclick="toggleKeyHelp()" title="keyboard shortcuts (?)">⌨</button>
    <button id="bellBtn" onclick="toggleBell()" title="browser alerts when new gigs land (while the dashboard is open)">🔔</button>
    <button id="themeBtn" onclick="toggleTheme()" title="light / dark theme">🌙</button>
    <button class="primary" onclick="fetchNow()" title="fetch every enabled source now">⚡ fetch gigs</button>
    <div id="userbox">
      <span class="who" id="whoami"></span>
      <button onclick="logout()" title="log out">⎋</button>
    </div>
  </header>
  <div class="hintbar" id="hintbar">loading…</div>
  <div id="hero" hidden>
    <div class="wolf">🐺</div>
    <h1>Connect your first job source</h1>
    <p>leadhound hunts <b>real</b> gigs from the sites you already use — no sample data needed. Three steps:</p>
    <ol class="check">
      <li id="st1"><span class="tick"><b>1</b></span>
        <span class="lbl">connect a job site<small>Freelancer.com needs zero setup · Upwork official OAuth · Fiverr beta cookie</small></span>
        <span class="grow"></span>
        <button onclick="showView('accounts')">⚙ accounts</button></li>
      <li id="st2"><span class="tick"><b>2</b></span>
        <span class="lbl">fetch real gigs<small>scored against your profile the moment they appear</small></span>
        <span class="grow"></span>
        <button class="primary" onclick="fetchNow()">⚡ fetch now</button></li>
      <li id="st3"><span class="tick"><b>3</b></span>
        <span class="lbl">snipe with your account<small>Freelancer.com live-fire bids · one-click kit everywhere else</small></span>
        <span class="grow"></span>
        <button onclick="showView('accounts')">🔗 link account</button></li>
    </ol>
    <div class="fine">the radar re-polls your sources every few minutes — sniping works while you sleep.</div>
    <div class="explore">just exploring? <a href="#" onclick="loadDemo(); return false;">load sample gigs</a></div>
  </div>
  <div id="board"></div>
</div>

<div id="accountsView" hidden>
  <div class="ahead">
    <div>
      <h2>🔗 connected accounts</h2>
      <div class="asub" id="acctSummary">loading…</div>
    </div>
    <div class="spacer"></div>
    <button class="primary" onclick="fetchNow()">⚡ fetch all sources</button>
  </div>
  <div id="acctGrid" class="agrid">loading…</div>
  <div id="tgCard" class="conn">
    <div class="connhead">
      <b>📱 telegram pocket sniper</b>
      <span class="badge off" id="tgBadge">off</span>
    </div>
    <div class="blurb">gigs that clear your score bar land in your chat seconds after the
      radar spots them — read the pitch on your phone, then hit the dashboard (or the bot,
      coming next) to fire.</div>
    <div class="fields">
      <div><label for="tgToken">bot token</label>
        <input id="tgToken" type="password" placeholder="123456:ABC-DEF…" autocomplete="off">
        <div class="hint">from @BotFather — stored locally, never shown again</div></div>
      <div><label for="tgChat">chat id</label>
        <input id="tgChat" type="text" placeholder="e.g. 424242" autocomplete="off">
        <div class="hint">message @userinfobot on Telegram to see yours</div></div>
      <div><label for="tgMin">push gigs scoring ≥</label>
        <input id="tgMin" type="number" min="0" max="100" step="5" value="70"></div>
    </div>
    <div class="connacts">
      <button class="primary" onclick="saveTelegram()">💾 save</button>
      <button onclick="testTelegram()">📨 send test message</button>
      <button id="tgTgl" onclick="toggleTelegram()">switch on</button>
      <button id="tgListen" onclick="toggleListen()">🎧 arm listener</button>
    </div>
    <div class="cstat" id="tgStat">no bot token yet</div>
  </div>
  <div class="afoot">credentials live in your local SQLite (secrets masked in the UI) — nothing is sent
    anywhere except the sites you enable. the radar re-polls enabled sources every few minutes while the server runs.
    · <a href="#" onclick="loadDemo(); return false;">just exploring? load sample gigs</a></div>
</div>

<div id="toasts"></div>

<div id="keyHelp" hidden>
  <div class="kbox">
    <h3>⌨ cockpit keys</h3>
    <div class="krow"><b><kbd>j</kbd> / <kbd>k</kbd></b> next / previous gig (wrap around)</div>
    <div class="krow"><b><kbd>a</kbd></b> approve the selected gig</div>
    <div class="krow"><b><kbd>x</kbd> / <kbd>r</kbd></b> reject the selected gig</div>
    <div class="krow"><b><kbd>s</kbd></b> snipe — open the fire dialog</div>
    <div class="krow"><b><kbd>o</kbd></b> open the gig page</div>
    <div class="krow"><b><kbd>c</kbd></b> copy the proposal</div>
    <div class="krow"><b><kbd>d</kbd></b> edit the draft (A/B tabs too)</div>
    <div class="krow"><b><kbd>?</kbd></b> this help · <kbd>Esc</kbd> close / clear</div>
    <div class="krow"><b>note</b> keys pause while you type in any field — the board is mouseless, not hostile.</div>
  </div>
</div>

<div id="statsView" hidden>
  <div class="ahead">
    <div>
      <h2>📊 the scoreboard</h2>
      <div class="asub">what happened <b>after</b> the shots were fired — replies, wins, money.</div>
    </div>
  </div>
  <div id="statsBody">loading…</div>
</div>

<div id="snipeModal" hidden>
  <div class="sbox">
    <h3 id="sTitle"></h3>
    <div class="ssub" id="sSub"></div>
    <div class="smode" id="sMode"></div>
    <div class="svar" id="sVar" hidden></div>
    <label for="sText">proposal</label>
    <textarea id="sText" style="min-height:150px"></textarea>
    <div id="sApiFields" hidden>
      <div class="srow">
        <div><label for="sAmount">bid amount (USD)</label>
          <input id="sAmount" type="number" min="1" step="1"></div>
        <div><label for="sPeriod">delivery period (days)</label>
          <input id="sPeriod" type="number" min="1" step="1" value="7"></div>
      </div>
    </div>
    <div class="sbtns" id="sFireRow">
      <button id="sFire" onclick="onSnipeFire()"></button>
      <button onclick="closeSnipe()">cancel</button>
    </div>
    <div class="sbtns" id="sConfirmRow" hidden>
      <button class="primary" onclick="onSnipeConfirm()">✓ sent it — mark sniped</button>
      <button class="danger" onclick="closeSnipe()">cancel</button>
    </div>
    <div class="snote" id="sNote"></div>
  </div>
</div>

<script>
"use strict";
const COLS = [
  {key:"pending",  label:"🎯 Pending"},
  {key:"approved", label:"✅ Approved"},
  {key:"sent",     label:"🔥 Sniped"},
  {key:"rejected", label:"🗑 Rejected"},
];
const S = {jobs:[], cal:{}, q:"", auto:true, editing:null, draftVal:"", timer:null,
           demo:false, user:null, connectors:[], authMode:"login", view:"board",
           snipePlan:null, snipe:{}, linked:{}, stats:null, draftSide:"A", snipeVariant:"A",
           sel:null, selOrder:[], selScroll:false, knownIds:null};

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => Number(n).toLocaleString("en-US");
const ringColor = s => s >= 80 ? "var(--green)" : s >= 60 ? "var(--amber)" : "var(--red)";
const money = j => {
  if (j.hourly) return "$" + fmt(j.hourly) + "/hr";
  if (j.budget_max) return "$" + fmt(j.budget_max);
  if (j.budget_min) return "$" + fmt(j.budget_min) + "+";
  return null;
};

function toast(msg, err){
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 3400);
}

/* ------------------------------------------------- boot + auth */
async function boot(){
  try{
    const r = await fetch("/api/auth/me");
    if(r.ok){
      const d = await r.json();
      S.user = d.user;
      $("#authview").hidden = true;
      $("#app").hidden = false;
      $("#whoami").textContent = d.user.email;
      await load();
      loadConnectors();
      return;
    }
  }catch(e){ /* server down */ }
  S.user = null;
  $("#app").hidden = true;
  $("#authview").hidden = false;
  $("#aemail").focus();
}
window.authTab = mode => {
  S.authMode = mode;
  $("#tabLogin").classList.toggle("sel", mode === "login");
  $("#tabReg").classList.toggle("sel", mode === "register");
  $("#authbtn").textContent = mode === "login" ? "log in" : "create account";
  $("#autherr").textContent = "";
};
window.submitAuth = async () => {
  const body = {email: $("#aemail").value.trim(), password: $("#apass").value};
  try{
    const r = await fetch("/api/auth/" + S.authMode, {
      method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    const d = await r.json().catch(() => ({}));
    if(!r.ok){ $("#autherr").textContent = d.detail || ("http " + r.status); return; }
    S.user = d.user;
    $("#authview").hidden = true;
    $("#app").hidden = false;
    $("#whoami").textContent = d.user.email;
    await load(); loadConnectors();
  }catch(e){ $("#autherr").textContent = "could not reach the server"; }
};
window.logout = async () => {
  await fetch("/api/auth/logout", {method:"POST"}).catch(()=>{});
  clearInterval(S.timer);
  $("#app").hidden = true;
  $("#authview").hidden = false;
  S.user = null;
};

/* ------------------------------------------------- data */
async function load(){
  try{
    const r = await fetch("/api/state");
    if(r.status === 401){ boot(); return; }
    if(!r.ok) throw new Error("http " + r.status);
    const d = await r.json();
    S.jobs = d.jobs; S.cal = d.calibration || {}; S.demo = !!d.demo;
    S.snipe = d.snipe || {}; S.linked = d.linked || {};
    bellCheck(d.jobs);
    render();
  }catch(e){
    $("#hintbar").textContent = "⚠ could not reach the leadhound server — is it still running?";
  }
}

async function post(url, data, okMsg){
  try{
    const r = await fetch(url, {method:"POST",
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(data ?? {})});
    if(r.status === 401){ boot(); return null; }
    const d = await r.json().catch(() => ({}));
    if(!r.ok || d.ok === false){ toast(d.detail || d.error || ("http " + r.status), true); return null; }
    if(okMsg) toast(okMsg);
    return d;
  }catch(e){ toast("request failed", true); return null; }
}

window.act = (id, status) => post("/api/status", {id, status}, "moved to " + status + " ✓").then(load);
window.setOutcome = (id, o) => {
  if(!o) return;
  post("/api/outcome", {id, outcome:o}, "outcome: " + o + (o === "won" ? " 🎉" : "")).then(load);
};
window.toggleDraft = id => {
  if(S.editing === id){ S.editing = null; S.draftVal = ""; }
  else{
    if(S.editing !== null) saveDraft(S.editing, true);
    const j = S.jobs.find(x => x.id === id);
    S.editing = id; S.draftSide = "A"; S.draftVal = j ? (j.draft || "") : "";
  }
  render();
};
window.draftSide = (id, side) => {
  if(S.editing !== id) return;
  S.draftSide = side;
  const j = S.jobs.find(x => x.id === id);
  if(side === "A") S.draftVal = j ? (j.draft || "") : "";
  else{
    const v = (j && (j.variants || []).find(x => x.label === side));
    S.draftVal = v ? v.text : "";
  }
  render();
};
window.seedVariant = async id => {
  const j = S.jobs.find(x => x.id === id);
  if(!j) return;
  const base = (S.editing === id && S.draftSide === "A") ? S.draftVal : (j.draft || "");
  const d = await post(`/api/jobs/${id}/variants`,
    {label:"B", text: base}, "variant B created — tweak it, save, fire the duel ⚔");
  if(!d) return;
  j.variants = d.variants;
  S.draftSide = "B"; S.draftVal = base;
  render();
};
window.onDraftInput = id => { if(S.editing === id) S.draftVal = event.target.value; };
window.saveDraft = (id, silent) => {
  if(S.editing !== id) return;
  const val = S.draftVal;
  const side = S.draftSide || "A";
  if(val === null) return;
  S.editing = null; S.draftVal = "";
  if(side === "A"){
    post("/api/draft", {id, text:val}, silent ? null : "draft saved ✓");
  } else {
    post(`/api/jobs/${id}/variants`, {label: side, text: val},
         silent ? null : "variant " + side + " saved ✓").then(load);
  }
};
window.copyDraft = async id => {
  const j = S.jobs.find(x => x.id === id);
  const text = (S.editing === id) ? S.draftVal : (j ? j.draft : "");
  try{ await navigator.clipboard.writeText(text || ""); toast("copied to clipboard ✓"); }
  catch(e){ toast("clipboard blocked — select & copy manually", true); }
};

window.fetchNow = async () => {
  toast("fetching your sources…");
  const d = await post("/api/fetch", {}, null);
  if(!d) return;
  if(d.hint){ toast(d.hint, true); return; }
  const label = id => (S.connectors.find(c => c.id === id) || {}).label || id;
  const parts = (d.results || []).map(r =>
    r.error ? `${label(r.connector)}: ✗` : `${label(r.connector)} +${r.new || 0}`);
  const total = (d.results || []).reduce((a, r) => a + (r.new || 0), 0);
  toast(`⚡ ${total} new gig(s) — ${parts.join(" · ")}`);
  (d.results || []).filter(r => r.error).forEach(r => toast(label(r.connector) + ": " + r.error, true));
  await load(); loadConnectors();
};
window.loadDemo = () => post("/api/demo", {}, "sample gigs loaded ✓").then(() => { load(); showView("board"); });

/* ------------------------------------------------- theme */
function applyTheme(){
  const t = localStorage.getItem("lh_theme") || "dark";
  document.documentElement.dataset.theme = t;
  const b = $("#themeBtn");
  if(b) b.textContent = t === "light" ? "☀️" : "🌙";
}
window.toggleTheme = () => {
  const next = (localStorage.getItem("lh_theme") || "dark") === "light" ? "dark" : "light";
  localStorage.setItem("lh_theme", next);
  applyTheme();
};
applyTheme();

/* ------------------------------------------------- PWA install */
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

/* ------------------------------------------------- browser alerts */
window.toggleBell = async () => {
  const on = localStorage.getItem("lh_bell") === "1";
  if(on){
    localStorage.setItem("lh_bell", "0");
    $("#bellBtn").classList.remove("on");
    toast("browser alerts off");
    return;
  }
  if(!("Notification" in window)){ toast("this browser has no Notification API", true); return; }
  const perm = Notification.permission === "granted"
    ? "granted" : await Notification.requestPermission();
  if(perm !== "granted"){ toast("notifications are blocked in the browser settings", true); return; }
  localStorage.setItem("lh_bell", "1");
  $("#bellBtn").classList.add("on");
  toast("🔔 alerts on — new gigs ping you while the dashboard is open");
};

function bellCheck(jobs){
  const bell = $("#bellBtn");
  if(bell) bell.classList.toggle("on", localStorage.getItem("lh_bell") === "1");
  const ids = new Set(jobs.map(j => j.id));
  if(S.knownIds === null){ S.knownIds = ids; return; }  // baseline: no spam on boot
  const fresh = jobs.filter(j => !S.knownIds.has(j.id));
  S.knownIds = ids;
  const on = localStorage.getItem("lh_bell") === "1";
  if(!on || !fresh.length || !("Notification" in window) || Notification.permission !== "granted") return;
  const top = fresh.slice().sort((a, b) => b.score - a.score)[0];
  try{
    const n = new Notification("🐺 leadhound — " + fresh.length + " new gig(s)",
      {body: "top score " + top.score + " · " + top.title.slice(0, 90)});
    n.onclick = () => { window.focus(); showView("board"); };
  }catch(e){ /* some browsers throttle background notifications */ }
}

/* ------------------------------------------------- snipe flow */
window.openSnipe = async id => {
  let r, p;
  try{ r = await fetch(`/api/jobs/${id}/snipe-plan`); }catch(e){ toast("request failed", true); return; }
  if(r.status === 401){ boot(); return; }
  p = await r.json().catch(() => ({}));
  if(!r.ok){ toast(p.detail || ("http " + r.status), true); return; }
  S.snipePlan = p;
  renderSnipeDialog();
};

function renderSnipeDialog(){
  const p = S.snipePlan;
  const isApi = p.mode === "api";
  S.snipeVariant = "A";
  const vars = p.variants || [];
  if(vars.length){
    const chips = [`<button class="sel" data-v="A" onclick="pickVariant('A')">A · main draft</button>`]
      .concat(vars.map(v =>
        `<button data-v="${esc(v.label)}" onclick="pickVariant('${esc(v.label)}')">${esc(v.label)} · duel</button>`));
    $("#sVar").innerHTML = `<label>proposal version — track which one wins</label>
      <div class="svchips">${chips.join("")}</div>`;
    $("#sVar").hidden = false;
  } else { $("#sVar").hidden = true; }
  $("#sTitle").textContent = p.source + " · " + (p.amount ? "$" + fmt(p.amount) : "budget TBD");
  $("#sSub").textContent = "🎯 " + (isApi
    ? "live-fire mode — the bid lands on Freelancer.com before you close this dialog"
    : "kit mode — your proposal + the gig page, fired from your own logged-in session");
  $("#sMode").className = "smode" + (isApi ? " fire" : "");
  $("#sMode").innerHTML = isApi
    ? `🔥 <b>live-fire</b> — a REAL bid will be placed on Freelancer.com${p.identity ? " as <b>@" + esc(p.identity.username) + "</b>" : ""} via the official API, on your account.`
    : `🎯 leadhound copies your proposal and opens the gig — you paste &amp; send. ` +
      (p.source === "freelancer" && !p.linked
        ? `or <a href="#" onclick="closeSnipe(); showView('accounts'); return false;">link your Freelancer.com account</a> to fire real bids instead.`
        : "");
  $("#sText").value = p.text || "";
  $("#sApiFields").hidden = !isApi;
  $("#sAmount").value = p.amount || "";
  $("#sPeriod").value = p.period || 7;
  $("#sFire").textContent = isApi ? "🔥 fire real bid" : "🎯 open gig + copy proposal";
  $("#sFire").className = isApi ? "fire" : "primary";
  $("#sFireRow").hidden = false;
  $("#sConfirmRow").hidden = true;
  $("#sNote").textContent = isApi
    ? "bids are user-triggered only — leadhound never auto-bids in the background."
    : "after you send it, mark the outcome (replied / won / lost) to calibrate the scope.";
  $("#snipeModal").hidden = false;
}

window.closeSnipe = () => { $("#snipeModal").hidden = true; S.snipePlan = null; };

window.pickVariant = label => {
  S.snipeVariant = label;
  const p = S.snipePlan;
  if(!p) return;
  if(label === "A") $("#sText").value = p.text || "";
  else{
    const v = (p.variants || []).find(x => x.label === label);
    $("#sText").value = v ? v.text : "";
  }
  document.querySelectorAll("#sVar .svchips button").forEach(b =>
    b.classList.toggle("sel", b.dataset.v === label));
};

window.onSnipeFire = async () => {
  const p = S.snipePlan;
  if(!p) return;
  const text = $("#sText").value;
  if(p.mode === "api"){
    const btn = $("#sFire");
    btn.disabled = true;
    const d = await post(`/api/jobs/${p.id}/snipe`,
      {amount: parseFloat($("#sAmount").value) || 0,
       period: parseInt($("#sPeriod").value) || 7, text,
       variant: S.snipeVariant || "A"}, null);
    btn.disabled = false;
    if(!d) return;
    closeSnipe();
    toast(`🔥 REAL bid #${d.bid_id} placed on Freelancer.com ($${d.amount}) — good hunting!`);
    load();
  } else {
    try{ await navigator.clipboard.writeText(text || ""); }
    catch(e){ toast("clipboard blocked — copy the proposal from the dialog", true); }
    window.open(p.url, "_blank", "noopener");
    $("#sFireRow").hidden = true;
    $("#sConfirmRow").hidden = false;
    $("#sNote").textContent = "proposal copied + gig opened in a new tab. paste & send it there, then confirm below.";
  }
};

window.onSnipeConfirm = async () => {
  const p = S.snipePlan;
  if(!p) return;
  const d = await post(`/api/jobs/${p.id}/snipe-confirm`,
    {variant: S.snipeVariant || "A"}, null);
  if(!d) return;
  closeSnipe();
  toast("🎯 sniped" + (S.snipeVariant && S.snipeVariant !== "A" ? " (variant " + S.snipeVariant + ")" : "")
    + " — mark the outcome when they reply");
  load();
};

function updateSteps(){
  const connected = S.connectors.some(c => c.enabled);
  const real = S.jobs.some(j => j.source !== "demo");
  const s1 = $("#st1"), s2 = $("#st2");
  if(s1) s1.classList.toggle("done", connected);
  if(s2) s2.classList.toggle("done", real);
}

/* ------------------------------------------------- connectors */
const KINDLABEL = {public:"no setup", keys:"API keys", cookie:"cookie", feed:"feed URL"};
window.showView = v => {
  S.view = v;
  $("#tabBoard").classList.toggle("sel", v === "board");
  $("#tabStats").classList.toggle("sel", v === "stats");
  $("#tabAccts").classList.toggle("sel", v === "accounts");
  $("#accountsView").hidden = v !== "accounts";
  $("#statsView").hidden = v !== "stats";
  ["#hero", "#board", "#hintbar"].forEach(sel => {
    const el = $(sel);
    if(el) el.style.display = v === "board" ? "" : "none";
  });
  if(v === "accounts"){ loadConnectors(); loadNotify(); }
  else if(v === "stats") loadStats();
  else updateSteps();
};

/* ------------------------------------------------- stats */
async function loadStats(){
  try{
    const r = await fetch("/api/stats");
    if(r.status === 401){ boot(); return; }
    if(!r.ok) throw new Error("http " + r.status);
    S.stats = await r.json();
    renderStats();
  }catch(e){
    const b = $("#statsBody");
    if(b) b.innerHTML = `<div class="empty">could not load stats — is the server up?</div>`;
  }
}

function renderStats(){
  const d = S.stats;
  if(!d) return;
  const f = d.funnel || {}, p = d.pipeline || {}, cal = d.calibration || {};
  const pct = x => x == null ? "—" : x + "%";
  const money0 = n => "$" + Number(n || 0).toLocaleString("en-US");
  const duelVerdict = (a, b) => {
    if(!a || !b || !a.sent || !b.sent) return "";
    const ra = a.replies / a.sent, rb = b.replies / b.sent;
    if(ra === rb) return "";
    const win = ra > rb ? "main draft (A)" : "variant B";
    return `<div class="sline">⚔ <b>${esc(win)}</b> replies more so far — crown it or keep testing.</div>`;
  };
  const cards = [
    {k:"shots fired", v:f.sniped ?? 0, s:"sniped gigs, all time", cls:""},
    {k:"reply rate", v:pct(f.reply_rate), s:f.replies + " of " + (f.sniped ?? 0) + " replied", cls:""},
    {k:"win rate", v:pct(f.win_rate), s:f.wins + "W / " + (f.losses ?? 0) + "L resolved", cls:"hot"},
    {k:"won value", v:money0(f.won_value), s:"fixed-price, all time", cls:"hot"},
    {k:"in play", v:money0(p.inplay_value), s:(p.inplay_n ?? 0) + " gig(s) awaiting a verdict", cls:""},
    {k:"interviews", v:f.interviews ?? 0, s:"the stage between reply and verdict", cls:""},
  ];
  const maxSent = Math.max(1, ...(f.by_source || []).map(r => r.sent || 0));
  const srcRows = (f.by_source || []).map(r => `
    <div class="brow">
      <span class="bl" title="${esc(r.source)}">${esc(r.source)}</span>
      <span class="btrack"><span class="bfill ${r.wins ? "g" : ""}" style="width:${Math.round(100*(r.sent||0)/maxSent)}%"></span></span>
      <span class="bn">${r.sent} fired · ${r.replies} replied${r.wins ? " · 🏆 " + r.wins + " · " + money0(r.won_value) : ""}${r.reply_rate != null ? " · " + r.reply_rate + "%" : ""}</span>
    </div>`).join("") || `<div class="sline">nothing fired yet — snipe something first.</div>`;
  const mApi = (f.by_method || {})["freelancer-api"], mKit = (f.by_method || {})["kit"];
  const mline = m => m
    ? `<div class="sline">${m.sent} fired · <b>${m.replies} replied</b>${m.wins ? " · 🏆 " + m.wins + " won" : ""}</div>`
    : `<div class="sline">none yet</div>`;
  const bv = f.by_variant || {};
  const duel = (bv["A"] && bv["B"]) ? `
    <div class="spanel">
      <h3>proposal duel (A/B)</h3>
      <div class="sline">🅰 <b>main draft</b></div>
      ${mline(bv["A"])}
      <div class="sline">🅱 <b>variant B</b></div>
      ${mline(bv["B"])}
      ${duelVerdict(bv["A"], bv["B"])}
    </div>` : "";
  const calBits = Object.entries(cal).filter(([k]) => k !== "hint").map(([k, v]) =>
    `<span class="chip">${esc(k)}: ${v.n} (avg ${v.avg_score})</span>`).join(" ");
  const body = $("#statsBody");
  if(!body) return;
  body.innerHTML = `
    <div class="scards">${cards.map(c => `
      <div class="scard ${c.cls}"><div class="k">${esc(c.k)}</div><div class="v">${c.v}</div><div class="s">${esc(c.s)}</div></div>`).join("")}
    </div>
    <div class="spanel">
      <h3>per-source conversion</h3>
      ${srcRows}
      <div class="sline">bar = share of your shots · % = reply rate. feed the green rows, prune the dead ones.</div>
    </div>
    <div class="spanel">
      <h3>live-fire vs kit</h3>
      <div class="sline">🔥 <b>live-fire bids</b> — official Freelancer.com API, real bids on your account</div>
      ${mline(mApi)}
      <div class="sline">🎯 <b>snipe kit</b> — proposal copied + gig opened, you paste &amp; send</div>
      ${mline(mKit)}
    </div>
    ${duel}
    <div class="spanel">
      <h3>scope calibration</h3>
      <div class="sline">${calBits || "no outcomes marked yet"}</div>
      ${cal.hint ? `<div class="sline">🧠 ${esc(cal.hint)}</div>` : ""}
    </div>`;
}

async function loadRadar(){
  try{
    const r = await fetch("/api/radar");
    if(!r.ok) return null;
    return await r.json();
  }catch(e){ return null; }
}

async function loadConnectors(){
  try{
    const r = await fetch("/api/connectors");
    if(r.status === 401) return;
    const d = await r.json();
    S.connectors = d.connectors || [];
    renderAccounts();
  }catch(e){}
}

function connState(c){
  const st = c.status || {};
  if(c.id === "freelancer_account" && (c.settings || {}).identity){
    return {cls:"ok", txt:"✅ linked as @" + c.settings.identity.username};
  }
  if(c.enabled && st.last_error) return {cls:"err", txt:"❌ error"};
  if(c.enabled && st.last_status === "ok") return {cls:"ok", txt:"✅ connected"};
  if(c.enabled) return {cls:"warn", txt:"🟡 on — not tested yet"};
  const needs = ["keys","cookie","feed"].includes(c.kind) &&
                (c.fields || []).some(f => !(c.settings || {})[f.name]);
  return needs ? {cls:"warn", txt:"⚠ setup needed"} : {cls:"off", txt:"⚫ off"};
}

const OAUTH_CIDS = ["upwork", "freelancer_account"];
const WIZARDS = {
  freelancer_account: () => `
    <details class="wiz"><summary>how to link Freelancer.com (2 min, official API — enables 🔥 live-fire bids)</summary>
      <ol>
        <li>create a free app at <a href="https://www.freelancer.com/developers/applications" target="_blank" rel="noopener noreferrer">freelancer.com/developers/applications</a></li>
        <li>add this <b>redirect URI</b> to your app: <code>${esc(location.origin)}/api/connectors/freelancer_account/callback</code>
            <button onclick="copyRuri('freelancer_account')">⧉ copy</button></li>
        <li>paste the <b>client id</b> + <b>secret</b> above → 💾 save</li>
        <li>hit 🔗 connect → approve in the Freelancer tab that opens</li>
        <li>done — every Freelancer.com gig card now fires REAL bids on your account</li>
      </ol>
      <div class="warn">⚠ bids are placed on YOUR account with YOUR token, only when you click 🎯 snipe. leadhound never auto-bids in the background.</div>
    </details>`,
  upwork: () => `
    <details class="wiz"><summary>how to connect Upwork (2 min, official API)</summary>
      <ol>
        <li>create a free app at <a href="https://www.upwork.com/developer/applications" target="_blank" rel="noopener noreferrer">upwork.com/developer/applications</a> — any name, "desktop app" type is fine</li>
        <li>add this <b>redirect URI</b> to your app: <code>${esc(location.origin)}/api/connectors/upwork/callback</code>
            <button onclick="copyRuri('upwork')">⧉ copy</button></li>
        <li>paste the <b>client id</b> + <b>secret</b> above → 💾 save</li>
        <li>hit 🔗 connect → approve in the Upwork tab that opens</li>
        <li>⚡ run now — real jobs land on your board, token auto-refreshes forever</li>
      </ol>
      <div class="warn">⚠ Upwork's API doesn't let third-party apps submit proposals — sniping there uses the honest one-click kit (proposal copied + gig opened).</div>
    </details>`,
  fiverr: () => `
    <details class="wiz"><summary>how to get your Fiverr cookie (1 min)</summary>
      <ol>
        <li>log into fiverr.com in this browser</li>
        <li>press F12 → <b>Network</b> tab → click any request to fiverr.com</li>
        <li>Request Headers → copy the whole <b>cookie:</b> value</li>
        <li>paste it above → 💾 save → ⚡ run now</li>
      </ol>
      <div class="warn">⚠ beta, honestly labeled: Fiverr has no public API. if it logs you out or their page changes, paste a fresh cookie. skip this connector if that's too spicy.</div>
    </details>`,
};

function renderAccounts(){
  const n = S.connectors.filter(c => c.enabled).length;
  $("#connN").textContent = n;
  const connected = S.connectors.filter(c => connState(c).cls === "ok").length;
  const errors = S.connectors.filter(c => connState(c).cls === "err").length;
  $("#acctSummary").innerHTML =
    `<b>${connected}</b> of ${S.connectors.length} sources connected` +
    (errors ? ` · <span style="color:var(--red)">${errors} with errors</span>` : "") +
    ` · <span id="radarLine">checking radar…</span>`;
  loadRadar().then(rd => {
    const el = $("#radarLine");
    if(!el) return;
    el.innerHTML = !rd || !rd.running
      ? `radar: <span style="color:var(--amber)">idle (radar runs with <code>leadhound web</code>)</span>`
      : `📡 radar <b>live</b> · sweeps every ${rd.interval_minutes} min` +
        (rd.enabled_sources ? ` · ${rd.enabled_sources} source(s) armed` : "");
  });
  $("#acctGrid").innerHTML = S.connectors.map(c => {
    const st = c.status || {};
    const badge = connState(c);
    const statLine = st.last_error
      ? `⚠ ${esc(st.last_error)}`
      : st.last_run
        ? `⏱ last sweep ${esc(String(st.last_run).slice(0,16))} · +${st.last_count || 0} new gig(s)`
        : "never run yet";
    const fields = (c.fields || []).map(f => `
      <div>
        <label>${esc(f.label)}</label>
        <input id="f_${esc(c.id)}_${esc(f.name)}" type="${f.secret ? "password" : "text"}"
               value="${esc((c.settings || {})[f.name] ?? "")}"
               placeholder="${esc(f.placeholder || "")}" autocomplete="off">
        ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ""}
      </div>`).join("");
    const needsSave = (c.fields || []).length > 0;
    const wiz = WIZARDS[c.id] ? WIZARDS[c.id]() : "";
    return `<div class="conn ${c.enabled ? "on" : ""}">
      <div class="connhead">
        <b>${esc(c.label)}</b>
        <span class="kchip ${esc(c.kind)}">${esc(KINDLABEL[c.kind] || c.kind)}</span>
        <span class="badge ${badge.cls}">${badge.txt}</span>
      </div>
      <div class="blurb">${esc(c.blurb)}</div>
      ${fields ? `<div class="fields">${fields}</div>` : ""}
      <div class="connacts">
        ${needsSave ? `<button onclick="saveConn('${esc(c.id)}')">💾 save</button>` : ""}
        <button onclick="toggleConn('${esc(c.id)}', ${!c.enabled})">${c.enabled ? "switch off" : "switch on"}</button>
        <button onclick="runConn('${esc(c.id)}')">⚡ ${needsSave ? "save & test" : "run now"}</button>
        ${OAUTH_CIDS.includes(c.id) ? `<button onclick="oauthConnect('${esc(c.id)}')">🔗 connect</button>` : ""}
        ${c.setup_url ? `<a href="${esc(c.setup_url)}" target="_blank" rel="noopener noreferrer">get keys ↗</a>` : ""}
      </div>
      ${wiz}
      <div class="cstat ${st.last_error ? "err" : ""}">${statLine}</div>
    </div>`;
  }).join("");
}

window.toggleConn = async (cid, enabled) => {
  const d = await post("/api/connectors/" + cid, {enabled}, enabled ? "source on ✓" : "source off");
  if(d){ loadConnectors(); }
};
window.saveConn = async cid => {
  const conn = S.connectors.find(c => c.id === cid);
  const settings = {};
  (conn.fields || []).forEach(f => {
    const el = $("#f_" + cid + "_" + f.name);
    if(el) settings[f.name] = el.value;
  });
  const d = await post("/api/connectors/" + cid, {settings}, "settings saved ✓");
  if(d){ loadConnectors(); }
};
window.runConn = async cid => {
  toast("running " + cid + "…");
  const d = await post("/api/connectors/" + cid + "/run", {}, null);
  if(!d) return;
  if(d.error) toast(cid + ": " + d.error, true);
  else toast(cid + ": " + (d.new || 0) + " new gig(s) ✓");
  await load(); loadConnectors();
};
window.copyRuri = async cid => {
  const uri = location.origin + "/api/connectors/" + cid + "/callback";
  try{ await navigator.clipboard.writeText(uri); toast("redirect URI copied ✓"); }
  catch(e){ toast(uri); }
};
window.oauthConnect = async cid => {
  const d = await post(`/api/connectors/${cid}/auth/start`, {}, null);
  if(!d) return;
  toast("authorize in the tab that opens, then ⚡ save & test");
  window.open(d.authorize_url, "_blank", "noopener");
};

/* ------------------------------------------------- telegram pocket sniper */
async function loadNotify(){
  try{
    const d = await (await fetch("/api/notify")).json();
    if(!d.ok) return;
    const n = d.notify;
    $("#tgToken").placeholder = n.has_token ? "••• saved — type to replace" : "123456:ABC-DEF…";
    $("#tgChat").value = n.telegram_chat_id || "";
    $("#tgMin").value = n.push_min_score;
    $("#tgTgl").textContent = n.telegram_enabled ? "switch off" : "switch on";
    const badge = $("#tgBadge");
    badge.textContent = n.listening ? "listening" : (n.telegram_enabled ? "armed" : "off");
    badge.className = "badge " + (n.listening ? "ok" : (n.telegram_enabled ? "warn" : "off"));
    $("#tgListen").textContent = n.listen_enabled ? "🎧 disarm listener" : "🎧 arm listener";
    $("#tgStat").textContent = n.has_token
      ? (n.listening
          ? "bot token saved ✓ · two-way listener live — try /queue in your chat"
          : "bot token saved ✓")
      : "no bot token yet";
  }catch{ /* dashboard stays usable offline */ }
}
window.saveTelegram = async () => {
  const tok = $("#tgToken").value.trim();
  const body = {
    chat_id: $("#tgChat").value.trim(),
    push_min_score: Math.max(0, Math.min(100, +$("#tgMin").value || 0)),
  };
  if(tok) body.token = tok;
  const d = await post("/api/notify/telegram", body, "telegram saved ✓");
  if(d){ $("#tgToken").value = ""; loadNotify(); }
};
window.testTelegram = async () => {
  try{
    const r = await fetch("/api/notify/telegram/test", {method: "POST"});
    const d = await r.json().catch(() => ({ok:false, detail:"bad response"}));
    toast(d.ok ? "📱 test message sent — check your chat" : "telegram says: " + (d.detail || "failed"), !d.ok);
  }catch{ toast("network error", true); }
};
window.toggleTelegram = async () => {
  try{
    const cur = (await (await fetch("/api/notify")).json()).notify;
    if(!cur || !cur.has_token){ toast("save a bot token first", true); return; }
    const d = await post("/api/notify/telegram",
      {enabled: !cur.telegram_enabled}, cur.telegram_enabled ? "push off" : "📱 push armed");
    if(d) loadNotify();
  }catch{ toast("network error", true); }
};
window.toggleListen = async () => {
  try{
    const cur = (await (await fetch("/api/notify")).json()).notify;
    if(!cur || !cur.has_token){ toast("save a bot token + chat id first", true); return; }
    const d = await post("/api/notify/telegram/listen",
      {listen: !cur.listen_enabled},
      cur.listen_enabled ? "listener off" : "🎧 pocket listener armed — /queue in your chat");
    if(d) loadNotify();
  }catch{ toast("network error", true); }
};

/* ------------------------------------------------- board */
function toggleAuto(){
  S.auto = !S.auto;
  $("#autoBtn").classList.toggle("on", S.auto);
  if(S.auto){ S.timer = setInterval(tick, 8000); load(); }
  else{ clearInterval(S.timer); }
}
function tick(){ if(S.auto && S.editing === null) load(); }

function chips(){
  const total = S.jobs.length;
  const hot = S.jobs.filter(j => j.score >= 80).length;
  const pend = S.jobs.filter(j => j.status === "pending").length;
  const won = S.jobs.filter(j => j.outcome === "won").length;
  const replied = S.jobs.filter(j => j.outcome === "replied").length;
  const sn7 = S.snipe.sniped_7d || 0;
  const rate = S.snipe.reply_rate;
  const bits = [
    `<span class="chip blue">${total} gigs tracked</span>`,
    `<span class="chip green">🔥 ${hot} hot</span>`,
    `<span class="chip">${pend} pending</span>`,
    `<span class="chip amber">🎯 ${sn7} sniped · 7d</span>`,
    (rate != null ? `<span class="chip amber">↩ ${rate}% reply rate</span>` : `<span class="chip amber">↩ ${replied} replied</span>`),
    `<span class="chip green">🏆 ${won} won</span>`,
  ];
  $("#chips").innerHTML = bits.join("");
  const h = S.cal && S.cal.hint;
  const calText = h ? `🧠 scope calibration: <b>${esc(h)}</b>` : "🧠 mark outcomes (replied / won / lost) to calibrate the scope";
  $("#hintbar").innerHTML = S.demo
    ? `<span class="chip amber">🎲 demo mode</span>&nbsp; these are sample gigs — hit <b>⚡ fetch gigs</b> (or ⚙ sources) to hunt real ones &nbsp;·&nbsp; ${calText}`
    : calText;
}

function card(j){
  const m = money(j);
  const flags = (j.red_flags || []).map(f =>
    `<span class="chip red">⚑ ${esc(f)}</span>`).join("");
  const skills = (j.matched || []).slice(0, 6).map(s =>
    `<span class="chip green">${esc(s)}</span>`).join("");
  const tags = (j.tags || []).slice(0, 3).map(t =>
    `<span class="chip">${esc(t)}</span>`).join("");
  const ob = j.outcome
    ? `<span class="obadge o-${esc(j.outcome)}">${esc(j.outcome)}</span>` : "";
  const vtag = (j.sent_variant && j.sent_variant !== "A")
    ? " · " + esc(j.sent_variant) : "";
  const sbadge = j.snipe_method === "freelancer-api"
    ? `<span class="schip" title="${esc(j.snipe_note || "")}">🔥 live-fire bid${vtag}</span>`
    : j.snipe_method === "kit"
      ? `<span class="schip" title="${esc(j.snipe_note || "")}">🎯 kit${vtag}</span>` : "";
  const open = S.editing === j.id;
  const hasB = (j.variants || []).some(v => v.label === "B");

  let acts = "";
  if(j.status === "pending")
    acts = `<button class="snipebtn" onclick="openSnipe(${j.id})">🎯 snipe</button>
            <button onclick="act(${j.id},'approved')">✓ approve</button>
            <button onclick="act(${j.id},'rejected')">✗ reject</button>`;
  else if(j.status === "approved")
    acts = `<button class="snipebtn" onclick="openSnipe(${j.id})">🎯 snipe</button>
            <button onclick="act(${j.id},'sent')">➤ mark sent</button>
            <button onclick="act(${j.id},'rejected')">✗ reject</button>`;
  else if(j.status === "sent")
    acts = `<select onchange="setOutcome(${j.id}, this.value)">
              <option value="">outcome…</option>
              <option value="replied"${j.outcome==="replied"?" selected":""}>↩ replied</option>
              <option value="interview"${j.outcome==="interview"?" selected":""}>🎤 interview</option>
              <option value="won"${j.outcome==="won"?" selected":""}>🏆 won</option>
              <option value="lost"${j.outcome==="lost"?" selected":""}>✗ lost</option>
            </select>
            <button onclick="act(${j.id},'approved')">↩ back</button>`;
  else
    acts = `<button onclick="act(${j.id},'pending')">↩ restore</button>`;

  return `<div class="card ${j.score>=80?"hot":(j.score<60?"cold":"")} ${S.sel===j.id?"selk":""}">
    <div class="row">
      <div class="ring" style="border-color:${ringColor(j.score)};color:${ringColor(j.score)}">${j.score}</div>
      <div style="min-width:0">
        <div class="ttl"><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a> ${ob}${sbadge}</div>
        <div class="meta">
          <span class="chip blue">${esc(j.source)}</span>
          ${m ? `<span class="chip amber">$${esc(m).replace("$","")}</span>` : ""}
          ${j.fetched_at ? `<span class="chip">${esc(j.fetched_at.slice(0,10))}</span>` : ""}
        </div>
      </div>
    </div>
    ${(skills || flags || tags) ? `<div class="skills">${skills}${flags}${tags}</div>` : ""}
    ${j.intel ? `<div class="intel">🔬 ${esc(j.intel)}</div>` : ""}
    ${j.body ? `<div class="prev">${esc(j.body)}</div>` : ""}
    ${j.budget_note ? `<div class="prev">${esc(j.budget_note)}</div>` : ""}
    <div class="acts">${acts}
      <button onclick="toggleDraft(${j.id})">✎ ${open ? "close" : "draft"}</button>
      <button onclick="copyDraft(${j.id})">⧉ copy</button>
    </div>
    ${open ? `<div class="draftbox">
        <div class="dtabs">
          <button class="${(S.draftSide||"A")==="A"?"sel":""}" onclick="draftSide(${j.id},'A')">A · main</button>
          ${hasB
            ? `<button class="${S.draftSide==="B"?"sel":""}" onclick="draftSide(${j.id},'B')">B · duel</button>`
            : `<button onclick="seedVariant(${j.id})" title="clone the draft as variant B and see which tone wins">⚔ add B — A/B test</button>`}
        </div>
        <textarea oninput="onDraftInput(${j.id})" id="ta${j.id}"></textarea>
        <div class="draftbtns">
          <button onclick="saveDraft(${j.id})">💾 save ${(S.draftSide||"A")==="A" ? "draft" : "variant " + esc(S.draftSide)}</button>
          <button onclick="copyDraft(${j.id})">⧉ copy</button>
        </div>
      </div>` : ""}
  </div>`;
}

function filteredJobs(){
  const q = S.q.trim().toLowerCase();
  let jobs = S.jobs;
  if(q) jobs = jobs.filter(j =>
    (j.title + " " + j.body + " " + j.source + " " + (j.tags||[]).join(" ")).toLowerCase().includes(q));
  return jobs;
}

function render(){
  chips();
  updateSteps();
  const jobs = filteredJobs();
  $("#hero").hidden = S.jobs.length > 0;
  $("#board").style.display = S.jobs.length ? "" : "none";
  const order = [];
  $("#board").innerHTML = COLS.map(c => {
    const list = jobs.filter(j => j.status === c.key).sort((a,b) => b.score - a.score || b.id - a.id);
    list.forEach(j => order.push(j.id));
    return `<div class="col">
      <h2>${c.label} <span class="n">${list.length}</span></h2>
      <div class="cards">${list.length
        ? list.map(card).join("")
        : `<div class="empty">nothing here</div>`}</div>
    </div>`;
  }).join("");
  S.selOrder = order;
  if(S.sel != null && S.selScroll){
    const el = document.querySelector(".card.selk");
    if(el) el.scrollIntoView({block:"nearest", behavior:"smooth"});
    S.selScroll = false;
  }
  if(S.editing !== null){
    const ta = $("#ta" + S.editing);
    if(ta){ ta.value = S.draftVal; ta.focus(); }
  }
}

/* ------------------------------------------------- keyboard cockpit */
const TYPING = () => /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "");

function kMove(dir){
  const order = S.selOrder || [];
  if(!order.length) return;
  const idx = order.indexOf(S.sel);
  const next = idx === -1 ? (dir > 0 ? 0 : order.length - 1)
    : (idx + dir + order.length) % order.length;
  S.sel = order[next];
  S.selScroll = true;
  render();
}

function kNeighbor(){
  const order = S.selOrder || [];
  const idx = order.indexOf(S.sel);
  return order.length ? order[(idx + 1) % order.length] : null;
}

window.kAct = (id, status) => {
  const nid = kNeighbor();          // keep the flow: act, then aim at the next gig
  if(nid != null){ S.sel = nid; S.selScroll = true; }
  act(id, status);
};

window.kOpen = id => {
  const j = S.jobs.find(x => x.id === id);
  if(j) window.open(j.url, "_blank", "noopener");
};

window.toggleKeyHelp = () => { $("#keyHelp").hidden = !$("#keyHelp").hidden; };

document.addEventListener("keydown", e => {
  if(e.key === "Escape"){
    if(!$("#keyHelp").hidden){ $("#keyHelp").hidden = true; return; }
    if(!$("#snipeModal").hidden){ closeSnipe(); return; }
    if(S.editing !== null){ saveDraft(S.editing, true); render(); return; }
    if(S.sel != null){ S.sel = null; render(); }
    return;
  }
  if(!$("#snipeModal").hidden || !$("#keyHelp").hidden) return;
  if(TYPING()) return;
  if(e.key === "?"){ toggleKeyHelp(); return; }
  const j = S.jobs.find(x => x.id === S.sel);
  const k = e.key.toLowerCase();
  if(k === "j" || e.key === "ArrowDown"){ e.preventDefault(); kMove(1); }
  else if(k === "k" || e.key === "ArrowUp"){ e.preventDefault(); kMove(-1); }
  else if(!j){ /* nothing aimed — movement keys only */ }
  else if(k === "a" && j.status === "pending") kAct(j.id, "approved");
  else if((k === "x" || k === "r") && (j.status === "pending" || j.status === "approved")) kAct(j.id, "rejected");
  else if(k === "s" && (j.status === "pending" || j.status === "approved")) openSnipe(j.id);
  else if(k === "o") kOpen(j.id);
  else if(k === "c") copyDraft(j.id);
  else if(k === "d") toggleDraft(j.id);
});

S.timer = setInterval(tick, 8000);
boot();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- PWA assets
# Sniper-scope icon: pure vector, renders identically everywhere (no font games).
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#0d1117"/>
  <path d="M256 40v96M256 376v96M40 256h96M376 256h96" stroke="#58a6ff" stroke-width="26" stroke-linecap="round"/>
  <circle cx="256" cy="256" r="148" fill="none" stroke="#58a6ff" stroke-width="26"/>
  <circle cx="256" cy="256" r="72" fill="none" stroke="#3fb950" stroke-width="26"/>
  <circle cx="256" cy="256" r="24" fill="#f85149"/>
</svg>"""

MANIFEST = r"""{
  "name": "leadhound — gig sniper",
  "short_name": "leadhound",
  "description": "Watches freelance job boards, scores every gig, drafts the proposal. You approve and fire.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0d1117",
  "theme_color": "#0d1117",
  "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]
}"""

# Shell cache only — /api/* is live data and is NEVER cached. Navigation goes
# network-first so updates land on the next reload; icons are cache-first.
SW_JS = r"""/* leadhound service worker — pocket-console shell cache */
const CACHE = "leadhound-v1";
const SHELL = ["/", "/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/sw.js") return;
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put("/", copy)).catch(() => {});
        return r;
      }).catch(() => caches.match("/").then(r => r || Response.error()))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
      return r;
    }).catch(() => Response.error()))
  );
});"""
