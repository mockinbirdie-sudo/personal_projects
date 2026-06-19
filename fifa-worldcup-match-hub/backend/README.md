# World Cup Match Hub — Backend

Python/FastAPI service that ingests FIFA World Cup match data from [API-Football](https://www.api-football.com/)
and serves it to the Lovable frontend.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in API_FOOTBALL_KEY
```

Get a free API-Football key at https://dashboard.api-football.com/register (RapidAPI or direct, free tier
includes historical World Cup data — `WC_SEASON=2022` works today; switch to `2026` once fixtures exist).

## Run tests (no API key required — uses local sample_data/ fixtures)

```bash
pytest
```

## Run the ingestion job once

```bash
python -m ingestion.fetch_matches
```

Pulls fixtures for `WC_LEAGUE_ID`/`WC_SEASON` (.env) within the last 24h, plus events/stats/player-stats,
and stores them in the DB at `DATABASE_URL` (defaults to local SQLite `worldcup.db`).

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Endpoints:
- `GET /matches/recent` — matches from the last 24h (Screen 1)
- `GET /matches/{id}/timeline` — events + stats for a match (Screen 2)
- `GET /matches/{id}/players` — per-match player stats (Screen 3, match view)
- `GET /players/{id}/tournament` — cumulative tournament stats for a player (Screen 3, tournament view)
- `GET /health`

## Deploying

Container-friendly FastAPI app — deploy to Render/Railway free tier with `DATABASE_URL` pointed at a
Supabase/Postgres instance and `API_FOOTBALL_KEY` set as an env var. Call `start_scheduler()` from
`ingestion.fetch_matches` at app startup (or run it as a separate scheduled job) to keep data fresh.
