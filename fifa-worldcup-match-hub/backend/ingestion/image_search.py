"""Optional: real match photos via NewsAPI.org's /v2/everything, which (unlike Google News RSS)
returns an actual `urlToImage` per article — real article photos, no scraping needed. Supplements
TheSportsDB's images, which are sometimes just team logos for matches not yet editorially curated.

NOTE: NewsAPI.org's free Developer plan is licensed for development/testing only, not production
use. Used here anyway by explicit choice — see conversation/decision log if revisiting this.

Free tier: 100 requests/day. Callers must search at most once per match (see
Match.custom_images_fetched) to stay well within that budget.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_match_images(query: str, max_results: int = 5) -> list[str]:
    if not settings.news_api_key:
        return []
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "apiKey": settings.news_api_key,
                    "q": query,
                    "pageSize": max_results,
                    "sortBy": "relevancy",
                    "language": "en",
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    "NewsAPI image fetch failed for query %r: %s %s",
                    query, resp.status_code, resp.text[:500],
                )
                return []
            data = resp.json()
    except httpx.HTTPError:
        logger.warning("NewsAPI image fetch failed for query %r", query, exc_info=True)
        return []
    return [a["urlToImage"] for a in data.get("articles", []) if a.get("urlToImage")]
