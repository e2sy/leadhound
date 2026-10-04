"""Embedded single-page app served by leadhound.api.

Vanilla HTML/CSS/JS — no CDN, no build step, works fully offline.
v2: account gate (login/register), sources drawer (per-connector setup,
enable, run-now), explicit demo button, honest empty state.
All user-controlled strings are HTML-escaped with esc() before insertion.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🐺 leadhound — snipe console</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2129; --line:#21262d;
    --txt:#e6edf3; --dim:#8b949e; --blue:#58a6ff; --green:#3fb950;
    --red:#f85149; --amber:#e3b341; --cyan:#39c5cf;
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

  header{position:sticky; top:0; z-index:10; background:rgba(13,17,23,.92);
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
  #hero .hbtns{display:flex; gap:10px; justify-content:center; flex-wrap:wrap}
  #hero .fine{margin-top:16px; font-size:11.5px; color:var(--dim)}

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

  /* ---------------- sources drawer ---------------- */
  #scrim{position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:20; opacity:0;
         pointer-events:none; transition:opacity .18s}
  #scrim.open{opacity:1; pointer-events:auto}
  #drawer{position:fixed; top:0; right:0; bottom:0; width:min(420px, 94vw); z-index:30;
          background:var(--panel); border-left:1px solid var(--line);
          transform:translateX(102%); transition:transform .2s ease; display:flex; flex-direction:column}
  #drawer.open{transform:none}
  #drawer .dhead{padding:14px 16px; border-bottom:1px solid var(--line); display:flex; align-items:center; gap:10px}
  #drawer .dhead h2{font-size:15px}
  #drawer .dsub{padding:10px 16px; font-size:12px; color:var(--dim); border-bottom:1px solid var(--line)}
  #connlist{flex:1; overflow-y:auto; padding:12px}
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
  #drawer .dfoot{padding:10px 16px; border-top:1px solid var(--line); font-size:11px; color:var(--dim)}

  #toasts{position:fixed; right:14px; bottom:14px; display:flex; flex-direction:column; gap:8px; z-index:50}
  .toast{background:var(--panel); border:1px solid var(--green); color:var(--txt);
         border-radius:10px; padding:8px 14px; font-size:13px; box-shadow:0 6px 24px rgba(0,0,0,.5)}
  .toast.err{border-color:var(--red)}

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
    <button onclick="openDrawer()" title="connect job sites">⚙ sources <span id="connN" class="chip blue">0</span></button>
    <button id="autoBtn" class="on" onclick="toggleAuto()" title="auto-refresh every 8s">⟳ auto</button>
    <button class="primary" onclick="fetchNow()" title="fetch every enabled source now">⚡ fetch gigs</button>
    <div id="userbox">
      <span class="who" id="whoami"></span>
      <button onclick="logout()" title="log out">⎋</button>
    </div>
  </header>
  <div class="hintbar" id="hintbar">loading…</div>
  <div id="hero" hidden>
    <div class="wolf">🐺</div>
    <h1>Your board is empty</h1>
    <p>Connect sources and fetch real gigs — Freelancer.com works with zero setup,
       Upwork connects with your app keys, Fiverr with your session cookie,
       or point the RSS connector at any job feed.</p>
    <div class="hbtns">
      <button class="primary" onclick="fetchNow()">⚡ fetch gigs now</button>
      <button onclick="openDrawer()">⚙ connect sources</button>
      <button onclick="loadDemo()">🎲 load sample gigs</button>
    </div>
    <div class="fine">fetching pulls from the live job boards — the radar re-polls every few minutes while this tab's server runs.</div>
  </div>
  <div id="board"></div>
</div>

<div id="scrim" onclick="closeDrawer()"></div>
<aside id="drawer">
  <div class="dhead">
    <h2>⚙ job sources</h2>
    <div class="spacer"></div>
    <button onclick="closeDrawer()">✕</button>
  </div>
  <div class="dsub">switch a source on → fill its settings → ⚡ run. enabled sources re-poll automatically every few minutes.</div>
  <div id="connlist">loading…</div>
  <div class="dfoot">credentials are stored in your local SQLite (secrets masked in the UI) — nothing is sent anywhere except the sites you enable.</div>
</aside>

<div id="toasts"></div>

<script>
"use strict";
const COLS = [
  {key:"pending",  label:"🎯 Pending"},
  {key:"approved", label:"✅ Approved"},
  {key:"sent",     label:"📤 Sent"},
  {key:"rejected", label:"🗑 Rejected"},
];
const S = {jobs:[], cal:{}, q:"", auto:true, editing:null, draftVal:"", timer:null,
           demo:false, user:null, connectors:[], authMode:"login"};

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
    S.editing = id; S.draftVal = j ? (j.draft || "") : "";
  }
  render();
};
window.onDraftInput = id => { if(S.editing === id) S.draftVal = event.target.value; };
window.saveDraft = (id, silent) => {
  if(S.editing !== id) return;
  const val = S.draftVal;
  if(val === null) return;
  S.editing = null; S.draftVal = "";
  post("/api/draft", {id, text:val}, silent ? null : "draft saved ✓");
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
  const total = (d.results || []).reduce((a, r) => a + (r.new || 0), 0);
  const errs = (d.results || []).filter(r => r.error);
  toast(total + " new gig(s) across " + (d.results || []).length + " source(s) ✓");
  errs.forEach(r => toast(r.connector + ": " + r.error, true));
  await load(); loadConnectors();
};
window.loadDemo = () => post("/api/demo", {}, "sample gigs loaded ✓").then(load);

/* ------------------------------------------------- connectors */
const KINDLABEL = {public:"no setup", keys:"API keys", cookie:"cookie", feed:"feed URL"};
window.openDrawer = () => { $("#drawer").classList.add("open"); $("#scrim").classList.add("open"); loadConnectors(); };
window.closeDrawer = () => { $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open"); };

async function loadConnectors(){
  try{
    const r = await fetch("/api/connectors");
    if(r.status === 401) return;
    const d = await r.json();
    S.connectors = d.connectors || [];
    renderConnectors();
  }catch(e){}
}

function renderConnectors(){
  const n = S.connectors.filter(c => c.enabled).length;
  $("#connN").textContent = n;
  $("#connlist").innerHTML = S.connectors.map(c => {
    const st = c.status || {};
    const statLine = st.last_error
      ? `⚠ ${esc(st.last_error)}`
      : st.last_run
        ? `⏱ last run ${esc(String(st.last_run).slice(0,16))} · +${st.last_count || 0} new`
        : "never run yet";
    const fields = (c.fields || []).map(f => `
      <div>
        <label>${esc(f.label)}</label>
        <input id="f_${esc(c.id)}_${esc(f.name)}" type="${f.secret ? "password" : "text"}"
               value="${esc((c.settings || {})[f.name] ?? "")}"
               placeholder="${esc(f.placeholder || "")}" autocomplete="off">
        ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ""}
      </div>`).join("");
    const extra = c.id === "upwork" && c.enabled
      ? `<button onclick="upworkConnect()">🔗 connect upwork</button>` : "";
    return `<div class="conn ${c.enabled ? "on" : ""}">
      <div class="connhead">
        <b>${esc(c.label)}</b>
        <span class="kchip ${esc(c.kind)}">${esc(KINDLABEL[c.kind] || c.kind)}</span>
        <span class="switch">${c.enabled ? "on" : "off"}
          <input type="checkbox" ${c.enabled ? "checked" : ""} onchange="toggleConn('${esc(c.id)}', this.checked)">
        </span>
      </div>
      <div class="blurb">${esc(c.blurb)}</div>
      ${fields ? `<div class="fields">${fields}</div>` : ""}
      <div class="connacts">
        ${fields ? `<button onclick="saveConn('${esc(c.id)}')">💾 save</button>` : ""}
        <button onclick="runConn('${esc(c.id)}')">⚡ run now</button>
        ${extra}
        ${c.setup_url ? `<a href="${esc(c.setup_url)}" target="_blank" rel="noopener noreferrer">get keys ↗</a>` : ""}
      </div>
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
window.upworkConnect = async () => {
  const d = await post("/api/connectors/upwork/auth/start", {}, null);
  if(!d) return;
  toast("authorize in the Upwork tab, then come back and ⚡ run");
  window.open(d.authorize_url, "_blank", "noopener");
  if(d.redirect_uri) toast("use this redirect URI in your Upwork app: " + d.redirect_uri);
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
  const bits = [
    `<span class="chip blue">${total} gigs tracked</span>`,
    `<span class="chip green">🔥 ${hot} hot</span>`,
    `<span class="chip">${pend} pending</span>`,
    `<span class="chip amber">↩ ${replied} replied</span>`,
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
  const open = S.editing === j.id;

  let acts = "";
  if(j.status === "pending")
    acts = `<button onclick="act(${j.id},'approved')">✓ approve</button>
            <button onclick="act(${j.id},'rejected')">✗ reject</button>`;
  else if(j.status === "approved")
    acts = `<button onclick="act(${j.id},'sent')">➤ mark sent</button>
            <button onclick="act(${j.id},'rejected')">✗ reject</button>`;
  else if(j.status === "sent")
    acts = `<select onchange="setOutcome(${j.id}, this.value)">
              <option value="">outcome…</option>
              <option value="replied"${j.outcome==="replied"?" selected":""}>↩ replied</option>
              <option value="won"${j.outcome==="won"?" selected":""}>🏆 won</option>
              <option value="lost"${j.outcome==="lost"?" selected":""}>✗ lost</option>
            </select>
            <button onclick="act(${j.id},'approved')">↩ back</button>`;
  else
    acts = `<button onclick="act(${j.id},'pending')">↩ restore</button>`;

  return `<div class="card ${j.score>=80?"hot":(j.score<60?"cold":"")}">
    <div class="row">
      <div class="ring" style="border-color:${ringColor(j.score)};color:${ringColor(j.score)}">${j.score}</div>
      <div style="min-width:0">
        <div class="ttl"><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a> ${ob}</div>
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
        <textarea oninput="onDraftInput(${j.id})" id="ta${j.id}"></textarea>
        <div class="draftbtns">
          <button onclick="saveDraft(${j.id})">💾 save draft</button>
          <button onclick="copyDraft(${j.id})">⧉ copy</button>
        </div>
      </div>` : ""}
  </div>`;
}

function render(){
  chips();
  const q = S.q.trim().toLowerCase();
  let jobs = S.jobs;
  if(q) jobs = jobs.filter(j =>
    (j.title + " " + j.body + " " + j.source + " " + (j.tags||[]).join(" ")).toLowerCase().includes(q));
  $("#hero").hidden = S.jobs.length > 0;
  $("#board").style.display = S.jobs.length ? "" : "none";
  $("#board").innerHTML = COLS.map(c => {
    const list = jobs.filter(j => j.status === c.key).sort((a,b) => b.score - a.score || b.id - a.id);
    return `<div class="col">
      <h2>${c.label} <span class="n">${list.length}</span></h2>
      <div class="cards">${list.length
        ? list.map(card).join("")
        : `<div class="empty">nothing here</div>`}</div>
    </div>`;
  }).join("");
  if(S.editing !== null){
    const ta = $("#ta" + S.editing);
    if(ta){ ta.value = S.draftVal; ta.focus(); }
  }
}

S.timer = setInterval(tick, 8000);
boot();
</script>
</body>
</html>
"""
