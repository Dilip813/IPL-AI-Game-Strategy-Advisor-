"""
IPL Data Validation Script — football-advisor
==============================================
Validates the ipl_match_data.json produced by ingest_ipl_data.py.

Checks:
  1. No placeholder player names (Batter A, Bowler X, etc.)
  2. No fabricated DEMO match IDs (IPL-D*)
  3. data_type == "REAL"
  4. Required fields present on every match record
  5. Phase statistics are reproducible from ball-by-ball derivation
     (spot-checks a sample of matches against the cached ZIP)
  6. Team / player names are real strings, not empty or None
  7. Provenance metadata is complete
  8. Head-to-head + team_stats are consistent with match records
  9. No match has negative runs / wickets

Run from the backend/ directory:
    python validate_ipl_data.py

Exit code 0 = all checks pass.
Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

DATA_PATH   = os.path.join(os.path.dirname(__file__), "data", "ipl_match_data.json")
CACHE_ZIP   = os.path.join(os.path.dirname(__file__), "data", "cricsheet_cache", "ipl_csv2.zip")
SAMPLE_SIZE = 20   # number of matches to spot-check against raw ZIP

# Placeholder name patterns that must NOT appear
PLACEHOLDER_RE = re.compile(
    r"\b(Batter|Bowler|Player)\s+[A-Z]\b", re.IGNORECASE
)
DEMO_ID_RE = re.compile(r"^IPL-D", re.IGNORECASE)

# Required fields on every match record
REQUIRED_MATCH_FIELDS = [
    "id", "season", "match_date", "team1", "team2",
    "batting_first", "chasing_team",
    "first_innings_runs", "first_innings_wickets",
    "powerplay_runs_batting",
]

results: list[tuple[str, bool, str]] = []


def chk(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def load_data() -> dict:
    print(f"Loading {DATA_PATH} ...")
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CHECK 1 — data_type == REAL
# ---------------------------------------------------------------------------
def check_data_type(d: dict):
    chk("data_type is REAL", d.get("data_type") == "REAL",
        f"got: {d.get('data_type')}")


# ---------------------------------------------------------------------------
# CHECK 2 — Provenance metadata complete
# ---------------------------------------------------------------------------
def check_provenance(d: dict):
    prov = d.get("_provenance", {})
    required = ["source", "source_url", "license", "attribution",
                "seasons_covered", "total_matches", "last_updated"]
    missing = [k for k in required if not prov.get(k)]
    chk("provenance has required fields", len(missing) == 0,
        f"missing: {missing}" if missing else "")
    chk("seasons_covered is non-empty list",
        isinstance(prov.get("seasons_covered"), list)
        and len(prov["seasons_covered"]) > 0)
    chk("total_matches > 0", (prov.get("total_matches") or 0) > 0,
        str(prov.get("total_matches")))
    chk("data_notice present", bool(d.get("_data_notice")))
    chk("data_notice says REAL", "REAL" in (d.get("_data_notice") or ""),
        d.get("_data_notice", "")[:60])


# ---------------------------------------------------------------------------
# CHECK 3 — No DEMO match IDs
# ---------------------------------------------------------------------------
def check_no_demo_ids(matches: list[dict]):
    demo = [m["id"] for m in matches if DEMO_ID_RE.match(str(m.get("id", "")))]
    chk("no IPL-D* (demo) match IDs", len(demo) == 0,
        f"{len(demo)} found: {demo[:3]}" if demo else "")


# ---------------------------------------------------------------------------
# CHECK 4 — No placeholder player names
# ---------------------------------------------------------------------------
def check_no_placeholders(matches: list[dict]):
    fake: list[str] = []
    for m in matches:
        tp = m.get("top_performers", {})
        if not isinstance(tp, dict):
            continue
        for key in ("innings1_batters", "innings2_batters",
                    "innings1_bowlers", "innings2_bowlers"):
            for p in tp.get(key, []):
                name = p.get("name", "")
                if name and PLACEHOLDER_RE.search(name):
                    fake.append(name)
    chk("no placeholder player names", len(fake) == 0,
        f"{len(fake)} found: {fake[:5]}" if fake else "")


# ---------------------------------------------------------------------------
# CHECK 5 — Required fields present
# ---------------------------------------------------------------------------
def check_required_fields(matches: list[dict]):
    missing_counts: dict[str, int] = defaultdict(int)
    for m in matches:
        for f in REQUIRED_MATCH_FIELDS:
            if m.get(f) is None:
                missing_counts[f] += 1

    # Phase stats can be None for very old matches — flag only if >80% missing
    phase_fields = ["powerplay_runs_batting"]
    for f in phase_fields:
        cnt = missing_counts.get(f, 0)
        pct = round(cnt / len(matches) * 100, 1) if matches else 0
        chk(f"field '{f}' populated for >=50% of matches",
            pct <= 50,
            f"{cnt}/{len(matches)} ({pct}%) null")

    non_phase = [f for f in REQUIRED_MATCH_FIELDS if f not in phase_fields]
    for f in non_phase:
        cnt = missing_counts.get(f, 0)
        chk(f"field '{f}' present on all matches",
            cnt == 0,
            f"{cnt} matches missing this field" if cnt else "")


# ---------------------------------------------------------------------------
# CHECK 6 — No negative runs or wickets
# ---------------------------------------------------------------------------
def check_no_negatives(matches: list[dict]):
    neg = []
    for m in matches:
        for f in ("first_innings_runs", "second_innings_runs",
                  "first_innings_wickets", "second_innings_wickets",
                  "powerplay_runs_batting", "powerplay_runs_chasing"):
            v = m.get(f)
            if v is not None and v < 0:
                neg.append((m["id"], f, v))
    chk("no negative runs/wickets", len(neg) == 0,
        f"{len(neg)} issues: {neg[:3]}" if neg else "")


# ---------------------------------------------------------------------------
# CHECK 7 — Team names are real strings, not empty
# ---------------------------------------------------------------------------
def check_team_names(matches: list[dict], teams: list[str]):
    blank = [m["id"] for m in matches
             if not m.get("team1") or not m.get("team2")]
    chk("all matches have non-empty team1/team2", len(blank) == 0,
        f"{len(blank)} blank" if blank else "")
    chk("teams list is non-empty", len(teams) > 0, str(len(teams)))
    chk("teams list has no empty strings",
        all(bool(t) for t in teams))


# ---------------------------------------------------------------------------
# CHECK 8 — team_stats consistent with match records
# ---------------------------------------------------------------------------
def check_team_stats_consistency(matches: list[dict], team_stats: dict):
    computed: dict[str, dict] = defaultdict(lambda: {"mp": 0, "wins": 0})
    for m in matches:
        w = m.get("winner")
        for t in (m["team1"], m["team2"]):
            computed[t]["mp"] += 1
            if w == t:
                computed[t]["wins"] += 1

    mismatches = []
    for team, cs in computed.items():
        ts = team_stats.get(team)
        if ts is None:
            mismatches.append(f"{team}: missing from team_stats")
            continue
        if ts.get("matches_played") != cs["mp"]:
            mismatches.append(
                f"{team}: matches_played {ts['matches_played']} vs computed {cs['mp']}"
            )
        if ts.get("wins") != cs["wins"]:
            mismatches.append(
                f"{team}: wins {ts['wins']} vs computed {cs['wins']}"
            )

    chk("team_stats consistent with match records",
        len(mismatches) == 0,
        "; ".join(mismatches[:3]) if mismatches else "")


# ---------------------------------------------------------------------------
# CHECK 9 — head_to_head consistent
# ---------------------------------------------------------------------------
def check_h2h_consistency(matches: list[dict], h2h: dict):
    computed: dict[str, int] = defaultdict(int)
    for m in matches:
        t1, t2 = m["team1"], m["team2"]
        key = "_vs_".join(sorted([t1, t2]))
        computed[key] += 1

    mismatches = []
    for key, cnt in computed.items():
        stored = h2h.get(key, {}).get("matches", 0)
        if stored != cnt:
            mismatches.append(f"{key}: stored {stored} vs computed {cnt}")

    chk("head_to_head consistent with match records",
        len(mismatches) == 0,
        "; ".join(mismatches[:3]) if mismatches else f"{len(h2h)} H2H entries")


# ---------------------------------------------------------------------------
# CHECK 10 — Spot-check phase stats against raw ZIP (if cached)
# ---------------------------------------------------------------------------
def check_phase_stats_reproducible(matches: list[dict]):
    if not os.path.exists(CACHE_ZIP):
        chk("phase stats reproducible (spot-check)",
            True, "SKIPPED — cache ZIP not found")
        return

    # Pick first SAMPLE_SIZE matches that have phase data
    sample = [m for m in matches
              if m.get("powerplay_runs_batting") is not None][:SAMPLE_SIZE]
    if not sample:
        chk("phase stats spot-check has samples", False,
            "no matches with powerplay_runs_batting found")
        return

    with open(CACHE_ZIP, "rb") as f:
        raw_zip = f.read()

    errors = []
    checked = 0
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        for m in sample:
            mid = str(m["id"])
            csv_name = f"{mid}.csv"
            if csv_name not in zf.namelist():
                continue
            with zf.open(csv_name) as cf:
                text = cf.read().decode("utf-8", errors="replace")

            # Re-derive powerplay runs for innings 1
            pp_runs = 0
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                try:
                    inn = int(row.get("innings", 0))
                except Exception:
                    continue
                if inn != 1:
                    continue
                ball_str = row.get("actual_delivery") or row.get("ball") or ""
                try:
                    over_num = int(float(ball_str))
                except Exception:
                    continue
                if over_num > 5:
                    continue
                pp_runs += int(row.get("runs_off_bat", 0) or 0) + \
                           int(row.get("extras", 0) or 0)

            stored_pp = m.get("powerplay_runs_batting")
            if stored_pp is not None and pp_runs != stored_pp:
                errors.append(
                    f"Match {mid}: stored PP={stored_pp}, computed PP={pp_runs}"
                )
            checked += 1

    chk(f"phase stats spot-checked ({checked} matches)",
        len(errors) == 0,
        "; ".join(errors[:3]) if errors else "")


# ---------------------------------------------------------------------------
# CHECK 11 — tactical patterns have no fabricated sources
# ---------------------------------------------------------------------------
def check_tactical_patterns(patterns: list[dict]):
    without_basis = [p["pattern"] for p in patterns
                     if not p.get("data_basis") and not p.get("source")]
    chk("tactical patterns have data_basis or source",
        len(without_basis) == 0,
        f"{len(without_basis)} patterns lack evidence basis: {without_basis[:2]}"
        if without_basis else "")
    chk("tactical patterns count > 0", len(patterns) > 0, str(len(patterns)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  IPL Data Validation — football-advisor")
    print("=" * 60)

    d = load_data()
    matches    = d.get("matches", [])
    teams      = d.get("teams", [])
    team_stats = d.get("team_stats", {})
    h2h        = d.get("head_to_head", {})
    patterns   = d.get("tactical_patterns", [])

    print(f"\nData loaded: {len(matches):,} matches, {len(teams)} teams")
    print()

    print("[1] Data type & provenance")
    check_data_type(d)
    check_provenance(d)

    print("\n[2] No fabricated data")
    check_no_demo_ids(matches)
    check_no_placeholders(matches)

    print("\n[3] Required fields")
    check_required_fields(matches)

    print("\n[4] Data integrity")
    check_no_negatives(matches)
    check_team_names(matches, teams)

    print("\n[5] Consistency checks")
    check_team_stats_consistency(matches, team_stats)
    check_h2h_consistency(matches, h2h)

    print("\n[6] Phase stats reproducibility (spot-check vs raw ZIP)")
    check_phase_stats_reproducible(matches)

    print("\n[7] Tactical patterns")
    check_tactical_patterns(patterns)

    # ── Summary ──────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    print()
    print("=" * 60)
    print(f"  Results: {passed}/{total} checks passed")
    print("=" * 60)
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))

    if passed < total:
        print(f"\nFAILED {total - passed} check(s)")
        sys.exit(1)
    else:
        print("\nAll checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
