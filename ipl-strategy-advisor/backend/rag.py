"""
RAG Pipeline — IPL AI Game Strategy Advisor
Retrieves relevant IPL historical match data, team stats, and tactical patterns
using keyword-based similarity scoring over the Cricsheet dataset.

NOTE: This is a lightweight in-memory RAG demonstration using TF-IDF-style
keyword scoring. In production, replace with a vector store (e.g. FAISS,
Chroma) backed by IBM watsonx.ai embeddings.
"""

import json
import os
import re
from typing import Any

IPL_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "ipl_match_data.json")

# ── Load once at import time ──────────────────────────────────────────────────
with open(IPL_DATA_PATH, "r") as fh:
    _IPL_DB: dict = json.load(fh)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Lower-case alphabetic tokens from any string."""
    return set(re.findall(r"[a-z]+", text.lower()))


def _score(doc_text: str, query_tokens: set[str]) -> int:
    """Count query token hits in document text."""
    return len(_tokenize(doc_text) & query_tokens)


def _ipl_match_to_text(m: dict) -> str:
    """Flatten an IPL match record to a searchable string."""
    parts = [
        m.get("team1", ""), m.get("team2", ""),
        m.get("venue", ""), m.get("season", ""),
        m.get("winner", ""), m.get("batting_first", ""),
        m.get("chasing_team", ""), m.get("notes") or "",
    ]
    return " ".join(str(p) for p in parts)


def _ipl_pattern_to_text(p: dict) -> str:
    return (
        f"{p.get('pattern','')} "
        f"{p.get('description','')} "
        f"{' '.join(p.get('affected_teams',[]))}"
    )


# ── Public IPL/Cricket API ────────────────────────────────────────────────────

def get_ipl_teams() -> list[str]:
    return _IPL_DB["teams"]


def get_all_ipl_matches() -> list[dict]:
    return _IPL_DB["matches"]


def get_ipl_venues() -> list[str]:
    return _IPL_DB.get("venues", [])


def get_ipl_seasons() -> list[str]:
    seasons = list({m["season"] for m in _IPL_DB["matches"]})
    return sorted(seasons, reverse=True)


def get_ipl_team_stats(team: str) -> dict | None:
    return _IPL_DB["team_stats"].get(team)


def get_all_ipl_team_stats() -> dict:
    return _IPL_DB["team_stats"]


def get_ipl_tactical_patterns() -> list[dict]:
    return _IPL_DB.get("tactical_patterns", [])


def get_ipl_data_notice() -> str:
    """Return provenance/data-notice string."""
    return _IPL_DB.get("_data_notice", _IPL_DB.get("_provenance", {}).get("source", "IPL data"))


def get_ipl_provenance() -> dict:
    """Return full provenance metadata."""
    return _IPL_DB.get("_provenance", {})


def retrieve_ipl_matches(our_team: str, opponent: str, venue: str = "",
                          season: str = "", top_k: int = 6) -> list[dict]:
    """Return top-k IPL matches most relevant to the given teams/venue/season."""
    query = f"{our_team} {opponent} {venue} {season}"
    query_tokens = _tokenize(query)
    scored = []
    for m in _IPL_DB["matches"]:
        text = _ipl_match_to_text(m)
        base_score = _score(text, query_tokens)
        if our_team in (m["team1"], m["team2"]):
            base_score += 5
        if opponent in (m["team1"], m["team2"]):
            base_score += 5
        if venue and venue == m.get("venue", ""):
            base_score += 3
        if season and season in m.get("season", ""):
            base_score += 2
        scored.append((base_score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:top_k]]


def retrieve_ipl_patterns_for_team(team: str) -> list[dict]:
    """Return IPL tactical patterns that mention the given team."""
    return [
        p for p in _IPL_DB.get("tactical_patterns", [])
        if team in p.get("affected_teams", [])
    ]


def retrieve_ipl_relevant_patterns(query: str, top_k: int = 3) -> list[dict]:
    """Return top-k IPL tactical patterns for a free-text query."""
    query_tokens = _tokenize(query)
    scored = [
        (_score(_ipl_pattern_to_text(p), query_tokens), p)
        for p in _IPL_DB.get("tactical_patterns", [])
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k] if scored and scored[0][0] > 0]


def get_ipl_h2h(team_a: str, team_b: str) -> dict:
    """Return head-to-head record between two IPL teams from the dataset."""
    h2h = _IPL_DB.get("head_to_head", {})
    key1 = f"{team_a}_vs_{team_b}"
    key2 = f"{team_b}_vs_{team_a}"
    return h2h.get(key1) or h2h.get(key2) or {}


def retrieve_ipl_context_for_whatif(scenario: str, our_team: str,
                                     opponent: str) -> dict[str, Any]:
    """Retrieve IPL context snippets relevant to a cricket What-If scenario."""
    query_tokens = _tokenize(f"{scenario} {our_team} {opponent}")
    matches = []
    for m in _IPL_DB["matches"]:
        text = _ipl_match_to_text(m)
        score = _score(text, query_tokens)
        if our_team in (m["team1"], m["team2"]):
            score += 3
        if opponent in (m["team1"], m["team2"]):
            score += 3
        matches.append((score, m))
    matches.sort(key=lambda x: x[0], reverse=True)

    patterns = []
    for p in _IPL_DB.get("tactical_patterns", []):
        text = _ipl_pattern_to_text(p)
        patterns.append((_score(text, query_tokens), p))
    patterns.sort(key=lambda x: x[0], reverse=True)

    return {
        "matches": [m for _, m in matches[:3]],
        "patterns": [p for _, p in patterns[:3] if patterns and patterns[0][0] > 0],
        "our_stats": get_ipl_team_stats(our_team),
        "opponent_stats": get_ipl_team_stats(opponent),
    }
