"""
Cricket / IPL Multi-Agent System — IPL AI Game Strategy Advisor

Agents:
  1. IPLMatchAnalysisAgent       — historical IPL match retrieval & analysis
  2. IPLOpponentStrategyAgent    — opponent batting/bowling/phase profiling
  3. IPLStrategyRecommendationAgent — full cricket tactical game plan
  4. IPLInsightExplanationAgent  — plain coaching language (Granite or rule-based)

Additional engines:
  CricketWhatIfEngine      — scenario-based tactical adjustments
  CricketRealtimeEngine    — live event tactical responses
"""

from __future__ import annotations

import os
import re
from typing import Any

import rag


# ── Optional IBM watsonx.ai / Granite integration ────────────────────────────
WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY", "")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
_WATSONX_AVAILABLE = bool(WATSONX_API_KEY and WATSONX_PROJECT_ID)

_llm = None
if _WATSONX_AVAILABLE:
    try:
        from ibm_watsonx_ai.foundation_models import ModelInference
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

        _llm = ModelInference(
            model_id="ibm/granite-13b-chat-v2",
            credentials={"apikey": WATSONX_API_KEY, "url": WATSONX_URL},
            project_id=WATSONX_PROJECT_ID,
            params={
                GenParams.MAX_NEW_TOKENS: 512,
                GenParams.TEMPERATURE: 0.3,
                GenParams.REPETITION_PENALTY: 1.1,
            },
        )
    except Exception as e:
        print(f"[watsonx] Could not initialise model: {e}")
        _llm = None


def _call_llm(prompt: str) -> str | None:
    """Call IBM Granite via watsonx.ai; return None if unavailable."""
    if _llm is None:
        return None
    try:
        response = _llm.generate_text(prompt=prompt)
        return response.strip() if response else None
    except Exception as e:
        print(f"[watsonx] inference error: {e}")
        return None


# =============================================================================
# AGENT 1 — IPL Match Analysis Agent
# =============================================================================

class IPLMatchAnalysisAgent:
    """
    Retrieves relevant IPL historical matches and aggregates batting, bowling,
    powerplay/middle/death phase statistics, toss patterns, venue patterns,
    and head-to-head records.
    """
    name = "IPL Match Analysis Agent"

    def run(self, our_team: str, opponent: str,
            venue: str = "", season: str = "") -> dict[str, Any]:

        # ── RAG retrieval ────────────────────────────────────────────────────
        matches = rag.retrieve_ipl_matches(our_team, opponent, venue, season, top_k=8)
        our_stats   = rag.get_ipl_team_stats(our_team)   or {}
        opp_stats   = rag.get_ipl_team_stats(opponent)   or {}
        h2h         = rag.get_ipl_h2h(our_team, opponent)
        data_notice = rag.get_ipl_data_notice()
        provenance  = rag.get_ipl_provenance()

        # ── Matches involving each team ──────────────────────────────────────
        our_matches = [m for m in matches if our_team  in (m["team1"], m["team2"])]
        opp_matches = [m for m in matches if opponent  in (m["team1"], m["team2"])]
        h2h_matches = [m for m in matches
                       if {our_team, opponent} == {m["team1"], m["team2"]}]

        # ── Aggregate phase stats for opponent (batting first) ───────────────
        def _phase_avg(ms, team, phase_key_pfx):
            vals = []
            for m in ms:
                is_bat_first = m.get("batting_first") == team
                pfx = "batting" if is_bat_first else "chasing"
                v = m.get(f"{phase_key_pfx}_{pfx}")
                if v is not None:
                    vals.append(v)
            return round(sum(vals) / len(vals), 1) if vals else None

        opp_pp_runs  = _phase_avg(opp_matches, opponent, "powerplay_runs")
        opp_pp_wkts  = _phase_avg(opp_matches, opponent, "powerplay_wickets")
        opp_mo_runs  = _phase_avg(opp_matches, opponent, "middle_overs_runs")
        opp_do_runs  = _phase_avg(opp_matches, opponent, "death_overs_runs")

        our_pp_runs  = _phase_avg(our_matches, our_team,  "powerplay_runs")
        our_mo_runs  = _phase_avg(our_matches, our_team,  "middle_overs_runs")
        our_do_runs  = _phase_avg(our_matches, our_team,  "death_overs_runs")

        # ── Toss analysis ────────────────────────────────────────────────────
        toss_won_bat  = sum(1 for m in opp_matches
                           if m.get("toss_winner") == opponent
                           and m.get("toss_decision") == "bat")
        toss_won_field = sum(1 for m in opp_matches
                            if m.get("toss_winner") == opponent
                            and m.get("toss_decision") == "field")

        # ── Venue analysis ───────────────────────────────────────────────────
        venue_matches = [m for m in matches if venue and m.get("venue") == venue] if venue else []

        # ── Match summary ────────────────────────────────────────────────────
        match_summary = []
        for m in matches:
            match_summary.append({
                "id":           m["id"],
                "season":       m.get("season"),
                "match_date":   m.get("match_date"),
                "venue":        m.get("venue"),
                "team1":        m["team1"],
                "team2":        m["team2"],
                "toss_winner":  m.get("toss_winner"),
                "toss_decision":m.get("toss_decision"),
                "winner":       m.get("winner"),
                "result":       m.get("result"),
                "batting_first":m.get("batting_first"),
                "first_innings_runs":   m.get("first_innings_runs"),
                "first_innings_wickets":m.get("first_innings_wickets"),
                "second_innings_runs":  m.get("second_innings_runs"),
                "second_innings_wickets":m.get("second_innings_wickets"),
                "powerplay_runs_batting": m.get("powerplay_runs_batting"),
                "powerplay_wickets_batting": m.get("powerplay_wickets_batting"),
                "notes":        m.get("notes"),
            })

        # ── Enrich phase stats from team-level real data if match sample small ─
        def _enrich(val, stats_key):
            """Use per-match avg if available, else fall back to team-level stats."""
            return val if val is not None else our_stats.get(stats_key)

        return {
            "agent": self.name,
            "our_team": our_team,
            "opponent": opponent,
            "venue":    venue or "Any",
            "season":   season or "All seasons",
            "retrieved_match_count": len(matches),
            "h2h_match_count": len(h2h_matches),
            "h2h_record": h2h,
            "match_summary": match_summary,
            "our_stats": our_stats,
            "opponent_stats": opp_stats,
            "phase_analysis": {
                "opponent": {
                    # Use per-match averages from retrieved sample; fall back to
                    # team-level pre-computed stats from the full real dataset
                    "avg_powerplay_runs":    opp_pp_runs  if opp_pp_runs  is not None
                                             else opp_stats.get("avg_powerplay_runs"),
                    "avg_powerplay_wickets": opp_pp_wkts  if opp_pp_wkts  is not None
                                             else opp_stats.get("avg_powerplay_wickets"),
                    "avg_middle_overs_runs": opp_mo_runs  if opp_mo_runs  is not None
                                             else opp_stats.get("avg_middle_overs_runs"),
                    "avg_death_overs_runs":  opp_do_runs  if opp_do_runs  is not None
                                             else opp_stats.get("avg_death_overs_runs"),
                },
                "our_team": {
                    "avg_powerplay_runs":    our_pp_runs  if our_pp_runs  is not None
                                             else our_stats.get("avg_powerplay_runs"),
                    "avg_middle_overs_runs": our_mo_runs  if our_mo_runs  is not None
                                             else our_stats.get("avg_middle_overs_runs"),
                    "avg_death_overs_runs":  our_do_runs  if our_do_runs  is not None
                                             else our_stats.get("avg_death_overs_runs"),
                },
            },
            "toss_analysis": {
                "opp_toss_won_batted":   toss_won_bat,
                "opp_toss_won_fielded":  toss_won_field,
                "total_toss_wins":       toss_won_bat + toss_won_field,
            },
            "venue_matches": len(venue_matches),
            "retrieved_matches_raw": matches,
            "data_notice": data_notice,
            "provenance":  provenance,
            "data_type":   provenance.get("data_type", "REAL"),
        }


# =============================================================================
# AGENT 2 — IPL Opponent Strategy Agent
# =============================================================================

class IPLOpponentStrategyAgent:
    """
    Builds a detailed cricket tactical profile of the opponent based on
    retrieved IPL data. Identifies batting/bowling phase tendencies,
    chasing/defending patterns, key player patterns, and tactical weaknesses.
    """
    name = "IPL Opponent Strategy Agent"

    def run(self, match_analysis: dict[str, Any]) -> dict[str, Any]:
        opponent    = match_analysis["opponent"]
        opp_stats   = match_analysis["opponent_stats"]
        opp_matches = match_analysis["retrieved_matches_raw"]
        phase       = match_analysis["phase_analysis"]["opponent"]

        # ── Retrieve patterns for opponent ───────────────────────────────────
        tactical_patterns = rag.retrieve_ipl_patterns_for_team(opponent)

        # ── Batting-first vs chasing tendencies ──────────────────────────────
        bat_first_wins  = 0
        bat_first_total = 0
        chase_wins      = 0
        chase_total     = 0

        for m in opp_matches:
            if m.get("batting_first") == opponent:
                bat_first_total += 1
                if m.get("winner") == opponent:
                    bat_first_wins += 1
            elif m.get("chasing_team") == opponent:
                chase_total += 1
                if m.get("winner") == opponent:
                    chase_wins += 1

        # ── Home venue (from real data stats) ────────────────────────────────
        home_venue  = opp_stats.get("home_venue", None)

        # ── Powerplay category ───────────────────────────────────────────────
        avg_pp = phase.get("avg_powerplay_runs")
        if avg_pp is not None:
            if avg_pp >= 60:
                pp_profile = "explosive"
            elif avg_pp >= 50:
                pp_profile = "aggressive"
            elif avg_pp >= 40:
                pp_profile = "moderate"
            else:
                pp_profile = "conservative"
        else:
            pp_profile = "unknown"

        # ── Enrich weaknesses with pattern evidence ──────────────────────────
        pattern_vulnerabilities = []
        for p in tactical_patterns:
            pattern_vulnerabilities.append({
                "pattern": p["pattern"],
                "evidence": p["description"],
                "how_to_exploit": p.get("exploiting_approach", ""),
            })

        # ── Top performers from real data (new schema) ───────────────────────
        batters: dict[str, dict] = {}
        bowlers: dict[str, dict] = {}
        for m in opp_matches:
            tp = m.get("top_performers", {})
            # Real data schema: top_performers is a dict with inn1/inn2 keys
            if isinstance(tp, dict):
                batting_team = m.get("batting_first") == opponent
                batter_list  = tp.get("innings1_batters" if batting_team else "innings2_batters", [])
                bowler_list  = tp.get("innings2_bowlers" if batting_team else "innings1_bowlers", [])
                for p in batter_list:
                    n = p.get("name", "")
                    if n:
                        if n not in batters:
                            batters[n] = {"runs": 0, "innings": 0}
                        batters[n]["runs"] += p.get("runs", 0)
                        batters[n]["innings"] += 1
                for p in bowler_list:
                    n = p.get("name", "")
                    if n:
                        if n not in bowlers:
                            bowlers[n] = {"wickets": 0, "balls": 0, "runs": 0}
                        bowlers[n]["wickets"] += p.get("wkts", 0)
                        bowlers[n]["balls"]   += p.get("balls", 0)
                        bowlers[n]["runs"]    += p.get("runs", 0)

        # ── Use pre-computed stats from real data where available ─────────────
        bf_total = opp_stats.get("batting_first_matches", bat_first_total)
        bf_wins  = opp_stats.get("batting_first_wins", bat_first_wins)
        bf_wr    = opp_stats.get("batting_first_win_pct",
                                  round(bat_first_wins / bat_first_total * 100, 0)
                                  if bat_first_total else None)
        ch_total = opp_stats.get("chasing_matches", chase_total)
        ch_wins  = opp_stats.get("chasing_wins", chase_wins)
        ch_wr    = opp_stats.get("chasing_win_pct",
                                  round(chase_wins / chase_total * 100, 0)
                                  if chase_total else None)

        return {
            "agent": self.name,
            "opponent": opponent,
            "preferred_approach": opp_stats.get("preferred_approach", "unknown"),
            "spin_reliance":      opp_stats.get("spin_reliance") or "unknown",
            "powerplay_profile":  pp_profile,
            "avg_powerplay_runs": avg_pp,
            "avg_powerplay_wickets": phase.get("avg_powerplay_wickets"),
            "avg_middle_overs_runs": phase.get("avg_middle_overs_runs"),
            "avg_death_overs_runs":  phase.get("avg_death_overs_runs"),
            "batting_first": {
                "matches":  bf_total,
                "wins":     bf_wins,
                "win_rate": bf_wr,
            },
            "chasing": {
                "matches":  ch_total,
                "wins":     ch_wins,
                "win_rate": ch_wr,
            },
            "home_venue": home_venue,
            "strengths":    opp_stats.get("strengths", []),
            "weaknesses":   opp_stats.get("weaknesses", []),
            "tactical_vulnerabilities": pattern_vulnerabilities,
            "all_tactical_patterns": tactical_patterns,
            "key_batters":  batters,
            "key_bowlers":  bowlers,
        }


# =============================================================================
# AGENT 3 — IPL Strategy Recommendation Agent
# =============================================================================

class IPLStrategyRecommendationAgent:
    """
    Combines match analysis and opponent profile to produce a complete IPL
    tactical game plan — batting, bowling, fielding, phase-by-phase strategy.
    Every recommendation cites historical evidence.
    """
    name = "IPL Strategy Recommendation Agent"

    def run(self, our_team: str, match_analysis: dict,
            opponent_profile: dict) -> dict[str, Any]:

        opp             = opponent_profile["opponent"]
        opp_approach    = opponent_profile["preferred_approach"]
        opp_pp_profile  = opponent_profile["powerplay_profile"]
        opp_pp_runs     = opponent_profile["avg_powerplay_runs"]
        opp_pp_wkts     = opponent_profile["avg_powerplay_wickets"]
        opp_mo_runs     = opponent_profile["avg_middle_overs_runs"]
        opp_do_runs     = opponent_profile["avg_death_overs_runs"]
        opp_spin        = opponent_profile["spin_reliance"]
        bf_record       = opponent_profile["batting_first"]
        ch_record       = opponent_profile["chasing"]
        our_stats       = match_analysis["our_stats"]
        our_pp_runs     = match_analysis["phase_analysis"]["our_team"]["avg_powerplay_runs"]
        vulnerabilities = opponent_profile["tactical_vulnerabilities"]

        # ── Toss / match situation advice ────────────────────────────────────
        if opp_approach == "bat first":
            toss_advice = (
                f"{opp} prefers to bat first. If you win the toss, consider fielding first "
                f"to disrupt their preferred pattern and put them under unfamiliar chase pressure."
            )
        elif opp_approach == "chase":
            toss_advice = (
                f"{opp} prefers to chase. If you win the toss, consider batting first to "
                f"set a target and make them play against their preferred style."
            )
        else:
            toss_advice = (
                f"{opp} is versatile. Decide based on pitch conditions and your team's stronger phase."
            )

        # ── Powerplay bowling plan ───────────────────────────────────────────
        if opp_pp_profile in ("explosive", "aggressive"):
            pp_bowling = (
                f"{opp} averages ~{opp_pp_runs} runs in the powerplay ({opp_pp_profile}). "
                "Bowl attacking lines to create early wickets — off-stump channel at pace "
                "to induce drives, with a deep cover and deep point boundary protection. "
                "One short-pitch delivery per over to disrupt rhythm. "
                "Historical evidence: teams removing the top order early (2+ wickets by over 6) "
                "have significantly reduced the final total."
            )
        else:
            pp_bowling = (
                f"{opp} is moderate/conservative in the powerplay (~{opp_pp_runs} runs). "
                "Apply pressure without attacking field — two slips for edges, "
                "bowl at the crease to restrict boundaries. "
                "Avoid expensive wides or no-balls that release pressure."
            )

        # ── Powerplay batting plan ───────────────────────────────────────────
        our_pp = our_stats.get("avg_powerplay_runs")
        if our_pp and our_pp >= 55:
            pp_batting = (
                f"Your team averages {our_pp} powerplay runs — a genuine strength. "
                "Back your openers to be aggressive from ball one. "
                "Target pace outside off-stump to drive through the covers. "
                "Aim for 55+ with maximum 1 wicket by over 6."
            )
        else:
            pp_batting = (
                "Build steadily in the powerplay. Rotate strike and pick boundaries selectively. "
                "Target short-pitched deliveries from pace and any spin introduced early. "
                "Aim for 45+ runs with wickets in hand to accelerate from over 7."
            )

        # ── Middle overs plan ────────────────────────────────────────────────
        if opp_spin == "high":
            mo_bowling = (
                f"{opp} relies on spin and performs well in the middle overs (~{opp_mo_runs} runs). "
                "Use pace variation and cutters in overs 8–15. "
                "Avoid slow bowlers who may play into their strength. "
                "Field attacking — mid-on, mid-off up to save the single."
            )
        else:
            mo_bowling = (
                f"{opp} scores ~{opp_mo_runs or '?'} in middle overs. "
                "Use your best spinner in this phase to build dot-ball pressure. "
                "Economy under 7 RPO in this phase is the target. "
                "Two fielders on the boundary, attack with one spinning option."
            )

        mo_batting = (
            "Middle overs (7–15): rotate strike and build a platform. "
            "Do not sacrifice wickets for boundaries — the death overs are where acceleration happens. "
            "Target any change bowlers introduced in overs 11–14."
        )

        # ── Death overs plan ─────────────────────────────────────────────────
        if opp_do_runs and opp_do_runs >= 50:
            do_bowling = (
                f"{opp} is dangerous in the death overs (~{opp_do_runs} runs). "
                "Bowl yorkers consistently — no full-toss, no short-pitch. "
                "Use your best death-over specialist in overs 17–20. "
                "One pace change (slower ball) per over. "
                "Historical data shows 4+ wicket losses in this phase derail chases."
            )
        else:
            do_bowling = (
                f"{opp} scores ~{opp_do_runs or '?'} in the death. "
                "Maintain yorkers on off-stump. "
                "Save your best bowler for overs 18–20 to clean up the tail."
            )

        do_batting = (
            "Death overs (16–20): ensure at least 3 wickets in hand at over 16. "
            "Target loose deliveries — full-toss and half-volleys — for maximums. "
            "Use your best power-hitters in the top 5 so they are available for these overs."
        )

        # ── Batting first vs chasing strategy ───────────────────────────────
        bf_win_rt = bf_record.get("win_rate")
        ch_win_rt = ch_record.get("win_rate")
        if bf_win_rt is not None and ch_win_rt is not None:
            if bf_win_rt > ch_win_rt:
                match_situation = (
                    f"{opp} wins {bf_win_rt}% when batting first vs {ch_win_rt}% when chasing. "
                    "They are significantly stronger when setting a target. Force them to chase."
                )
            else:
                match_situation = (
                    f"{opp} wins {ch_win_rt}% when chasing vs {bf_win_rt}% when batting first. "
                    "They are a strong chasing side. Set them a large target (185+) to overwhelm them."
                )
        else:
            match_situation = (
                "Insufficient data to determine a preference. "
                "Apply your team's stronger phase strategy regardless."
            )

        # ── Fielding suggestions ─────────────────────────────────────────────
        fielding = []
        if opp_pp_profile in ("explosive", "aggressive"):
            fielding.append(
                "Powerplay: deep cover + deep point boundary riders to cut off the drives. "
                "Two slips for edge catches early."
            )
        else:
            fielding.append(
                "Powerplay: two slips, point, cover — attack field to create pressure."
            )
        if opp_spin == "high":
            fielding.append(
                "Middle overs: deep square leg + long on when spin is bowling. "
                "Attack with mid-off/mid-on up to build dot-ball pressure."
            )
        if opp_do_runs and opp_do_runs >= 50:
            fielding.append(
                "Death overs: all boundary fielders deployed. "
                "One catcher at deep mid-wicket for attempted maximums."
            )

        # ── Key tactical adjustments ─────────────────────────────────────────
        adjustments = []
        for v in vulnerabilities:
            adjustments.append({
                "area":        v["pattern"],
                "instruction": v["how_to_exploit"],
                "evidence":    v["evidence"],
            })
        if not adjustments:
            adjustments.append({
                "area": "General",
                "instruction": "Focus on team strengths: "
                               + ", ".join(our_stats.get("strengths", [])[:2]),
                "evidence": "Based on historical team statistics in demo dataset.",
            })

        # ── Evidence citations ───────────────────────────────────────────────
        evidence = [
            f"{m['team1']} vs {m['team2']} ({m.get('match_date','?')}) — "
            f"{m.get('result','?')}. {(m.get('notes') or '')[:100]}..."
            for m in match_analysis["retrieved_matches_raw"][:4]
        ]

        return {
            "agent": self.name,
            "our_team": our_team,
            "opponent": opp,
            "toss_advice": toss_advice,
            "match_situation_strategy": match_situation,
            "bowling": {
                "powerplay": pp_bowling,
                "middle_overs": mo_bowling,
                "death_overs": do_bowling,
            },
            "batting": {
                "powerplay": pp_batting,
                "middle_overs": mo_batting,
                "death_overs": do_batting,
            },
            "fielding_suggestions": fielding,
            "key_adjustments": adjustments,
            "evidence_matches": evidence,
        }


# =============================================================================
# AGENT 4 — IPL Insight Explanation Agent
# =============================================================================

class IPLInsightExplanationAgent:
    """
    Converts technical IPL analysis into plain coach-friendly insights.
    Uses IBM Granite via watsonx.ai when available; falls back to templates.
    """
    name = "IPL Insight Explanation Agent"

    def run(self, our_team: str, opponent: str,
            opponent_profile: dict, recommendation: dict) -> dict[str, Any]:

        opp_pp_profile = opponent_profile["powerplay_profile"]
        opp_approach   = opponent_profile["preferred_approach"]
        opp_strengths  = opponent_profile["strengths"]
        opp_weaknesses = opponent_profile["weaknesses"]
        vulnerabilities = opponent_profile["tactical_vulnerabilities"]
        bowling_plan   = recommendation["bowling"]
        batting_plan   = recommendation["batting"]

        # ── Build Granite prompt ─────────────────────────────────────────────
        prompt = (
            f"You are an expert IPL cricket analyst and coach.\n"
            f"Our team: {our_team}  |  Opponent: {opponent}\n"
            f"Opponent powerplay profile: {opp_pp_profile}\n"
            f"Opponent preferred approach: {opp_approach}\n"
            f"Opponent strengths: {', '.join(opp_strengths[:3])}\n"
            f"Opponent weaknesses: {', '.join(opp_weaknesses[:3])}\n\n"
            f"Powerplay bowling plan: {bowling_plan['powerplay'][:120]}\n"
            f"Death overs bowling plan: {bowling_plan['death_overs'][:120]}\n\n"
            "Provide 4-5 concise coaching insights (bullet points). "
            "Each must reference a specific cricket tactical pattern or match evidence. "
            "Write for a cricket coach. Be direct, specific, actionable."
        )
        granite_response = _call_llm(prompt)

        if granite_response:
            lines = [l.strip("•-– ").strip() for l in granite_response.split("\n") if l.strip()]
            key_insights = [l for l in lines if len(l) > 20][:6]
            insight_source = "IBM Granite (watsonx.ai)"
        else:
            key_insights = self._template_insights(
                our_team, opponent, opponent_profile, recommendation
            )
            insight_source = "Rule-based engine (watsonx.ai not configured)"

        summary = (
            f"{our_team} should approach this IPL fixture with a focus on "
            f"{opp_pp_profile.upper()} powerplay pressure from {opponent}. "
            f"{opponent}'s preferred style is to '{opp_approach}' — "
            f"exploit their known weaknesses in "
            f"{', '.join(opp_weaknesses[:2]) or 'the identified phases'}."
        )

        return {
            "agent": self.name,
            "our_team": our_team,
            "opponent": opponent,
            "summary": summary,
            "key_insights": key_insights,
            "insight_source": insight_source,
            "data_disclaimer": rag.get_ipl_data_notice(),
            "granite_used": granite_response is not None,
        }

    def _template_insights(self, our_team, opponent, profile, rec) -> list[str]:
        insights = []
        opp_pp   = profile["powerplay_profile"]
        opp_app  = profile["preferred_approach"]
        opp_spin = profile["spin_reliance"]
        opp_pp_r = profile["avg_powerplay_runs"]
        opp_do_r = profile["avg_death_overs_runs"]
        vulns    = profile["tactical_vulnerabilities"]

        # Insight 1 — powerplay
        if opp_pp in ("explosive", "aggressive"):
            insights.append(
                f"{opponent} averages ~{opp_pp_r} runs in the powerplay — classified as {opp_pp}. "
                "Priority: take early wickets to disrupt their powerplay momentum. "
                "Bowl attacking off-stump lines at pace. "
                "Historical data shows early dismissals significantly limit final totals."
            )
        else:
            insights.append(
                f"{opponent} is measured in the powerplay (~{opp_pp_r} runs). "
                "Apply pressure without over-attacking. "
                "Use two slips and attack fields to generate edges."
            )

        # Insight 2 — match situation
        bf = profile["batting_first"]
        ch = profile["chasing"]
        if bf.get("win_rate") and ch.get("win_rate"):
            stronger = "batting first" if bf["win_rate"] >= ch["win_rate"] else "chasing"
            insights.append(
                f"{opponent} is stronger when {stronger} "
                f"({bf['win_rate']}% bat-first win rate, {ch['win_rate']}% chasing win rate). "
                f"Force them into their weaker role by winning the toss and acting accordingly. "
                f"Evidence from {bf['matches'] + ch['matches']} retrieved matches."
            )

        # Insight 3 — spin
        if opp_spin == "high":
            insights.append(
                f"{opponent} relies on spin, which is effective in middle overs on slow surfaces. "
                "Counter by targeting pace bowlers and using sweeps/reverse sweeps against spinners. "
                "Keep strike rotation going at 7–8 per over even against spin to avoid pressure."
            )
        else:
            insights.append(
                f"{opponent} relies primarily on pace. "
                "Use your best spin option in the middle overs (7–15) to build dot-ball pressure. "
                "Economy under 7 RPO in this phase has been decisive in similar matches."
            )

        # Insight 4 — death overs
        if opp_do_r and opp_do_r >= 50:
            insights.append(
                f"{opponent} scores heavily in the death overs (~{opp_do_r} runs in 5 overs). "
                "Use your most experienced death-overs specialist in overs 18–20. "
                "Yorkers on off-stump are essential — historical data shows 4+ death-over wickets "
                "have directly caused chase failures."
            )
        else:
            insights.append(
                f"{opponent} scores ~{opp_do_r or 'unknown'} in the death. "
                "Maintain consistent yorker length. "
                "Save your strike bowler for overs 18–20."
            )

        # Insight 5 — key vulnerability
        if vulns:
            v = vulns[0]
            insights.append(
                f"Key tactical opportunity: {v['pattern']}. "
                f"{v['how_to_exploit']} "
                f"(Evidence: {v['evidence'][:110]})"
            )

        return insights


# =============================================================================
# CRICKET WHAT-IF ENGINE
# =============================================================================

class CricketWhatIfEngine:
    """
    Produces tactical advice for cricket-specific in-game scenarios.
    Uses IPL RAG to ground responses in historical evidence.
    """

    _SCENARIO_MAP = {
        "2 wickets in powerplay": {
            "keywords": ["2 wickets", "two wickets", "wickets in powerplay",
                         "lost wickets powerplay", "wicket in powerplay"],
            "advice": lambda opp, ctx: (
                "Two wickets lost in the powerplay puts your team under pressure early. "
                "Instruct the incoming batter to settle in for at least 8–10 balls before going big. "
                "Aim for 35–40 in the remaining powerplay overs with wickets preserved. "
                "The middle-order must bat deep — do not panic and throw wickets. "
                "Historical evidence: teams who stabilised after early powerplay wickets "
                "and maintained 7 wickets at the 10-over mark successfully chased comparable totals."
            ),
        },
        "need 60 from 30": {
            "keywords": ["60 from 30", "60 runs 30 balls", "need 60 off 30",
                         "12 per over", "60 off 30"],
            "advice": lambda opp, ctx: (
                "Needing 60 from 30 balls requires 12 runs per over. "
                "Instruct your batter to target the 5th and 6th stump — "
                "force wide deliveries or drive full-length balls through the off side. "
                "One maximum per over is the minimum target. "
                "Identify the weakest bowler remaining and target their overs for 16+ runs. "
                "Keep at least 3 wickets — do not go for broke with only one wicket remaining."
            ),
        },
        "opponent heavy powerplay": {
            "keywords": ["opponent scored heavily", "powerplay heavy", "big powerplay",
                         "opponent powerplay", "60 in powerplay", "scored heavily powerplay"],
            "advice": lambda opp, ctx: (
                f"{opp} has posted a big powerplay total. "
                "Focus on rebuilding composure in your bowling — "
                "the required economy in the remaining overs must now be tighter than planned. "
                "In your chase, do not try to match them blow-for-blow in the powerplay; "
                "preserve wickets and accelerate from overs 7 onwards. "
                "Historical data: teams that chased aggressively after conceding 65+ powerplay runs "
                "often lost 3+ wickets before the 10th over, collapsing the chase entirely."
            ),
        },
        "defending low total": {
            "keywords": ["defending low", "low total", "small total", "defend 140",
                         "defend 150", "under 160"],
            "advice": lambda opp, ctx: (
                "Defending a low total requires early wickets. "
                "Bowl aggressively with pace from both ends in the powerplay. "
                "Use your two best bowlers in overs 1–4. "
                "Attack with 3 slips and gully to create edge opportunities. "
                "In middle overs, mix spin and pace to vary rhythm. "
                "Historical pattern: defending 160 has been achieved through 5+ wickets "
                "by the 16th over — target is 3 wickets by the 10th over."
            ),
        },
        "chasing high total": {
            "keywords": ["chasing high", "high total", "200 target", "chase 190",
                         "190 target", "big chase", "195", "200"],
            "advice": lambda opp, ctx: (
                "Chasing a high total (185+) demands a controlled powerplay approach. "
                "Target 55+ in the powerplay with no more than 1 wicket. "
                "Middle overs: 75+ with wickets in hand is the critical platform. "
                "Death overs: with 3+ wickets in hand at over 16, you can target 60+ "
                "in the last 5 overs. "
                "Historical data: teams with 3+ wickets intact at over 16 successfully "
                "chased totals above 185 in similar demo match scenarios."
            ),
        },
        "key bowler unavailable": {
            "keywords": ["bowler unavailable", "key bowler out", "bowler injured",
                         "missing bowler", "bowler missing",
                         "bowler is unavailable", "key bowler is unavailable"],
            "advice": lambda opp, ctx: (
                "Key bowler is unavailable. Redistribute their overs across three change bowlers. "
                "Avoid giving 4 overs to one inexperienced bowler — "
                "split 2 + 2 across two part-time options in non-critical overs 8–14. "
                "Save your remaining frontline bowlers for the powerplay and death. "
                "Historical insight: teams that covered missing bowlers with multiple part-timers "
                "conceded fewer runs than those relying on one replacement for full allocation."
            ),
        },
    }

    def analyze(self, scenario: str, our_team: str, opponent: str) -> dict[str, Any]:
        scenario_lower = scenario.lower()
        context = rag.retrieve_ipl_context_for_whatif(scenario, our_team, opponent)

        matched_type = None
        advice = None
        for stype, sdata in self._SCENARIO_MAP.items():
            if any(kw in scenario_lower for kw in sdata["keywords"]):
                matched_type = stype
                advice = sdata["advice"](opponent, context)
                break

        if advice is None:
            advice = self._generic_response(scenario, opponent, context)

        evidence = []
        for m in context.get("matches", [])[:2]:
            evidence.append(
                f"{m['team1']} vs {m['team2']} ({m.get('match_date','?')}): "
                f"{(m.get('notes') or '')[:100]}..."
            )
        for p in context.get("patterns", [])[:2]:
            evidence.append(f"Pattern: {p['pattern']} — {p['description'][:100]}...")

        granite_enrichment = None
        if _WATSONX_AVAILABLE:
            gpt_prompt = (
                f"Cricket IPL tactical scenario: '{scenario}'\n"
                f"Our team: {our_team}, Opponent: {opponent}\n"
                f"Base advice: {advice}\n\n"
                "Provide 2 additional specific tactical instructions for the cricket captain. "
                "Be concise and practical."
            )
            granite_enrichment = _call_llm(gpt_prompt)

        return {
            "scenario": scenario,
            "scenario_type": matched_type or "custom",
            "sport": "cricket",
            "our_team": our_team,
            "opponent": opponent,
            "tactical_adjustment": advice,
            "granite_enrichment": granite_enrichment,
            "supporting_evidence": evidence,
            "data_disclaimer": rag.get_ipl_data_notice(),
        }

    def _generic_response(self, scenario: str, opponent: str, context: dict) -> str:
        opp_stats = context.get("opponent_stats") or {}
        weaknesses = opp_stats.get("weaknesses", [])
        resp = (
            f"Scenario: '{scenario}'. "
            "Assess how this changes your current tactical position. "
            "Maintain your structural game plan and adapt in the next over. "
        )
        if weaknesses:
            resp += f"Continue targeting {opponent}'s known weaknesses: {', '.join(weaknesses[:2])}."
        return resp


# =============================================================================
# CRICKET REAL-TIME INSIGHT ENGINE
# =============================================================================

class CricketRealtimeEngine:
    """
    Generates immediate tactical adjustments for simulated live cricket events.
    """

    def analyze(self, event: str, our_team: str, opponent: str) -> dict[str, Any]:
        event_lower = event.lower()
        context = rag.retrieve_ipl_context_for_whatif(event, our_team, opponent)

        # Wicket fall
        wkt_match = re.search(r"(\d+)\s*wickets?", event_lower)
        runs_match = re.search(r"(\d+)\s*(?:for|\/)\s*(\d+)", event_lower)

        if "wicket" in event_lower and wkt_match:
            wkts = int(wkt_match.group(1))
            adjustment = self._wicket_response(wkts, event_lower, opponent)
        elif "powerplay" in event_lower and any(x in event_lower for x in ["scored", "runs", "total"]):
            adjustment = (
                "Powerplay over. Assess the current run rate vs target or total. "
                "Introduce your best spinner early in over 7 to create dot-ball pressure. "
                "Set a 7 RPO budget in overs 7–15 to maintain match control."
            )
        elif "boundary" in event_lower or "four" in event_lower or "six" in event_lower:
            adjustment = (
                "Boundary conceded. Reset field immediately — do not bowl at the same area again. "
                "Move the point fielder wider. "
                "Bring mid-off up for the next delivery to prevent the push-drive single and apply pressure."
            )
        elif "50" in event_lower or "fifty" in event_lower or "half century" in event_lower:
            adjustment = (
                "Opposition batter has reached 50. "
                "Target them with a change of pace or a wide yorker — "
                "batters often reset and are vulnerable immediately after a milestone. "
                "Use an off-side attack to force a drive against the spin."
            )
        elif "rain" in event_lower or "dls" in event_lower:
            adjustment = (
                "Rain interruption / DLS scenario. "
                "Recalculate required run rate under revised DLS target immediately. "
                "If batting: accelerate to keep ahead of DLS par. "
                "If bowling: protect the DLS par score in every over."
            )
        elif "new batter" in event_lower or "wicket" in event_lower:
            adjustment = (
                "New batter at the crease. "
                "Attack immediately — bowl straight at the stumps for the first 2 deliveries. "
                "Set a short leg or silly mid-on to create mental pressure. "
                "Most wickets in T20 cricket fall in the first 3 balls faced by new batters."
            )
        else:
            adjustment = (
                f"Live event: '{event}'. "
                "Maintain your tactical structure. "
                f"Continue targeting {opponent}'s known weaknesses identified in the analysis. "
                "Communicate the plan across the team immediately."
            )

        evidence = [(m.get("notes") or "")[:100] + "..." for m in context.get("matches", [])[:2]]

        granite_enrichment = None
        if _WATSONX_AVAILABLE:
            gpt_prompt = (
                f"Live IPL cricket event: '{event}'\n"
                f"Our team: {our_team}, Opponent: {opponent}\n"
                f"Initial adjustment: {adjustment}\n\n"
                "Provide 2 additional specific immediate cricket tactics. Be very brief."
            )
            granite_enrichment = _call_llm(gpt_prompt)

        return {
            "event": event,
            "sport": "cricket",
            "our_team": our_team,
            "opponent": opponent,
            "immediate_adjustment": adjustment,
            "granite_enrichment": granite_enrichment,
            "supporting_evidence": evidence,
            "data_disclaimer": rag.get_ipl_data_notice(),
        }

    def _wicket_response(self, wkts: int, event_lower: str, opponent: str) -> str:
        if "we" in event_lower or "our" in event_lower:
            if wkts >= 3:
                return (
                    f"Your team has lost {wkts} wickets. Danger zone. "
                    "Instruct remaining batters to consolidate — rotate strike, "
                    "no risky shots for the next 2 overs. "
                    "Target loose deliveries only. Preserve the remaining partnerships. "
                    "A 5th-wicket partnership of 30+ can still rescue the innings."
                )
            else:
                return (
                    f"Your team has lost {wkts} wicket(s). Remain composed. "
                    "New batter should take 5–8 balls to settle. "
                    "Do not panic — continue the original game plan."
                )
        else:
            if wkts >= 3:
                return (
                    f"{opponent} has lost {wkts} wickets. "
                    "Excellent position — increase the pressure immediately. "
                    "Bring your best bowler back on. "
                    "Set an attacking field — two slips, short cover. "
                    "Target the stumps of the new batter on every delivery."
                )
            else:
                return (
                    f"{opponent} has lost {wkts} wicket(s). "
                    "Maintain pressure. "
                    "Do not let the new batter settle — bowl straight for 2 overs."
                )


# =============================================================================
# Convenience: run the full IPL pipeline
# =============================================================================

def run_full_ipl_analysis(our_team: str, opponent: str,
                           venue: str = "", season: str = "") -> dict[str, Any]:
    """Run all four IPL agents in sequence and return the combined result."""
    # Agent 1
    match_agent = IPLMatchAnalysisAgent()
    match_analysis = match_agent.run(our_team, opponent, venue, season)

    # Agent 2
    opp_agent = IPLOpponentStrategyAgent()
    opponent_profile = opp_agent.run(match_analysis)

    # Agent 3
    rec_agent = IPLStrategyRecommendationAgent()
    recommendation = rec_agent.run(our_team, match_analysis, opponent_profile)

    # Agent 4
    insight_agent = IPLInsightExplanationAgent()
    insights = insight_agent.run(our_team, opponent, opponent_profile, recommendation)

    return {
        "sport": "cricket",
        "league": "IPL",
        "our_team": our_team,
        "opponent": opponent,
        "venue": venue or "Any",
        "season": season or "All seasons",
        "match_analysis": match_analysis,
        "opponent_profile": opponent_profile,
        "recommendation": recommendation,
        "insights": insights,
    }
