from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, init_db
from app.models import (
    Match,
    MatchEvent,
    MatchStat,
    Player,
    PlayerMatchStat,
    PlayerSentiment,
    PlayerTournamentStat,
    TeamSentiment,
)
from app.schemas import (
    EventOut,
    MatchSentimentOut,
    MatchStatOut,
    MatchSummaryOut,
    MatchTimelineOut,
    PlayerMatchStatOut,
    PlayerSentimentOut,
    PlayerTournamentStatOut,
    TeamOut,
    TeamSentimentOut,
)

app = FastAPI(title="World Cup Match Hub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    from ingestion.fetch_matches import start_scheduler

    start_scheduler()


def _key_events_for(match: Match) -> list[str]:
    highlights = []
    for ev in sorted(match.events, key=lambda e: e.minute):
        if ev.type == "Goal":
            highlights.append(f"⚽ {ev.minute}' Goal ({ev.detail})")
        elif ev.type == "Card" and ev.detail == "Red Card":
            highlights.append(f"\U0001F7E5 {ev.minute}' Red Card")
    return highlights[:3]


def _to_match_summary(match: Match) -> MatchSummaryOut:
    images = [u for u in match.highlight_image_urls.split(",") if u]
    return MatchSummaryOut(
        id=match.id,
        home_team=TeamOut.model_validate(match.home_team),
        away_team=TeamOut.model_validate(match.away_team),
        kickoff_utc=match.kickoff_utc,
        status=match.status,
        home_score=match.home_score,
        away_score=match.away_score,
        venue=match.venue,
        stage=match.stage,
        highlight_images=images,
        highlight_video_url=match.highlight_video_url,
        key_events=_key_events_for(match),
    )


@app.get("/matches/recent", response_model=list[MatchSummaryOut])
def get_recent_matches(db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    matches = (
        db.query(Match)
        .filter(Match.kickoff_utc >= cutoff)
        .order_by(Match.kickoff_utc.desc())
        .all()
    )
    return [_to_match_summary(m) for m in matches]


@app.get("/matches/{match_id}/timeline", response_model=MatchTimelineOut)
def get_match_timeline(match_id: int, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.minute)
        .all()
    )
    stats = db.query(MatchStat).filter(MatchStat.match_id == match_id).all()
    return MatchTimelineOut(
        match=_to_match_summary(match),
        events=[EventOut.model_validate(e) for e in events],
        stats=[MatchStatOut.model_validate(s) for s in stats],
    )


@app.get("/matches/{match_id}/players", response_model=list[PlayerMatchStatOut])
def get_match_players(match_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(PlayerMatchStat, Player)
        .join(Player, Player.id == PlayerMatchStat.player_id)
        .filter(PlayerMatchStat.match_id == match_id)
        .all()
    )
    return [
        PlayerMatchStatOut(
            player_id=p.id,
            player_name=p.name,
            team_id=pms.team_id,
            position=p.position,
            minutes_played=pms.minutes_played,
            goals=pms.goals,
            assists=pms.assists,
            shots_total=pms.shots_total,
            shots_on_target=pms.shots_on_target,
            passes_total=pms.passes_total,
            passes_accuracy=pms.passes_accuracy,
            tackles=pms.tackles,
            duels_won=pms.duels_won,
            dribbles_success=pms.dribbles_success,
            fouls_committed=pms.fouls_committed,
            yellow_cards=pms.yellow_cards,
            red_cards=pms.red_cards,
            rating=pms.rating,
        )
        for pms, p in rows
    ]


@app.get("/players/{player_id}/tournament", response_model=PlayerTournamentStatOut)
def get_player_tournament_stats(player_id: int, db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    stats = db.get(PlayerTournamentStat, player_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="No tournament stats for this player yet")
    return PlayerTournamentStatOut(
        player_id=player.id,
        player_name=player.name,
        team_id=player.team_id,
        position=player.position,
        matches_played=stats.matches_played,
        minutes_played=stats.minutes_played,
        goals=stats.goals,
        assists=stats.assists,
        shots_total=stats.shots_total,
        shots_on_target=stats.shots_on_target,
        passes_total=stats.passes_total,
        passes_accuracy_avg=stats.passes_accuracy_avg,
        tackles=stats.tackles,
        yellow_cards=stats.yellow_cards,
        red_cards=stats.red_cards,
        rating_avg=stats.rating_avg,
    )


@app.get("/matches/{match_id}/sentiment", response_model=MatchSentimentOut)
def get_match_sentiment(match_id: int, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    team_rows = db.query(TeamSentiment).filter(TeamSentiment.match_id == match_id).all()
    player_rows = (
        db.query(PlayerSentiment, Player)
        .join(Player, Player.id == PlayerSentiment.player_id)
        .filter(PlayerSentiment.match_id == match_id)
        .all()
    )
    return MatchSentimentOut(
        teams=[
            TeamSentimentOut(
                team_id=t.team_id,
                score=t.score,
                sample_size=t.sample_size,
                sources=[s for s in t.sources.split(",") if s],
                summary=t.summary,
            )
            for t in team_rows
        ],
        players=[
            PlayerSentimentOut(
                player_id=ps.player_id,
                player_name=p.name,
                score=ps.score,
                sample_size=ps.sample_size,
                sources=[s for s in ps.sources.split(",") if s],
                summary=ps.summary,
            )
            for ps, p in player_rows
        ],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/reset-db")
def reset_db(token: str):
    """One-time schema reset for picking up model changes (e.g. new columns) that
    create_all() can't apply to existing tables. Requires ADMIN_RESET_TOKEN to be set
    and matched; disabled (404) when the token env var is empty.
    """
    if not settings.admin_reset_token or token != settings.admin_reset_token:
        raise HTTPException(status_code=404)
    from app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "reset"}
