"""Thin wrapper around the API-Football v3 REST API.

Docs: https://www.api-football.com/documentation-v3
"""
from __future__ import annotations

import time

import httpx

from app.config import settings

# API-Football's free plan caps requests at 10/minute. Space calls out comfortably under
# that (6.5s apart) and retry once with a longer backoff if we still get rate-limited.
_MIN_SECONDS_BETWEEN_REQUESTS = 6.5
_RATE_LIMIT_RETRY_SECONDS = 65


class ApiFootballClient:
    def __init__(self, api_key: str | None = None, host: str | None = None) -> None:
        self.api_key = api_key or settings.api_football_key
        self.host = host or settings.api_football_host
        self.base_url = f"https://{self.host}"
        self._last_request_at: float = 0.0

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(_MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    def _get(self, path: str, params: dict, _retried: bool = False) -> dict:
        self._throttle()
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            self._last_request_at = time.monotonic()
            if resp.status_code == 429 and not _retried:
                time.sleep(_RATE_LIMIT_RETRY_SECONDS)
                return self._get(path, params, _retried=True)
            resp.raise_for_status()
            return resp.json()

    def get_fixtures(self, league_id: int, season: int, date: str | None = None) -> list[dict]:
        """Fixtures for a league/season, optionally filtered to a single date (YYYY-MM-DD).

        API-Football's free plan rejects the `season` filter outside 2022-2024, even when the
        `league`+`date` combination is otherwise within the allowed (current) date window. A
        bare `date` query is not subject to that restriction, so we fetch by date and filter
        for the target league client-side instead of passing `league`/`season` to the API.
        """
        params: dict = {}
        if date:
            params["date"] = date
        data = self._get("/fixtures", params)
        fixtures = data.get("response", [])
        return [
            f for f in fixtures
            if f["league"]["id"] == league_id and f["league"]["season"] == season
        ]

    def get_fixture_events(self, fixture_id: int) -> list[dict]:
        data = self._get("/fixtures/events", {"fixture": fixture_id})
        return data.get("response", [])

    def get_fixture_statistics(self, fixture_id: int) -> list[dict]:
        data = self._get("/fixtures/statistics", {"fixture": fixture_id})
        return data.get("response", [])

    def get_fixture_player_stats(self, fixture_id: int) -> list[dict]:
        data = self._get("/fixtures/players", {"fixture": fixture_id})
        return data.get("response", [])
