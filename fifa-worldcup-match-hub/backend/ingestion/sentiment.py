"""Computes a 1-10 public sentiment score for teams and players in a match.

Text sources (best-effort, free):
- YouTube comments on the match's highlight video, when one exists and an API key is set.
- Google News RSS headlines mentioning the team/player, as a fallback or supplement when the
  YouTube signal is thin (no key, no video yet, or too few comments).

Scoring: VADER (a lexicon-based sentiment analyzer; free, runs locally, no external calls)
gives each text a compound score in [-1, 1], averaged and mapped onto a 1-10 scale.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

import feedparser
import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import settings
from app.models import Match, Player, PlayerSentiment, Team, TeamSentiment

logger = logging.getLogger(__name__)

_analyzer = SentimentIntensityAnalyzer()
_MIN_SAMPLE_FOR_CONFIDENT_SCORE = 5

_YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]{11})")


def _extract_youtube_id(url: str) -> str | None:
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def fetch_youtube_comments(video_url: str, max_results: int = 50) -> list[str]:
    if not settings.youtube_api_key:
        return []
    video_id = _extract_youtube_id(video_url)
    if not video_id:
        return []
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": max_results,
                    "textFormat": "plainText",
                    "key": settings.youtube_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.warning("YouTube comments fetch failed for video %s", video_id, exc_info=True)
        return []
    return [
        item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
        for item in data.get("items", [])
    ]


def fetch_news_headlines(query: str, max_results: int = 20) -> list[str]:
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
    except Exception:
        logger.warning("News RSS fetch failed for query %r", query, exc_info=True)
        return []
    return [entry.title for entry in feed.entries[:max_results]]


def score_texts(texts: list[str]) -> tuple[float, int]:
    """Returns (score 1-10, sample_size). Defaults to a neutral 5.5 with 0 samples."""
    if not texts:
        return 5.5, 0
    compounds = [_analyzer.polarity_scores(t)["compound"] for t in texts]
    avg_compound = sum(compounds) / len(compounds)
    score = round((avg_compound + 1) * 4.5 + 1, 1)  # map [-1, 1] -> [1, 10]
    return score, len(texts)


def _gather_texts(subject_query: str, video_url: str | None) -> tuple[list[str], list[str]]:
    """Returns (texts, sources_used)."""
    texts: list[str] = []
    sources: list[str] = []

    if video_url:
        comments = fetch_youtube_comments(video_url)
        if comments:
            texts.extend(comments)
            sources.append("youtube")

    if len(texts) < _MIN_SAMPLE_FOR_CONFIDENT_SCORE:
        headlines = fetch_news_headlines(subject_query)
        if headlines:
            texts.extend(headlines)
            sources.append("news")

    return texts, sources


def compute_match_sentiment(db, match: Match) -> None:
    """Computes and upserts team-level and player-level sentiment for a finished/live match.
    Best-effort: any fetch failure for one subject is logged and skipped, never raised, since
    sentiment is a supplementary feature that must never block core match ingestion.
    """
    db.query(TeamSentiment).filter(TeamSentiment.match_id == match.id).delete()
    db.query(PlayerSentiment).filter(PlayerSentiment.match_id == match.id).delete()

    for team_id in (match.home_team_id, match.away_team_id):
        try:
            team = db.get(Team, team_id)
            texts, sources = _gather_texts(f"{team.name} World Cup 2026", match.highlight_video_url)
            score, sample_size = score_texts(texts)
            db.add(
                TeamSentiment(
                    match_id=match.id, team_id=team_id, score=score,
                    sample_size=sample_size, sources=",".join(sources),
                )
            )
        except Exception:
            logger.warning("Sentiment scoring failed for team %s in match %s", team_id, match.id, exc_info=True)

    from app.models import PlayerMatchStat

    player_ids = [r[0] for r in db.query(PlayerMatchStat.player_id).filter_by(match_id=match.id).all()]
    for player_id in player_ids:
        try:
            player = db.get(Player, player_id)
            texts, sources = _gather_texts(f"{player.name} World Cup 2026", match.highlight_video_url)
            score, sample_size = score_texts(texts)
            db.add(
                PlayerSentiment(
                    match_id=match.id, player_id=player_id, score=score,
                    sample_size=sample_size, sources=",".join(sources),
                )
            )
        except Exception:
            logger.warning("Sentiment scoring failed for player %s in match %s", player_id, match.id, exc_info=True)
