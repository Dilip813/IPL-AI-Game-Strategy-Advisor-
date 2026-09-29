"""
IPL Data Ingestion Pipeline — football-advisor
===============================================
Processes the Cricsheet IPL ball-by-ball CSV2 dataset
(freely available under CC BY 4.0) into a match-level
summary JSON used by the application.

Source:  https://cricsheet.org/downloads/ipl_csv2.zip
License: Creative Commons Attribution 4.0 (CC BY 4.0)
Credit:  Cricsheet — Stephen Rushe (https://cricsheet.org)

Each match in the ZIP has two files:
  {id}.csv        — ball-by-ball delivery data
  {id}_info.csv   — match metadata (teams, toss, winner, players …)

This script aggregates both into per-match records, computes
phase statistics (powerplay / middle / death overs), team-level
statistics, head-to-head records, and data-derived tactical
patterns — using only numbers that appear in the actual data.

Run from the backend/ directory:
    python ingest_ipl_data.py [--force]
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
import urllib.request
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CRICSHEET_ZIP_URL = "https://cricsheet.org/downloads/ipl_csv2.zip"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "cricsheet_cache")
CACHE_ZIP = os.path.join(CACHE_DIR, "ipl_csv2.zip")
OUT_PATH  = os.path.join(os.path.dirname(__file__), "data", "ipl_match_data.json")

# Franchise name normalisation (historical → current/canonical)
TEAM_NORMALISE: dict[str, str] = {
    "Rising Pune Supergiant":       "Rising Pune Supergiants",
    "Rising Pune Supergiants":      "Rising Pune Supergiants",
    "Delhi Daredevils":             "Delhi Capitals",
    "Delhi Capitals":               "Delhi Capitals",
    "Deccan Chargers":              "Deccan Chargers",
    "Sunrisers Hyderabad":          "Sunrisers Hyderabad",
    "Kings XI Punjab":              "Punjab Kings",
    "Punjab Kings":                 "Punjab Kings",
    "Royal Challengers Bangalore":  "Royal Challengers Bengaluru",
    "Royal Challengers Bengaluru":  "Royal Challengers Bengaluru",
    "Chennai Super Kings":          "Chennai Super Kings",
    "Mumbai Indians":               "Mumbai Indians",
    "Kolkata Knight Riders":        "Kolkata Knight Riders",
    "Rajasthan Royals":             "Rajasthan Royals",
    "Lucknow Super Giants":         "Lucknow Super Giants",
    "Gujarat Titans":               "Gujarat Titans",
    "Gujarat Lions":                "Gujarat Lions",
    "Pune Warriors":                "Pune Warriors",
    "Kochi Tuskers Kerala":         "Kochi Tuskers Kerala",
}


def _norm(name: str) -> str:
    n = name.strip()
    return TEAM_NORMALISE.get(n, n)


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _download_zip(force: bool = False) -> bytes:
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not force and os.path.exists(CACHE_ZIP):
        print(f"  [cache] Using cached ZIP: {CACHE_ZIP}")
        with open(CACHE_ZIP, "rb") as f:
            return f.read()
    print(f"  [download] Fetching {CRICSHEET_ZIP_URL} ...")
    req = urllib.request.Request(
        CRICSHEET_ZIP_URL,
        headers={"User-Agent": "football-advisor-ipl/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(CACHE_ZIP, "wb") as f:
        f.write(data)
    print(f"  [download] Saved {len(data):,} bytes.")
    return data


# ---------------------------------------------------------------------------
# Parse _info.csv → match metadata dict
# ---------------------------------------------------------------------------

def _parse_info(text: str) -> dict:
    """Parse a Cricsheet _info.csv file into a flat metadata dict."""
    meta: dict[str, object] = {
        "teams": [],
        "players": defaultdict(list),
    }
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < 3 or row[0] != "info":
            continue
        key = row[1].strip()
        val = row[2].strip()

        if key == "team":
            meta["teams"].append(_norm(val))
        elif key == "player":
            team = _norm(val)
            player = row[3].strip() if len(row) > 3 else ""
            meta["players"][team].append(player)
        elif key in ("season", "date", "venue", "city",
                     "toss_winner", "toss_decision",
                     "player_of_match", "winner",
                     "winner_runs", "winner_wickets",
                     "match_id", "event"):
            if key == "toss_winner":
                meta[key] = _norm(val)
            elif key == "winner":
                meta[key] = _norm(val) if val not in ("no result", "tie") else val
            else:
                meta[key] = val
        elif key == "outcome":
            meta["outcome"] = val
    return meta


# ---------------------------------------------------------------------------
# Parse ball-by-ball .csv → per-innings aggregate stats
# ---------------------------------------------------------------------------

def _parse_deliveries(text: str) -> dict:
    """
    Aggregate ball-by-ball data into innings-level phase statistics.
    Returns dict keyed by innings number (1, 2) with:
        runs, wickets, overs_faced,
        powerplay_runs, powerplay_wickets,
        middle_runs, middle_wickets,
        death_runs, death_wickets,
        batting_team, bowling_team,
        batters (name→runs), bowlers (name→{overs,runs,wkts})
    """
    innings: dict[int, dict] = defaultdict(lambda: {
        "runs": 0, "wickets": 0, "legal_balls": 0,
        "powerplay_runs": 0, "powerplay_wickets": 0,
        "middle_runs": 0,    "middle_wickets": 0,
        "death_runs": 0,     "death_wickets": 0,
        "batting_team": None, "bowling_team": None,
        "batters": defaultdict(int),
        "bowlers": defaultdict(lambda: {"balls": 0, "runs": 0, "wkts": 0}),
    })

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            inn = int(row.get("innings", 0))
        except (ValueError, TypeError):
            continue
        if inn not in (1, 2):
            continue

        d = innings[inn]
        if d["batting_team"] is None:
            d["batting_team"] = _norm(row.get("batting_team", "") or "")
        if d["bowling_team"] is None:
            d["bowling_team"] = _norm(row.get("bowling_team", "") or "")

        # Ball number (over.ball format)
        ball_str = row.get("actual_delivery") or row.get("ball") or ""
        try:
            over_num = int(float(ball_str))   # 0-indexed over
        except (ValueError, TypeError):
            continue

        runs_off_bat = int(row.get("runs_off_bat", 0) or 0)
        extras       = int(row.get("extras", 0) or 0)
        wides        = int(row.get("wides", 0) or 0)
        noballs      = int(row.get("noballs", 0) or 0)
        total_runs   = runs_off_bat + extras
        is_legal     = (wides == 0 and noballs == 0)
        wicket       = 1 if row.get("wicket_type", "").strip() else 0

        d["runs"] += total_runs
        d["wickets"] += wicket
        if is_legal:
            d["legal_balls"] += 1

        striker = row.get("striker", "").strip()
        if striker:
            d["batters"][striker] += runs_off_bat

        bowler = row.get("bowler", "").strip()
        if bowler and is_legal:
            d["bowlers"][bowler]["balls"] += 1
            d["bowlers"][bowler]["runs"]  += runs_off_bat + (0 if not noballs else extras)
            d["bowlers"][bowler]["wkts"]  += wicket

        # Phase classification (overs 0-5 = PP, 6-14 = middle, 15-19 = death)
        if over_num <= 5:
            d["powerplay_runs"]    += total_runs
            d["powerplay_wickets"] += wicket
        elif over_num <= 14:
            d["middle_runs"]    += total_runs
            d["middle_wickets"] += wicket
        else:
            d["death_runs"]    += total_runs
            d["death_wickets"] += wicket

    # Convert defaultdicts to plain dicts
    result = {}
    for k, v in innings.items():
        overs_bowled = round(v["legal_balls"] / 6, 1) if v["legal_balls"] else 0
        top_batters = sorted(v["batters"].items(), key=lambda x: x[1], reverse=True)[:5]
        top_bowlers = sorted(
            v["bowlers"].items(),
            key=lambda x: x[1]["wkts"] * 100 - x[1]["runs"],
            reverse=True
        )[:5]
        result[k] = {
            "runs":      v["runs"],
            "wickets":   v["wickets"],
            "overs":     overs_bowled,
            "powerplay_runs":     v["powerplay_runs"],
            "powerplay_wickets":  v["powerplay_wickets"],
            "middle_runs":        v["middle_runs"],
            "middle_wickets":     v["middle_wickets"],
            "death_runs":         v["death_runs"],
            "death_wickets":      v["death_wickets"],
            "batting_team":  v["batting_team"],
            "bowling_team":  v["bowling_team"],
            "top_batters":   [{"name": n, "runs": r} for n, r in top_batters],
            "top_bowlers":   [{"name": n, **s}        for n, s in top_bowlers],
        }
    return result


# ---------------------------------------------------------------------------
# Build one match record from info + deliveries
# ---------------------------------------------------------------------------

def _build_match(match_id: str, info: dict, inn_data: dict) -> dict | None:
    teams = info.get("teams", [])
    if len(teams) < 2:
        return None

    team1, team2 = teams[0], teams[1]

    # Toss
    toss_winner   = info.get("toss_winner", "")
    toss_decision = info.get("toss_decision", "")

    # Derive batting first from toss
    if toss_decision == "bat":
        batting_first = toss_winner
        chasing_team  = team2 if toss_winner == team1 else team1
    elif toss_decision == "field":
        batting_first = team2 if toss_winner == team1 else team1
        chasing_team  = toss_winner
    else:
        # Fall back to inn_data order
        batting_first = inn_data.get(1, {}).get("batting_team") or team1
        chasing_team  = inn_data.get(2, {}).get("batting_team") or team2

    inn1 = inn_data.get(1, {})
    inn2 = inn_data.get(2, {})

    winner = info.get("winner")

    # Result string built from real data only
    result_str = None
    if winner and winner not in ("no result", "tie"):
        by_runs = info.get("winner_runs")
        by_wkts = info.get("winner_wickets")
        if by_runs:
            result_str = f"{winner} won by {by_runs} runs"
        elif by_wkts:
            result_str = f"{winner} won by {by_wkts} wickets"
        else:
            result_str = f"{winner} won"
    elif winner == "tie":
        result_str = "Tie"
    else:
        result_str = "No result"

    # Phase stats — only from inn_data, never invented
    def _val(d: dict, key: str):
        v = d.get(key)
        return v if v is not None else None

    rec = {
        "id":           match_id,
        "season":       info.get("season") or info.get("date", "")[:4] or None,
        "match_date":   info.get("date", "").replace("/", "-") or None,
        "venue":        info.get("venue") or None,
        "city":         info.get("city") or None,
        "team1":        team1,
        "team2":        team2,
        "toss_winner":  toss_winner or None,
        "toss_decision":toss_decision or None,
        "batting_first":batting_first,
        "chasing_team": chasing_team,
        "winner":       winner if winner not in ("no result",) else None,
        "result":       result_str,
        "player_of_match": info.get("player_of_match") or None,
        # Innings scores from ball-by-ball aggregation
        "first_innings_runs":       _val(inn1, "runs"),
        "first_innings_wickets":    _val(inn1, "wickets"),
        "first_innings_overs":      _val(inn1, "overs"),
        "second_innings_runs":      _val(inn2, "runs"),
        "second_innings_wickets":   _val(inn2, "wickets"),
        "second_innings_overs":     _val(inn2, "overs"),
        # Phase stats — first innings (batting first team)
        "powerplay_runs_batting":    _val(inn1, "powerplay_runs"),
        "powerplay_wickets_batting": _val(inn1, "powerplay_wickets"),
        "middle_overs_runs_batting": _val(inn1, "middle_runs"),
        "middle_overs_wickets_batting": _val(inn1, "middle_wickets"),
        "death_overs_runs_batting":  _val(inn1, "death_runs"),
        "death_overs_wickets_batting":_val(inn1, "death_wickets"),
        # Phase stats — second innings (chasing team)
        "powerplay_runs_chasing":    _val(inn2, "powerplay_runs"),
        "powerplay_wickets_chasing": _val(inn2, "powerplay_wickets"),
        "middle_overs_runs_chasing": _val(inn2, "middle_runs"),
        "middle_overs_wickets_chasing": _val(inn2, "middle_wickets"),
        "death_overs_runs_chasing":  _val(inn2, "death_runs"),
        "death_overs_wickets_chasing":_val(inn2, "death_wickets"),
        # Top performers from real data
        "top_performers": {
            "innings1_batters": _val(inn1, "top_batters") or [],
            "innings1_bowlers": _val(inn1, "top_bowlers") or [],
            "innings2_batters": _val(inn2, "top_batters") or [],
            "innings2_bowlers": _val(inn2, "top_bowlers") or [],
        },
        "notes": None,
    }
    return rec


# ---------------------------------------------------------------------------
# Aggregate team-level statistics
# ---------------------------------------------------------------------------

def _compute_team_stats(matches: list[dict]) -> dict:
    stats: dict[str, dict] = defaultdict(lambda: {
        "mp": 0, "wins": 0, "losses": 0, "nr": 0,
        "bf_m": 0, "bf_w": 0, "ch_m": 0, "ch_w": 0,
        "fi_runs": [], "pp_runs": [], "pp_wkts": [],
        "mo_runs": [], "do_runs": [],
        "seasons": set(), "venues": defaultdict(int),
    })

    for m in matches:
        w = m.get("winner")
        bf = m.get("batting_first")
        for team in (m["team1"], m["team2"]):
            s = stats[team]
            s["mp"] += 1
            s["seasons"].add(m.get("season") or "unknown")
            if m.get("venue"):
                s["venues"][m["venue"]] += 1

            if w == team:
                s["wins"] += 1
            elif w:
                s["losses"] += 1
            else:
                s["nr"] += 1

            is_bf = (bf == team)
            if is_bf:
                s["bf_m"] += 1
                if w == team:
                    s["bf_w"] += 1
                if m.get("first_innings_runs") is not None:
                    s["fi_runs"].append(m["first_innings_runs"])
                if m.get("powerplay_runs_batting") is not None:
                    s["pp_runs"].append(m["powerplay_runs_batting"])
                if m.get("powerplay_wickets_batting") is not None:
                    s["pp_wkts"].append(m["powerplay_wickets_batting"])
                if m.get("middle_overs_runs_batting") is not None:
                    s["mo_runs"].append(m["middle_overs_runs_batting"])
                if m.get("death_overs_runs_batting") is not None:
                    s["do_runs"].append(m["death_overs_runs_batting"])
            else:
                s["ch_m"] += 1
                if w == team:
                    s["ch_w"] += 1

    def _avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else None

    result = {}
    for team, s in stats.items():
        mp = s["mp"]
        bf_wr = round(s["bf_w"] / s["bf_m"] * 100, 1) if s["bf_m"] else None
        ch_wr = round(s["ch_w"] / s["ch_m"] * 100, 1) if s["ch_m"] else None
        home  = max(s["venues"], key=s["venues"].get) if s["venues"] else None

        strengths, weaknesses = [], []
        if bf_wr and bf_wr >= 55 and s["bf_m"] >= 5:
            strengths.append(
                f"Strong batting-first record ({bf_wr}% win rate, "
                f"{s['bf_w']}/{s['bf_m']} matches)"
            )
        if bf_wr and bf_wr < 45 and s["bf_m"] >= 5:
            weaknesses.append(
                f"Struggles batting first ({bf_wr}% win rate, "
                f"{s['bf_w']}/{s['bf_m']} matches)"
            )
        if ch_wr and ch_wr >= 55 and s["ch_m"] >= 5:
            strengths.append(
                f"Strong chasing side ({ch_wr}% win rate, "
                f"{s['ch_w']}/{s['ch_m']} chases)"
            )
        if ch_wr and ch_wr < 45 and s["ch_m"] >= 5:
            weaknesses.append(
                f"Struggles chasing ({ch_wr}% win rate, "
                f"{s['ch_w']}/{s['ch_m']} chases)"
            )
        wpc = round(s["wins"] / mp * 100, 1) if mp else None
        if wpc and wpc >= 55 and mp >= 10:
            strengths.append(
                f"Historically strong overall win rate ({wpc}% across {mp} matches)"
            )
        if home:
            strengths.append(
                f"Home ground advantage at {home.split(',')[0]}"
            )
        avg_pp = _avg(s["pp_runs"])
        if avg_pp and avg_pp >= 55 and len(s["pp_runs"]) >= 5:
            strengths.append(
                f"Explosive powerplay batting (avg {avg_pp} runs, "
                f"{len(s['pp_runs'])} matches with data)"
            )
        if avg_pp and avg_pp < 42 and len(s["pp_runs"]) >= 5:
            weaknesses.append(
                f"Conservative powerplay batting (avg {avg_pp} runs)"
            )

        result[team] = {
            "matches_played":         mp,
            "wins":                   s["wins"],
            "losses":                 s["losses"],
            "no_result":              s["nr"],
            "win_pct":                wpc,
            "batting_first_matches":  s["bf_m"],
            "batting_first_wins":     s["bf_w"],
            "batting_first_win_pct":  bf_wr,
            "chasing_matches":        s["ch_m"],
            "chasing_wins":           s["ch_w"],
            "chasing_win_pct":        ch_wr,
            "avg_first_innings":      _avg(s["fi_runs"]),
            "avg_powerplay_runs":     avg_pp,
            "avg_powerplay_wickets":  _avg(s["pp_wkts"]),
            "avg_middle_overs_runs":  _avg(s["mo_runs"]),
            "avg_death_overs_runs":   _avg(s["do_runs"]),
            "seasons_present":        sorted(s["seasons"]),
            "home_venue":             home,
            "preferred_approach": (
                "bat first"  if (bf_wr or 0) > (ch_wr or 0) else
                "chase"      if (ch_wr or 0) > (bf_wr or 0) else "versatile"
            ),
            "spin_reliance": None,  # not derivable from match-summary CSV
            "strengths":  strengths  or ["Insufficient data for specific strength claims"],
            "weaknesses": weaknesses or ["Insufficient data for specific weakness claims"],
        }
    return result


# ---------------------------------------------------------------------------
# Head-to-head
# ---------------------------------------------------------------------------

def _compute_h2h(matches: list[dict]) -> dict:
    h2h: dict[str, dict] = {}
    for m in matches:
        t1, t2 = m["team1"], m["team2"]
        key = "_vs_".join(sorted([t1, t2]))
        if key not in h2h:
            h2h[key] = {"matches": 0, "wins": {}}
        h2h[key]["matches"] += 1
        h2h[key]["wins"].setdefault(t1, 0)
        h2h[key]["wins"].setdefault(t2, 0)
        w = m.get("winner")
        if w in (t1, t2):
            h2h[key]["wins"][w] += 1
    return h2h


# ---------------------------------------------------------------------------
# Derive tactical patterns from real data
# ---------------------------------------------------------------------------

def _derive_patterns(matches: list[dict], team_stats: dict) -> list[dict]:
    patterns = []

    decided = [m for m in matches if m.get("winner")]
    total = len(decided)
    if total:
        bf_wins = sum(1 for m in decided if m["winner"] == m.get("batting_first"))
        ch_wins = total - bf_wins
        bf_pct  = round(bf_wins / total * 100, 1)
        patterns.append({
            "pattern": "Batting-first vs chasing — overall IPL dataset",
            "description": (
                f"Across {total:,} completed IPL matches in this dataset, "
                f"batting-first teams won {bf_wins:,} ({bf_pct}%) "
                f"and chasing teams won {ch_wins:,} ({100-bf_pct}%)."
            ),
            "affected_teams": [],
            "exploiting_approach": (
                "Consider venue-specific batting-first win rates when deciding "
                "toss strategy. Conditions vary significantly by ground and time of day."
            ),
            "data_basis": f"{total:,} completed matches",
        })

    # Powerplay data
    pp_data = [m for m in matches if m.get("powerplay_runs_batting") is not None]
    if len(pp_data) >= 10:
        pp_vals  = [m["powerplay_runs_batting"] for m in pp_data]
        avg_pp   = round(sum(pp_vals) / len(pp_vals), 1)
        high_pp  = [m for m in pp_data if m["powerplay_runs_batting"] >= avg_pp + 5]
        h_bf_win = sum(1 for m in high_pp if m["winner"] == m.get("batting_first"))
        h_total  = len(high_pp)
        patterns.append({
            "pattern": "Powerplay scoring impact on match outcome",
            "description": (
                f"Average powerplay score (batting first) across {len(pp_data):,} matches: "
                f"{avg_pp} runs. In {h_total} matches where the batting team scored "
                f"{avg_pp+5}+ in the powerplay, the batting team won "
                f"{h_bf_win} ({round(h_bf_win/h_total*100,1) if h_total else 0}%)."
            ),
            "affected_teams": [],
            "exploiting_approach": (
                f"Restrict opponents to below {avg_pp} runs in the powerplay. "
                "Early wickets significantly limit final total potential."
            ),
            "data_basis": f"{len(pp_data):,} matches with powerplay data",
        })

    # Team-specific
    for team, s in team_stats.items():
        if s["batting_first_win_pct"] and s["batting_first_win_pct"] >= 60 \
                and s["batting_first_matches"] >= 10:
            patterns.append({
                "pattern": f"{team} — dominant batting-first record",
                "description": (
                    f"{team} wins {s['batting_first_win_pct']}% when batting first "
                    f"({s['batting_first_wins']}/{s['batting_first_matches']} matches)."
                ),
                "affected_teams": [team],
                "exploiting_approach": (
                    f"Win the toss and field against {team} to deny them their preferred approach."
                ),
                "data_basis": f"{s['batting_first_matches']} batting-first matches",
            })
        if s["chasing_win_pct"] and s["chasing_win_pct"] >= 60 \
                and s["chasing_matches"] >= 10:
            patterns.append({
                "pattern": f"{team} — strong chasing record",
                "description": (
                    f"{team} wins {s['chasing_win_pct']}% when chasing "
                    f"({s['chasing_wins']}/{s['chasing_matches']} chases). "
                    f"Avg first innings score (when they bat first): "
                    f"{s['avg_first_innings'] or 'insufficient data'}."
                ),
                "affected_teams": [team],
                "exploiting_approach": (
                    f"Bat first against {team} and set a large target above their "
                    f"average chase target. Restrict powerplay to limit scoring platform."
                ),
                "data_basis": f"{s['chasing_matches']} chasing matches",
            })

    return patterns


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def run_ingestion(force: bool = False) -> dict:
    if force and os.path.exists(CACHE_ZIP):
        os.remove(CACHE_ZIP)
        print("[ingest] Cache cleared.")

    print("[ingest] Loading Cricsheet IPL data ...")
    raw_zip = _download_zip(force=force)

    print("[ingest] Parsing ball-by-ball delivery files ...")
    all_matches: list[dict] = []
    errors = 0

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        names = sorted(zf.namelist())
        # Group into (id → info_name, data_name) pairs
        info_files = {n.replace("_info.csv", ""): n
                      for n in names if n.endswith("_info.csv")}
        data_files = {n.replace(".csv", ""): n
                      for n in names
                      if n.endswith(".csv") and not n.endswith("_info.csv")}
        match_ids = sorted(set(info_files.keys()) & set(data_files.keys()))
        print(f"  Found {len(match_ids):,} complete match pairs.")

        for mid in match_ids:
            try:
                with zf.open(info_files[mid]) as f:
                    info_text = f.read().decode("utf-8", errors="replace")
                with zf.open(data_files[mid]) as f:
                    data_text = f.read().decode("utf-8", errors="replace")

                info    = _parse_info(info_text)
                inn_data = _parse_deliveries(data_text)
                rec     = _build_match(mid, info, inn_data)
                if rec:
                    all_matches.append(rec)
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [warn] Error processing {mid}: {e}")

    print(f"  Parsed {len(all_matches):,} match records ({errors} errors).")

    if not all_matches:
        print("[ingest] ERROR: No records produced. Aborting.")
        sys.exit(1)

    # Sort by date
    def _sort_key(m):
        try:
            return datetime.strptime(m["match_date"] or "2000-01-01", "%Y-%m-%d")
        except Exception:
            return datetime(2000, 1, 1)
    all_matches.sort(key=_sort_key)

    # Unique teams, venues, seasons
    all_teams   = sorted({t for m in all_matches for t in (m["team1"], m["team2"])})
    all_venues  = sorted({m["venue"] for m in all_matches if m.get("venue")})
    all_seasons = sorted({m["season"] for m in all_matches if m.get("season")}, reverse=True)

    # Ball-by-ball total
    total_bbb = sum(
        int(round((m["first_innings_overs"] or 0) * 6)) +
        int(round((m["second_innings_overs"] or 0) * 6))
        for m in all_matches
    )

    # All unique players
    all_players: set[str] = set()
    for m in all_matches:
        for inn in ("innings1_batters", "innings2_batters"):
            for p in m["top_performers"].get(inn, []):
                if p.get("name"):
                    all_players.add(p["name"])
        for inn in ("innings1_bowlers", "innings2_bowlers"):
            for p in m["top_performers"].get(inn, []):
                if p.get("name"):
                    all_players.add(p["name"])

    print(f"[ingest] Computing team statistics ...")
    team_stats = _compute_team_stats(all_matches)

    print(f"[ingest] Computing head-to-head ...")
    h2h = _compute_h2h(all_matches)

    print(f"[ingest] Deriving tactical patterns ...")
    patterns = _derive_patterns(all_matches, team_stats)

    provenance = {
        "data_type":       "REAL",
        "source":          "Cricsheet IPL ball-by-ball data (CSV2 format)",
        "source_url":      "https://cricsheet.org/downloads/ipl_csv2.zip",
        "license":         "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "attribution":     "Cricsheet — Stephen Rushe (https://cricsheet.org)",
        "seasons_covered": all_seasons,
        "total_matches":   len(all_matches),
        "total_teams":     len(all_teams),
        "total_players":   len(all_players),
        "approx_bbb_deliveries": total_bbb,
        "last_updated":    datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "processing_notes": (
            "Phase statistics (powerplay/middle/death overs) are derived directly "
            "from ball-by-ball delivery data. Match-level statistics are aggregated "
            "from individual deliveries with no interpolation or invention. "
            "Franchise names have been normalised for consistency "
            "(e.g. Delhi Daredevils → Delhi Capitals)."
        ),
    }

    out = {
        "_provenance": provenance,
        "_data_notice": (
            f"REAL IPL DATA — Source: Cricsheet (https://cricsheet.org), "
            f"licensed CC BY 4.0. Credit: Stephen Rushe. "
            f"{len(all_matches):,} matches across {len(all_seasons)} seasons "
            f"({all_seasons[-1] if all_seasons else '?'}–{all_seasons[0] if all_seasons else '?'}). "
            f"Phase statistics derived from {total_bbb:,} ball-by-ball deliveries."
        ),
        "league":    "IPL",
        "data_type": "REAL",
        "teams":     all_teams,
        "venues":    all_venues,
        "matches":   all_matches,
        "team_stats":        team_stats,
        "head_to_head":      h2h,
        "tactical_patterns": patterns,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    sz_mb = os.path.getsize(OUT_PATH) / 1_048_576
    print(f"\n[ingest] Done. Written {OUT_PATH} ({sz_mb:.1f} MB)")
    print(f"  Matches:           {len(all_matches):,}")
    print(f"  Teams:             {len(all_teams)}")
    print(f"  Venues:            {len(all_venues)}")
    print(f"  Seasons:           {all_seasons[:6]}{'...' if len(all_seasons) > 6 else ''}")
    print(f"  Unique players:    {len(all_players):,}")
    print(f"  ~Deliveries:       {total_bbb:,}")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Ingest Cricsheet IPL data")
    ap.add_argument("--force", action="store_true", help="Re-download ZIP")
    args = ap.parse_args()
    run_ingestion(force=args.force)
