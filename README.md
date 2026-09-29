# IPL AI Game Strategy Advisor

> College Agentic AI Demonstration Project  
> IBM watsonx.ai · IBM Granite · RAG · Multi-Agent Architecture  
> Real Cricsheet IPL Data · CC BY 4.0

---

## Project Overview

An AI-powered IPL (Indian Premier League) tactical advisor that uses:
- **Real Cricsheet IPL data** — 1,243 matches across 19 seasons (2007/08–2026)
- **RAG (Retrieval-Augmented Generation)** over ball-by-ball derived match statistics
- **4-agent pipeline** for end-to-end tactical analysis
- **IBM Granite** via watsonx.ai for natural language insights
- **Rule-based fallback** so it works without any API key

---

## Architecture

```
Real Cricsheet IPL Data (ipl_match_data.json)
         │  1,243 matches · 284,465 deliveries · 19 seasons
         ▼
   RAG Pipeline (rag.py)
   Keyword-based retrieval over IPL match records,
   team stats, and tactical patterns
         │
         ▼
┌──────────────────────────────────────────┐
│  Agent 1: IPL Match Analysis Agent       │  → Retrieves & aggregates IPL history
│  Agent 2: IPL Opponent Strategy Agent    │  → Profiles batting/bowling patterns
│  Agent 3: IPL Strategy Recommendation   │  → Phase-by-phase game plan
│  Agent 4: IPL Insight Explanation Agent │  → Plain coaching insights (Granite/fallback)
└──────────────────────────────────────────┘
         │
         ▼
   Flask REST API (app.py)
         │
         ▼
   IPL Dashboard (frontend/)
```

---

## File Structure

```
football-advisor/
├── backend/
│   ├── app.py                  ← Flask API server (IPL endpoints only)
│   ├── cricket_agents.py       ← 4 IPL agents + What-If + Real-Time engines
│   ├── rag.py                  ← IPL RAG retrieval pipeline
│   ├── ingest_ipl_data.py      ← Cricsheet data ingestion script
│   ├── validate_ipl_data.py    ← IPL data validation script
│   ├── requirements.txt
│   └── data/
│       ├── ipl_match_data.json         ← Real Cricsheet IPL data (1,243 matches)
│       └── cricsheet_cache/
│           └── ipl_csv2.zip            ← Cached Cricsheet raw ball-by-ball data
└── frontend/
    ├── index.html              ← Single-page IPL dashboard
    ├── app.js                  ← Frontend logic
    └── style.css               ← Dark sports analytics theme
```

---

## Quick Start

### 1. Install Python dependencies

```bash
cd football-advisor/backend
pip install -r requirements.txt
```

### 2. (Optional) Configure IBM watsonx.ai

Set these environment variables to enable IBM Granite text generation:

```bash
set WATSONX_API_KEY=your_api_key_here
set WATSONX_PROJECT_ID=your_project_id_here
set WATSONX_URL=https://us-south.ml.cloud.ibm.com
```

Without these, the system runs in **rule-based fallback mode** — all analysis, recommendations, and tactical advice are fully functional.

### 3. Start the backend

```bash
cd football-advisor/backend
python app.py
```

Backend will be available at `http://localhost:5000`

### 4. Open the frontend

Open `football-advisor/frontend/index.html` in a browser.

> **Note:** If you encounter CORS issues with a plain file:// URL, serve the frontend with:
> ```bash
> cd football-advisor/frontend
> python -m http.server 8080
> ```
> Then visit `http://localhost:8080`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cricket/teams` | IPL teams, venues, seasons, provenance |
| GET | `/api/cricket/matches?team=Name` | IPL matches (optional team filter) |
| GET | `/api/cricket/team-stats/<name>` | Stats for a single IPL team |
| POST | `/api/cricket/analyze` | Run full 4-agent IPL analysis |
| POST | `/api/cricket/what-if` | Cricket What-If scenario simulation |
| POST | `/api/cricket/realtime` | Live cricket event tactical insight |
| GET | `/api/cricket/tactical-patterns` | All IPL RAG tactical patterns |
| GET | `/api/health` | Health check + watsonx status |

### POST /api/cricket/analyze
```json
{
  "our_team": "Chennai Super Kings",
  "opponent": "Mumbai Indians",
  "venue": "MA Chidambaram Stadium, Chepauk",
  "season": "2023"
}
```

### POST /api/cricket/what-if
```json
{
  "scenario": "We lost 2 wickets in the powerplay",
  "our_team": "Chennai Super Kings",
  "opponent": "Mumbai Indians"
}
```

### POST /api/cricket/realtime
```json
{
  "event": "Opponent scored 68 in the powerplay",
  "our_team": "Chennai Super Kings",
  "opponent": "Mumbai Indians"
}
```

---

## IPL Teams Available

| Team | Seasons |
|------|---------|
| Chennai Super Kings | 2007/08–2026 |
| Mumbai Indians | 2007/08–2026 |
| Royal Challengers Bengaluru | 2007/08–2026 |
| Kolkata Knight Riders | 2007/08–2026 |
| Punjab Kings | 2007/08–2026 |
| Rajasthan Royals | 2007/08–2026 |
| Delhi Capitals | 2007/08–2026 |
| Sunrisers Hyderabad | 2013–2026 |
| Gujarat Titans | 2022–2026 |
| Lucknow Super Giants | 2022–2026 |
| Deccan Chargers | 2007/08–2012 |
| Rising Pune Supergiants | 2016–2017 |
| Gujarat Lions | 2016–2017 |
| Kochi Tuskers Kerala | 2011 |
| Pune Warriors | 2011–2013 |

---

## User Flow

1. **Select Our Team** from the sidebar dropdown (IPL teams)
2. **Select Opponent** from the sidebar dropdown
3. Optionally select **Venue** and **Season**
4. Click **Run IPL Agent Analysis**
5. Explore:
   - **Overview tab**: Team stats, phase averages, key insights
   - **Opponent Analysis tab**: Batting/bowling patterns, H2H, RAG evidence
   - **Recommendations tab**: Phase-by-phase game plan with historical evidence
   - **Match History tab**: Retrieved real IPL matches with scores
6. Use the **What-If Simulator** — select a scenario or type a custom one
7. Use the **Live Event Demo** — enter a simulated live match event

---

## Data Provenance

**Real IPL Data** sourced from [Cricsheet](https://cricsheet.org) by Stephen Rushe.  
Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).  
Phase statistics (powerplay/middle/death overs) are derived directly from 284,465 ball-by-ball delivery records.  
No interpolation or fabrication — all statistics are computed from raw data.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| AI Model | IBM Granite (ibm/granite-13b-chat-v2) via watsonx.ai |
| RAG | In-memory keyword retrieval (production: FAISS + watsonx embeddings) |
| Backend | Python 3.10+, Flask 3 |
| Frontend | Vanilla HTML/CSS/JS (no framework required) |
| Data | Real Cricsheet IPL ball-by-ball data (CC BY 4.0) |
