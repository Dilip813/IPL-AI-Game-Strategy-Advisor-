"""
Flask application — IPL AI Game Strategy Advisor
Entry point for all IPL/Cricket API routes.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

import rag
import cricket_agents

app = Flask(__name__)
CORS(app)  # allow cross-origin requests from the frontend


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# =============================================================================
# IPL / Cricket API routes
# =============================================================================

@app.route("/api/cricket/teams", methods=["GET"])
def cricket_teams():
    """Return IPL team list and provenance metadata."""
    prov = rag.get_ipl_provenance()
    return jsonify({
        "teams":       rag.get_ipl_teams(),
        "venues":      rag.get_ipl_venues(),
        "seasons":     rag.get_ipl_seasons(),
        "data_notice": rag.get_ipl_data_notice(),
        "data_type":   prov.get("data_type", "REAL"),
        "provenance":  prov,
    })


@app.route("/api/cricket/matches", methods=["GET"])
def cricket_matches():
    """Return IPL matches, optionally filtered by team."""
    team = request.args.get("team", "")
    matches = rag.get_all_ipl_matches()
    if team:
        matches = [m for m in matches if team in (m["team1"], m["team2"])]
    return jsonify({
        "matches": matches,
        "count": len(matches),
        "data_notice": rag.get_ipl_data_notice(),
    })


@app.route("/api/cricket/team-stats/<team_name>", methods=["GET"])
def cricket_team_stats(team_name: str):
    """Return IPL statistics for a single team."""
    stats = rag.get_ipl_team_stats(team_name)
    if stats is None:
        return _err(f"IPL team '{team_name}' not found.", 404)
    return jsonify({"team": team_name, "stats": stats})


@app.route("/api/cricket/analyze", methods=["POST"])
def cricket_analyze():
    """
    Run the full 4-agent IPL analysis pipeline.

    Body JSON:
    {
      "our_team": "Chennai Super Kings",
      "opponent": "Mumbai Indians",
      "venue": "MA Chidambaram Stadium, Chepauk",  (optional)
      "season": "2023"                              (optional)
    }
    """
    body = request.get_json(silent=True) or {}
    our_team = body.get("our_team", "").strip()
    opponent = body.get("opponent", "").strip()
    venue    = body.get("venue", "").strip()
    season   = body.get("season", "").strip()

    if not our_team or not opponent:
        return _err("Both 'our_team' and 'opponent' are required.")
    if our_team == opponent:
        return _err("'our_team' and 'opponent' must be different teams.")

    available = rag.get_ipl_teams()
    if our_team not in available:
        return _err(f"IPL team '{our_team}' not found. Available: {available}")
    if opponent not in available:
        return _err(f"IPL team '{opponent}' not found. Available: {available}")

    result = cricket_agents.run_full_ipl_analysis(our_team, opponent, venue, season)
    return jsonify(result)


@app.route("/api/cricket/what-if", methods=["POST"])
def cricket_whatif():
    """
    Cricket What-If scenario simulation.

    Body JSON:
    {
      "scenario": "We lost 2 wickets in the powerplay",
      "our_team": "Chennai Super Kings",
      "opponent": "Mumbai Indians"
    }
    """
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario", "").strip()
    our_team = body.get("our_team", "").strip()
    opponent = body.get("opponent", "").strip()

    if not scenario or not our_team or not opponent:
        return _err("'scenario', 'our_team', and 'opponent' are required.")

    engine = cricket_agents.CricketWhatIfEngine()
    result = engine.analyze(scenario, our_team, opponent)
    return jsonify(result)


@app.route("/api/cricket/realtime", methods=["POST"])
def cricket_realtime():
    """
    Simulated live cricket event insight.

    Body JSON:
    {
      "event": "Opponent scored 68 in the powerplay",
      "our_team": "Chennai Super Kings",
      "opponent": "Mumbai Indians"
    }
    """
    body = request.get_json(silent=True) or {}
    event    = body.get("event", "").strip()
    our_team = body.get("our_team", "").strip()
    opponent = body.get("opponent", "").strip()

    if not event or not our_team or not opponent:
        return _err("'event', 'our_team', and 'opponent' are required.")

    engine = cricket_agents.CricketRealtimeEngine()
    result = engine.analyze(event, our_team, opponent)
    return jsonify(result)


@app.route("/api/cricket/tactical-patterns", methods=["GET"])
def cricket_tactical_patterns():
    """Return all IPL tactical patterns."""
    return jsonify({
        "patterns": rag.get_ipl_tactical_patterns(),
        "data_notice": rag.get_ipl_data_notice(),
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "watsonx_configured": cricket_agents._WATSONX_AVAILABLE,
        "granite_model": "ibm/granite-13b-chat-v2" if cricket_agents._WATSONX_AVAILABLE else None,
        "data_source": "Real Cricsheet IPL data",
        "sport": "cricket",
        "league": "IPL",
    })


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  IPL AI Game Strategy Advisor — Backend")
    print("  http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, port=5000, use_reloader=False)
