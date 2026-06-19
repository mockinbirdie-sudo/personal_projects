"""Scheduled ingestion job: TheSportsDB is the primary source for fixtures, timelines, basic
stats, and images. If an API-Football key is configured and working, it's used as an optional
enhancement layer for richer per-match/per-player stats — its failure (suspension, rate limit,
no key) never blocks or wipes the TheSportsDB data already ingested.

Run manually:    python -m ingestion.fetch_matches
Run on a timer:  see start_scheduler() below, called from app.main on FastAPI startup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal, init_db
from ingestion.api_football_client import ApiFootballClient
from ingestion.normalize import (
    enhance_with_api_football,
    recompute_tournament_stats,
    upsert_events_sportsdb,
    upsert_lineup_sportsdb,
    upsert_match_sportsdb,
    upsert_match_stats_sportsdb,
)
from ingestion.sentiment import compute_match_sentiment
from ingestion.sportsdb_client import TheSportsDbClient

logger = logging.getLogger(__name__)


def _dates_in_last_24h() -> list[str]:
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)
    dates = {yesterday.date().isoformat(), now.date().isoformat()}
    return sorted(dates)


def run_ingestion() -> int:
    """Ingests World Cup fixtures within the last 24h from TheSportsDB, then optionally
    enhances with API-Football stats. Returns the number of fixtures processed.
    """
    sportsdb = TheSportsDbClient()
    af_client = ApiFootballClient() if settings.api_football_key else None

    db = SessionLocal()
    processed = 0
    try:
        events: list[dict] = []
        for date in _dates_in_last_24h():
            events.extend(sportsdb.get_events_for_date(date))

        for event_json in events:
            match = upsert_match_sportsdb(db, event_json)
            db.commit()

            if match.status not in ("NS", "TBD", ""):
                try:
                    timeline = sportsdb.get_timeline(match.id)
                    stats = sportsdb.get_event_stats(match.id)
                    lineup = sportsdb.get_lineup(match.id)

                    upsert_lineup_sportsdb(db, match, lineup)
                    upsert_events_sportsdb(db, match, timeline)
                    upsert_match_stats_sportsdb(db, match, stats)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.warning("Skipping TheSportsDB detail ingestion for match %s", match.id, exc_info=True)

                if af_client is not None:
                    try:
                        enhance_with_api_football(db, match, af_client)
                        db.commit()
                    except Exception:
                        db.rollback()
                        logger.warning(
                            "API-Football enhancement unavailable for match %s — continuing without it",
                            match.id,
                            exc_info=True,
                        )

                try:
                    compute_match_sentiment(db, match)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.warning("Sentiment computation failed for match %s", match.id, exc_info=True)

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
