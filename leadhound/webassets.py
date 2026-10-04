"""Embedded single-page dashboard served by leadhound.web.

Vanilla HTML/CSS/JS — no CDN, no build step, works fully offline.
All user-controlled strings are HTML-escaped with esc() before insertion.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🐺 leadhound — pipeline</title>
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
  input#q{background:var(--panel2); border:1px solid var(--line); color:var(--txt);
          border-radius:8px; padding:6px 10px; width:200px; outline:none}
  input#q:focus{border-color:var(--blue)}
  button{background:var(--panel2); border:1px solid var(--line); color:var(--txt);
         border-radius:8px; padding:5px 10px; cursor:pointer; font-size:12.5px}
  button:hover{border-color:var(--blue); color:var(--blue)}
  button.on{border-color:var(--green); color:var(--green)}

  .hintbar{padding:6px 16px; font-size:12px; color:var(--dim); border-bottom:1px solid var(--line)}
  .hintbar b{color:var(--amber)}

  .board{display:grid; grid-template-columns:repeat(4,1fr); gap:12px; padding:14px 16px 40px}
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
  .acts select{background:var(--panel); color:var(--txt); border:1px solid var(--line);
               border-radius:8px; padding:4px 6px; font-size:12px}
  .obadge{font-size:11.5px; padding:1px 8px; border-radius:999px; border:1px solid}
  .o-won{color:var(--green); border-color:var(--green)}
  .o-replied{color:var(--amber); border-color:var(--amber)}
  .o-lost{color:var(--red); border-color:var(--red)}

  details.draft{margin-top:8px; border-top:1px dashed var(--line); padding-top:8px}
  details.draft summary{cursor:pointer; font-size:12.5px; color:var(--blue); user-select:none}
  textarea{width:100%; min-height:130px; margin-top:7px; background:var(--bg);
           color:var(--txt); border:1px solid var(--line); border-radius:8px;
           padding:8px; font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; resize:vertical}
  textarea:focus{border-color:var(--blue); outline:none}
  .draftbtns{display:flex; gap:6px; margin-top:6px}
  .empty{color:var(--dim); font-size:12.5px; text-align:center; padding:22px 8px}

  #toasts{position:fixed; right:14px; bottom:14px; display:flex; flex-direction:column; gap:8px; z-index:50}
  .toast{background:var(--panel); border:1px solid var(--green); color:var(--txt);
         border-radius:10px; padding:8px 14px; font-size:13px; box-shadow:0 6px 24px rgba(0,0,0,.5)}
  .toast.err{border-color:var(--red)}

  @media (max-width:920px){
    .board{grid-template-columns:repeat(4, minmax(270px, 1fr)); overflow-x:auto}
    .cards{max-height:none}
    input#q{width:140px}
  }
</style>
</head>
<body>
<header>
  <div class="brand"><span class="wolf">🐺</span> LEADHOUND</div>
  <div class="chips" id="chips"></div>
  <div class="spacer"></div>
  <input id="q" placeholder="search gigs…" oninput="S.q=this.value; render()">
  <button id="autoBtn" class="on" onclick="toggleAuto()" title="auto-refresh every 8s">⟳ auto</button>
  <button onclick="load()">↻ now</button>
</header>
<div class="hintbar" id="hintbar">loading…</div>
<div class="board" id="board"></div>
<div id="toasts"></div>

<script>
"use strict";
const COLS = [
  {key:"pending",  label:"🎯 Pending"},
  {key:"approved", label:"✅ Approved"},
  {key:"sent",     label:"📤 Sent"},
  {key:"rejected", label:"🗑 Rejected"},
];
const S = {jobs:[], cal:{}, q:"", auto:true, editing:null, draftVal:"", timer:null};

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
  setTimeout(() => t.remove(), 2600);
}

async function load(){
  try{
    const r = await fetch("/api/state");
    if(!r.ok) throw new Error("http " + r.status);
    const d = await r.json();
    S.jobs = d.jobs; S.cal = d.calibration || {};
    render();
  }catch(e){
    $("#hintbar").textContent = "⚠ could not reach the leadhound server — is it still running?";
  }
}

async function post(url, data, okMsg){
  try{
    const r = await fetch(url, {method:"POST",
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(data)});
    const d = await r.json().catch(() => ({}));
    if(!r.ok || d.ok === false){ toast(d.error || ("http " + r.status), true); return; }
    toast(okMsg || "saved ✓");
    await load();
  }catch(e){ toast("request failed", true); }
}

window.act = (id, status) => post("/api/status", {id, status}, "moved to " + status + " ✓");
window.setOutcome = (id, o) => {
  if(!o) return;
  post("/api/outcome", {id, outcome:o}, "outcome: " + o + (o === "won" ? " 🎉" : ""));
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
  $("#hintbar").innerHTML = h ? `🧠 scope calibration: <b>${esc(h)}</b>` : "🧠 mark outcomes (replied / won / lost) to calibrate the scope";
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
load();
</script>
</body>
</html>
"""
