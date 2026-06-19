"""Maps raw provider JSON payloads onto the internal SQLAlchemy schema.

The `*_af_*`-style functions below (upsert_fixture, upsert_events, upsert_match_stats,
upsert_player_match_stats) map API-Football payloads and are now used only as an optional
enhancement layer (see enhance_with_api_football). The `*_sportsdb` functions are the primary
ingestion path: TheSportsDB supplies fixtures, timelines, basic stats, lineups, and all images.
"""
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


# --- TheSportsDB (primary data source) -------------------------------------------------------

_SPORTSDB_STAT_KEY_MAP = {
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on_target",
    "Ball Possession": "possession",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
}


def _int_or_none(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_team_sportsdb(db: Session, team_id: int, name: str, badge_url: str) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        team = Team(id=team_id, name=name, logo_url=badge_url or "")
        db.add(team)
    else:
        team.name = name
        team.logo_url = badge_url or team.logo_url
    return team


def upsert_match_sportsdb(db: Session, event_json: dict) -> Match:
    match_id = int(event_json["idEvent"])
    home_team = upsert_team_sportsdb(
        db, int(event_json["idHomeTeam"]), event_json["strHomeTeam"], event_json.get("strHomeTeamBadge", "")
    )
    away_team = upsert_team_sportsdb(
        db, int(event_json["idAwayTeam"]), event_json["strAwayTeam"], event_json.get("strAwayTeamBadge", "")
    )

    kickoff = datetime.fromisoformat(event_json["strTimestamp"])
    images = [
        u
        for u in (
            event_json.get("strPoster"),
            event_json.get("strThumb"),
            event_json.get("strBanner"),
            event_json.get("strFanart"),
            event_json.get("strSquare"),
        )
        if u
    ] or [home_team.logo_url, away_team.logo_url]
    video_url = event_json.get("strVideo") or None

    af_id = _int_or_none(event_json.get("idAPIfootball"))

    match = db.get(Match, match_id)
    if match is None:
        match = Match(
            id=match_id,
            api_football_id=af_id,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            kickoff_utc=kickoff,
            status=event_json.get("strStatus") or "NS",
            home_score=_int_or_none(event_json.get("intHomeScore")),
            away_score=_int_or_none(event_json.get("intAwayScore")),
            venue=event_json.get("strVenue") or "",
            stage=(f"Group {event_json['strGroup']}" if event_json.get("strGroup") else f"Round {event_json.get('intRound', '')}").strip(),
            highlight_image_urls=",".join(images),
            highlight_video_url=video_url,
        )
        db.add(match)
    else:
        match.api_football_id = af_id or match.api_football_id
        match.status = event_json.get("strStatus") or match.status
        match.home_score = _int_or_none(event_json.get("intHomeScore"))
        match.away_score = _int_or_none(event_json.get("intAwayScore"))
        match.highlight_image_urls = ",".join(images)
        match.highlight_video_url = video_url or match.highlight_video_url
    return match


def upsert_events_sportsdb(db: Session, match: Match, timeline_json: list[dict]) -> None:
    db.query(MatchEvent).filter(MatchEvent.match_id == match.id).delete()
    goal_counts: dict[int, int] = {}
    assist_counts: dict[int, int] = {}
    yellow_counts: dict[int, int] = {}
    red_counts: dict[int, int] = {}

    for ev in timeline_json:
        player_id = _int_or_none(ev.get("idPlayer")) or None
        assist_id = _int_or_none(ev.get("idAssist")) or None
        team_id = _int_or_none(ev.get("idTeam"))
        ev_type = ev["strTimeline"]
        detail = ev.get("strTimelineDetail") or ""

        db.add(
            MatchEvent(
                match_id=match.id,
                minute=_int_or_none(ev.get("intTime")) or 0,
                extra_minute=None,
                type=ev_type,
                detail=detail,
                team_id=team_id,
                player_id=player_id,
                assist_player_id=assist_id,
                description=(ev.get("strComment") or "").replace("NULL", ""),
            )
        )

        if ev_type == "Goal" and player_id:
            goal_counts[player_id] = goal_counts.get(player_id, 0) + 1
            if assist_id:
                assist_counts[assist_id] = assist_counts.get(assist_id, 0) + 1
        elif ev_type == "Card" and player_id:
            if "Yellow" in detail:
                yellow_counts[player_id] = yellow_counts.get(player_id, 0) + 1
            elif "Red" in detail:
                red_counts[player_id] = red_counts.get(player_id, 0) + 1

    for player_id in set(goal_counts) | set(assist_counts) | set(yellow_counts) | set(red_counts):
        pms = db.query(PlayerMatchStat).filter_by(player_id=player_id, match_id=match.id).one_or_none()
        if pms is None:
            continue  # player not in the ingested lineup; skip rather than guess their team
        pms.goals = goal_counts.get(player_id, pms.goals)
        pms.assists = assist_counts.get(player_id, pms.assists)
        pms.yellow_cards = yellow_counts.get(player_id, pms.yellow_cards)
        pms.red_cards = red_counts.get(player_id, pms.red_cards)


def upsert_match_stats_sportsdb(db: Session, match: Match, eventstats_json: list[dict]) -> None:
    db.query(MatchStat).filter(MatchStat.match_id == match.id).delete()
    if not eventstats_json:
        return
    home_fields: dict[str, float | None] = {}
    away_fields: dict[str, float | None] = {}
    for entry in eventstats_json:
        key = _SPORTSDB_STAT_KEY_MAP.get(entry.get("strStat", ""))
        if not key:
            continue
        home_fields[key] = _to_number(entry.get("intHome"))
        away_fields[key] = _to_number(entry.get("intAway"))
    db.add(MatchStat(match_id=match.id, team_id=match.home_team_id, **home_fields))
    db.add(MatchStat(match_id=match.id, team_id=match.away_team_id, **away_fields))


def upsert_lineup_sportsdb(db: Session, match: Match, lineup_json: list[dict]) -> None:
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id == match.id).delete()
    for entry in lineup_json:
        player_id = _int_or_none(entry.get("idPlayer"))
        if not player_id:
            continue
        team_id = match.home_team_id if entry.get("strHome") == "Yes" else match.away_team_id

        player = db.get(Player, player_id)
        if player is None:
            player = Player(
                id=player_id,
                name=entry.get("strPlayer", ""),
                team_id=team_id,
                position=entry.get("strPosition") or "",
                photo_url=entry.get("strCutout") or entry.get("strThumb") or "",
            )
            db.add(player)
        else:
            player.position = entry.get("strPosition") or player.position
            player.photo_url = entry.get("strCutout") or entry.get("strThumb") or player.photo_url

        db.add(PlayerMatchStat(player_id=player_id, match_id=match.id, team_id=team_id))


def enhance_with_api_football(db: Session, match: Match, af_client) -> None:
    """Best-effort enhancement: fills in richer match/player stats from API-Football when the
    fixture has a known cross-reference id and the API-Football key is working. Silently skips
    (raising back to the caller, which should catch+rollback) if the source is unavailable —
    TheSportsDB data already committed for this match must never depend on this succeeding.
    """
    if not match.api_football_id:
        return

    team_ids = [match.home_team_id, match.away_team_id]

    stats = af_client.get_fixture_statistics(match.api_football_id)
    if len(stats) == 2:
        for team_id, team_stats in zip(team_ids, stats):
            fields: dict[str, float | None] = {}
            for entry in team_stats.get("statistics", []):
                key = _STAT_KEY_MAP.get(entry["type"])
                if key:
                    fields[key] = _to_number(entry["value"])
            existing = db.query(MatchStat).filter_by(match_id=match.id, team_id=team_id).one_or_none()
            if existing is None:
                db.add(MatchStat(match_id=match.id, team_id=team_id, **fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)

    player_stats = af_client.get_fixture_player_stats(match.api_football_id)
    if len(player_stats) == 2:
        for team_id, team_block in zip(team_ids, player_stats):
            roster = {p.name.strip().lower(): p for p in db.query(Player).filter_by(team_id=team_id).all()}
            for entry in team_block.get("players", []):
                player = roster.get(entry["player"]["name"].strip().lower())
                if player is None:
                    continue
                pms = db.query(PlayerMatchStat).filter_by(player_id=player.id, match_id=match.id).one_or_none()
                if pms is None:
                    continue
                s = (entry.get("statistics") or [{}])[0]
                games = s.get("games") or {}
                goals = s.get("goals") or {}
                shots = s.get("shots") or {}
                passes = s.get("passes") or {}
                pms.minutes_played = games.get("minutes") or pms.minutes_played
                pms.goals = goals.get("total") if goals.get("total") is not None else pms.goals
                pms.assists = goals.get("assists") if goals.get("assists") is not None else pms.assists
                pms.shots_total = shots.get("total") or pms.shots_total
                pms.shots_on_target = shots.get("on") or pms.shots_on_target
                pms.passes_total = passes.get("total") or pms.passes_total
                pms.passes_accuracy = _to_number(passes.get("accuracy"))
                pms.tackles = (s.get("tackles") or {}).get("total") or pms.tackles
                pms.duels_won = (s.get("duels") or {}).get("won") or pms.duels_won
                pms.dribbles_success = (s.get("dribbles") or {}).get("success") or pms.dribbles_success
                pms.fouls_committed = (s.get("fouls") or {}).get("committed") or pms.fouls_committed
                pms.rating = _to_number(games.get("rating"))
