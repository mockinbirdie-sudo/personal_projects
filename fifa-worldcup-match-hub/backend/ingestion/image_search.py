"""Optional: real match photos via Google Custom Search (image search), scoped to a curated
list of football/news domains (Google discontinued free whole-web search for new Custom Search
engines in 2026). Supplements TheSportsDB's images, which are often just team logos for matches
that haven't been editorially curated yet.

Free tier: 100 queries/day. Callers must search at most once per match (see
Match.custom_images_fetched) to stay well within that budget.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_match_images(query: str, max_results: int = 5) -> list[str]:
    if not settings.youtube_api_key or not settings.search_engine_id:
        return []
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.youtube_api_key,
                    "cx": settings.search_engine_id,
                    "q": query,
                    "searchType": "image",
                    "num": max_results,
                    "safe": "active",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.warning("Custom Search image fetch failed for query %r", query, exc_info=True)
        return []
    return [item["link"] for item in data.get("items", []) if item.get("link")]
