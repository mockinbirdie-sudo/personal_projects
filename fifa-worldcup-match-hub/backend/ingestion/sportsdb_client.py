"""Thin wrapper around TheSportsDB v1 REST API — the primary data source for fixtures,
match timelines, basic stats, and all images.

Docs: https://www.thesportsdb.com/free_api
"""
from __future__ import annotations

import time

import httpx

from app.config import settings

# TheSportsDB's free key is a shared public key used by many consumers; space requests out
# to avoid tripping a burst rate limit, and retry once with backoff on 429/5xx.
_MIN_SECONDS_BETWEEN_REQUESTS = 1.5
_RETRY_BACKOFF_SECONDS = 10


class TheSportsDbClient:
    def __init__(self, api_key: str | None = None, host: str | None = None) -> None:
        self.api_key = api_key or settings.sportsdb_key
        self.host = host or settings.sportsdb_host
        self.base_url = f"https://{self.host}/api/v1/json/{self.api_key}"
        self._last_request_at: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(_MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    def _get(self, path: str, params: dict, _retried: bool = False) -> dict:
        self._throttle()
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
            self._last_request_at = time.monotonic()
            if resp.status_code in (429, 502, 503) and not _retried:
                time.sleep(_RETRY_BACKOFF_SECONDS)
                return self._get(path, params, _retried=True)
            resp.raise_for_status()
            return resp.json()

    def get_events_for_date(self, date: str, league_id: int | None = None) -> list[dict]:
        """All events for a date (YYYY-MM-DD), filtered to the given league (World Cup by default)."""
        league_id = league_id or settings.sportsdb_league_id
        data = self._get("/eventsday.php", {"d": date, "l": league_id})
        return data.get("events") or []

    def get_timeline(self, event_id: int) -> list[dict]:
        data = self._get("/lookuptimeline.php", {"id": event_id})
        return data.get("timeline") or []

    def get_event_stats(self, event_id: int) -> list[dict]:
        data = self._get("/lookupeventstats.php", {"id": event_id})
        return data.get("eventstats") or []

    def get_lineup(self, event_id: int) -> list[dict]:
        data = self._get("/lookuplineup.php", {"id": event_id})
        return data.get("lineup") or []
