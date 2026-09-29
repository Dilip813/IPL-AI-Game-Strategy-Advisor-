/* ─────────────────────────────────────────────────────────────────────────────
   IPL AI Game Strategy Advisor — Frontend Application Logic
   ───────────────────────────────────────────────────────────────────────────── */

const API = "http://localhost:5000/api";

// ── State ────────────────────────────────────────────────────────────────────
let state = {
  crOurTeam: "",
  crOpponent: "",
  crVenue: "",
  crSeason: "",
  crAnalysisResult: null,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);
const qsa = sel => document.querySelectorAll(sel);

function show(el) { if (el) el.style.display = ""; }
function hide(el) { if (el) el.style.display = "none"; }

function setHTML(id, html) {
  const el = $(id);
  if (el) el.innerHTML = html;
}

function spinner(msg = "Analysing…") {
  return `<div class="loading-overlay">
    <div class="spinner"></div>
    <span>${msg}</span>
  </div>`;
}

function emptyState(icon, title, desc) {
  return `<div class="empty-state">
    <div class="big-icon">${icon}</div>
    <div class="em">${title}</div>
    <p>${desc}</p>
  </div>`;
}

// ── API calls ─────────────────────────────────────────────────────────────────
async function apiFetch(path, method = "GET", body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "API error");
  return data;
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  await loadCricketTeams();
  await checkHealth();
  setupTabs();
  setupCricketScenarioChips();
  setupCricketEventListeners();
}

async function checkHealth() {
  try {
    const h = await apiFetch("/health");
    const statusEl = $("api-status");
    if (statusEl) {
      statusEl.textContent = h.watsonx_configured
        ? "IBM Granite connected"
        : "Rule-based engine (watsonx not configured)";
    }
  } catch {
    const statusEl = $("api-status");
    if (statusEl) statusEl.textContent = "Backend offline";
  }
}

// ── Tab system ────────────────────────────────────────────────────────────────
function setupTabs() {
  document.addEventListener("click", e => {
    const btn = e.target.closest(".tab-btn");
    if (!btn) return;
    const bar = btn.closest(".tab-bar");
    const panelContainer = bar?.nextElementSibling;
    if (!bar || !panelContainer) return;
    bar.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.tab;
    panelContainer.querySelectorAll(".tab-panel").forEach(p => {
      p.classList.toggle("active", p.id === target);
    });
  });
}

// =============================================================================
// IPL / CRICKET FRONTEND LOGIC
// =============================================================================

// ── Cricket provenance state ──────────────────────────────────────────────────
let cricketProvenance = null;

// ── Load cricket teams / venues / seasons ────────────────────────────────────
async function loadCricketTeams() {
  try {
    const data = await apiFetch("/cricket/teams");
    const teams   = data.teams   || [];
    const venues  = data.venues  || [];
    const seasons = data.seasons || [];
    cricketProvenance = data.provenance || null;

    // Update data badge in sidebar
    const badge = $("cr-data-badge");
    if (badge) {
      if (data.data_type === "REAL") {
        badge.innerHTML =
          `<span class="tag tag-green" style="font-size:11px">&#10003; Real IPL Data</span> ` +
          `<span class="tag tag-blue" style="font-size:10px">Cricsheet CC&nbsp;BY&nbsp;4.0</span>`;
      } else {
        badge.innerHTML = `<span class="tag tag-orange">Demo Data</span>`;
      }
    }

    // Update match/season info line
    const prov = data.provenance || {};
    const infoEl = $("cr-data-info");
    if (infoEl && prov.total_matches) {
      const seasons_arr = prov.seasons_covered || [];
      const oldest = seasons_arr[seasons_arr.length - 1] || "?";
      const newest = seasons_arr[0] || "?";
      infoEl.innerHTML =
        `${prov.total_matches.toLocaleString()} matches &middot; ` +
        `${seasons_arr.length} seasons (${oldest}&ndash;${newest}) &middot; ` +
        `${(prov.approx_bbb_deliveries || 0).toLocaleString()} deliveries`;
    }

    ["cr-our-team", "cr-opponent"].forEach(id => {
      const sel = $(id);
      if (!sel) return;
      sel.innerHTML = `<option value="">Select team…</option>` +
        teams.map(t => `<option value="${t}">${t}</option>`).join("");
    });

    const venueSel = $("cr-venue");
    if (venueSel) {
      venueSel.innerHTML = `<option value="">Any venue</option>` +
        venues.map(v => `<option value="${v}">${v}</option>`).join("");
    }

    const seasonSel = $("cr-season");
    if (seasonSel) {
      seasonSel.innerHTML = `<option value="">All seasons</option>` +
        seasons.map(s => `<option value="${s}">${s}</option>`).join("");
    }
  } catch (e) {
    console.error("Failed to load IPL teams:", e);
  }
}

// ── Cricket scenario chips ────────────────────────────────────────────────────
const CR_WHATIF_SCENARIOS = [
  "We lost 2 wickets in the powerplay",
  "Need 60 runs from 30 balls",
  "Opponent scored heavily in the powerplay",
  "We are defending a low total",
  "We are chasing a high total",
  "Key bowler is unavailable",
];

const CR_REALTIME_EVENTS = [
  "Opponent scored 68 in the powerplay",
  "We have lost 3 wickets in 5 overs",
  "Opponent hit back-to-back sixes",
  "New batter at the crease for opponent",
  "We need 80 from 10 overs",
  "Rain break — DLS target revised",
];

function setupCricketScenarioChips() {
  const wiContainer = $("cr-whatif-chips");
  if (wiContainer) {
    wiContainer.innerHTML = CR_WHATIF_SCENARIOS.map(s =>
      `<span class="chip" onclick="setCrWhatIfScenario('${s.replace(/'/g, "\\'")}')">${s}</span>`
    ).join("");
  }
  const rtContainer = $("cr-realtime-chips");
  if (rtContainer) {
    rtContainer.innerHTML = CR_REALTIME_EVENTS.map(s =>
      `<span class="chip" onclick="setCrRealtimeEvent('${s.replace(/'/g, "\\'")}')">${s}</span>`
    ).join("");
  }
}

function setCrWhatIfScenario(text) { const el = $("cr-whatif-input"); if (el) el.value = text; }
function setCrRealtimeEvent(text)  { const el = $("cr-realtime-input"); if (el) el.value = text; }

// ── Cricket event listeners ───────────────────────────────────────────────────
function setupCricketEventListeners() {
  const ourTeamSel = $("cr-our-team");
  const oppSel     = $("cr-opponent");
  const venueSel   = $("cr-venue");
  const seasonSel  = $("cr-season");

  if (ourTeamSel) ourTeamSel.addEventListener("change", e => {
    state.crOurTeam = e.target.value;
    setHTML("cr-our-name", state.crOurTeam || "—");
    updateCrAnalyzeBtn();
    resetCrAnalysis();
  });
  if (oppSel) oppSel.addEventListener("change", e => {
    state.crOpponent = e.target.value;
    setHTML("cr-opp-name", state.crOpponent || "—");
    updateCrAnalyzeBtn();
    resetCrAnalysis();
  });
  if (venueSel)  venueSel.addEventListener("change",  e => { state.crVenue  = e.target.value; });
  if (seasonSel) seasonSel.addEventListener("change", e => { state.crSeason = e.target.value; });

  const btnAnalyze  = $("btn-cr-analyze");
  const btnWhatif   = $("btn-cr-whatif");
  const btnRealtime = $("btn-cr-realtime");

  if (btnAnalyze)  btnAnalyze.addEventListener("click",  runCricketAnalysis);
  if (btnWhatif)   btnWhatif.addEventListener("click",   runCricketWhatIf);
  if (btnRealtime) btnRealtime.addEventListener("click", runCricketRealtime);
}

function updateCrAnalyzeBtn() {
  const can = state.crOurTeam && state.crOpponent && state.crOurTeam !== state.crOpponent;
  const btn = $("btn-cr-analyze");
  if (btn) btn.disabled = !can;
}

function resetCrAnalysis() {
  state.crAnalysisResult = null;
  const area = $("cr-dashboard-area");
  if (area) area.innerHTML = emptyState("🏏", "Select two IPL teams to begin",
    "Choose teams and click Run IPL Agent Analysis.");
}

// ── Cricket main analysis ─────────────────────────────────────────────────────
async function runCricketAnalysis() {
  if (!state.crOurTeam || !state.crOpponent) return;

  $("cr-dashboard-area").innerHTML = spinner("Running IPL 4-agent pipeline…");

  try {
    const result = await apiFetch("/cricket/analyze", "POST", {
      our_team: state.crOurTeam,
      opponent: state.crOpponent,
      venue:    state.crVenue  || "",
      season:   state.crSeason || "",
    });
    state.crAnalysisResult = result;
    renderCricketDashboard(result);
  } catch (e) {
    $("cr-dashboard-area").innerHTML =
      `<div class="disclaimer" style="margin:0">❌ Error: ${e.message}</div>`;
  }
}

// ── Cricket dashboard rendering ───────────────────────────────────────────────
function renderCricketDashboard(r) {
  const { match_analysis: ma, opponent_profile: op, recommendation: rec, insights: ins } = r;
  $("cr-dashboard-area").innerHTML = `
    ${renderCrVsHeader(r)}
    ${renderCrTabBar()}
    <div id="cr-tab-panels">
      <div class="tab-panel active" id="cr-tab-overview">
        ${renderCrOverviewTab(ma, op, rec, ins)}
      </div>
      <div class="tab-panel" id="cr-tab-analysis">
        ${renderCrAnalysisTab(ma, op)}
      </div>
      <div class="tab-panel" id="cr-tab-recommendations">
        ${renderCrRecommendationsTab(rec, ins)}
      </div>
      <div class="tab-panel" id="cr-tab-history">
        ${renderCrHistoryTab(ma)}
      </div>
    </div>
  `;
}

function renderCrTabBar() {
  return `<div class="tab-bar">
    <button class="tab-btn active" data-tab="cr-tab-overview">📊 Overview</button>
    <button class="tab-btn" data-tab="cr-tab-analysis">🔍 Opponent Analysis</button>
    <button class="tab-btn" data-tab="cr-tab-recommendations">♟️ Recommendations</button>
    <button class="tab-btn" data-tab="cr-tab-history">📋 Match History</button>
  </div>`;
}

function renderCrVsHeader(r) {
  const op  = r.opponent_profile;
  return `
    <div class="vs-header" style="background:rgba(210,153,34,0.08); border:1px solid rgba(210,153,34,0.2); border-radius:8px; margin-bottom:20px">
      <div class="vs-team">
        <div class="vs-team-name">${r.our_team}</div>
        <div class="vs-team-formation" style="color:var(--accent2)">
          ${r.match_analysis.our_stats.preferred_approach || "—"}
        </div>
        <div style="margin-top:4px">
          <span class="tag tag-blue">PP avg: ${r.match_analysis.our_stats.avg_powerplay_runs ?? "—"}</span>
        </div>
      </div>
      <div style="text-align:center">
        <div class="vs-divider">VS</div>
        <div style="font-size:11px; color:var(--muted); margin-top:4px">
          <span class="tag tag-orange">🏏 IPL</span>
        </div>
        <div style="font-size:11px; color:var(--muted)">
          ${r.venue !== "Any" ? r.venue.split(",")[0] : "Any venue"}
        </div>
      </div>
      <div class="vs-team">
        <div class="vs-team-name">${r.opponent}</div>
        <div class="vs-team-formation" style="color:var(--danger)">
          ${op.preferred_approach || "—"}
        </div>
        <div style="margin-top:4px">
          <span class="tag tag-red">PP: ${op.powerplay_profile || "—"}</span>
        </div>
      </div>
    </div>
  `;
}

// ── Cricket Overview Tab ──────────────────────────────────────────────────────
function renderCrOverviewTab(ma, op, rec, ins) {
  const ours  = ma.our_stats   || {};
  const opps  = ma.opponent_stats || {};
  const phase = ma.phase_analysis || {};
  const ourPh = phase.our_team  || {};
  const oppPh = phase.opponent  || {};

  return `
    <div class="dashboard-grid">
      ${renderCrTeamCard("Our Team", ma.our_team, ours, ourPh, "blue")}
      ${renderCrTeamCard("Opponent", ma.opponent, opps, oppPh, "red")}
    </div>
    ${renderCrPhaseBar("Our Team Phase Averages", ourPh, "blue")}
    ${renderCrPhaseBar("Opponent Phase Averages", oppPh, "red")}
    ${renderCrStrengthWeaknessRow(op)}
    ${renderCrKeyInsightsCard(ins)}
    <div style="font-size:11px; color:var(--muted); margin-top:4px">
      Source: Cricsheet (cricsheet.org) &middot; CC BY 4.0 &middot; ${cricketProvenance ? (cricketProvenance.total_matches||'').toLocaleString() + ' matches' : 'Real IPL data'}
    </div>
  `;
}

function renderCrTeamCard(label, teamName, stats, phase, colorClass) {
  const winRate = (stats.matches_played > 0)
    ? Math.round((stats.wins / stats.matches_played) * 100) : 0;
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          <span class="icon">${colorClass === "blue" ? "🔵" : "🔴"}</span>
          ${label}: ${teamName}
        </div>
      </div>
      <div class="card-body">
        <div class="stat-row">
          <span class="stat-label">Preferred Approach</span>
          <span class="stat-value"><span class="tag tag-${colorClass === "blue" ? "blue" : "red"}">${stats.preferred_approach || "—"}</span></span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Record (W/L)</span>
          <span class="stat-value">${stats.wins ?? "—"} / ${stats.losses ?? "—"}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Win Rate</span>
          <span class="stat-value">${winRate}%</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Avg First Innings</span>
          <span class="stat-value">${stats.avg_first_innings ?? "—"}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Avg Powerplay Runs</span>
          <span class="stat-value">${stats.avg_powerplay_runs ?? "—"}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Spin Reliance</span>
          <span class="stat-value">${stats.spin_reliance || "—"}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Home Wins / Losses</span>
          <span class="stat-value">${stats.home_wins ?? "—"} / ${stats.home_losses ?? "—"}</span>
        </div>
      </div>
    </div>
  `;
}

function renderCrPhaseBar(title, phase, colorClass) {
  if (!phase || (phase.avg_powerplay_runs == null && phase.avg_middle_overs_runs == null)) return "";
  return `
    <div class="card" style="margin-bottom:12px">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span>${title}</div>
      </div>
      <div class="card-body">
        <div class="phase-bar">
          <div class="phase-cell">
            <div class="phase-label">Powerplay</div>
            <div class="phase-val" style="color:var(--${colorClass === "blue" ? "accent" : "danger"})">${phase.avg_powerplay_runs ?? "—"}</div>
            <div class="phase-sub">avg runs (overs 1–6)</div>
          </div>
          <div class="phase-cell">
            <div class="phase-label">Middle Overs</div>
            <div class="phase-val" style="color:var(--warning)">${phase.avg_middle_overs_runs ?? "—"}</div>
            <div class="phase-sub">avg runs (overs 7–15)</div>
          </div>
          <div class="phase-cell">
            <div class="phase-label">Death Overs</div>
            <div class="phase-val" style="color:var(--accent2)">${phase.avg_death_overs_runs ?? "—"}</div>
            <div class="phase-sub">avg runs (overs 16–20)</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderCrStrengthWeaknessRow(op) {
  return `
    <div class="dashboard-grid" style="margin-bottom:12px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">✅</span>Opponent Strengths</div>
        </div>
        <div class="card-body">
          ${(op.strengths || []).map(s => `<div class="stat-row"><span>${s}</span></div>`).join("")
            || "<span style='color:var(--muted)'>No data</span>"}
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">⚠️</span>Opponent Weaknesses</div>
        </div>
        <div class="card-body">
          ${(op.weaknesses || []).map(s => `<div class="stat-row"><span>${s}</span></div>`).join("")
            || "<span style='color:var(--muted)'>No data</span>"}
        </div>
      </div>
    </div>
  `;
}

function renderCrKeyInsightsCard(ins) {
  return `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title">
          <span class="icon">💡</span>AI Key Insights
          <span class="agent-badge">${ins.insight_source || "AI Engine"}</span>
        </div>
      </div>
      <div class="card-body">
        <div style="background:rgba(210,153,34,0.07); border-left:3px solid var(--warning);
                    padding:10px 14px; border-radius:4px; font-size:13px; margin-bottom:14px; line-height:1.6">
          ${ins.summary || ""}
        </div>
        ${(ins.key_insights || []).map((txt, i) => `
          <div class="insight-item">
            <div class="insight-num" style="background:var(--warning)">${i+1}</div>
            <div class="insight-text">${txt}</div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

// ── Cricket Analysis Tab ──────────────────────────────────────────────────────
function renderCrAnalysisTab(ma, op) {
  const vulns    = op.tactical_vulnerabilities || [];
  const patterns = op.all_tactical_patterns    || [];
  const bf       = op.batting_first || {};
  const ch       = op.chasing       || {};
  const h2h      = ma.h2h_record    || {};

  return `
    <div class="dashboard-grid" style="margin-bottom:16px">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🏏</span>Batting First vs Chasing</div>
          <span class="agent-badge">Opponent Strategy Agent</span>
        </div>
        <div class="card-body">
          <div class="stat-row">
            <span class="stat-label">Batting First (M/W)</span>
            <span class="stat-value">${bf.matches ?? "—"} / ${bf.wins ?? "—"}
              ${bf.win_rate != null ? `<span class="tag tag-green">${bf.win_rate}%</span>` : ""}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Chasing (M/W)</span>
            <span class="stat-value">${ch.matches ?? "—"} / ${ch.wins ?? "—"}
              ${ch.win_rate != null ? `<span class="tag tag-blue">${ch.win_rate}%</span>` : ""}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Powerplay Profile</span>
            <span class="stat-value"><span class="tag tag-orange">${op.powerplay_profile || "—"}</span></span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Avg Powerplay Runs</span>
            <span class="stat-value">${op.avg_powerplay_runs ?? "—"}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Avg Middle Overs</span>
            <span class="stat-value">${op.avg_middle_overs_runs ?? "—"}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Avg Death Overs</span>
            <span class="stat-value">${op.avg_death_overs_runs ?? "—"}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">Spin Reliance</span>
            <span class="stat-value">${op.spin_reliance || "—"}</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">⚔️</span>Head-to-Head Record</div>
        </div>
        <div class="card-body">
          ${Object.keys(h2h).length === 0
            ? "<span style='color:var(--muted)'>No head-to-head data for this pairing.</span>"
            : Object.entries(h2h).map(([k, v]) =>
                `<div class="stat-row">
                  <span class="stat-label">${k.replace(/_/g," ")}</span>
                  <span class="stat-value">${v}</span>
                </div>`
              ).join("")}
          <div class="stat-row" style="margin-top:8px">
            <span class="stat-label">H2H Matches in Dataset</span>
            <span class="stat-value">${ma.h2h_match_count}</span>
          </div>
        </div>
      </div>
    </div>

    ${vulns.length > 0 ? `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">🎯</span>Tactical Vulnerabilities</div>
        <span class="agent-badge">IPL Opponent Strategy Agent</span>
      </div>
      <div class="card-body">
        ${vulns.map(v => `
          <div style="margin-bottom:16px; padding-bottom:16px; border-bottom:1px solid var(--border)">
            <div style="font-weight:600; margin-bottom:4px; color:var(--warning)">${v.pattern}</div>
            <div style="font-size:12px; color:var(--muted); margin-bottom:6px">${v.evidence}</div>
            <div style="font-size:13px; color:var(--accent2)">▶ ${v.how_to_exploit}</div>
          </div>
        `).join("")}
      </div>
    </div>` : ""}

    ${patterns.length > 0 ? `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">📌</span>Retrieved IPL Tactical Patterns (RAG)</div>
        <span class="agent-badge">IPL RAG Pipeline</span>
      </div>
      <div class="card-body">
        ${patterns.map(p => `
          <div style="margin-bottom:14px; padding-bottom:14px; border-bottom:1px solid var(--border)">
            <div style="font-weight:600; margin-bottom:3px">${p.pattern}</div>
            <div style="font-size:12px; color:var(--muted); margin-bottom:5px">${p.description}</div>
            <span class="tag tag-green">How to exploit:</span>
            <span style="font-size:12px"> ${p.exploiting_approach}</span>
          </div>
        `).join("")}
      </div>
    </div>` : ""}
  `;
}

// ── Cricket Recommendations Tab ───────────────────────────────────────────────
function renderCrRecommendationsTab(rec, ins) {
  const bowling = rec.bowling || {};
  const batting = rec.batting || {};
  return `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">♟️</span>Match Situation Strategy</div>
        <span class="agent-badge">IPL Strategy Recommendation Agent</span>
      </div>
      <div class="card-body">
        <div class="adjustment-box" style="border-color:rgba(210,153,34,0.3); background:rgba(210,153,34,0.05)">
          ${rec.toss_advice || ""}
        </div>
        <div style="font-size:13px; line-height:1.6">${rec.match_situation_strategy || ""}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">🎳</span>Bowling Strategy by Phase</div>
      </div>
      <div class="card-body">
        <div style="margin-bottom:14px">
          <div class="section-heading">Powerplay (Overs 1–6)</div>
          <div style="font-size:13px; line-height:1.6">${bowling.powerplay || "—"}</div>
        </div>
        <div style="margin-bottom:14px">
          <div class="section-heading">Middle Overs (7–15)</div>
          <div style="font-size:13px; line-height:1.6">${bowling.middle_overs || "—"}</div>
        </div>
        <div>
          <div class="section-heading">Death Overs (16–20)</div>
          <div style="font-size:13px; line-height:1.6">${bowling.death_overs || "—"}</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">🏏</span>Batting Strategy by Phase</div>
      </div>
      <div class="card-body">
        <div style="margin-bottom:14px">
          <div class="section-heading">Powerplay (Overs 1–6)</div>
          <div style="font-size:13px; line-height:1.6">${batting.powerplay || "—"}</div>
        </div>
        <div style="margin-bottom:14px">
          <div class="section-heading">Middle Overs (7–15)</div>
          <div style="font-size:13px; line-height:1.6">${batting.middle_overs || "—"}</div>
        </div>
        <div>
          <div class="section-heading">Death Overs (16–20)</div>
          <div style="font-size:13px; line-height:1.6">${batting.death_overs || "—"}</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">🏟️</span>Fielding Suggestions</div>
      </div>
      <div class="card-body">
        ${(rec.fielding_suggestions || []).map((f, i) => `
          <div class="insight-item">
            <div class="insight-num" style="background:var(--accent2)">${i+1}</div>
            <div class="insight-text">${f}</div>
          </div>
        `).join("") || "<span style='color:var(--muted)'>No suggestions</span>"}
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">🔧</span>Key Tactical Adjustments</div>
      </div>
      <div class="card-body">
        ${(rec.key_adjustments || []).map((adj, i) => `
          <div style="margin-bottom:14px; padding-bottom:14px; border-bottom:1px solid var(--border)">
            <div style="font-weight:600; color:var(--warning); margin-bottom:3px">${i+1}. ${adj.area}</div>
            <div style="font-size:13px; margin-bottom:4px">${adj.instruction}</div>
            <div style="font-size:11px; color:var(--muted)">Evidence: ${adj.evidence}</div>
          </div>
        `).join("")}
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title"><span class="icon">📄</span>Historical Evidence Used</div>
        <span class="agent-badge">IPL RAG Retrieval</span>
      </div>
      <div class="card-body">
        ${(rec.evidence_matches || []).map(e => `<div class="evidence-item">${e}</div>`).join("")}
      </div>
    </div>
  `;
}

// ── Cricket History Tab ───────────────────────────────────────────────────────
function renderCrHistoryTab(ma) {
  const matches = ma.match_summary || [];
  return `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title">
          <span class="icon">📋</span>Retrieved IPL Matches
          <span style="color:var(--muted); font-weight:400">
            (${ma.retrieved_match_count} matches, ${ma.h2h_match_count} H2H)
          </span>
        </div>
        <span class="agent-badge">IPL Match Analysis Agent</span>
      </div>
      <div class="card-body" style="padding:0; overflow-x:auto">
        <table class="match-table">
          <thead><tr>
            <th>Date</th><th>Team 1</th><th>Score 1</th>
            <th>Team 2</th><th>Score 2</th><th>Winner</th><th>PP Runs</th>
          </tr></thead>
          <tbody>
            ${matches.map(m => `
              <tr>
                <td style="color:var(--muted)">${m.match_date || m.season || "—"}</td>
                <td style="font-weight:${m.team1 === ma.our_team ? "700" : "400"};
                           color:${m.team1 === ma.our_team ? "var(--accent)" : "var(--text)"}">
                  ${m.team1}
                </td>
                <td><span class="score-badge">${m.first_innings_runs ?? "—"}/${m.first_innings_wickets ?? "—"}</span></td>
                <td style="font-weight:${m.team2 === ma.our_team ? "700" : "400"};
                           color:${m.team2 === ma.our_team ? "var(--accent)" : "var(--text)"}">
                  ${m.team2}
                </td>
                <td><span class="score-badge" style="color:var(--warning)">${m.second_innings_runs ?? "—"}/${m.second_innings_wickets ?? "—"}</span></td>
                <td style="color:var(--accent2); font-weight:600">${m.winner || "—"}</td>
                <td style="color:var(--muted)">${m.powerplay_runs_batting ?? "—"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📝</span>Match Notes</div>
      </div>
      <div class="card-body">
        ${matches.map(m => `
          <div style="margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid var(--border)">
            <div style="font-size:12px; font-weight:600; color:var(--muted); margin-bottom:3px">
              ${m.team1} vs ${m.team2}
              <span class="score-badge" style="margin:0 6px">${m.first_innings_runs}/${m.first_innings_wickets}</span>
              vs
              <span class="score-badge" style="color:var(--warning); margin:0 6px">${m.second_innings_runs}/${m.second_innings_wickets}</span>
              <span style="color:var(--border)">|</span>
              <span style="color:var(--accent2); margin-left:6px">${m.winner || ""}</span>
            </div>
            <div style="font-size:13px; line-height:1.5">${m.notes || ""}</div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

// ── Cricket What-If ───────────────────────────────────────────────────────────
async function runCricketWhatIf() {
  const scenario = $("cr-whatif-input")?.value?.trim();
  if (!scenario) return;
  if (!state.crOurTeam || !state.crOpponent) {
    $("cr-whatif-result").innerHTML = `<div class="disclaimer">Please select teams first.</div>`;
    return;
  }
  $("cr-whatif-result").innerHTML = spinner("Simulating cricket scenario…");
  try {
    const result = await apiFetch("/cricket/what-if", "POST", {
      scenario,
      our_team: state.crOurTeam,
      opponent: state.crOpponent,
    });
    renderCrWhatIfResult(result);
  } catch (e) {
    $("cr-whatif-result").innerHTML = `<div class="disclaimer">❌ ${e.message}</div>`;
  }
}

function renderCrWhatIfResult(r) {
  const evidence = r.supporting_evidence || [];
  $("cr-whatif-result").innerHTML = `
    <div style="margin-bottom:10px">
      <span class="tag tag-orange">Scenario: ${r.scenario_type}</span>
      <span class="tag tag-blue" style="margin-left:6px">🏏 Cricket</span>
    </div>
    <div class="adjustment-box" style="border-color:rgba(210,153,34,0.3); background:rgba(210,153,34,0.05)">
      ${r.tactical_adjustment}
    </div>
    ${r.granite_enrichment ? `
      <div style="margin-bottom:10px">
        <div class="section-heading">IBM Granite Enrichment</div>
        <div class="adjustment-box" style="border-color:rgba(163,113,247,0.3); background:rgba(163,113,247,0.05)">
          ${r.granite_enrichment}
        </div>
      </div>` : ""}
    ${evidence.length > 0 ? `
      <div>
        <div class="section-heading">Supporting Evidence (IPL RAG)</div>
        ${evidence.map(e => `<div class="evidence-item">${e}</div>`).join("")}
      </div>` : ""}
    <div style="margin-top:10px; font-size:11px; color:var(--muted)">
      Source: Cricsheet (cricsheet.org) &middot; CC BY 4.0
    </div>
  `;
}

// ── Cricket Real-time ─────────────────────────────────────────────────────────
async function runCricketRealtime() {
  const event = $("cr-realtime-input")?.value?.trim();
  if (!event) return;
  if (!state.crOurTeam || !state.crOpponent) {
    $("cr-realtime-result").innerHTML = `<div class="disclaimer">Please select teams first.</div>`;
    return;
  }
  $("cr-realtime-result").innerHTML = spinner("Generating cricket adjustment…");
  try {
    const result = await apiFetch("/cricket/realtime", "POST", {
      event,
      our_team: state.crOurTeam,
      opponent: state.crOpponent,
    });
    renderCrRealtimeResult(result);
  } catch (e) {
    $("cr-realtime-result").innerHTML = `<div class="disclaimer">❌ ${e.message}</div>`;
  }
}

function renderCrRealtimeResult(r) {
  const evidence = r.supporting_evidence || [];
  $("cr-realtime-result").innerHTML = `
    <div style="margin-bottom:10px">
      <span class="tag tag-blue">Live Cricket Event</span>
      <span style="font-size:12px; color:var(--muted); margin-left:8px">"${r.event}"</span>
    </div>
    <div class="adjustment-box" style="border-color:rgba(210,153,34,0.3); background:rgba(210,153,34,0.05)">
      ${r.immediate_adjustment}
    </div>
    ${r.granite_enrichment ? `
      <div style="margin-bottom:10px">
        <div class="section-heading">IBM Granite Enrichment</div>
        <div class="adjustment-box" style="border-color:rgba(163,113,247,0.3); background:rgba(163,113,247,0.05)">
          ${r.granite_enrichment}
        </div>
      </div>` : ""}
    ${evidence.length > 0 ? `
      <div>
        <div class="section-heading">Supporting Evidence</div>
        ${evidence.map(e => `<div class="evidence-item">${e}</div>`).join("")}
      </div>` : ""}
    <div style="margin-top:10px; font-size:11px; color:var(--muted)">Source: Cricsheet &middot; CC BY 4.0</div>
  `;
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
