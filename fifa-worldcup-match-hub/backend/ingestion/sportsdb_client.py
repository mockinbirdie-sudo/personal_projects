"""Thin wrapper around TheSportsDB v1 REST API — the primary data source for fixtures,
match timelines, basic stats, and all images.

Docs: https://www.thesportsdb.com/free_api
"""
from __future__ import annotations

import httpx

from app.config import settings


class TheSportsDbClient:
    def __init__(self, api_key: str | None = None, host: str | None = None) -> None:
        self.api_key = api_key or settings.sportsdb_key
        self.host = host or settings.sportsdb_host
        self.base_url = f"https://{self.host}/api/v1/json/{self.api_key}"

    def _get(self, path: str, params: dict) -> dict:
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
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
