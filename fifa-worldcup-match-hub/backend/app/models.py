from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)  # TheSportsDB idTeam
    name: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[str] = mapped_column(String, default="")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)  # TheSportsDB idEvent
    api_football_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, default="NS")  # NS, LIVE, FT, etc.
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(String, default="")
    stage: Mapped[str] = mapped_column(String, default="")  # e.g. "Group Stage", "Final"
    highlight_image_urls: Mapped[str] = mapped_column(String, default="")  # comma-separated URLs
    highlight_video_url: Mapped[str | None] = mapped_column(String, nullable=True)  # YouTube link, when curated

    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    events: Mapped[list["MatchEvent"]] = relationship(back_populates="match", cascade="all, delete-orphan")
    stats: Mapped[list["MatchStat"]] = relationship(back_populates="match", cascade="all, delete-orphan")


class MatchEvent(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    minute: Mapped[int] = mapped_column(Integer, default=0)
    extra_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # Goal, Card, subst, Var
    detail: Mapped[str] = mapped_column(String, default="")  # e.g. "Normal Goal", "Yellow Card"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    assist_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    description: Mapped[str] = mapped_column(String, default="")

    match: Mapped["Match"] = relationship(back_populates="events")

    __table_args__ = (UniqueConstraint("match_id", "minute", "type", "player_id", "detail", name="uq_event"),)


class MatchStat(Base):
    __tablename__ = "match_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    possession: Mapped[float | None] = mapped_column(Float, nullable=True)
    shots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offsides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pass_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    xg: Mapped[float | None] = mapped_column(Float, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="stats")

    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_match_team_stat"),)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)  # TheSportsDB idPlayer
    name: Mapped[str] = mapped_column(String, nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[str] = mapped_column(String, default="")
    photo_url: Mapped[str] = mapped_column(String, default="")


class PlayerMatchStat(Base):
    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    shots_total: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    passes_total: Mapped[int] = mapped_column(Integer, default=0)
    passes_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    duels_won: Mapped[int] = mapped_column(Integer, default=0)
    dribbles_success: Mapped[int] = mapped_column(Integer, default=0)
    fouls_committed: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("player_id", "match_id", name="uq_player_match"),)


class PlayerTournamentStat(Base):
    """Aggregated totals across all ingested matches for a player — recomputed on each ingestion run."""

    __tablename__ = "player_tournament_stats"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    shots_total: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    passes_total: Mapped[int] = mapped_column(Integer, default=0)
    passes_accuracy_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[float | None] = mapped_column(Float, nullable=True)


class TeamSentiment(Base):
    """Public sentiment (1=poor, 10=great) for a team in a specific match, derived from
    YouTube comments on the match highlight video and/or Google News headlines."""

    __tablename__ = "team_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 1-10
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[str] = mapped_column(String, default="")  # e.g. "youtube,news"

    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_team_sentiment"),)


class PlayerSentiment(Base):
    """Public sentiment (1=poor, 10=great) for a player in a specific match."""

    __tablename__ = "player_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 1-10
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[str] = mapped_column(String, default="")

    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_player_sentiment"),)
