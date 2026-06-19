"""Maps raw API-Football JSON payloads onto the internal SQLAlchemy schema."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Match,
    MatchEvent,
    MatchStat,
    Player,
    PlayerMatchStat,
    PlayerTournamentStat,
    Team,
)

_STAT_KEY_MAP = {
    "Ball Possession": "possession",
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on_target",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Offsides": "offsides",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Total passes": "passes_total",
    "Passes %": "pass_accuracy",
    "expected_goals": "xg",
}


def _to_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("%", "").strip()
        if value in ("", "None"):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_team(db: Session, team_json: dict) -> Team:
    team = db.get(Team, team_json["id"])
    if team is None:
        team = Team(id=team_json["id"], name=team_json["name"], logo_url=team_json.get("logo", ""))
        db.add(team)
    else:
        team.name = team_json["name"]
        team.logo_url = team_json.get("logo", "")
    return team


def upsert_fixture(db: Session, fixture_json: dict, highlight_image_urls: list[str] | None = None) -> Match:
    fx = fixture_json["fixture"]
    league = fixture_json["league"]
    teams = fixture_json["teams"]
    goals = fixture_json["goals"]

    home_team = upsert_team(db, teams["home"])
    away_team = upsert_team(db, teams["away"])

    match = db.get(Match, fx["id"])
    kickoff = datetime.fromisoformat(fx["date"].replace("Z", "+00:00"))
    images = ",".join(highlight_image_urls or [teams["home"].get("logo", ""), teams["away"].get("logo", "")])

    if match is None:
        match = Match(
            id=fx["id"],
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            kickoff_utc=kickoff,
            status=fx["status"]["short"],
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            venue=(fx.get("venue") or {}).get("name", "") or "",
            stage=league.get("round", ""),
            highlight_image_urls=images,
        )
        db.add(match)
    else:
        match.status = fx["status"]["short"]
        match.home_score = goals.get("home")
        match.away_score = goals.get("away")
        match.stage = league.get("round", "")
        match.highlight_image_urls = images
    return match


def upsert_events(db: Session, match_id: int, events_json: list[dict]) -> None:
    db.query(MatchEvent).filter(MatchEvent.match_id == match_id).delete()
    for ev in events_json:
        player = ev.get("player") or {}
        assist = ev.get("assist") or {}
        db.add(
            MatchEvent(
                match_id=match_id,
                minute=ev["time"]["elapsed"],
                extra_minute=ev["time"].get("extra"),
                type=ev["type"],
                detail=ev.get("detail", ""),
                team_id=ev["team"]["id"],
                player_id=player.get("id"),
                assist_player_id=assist.get("id"),
                description=ev.get("comments") or "",
            )
        )


def upsert_match_stats(db: Session, match_id: int, stats_json: list[dict]) -> None:
    db.query(MatchStat).filter(MatchStat.match_id == match_id).delete()
    for team_stats in stats_json:
        team_id = team_stats["team"]["id"]
        fields: dict[str, float | None] = {}
        for entry in team_stats.get("statistics", []):
            key = _STAT_KEY_MAP.get(entry["type"])
            if key:
                fields[key] = _to_number(entry["value"])
        db.add(MatchStat(match_id=match_id, team_id=team_id, **fields))


def upsert_player_match_stats(db: Session, match_id: int, player_stats_json: list[dict]) -> None:
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id == match_id).delete()
    for team_block in player_stats_json:
        team_id = team_block["team"]["id"]
        for entry in team_block.get("players", []):
            p = entry["player"]
            stats = (entry.get("statistics") or [{}])[0]
            games = stats.get("games") or {}
            goals = stats.get("goals") or {}
            shots = stats.get("shots") or {}
            passes = stats.get("passes") or {}
            tackles = stats.get("tackles") or {}
            dribbles = stats.get("dribbles") or {}
            fouls = stats.get("fouls") or {}
            cards = stats.get("cards") or {}

            player = db.get(Player, p["id"])
            if player is None:
                player = Player(id=p["id"], name=p["name"], team_id=team_id, photo_url=p.get("photo", ""))
                db.add(player)
            player.position = games.get("position") or player.position

            db.add(
                PlayerMatchStat(
                    player_id=p["id"],
                    match_id=match_id,
                    team_id=team_id,
                    minutes_played=games.get("minutes") or 0,
                    goals=goals.get("total") or 0,
                    assists=goals.get("assists") or 0,
                    shots_total=shots.get("total") or 0,
                    shots_on_target=shots.get("on") or 0,
                    passes_total=passes.get("total") or 0,
                    passes_accuracy=_to_number(passes.get("accuracy")),
                    tackles=tackles.get("total") or 0,
                    duels_won=(stats.get("duels") or {}).get("won") or 0,
                    dribbles_success=dribbles.get("success") or 0,
                    fouls_committed=fouls.get("committed") or 0,
                    yellow_cards=cards.get("yellow") or 0,
                    red_cards=cards.get("red") or 0,
                    rating=_to_number(games.get("rating")),
                )
            )


def recompute_tournament_stats(db: Session) -> None:
    """Recomputes per-player tournament aggregates from all stored player_match_stats."""
    db.query(PlayerTournamentStat).delete()
    rows = (
        db.query(
            PlayerMatchStat.player_id,
            func.count(PlayerMatchStat.match_id),
            func.sum(PlayerMatchStat.minutes_played),
            func.sum(PlayerMatchStat.goals),
            func.sum(PlayerMatchStat.assists),
            func.sum(PlayerMatchStat.shots_total),
            func.sum(PlayerMatchStat.shots_on_target),
            func.sum(PlayerMatchStat.passes_total),
            func.avg(PlayerMatchStat.passes_accuracy),
            func.sum(PlayerMatchStat.tackles),
            func.sum(PlayerMatchStat.yellow_cards),
            func.sum(PlayerMatchStat.red_cards),
            func.avg(PlayerMatchStat.rating),
        )
        .group_by(PlayerMatchStat.player_id)
        .all()
    )
    for (
        player_id,
        matches_played,
        minutes_played,
        goals,
        assists,
        shots_total,
        shots_on_target,
        passes_total,
        passes_accuracy_avg,
        tackles,
        yellow_cards,
        red_cards,
        rating_avg,
    ) in rows:
        db.add(
            PlayerTournamentStat(
                player_id=player_id,
                matches_played=matches_played or 0,
                minutes_played=minutes_played or 0,
                goals=goals or 0,
                assists=assists or 0,
                shots_total=shots_total or 0,
                shots_on_target=shots_on_target or 0,
                passes_total=passes_total or 0,
                passes_accuracy_avg=passes_accuracy_avg,
                tackles=tackles or 0,
                yellow_cards=yellow_cards or 0,
                red_cards=red_cards or 0,
                rating_avg=rating_avg,
            )
        )
