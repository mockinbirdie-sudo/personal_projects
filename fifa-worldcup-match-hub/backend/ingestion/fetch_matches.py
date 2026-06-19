"""Scheduled ingestion job: pulls World Cup fixtures (defaulting to the last 24h window)
plus their events/stats/player-stats, and upserts everything into the DB.

Run manually:    python -m ingestion.fetch_matches
Run on a timer:  see schedule() below (APScheduler), invoked from app.main on startup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal, init_db
from ingestion.api_football_client import ApiFootballClient
from ingestion.normalize import (
    recompute_tournament_stats,
    upsert_events,
    upsert_fixture,
    upsert_match_stats,
    upsert_player_match_stats,
)

logger = logging.getLogger(__name__)


def _dates_in_last_24h() -> list[str]:
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)
    dates = {yesterday.date().isoformat(), now.date().isoformat()}
    return sorted(dates)


def run_ingestion(league_id: int | None = None, season: int | None = None) -> int:
    """Fetches fixtures for the configured league/season within the last 24h and stores them.

    Returns the number of fixtures processed.
    """
    league_id = league_id or settings.wc_league_id
    season = season or settings.wc_season
    client = ApiFootballClient()
    db = SessionLocal()
    processed = 0
    try:
        fixtures: list[dict] = []
        for date in _dates_in_last_24h():
            fixtures.extend(client.get_fixtures(league_id, season, date=date))

        for fixture_json in fixtures:
            fixture_id = fixture_json["fixture"]["id"]
            upsert_fixture(db, fixture_json)
            db.commit()

            if fixture_json["fixture"]["status"]["short"] not in ("NS", "TBD"):
                try:
                    events = client.get_fixture_events(fixture_id)
                    upsert_events(db, fixture_id, events)

                    stats = client.get_fixture_statistics(fixture_id)
                    if stats:
                        upsert_match_stats(db, fixture_id, stats)

                    player_stats = client.get_fixture_player_stats(fixture_id)
                    if player_stats:
                        upsert_player_match_stats(db, fixture_id, player_stats)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.warning("Skipping detail ingestion for fixture %s after error", fixture_id, exc_info=True)

            processed += 1

        recompute_tournament_stats(db)
        db.commit()
        logger.info("Ingestion complete: %d fixtures processed", processed)
    except Exception:
        db.rollback()
        logger.exception("Ingestion run failed")
        raise
    finally:
        db.close()
    return processed


def start_scheduler() -> BackgroundScheduler:
    """Runs ingestion every 20 minutes in the background. Call once from the FastAPI app startup."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_ingestion, "interval", minutes=20, next_run_time=datetime.now())
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    count = run_ingestion()
    print(f"Processed {count} fixtures")
