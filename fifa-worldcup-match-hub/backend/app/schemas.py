from datetime import datetime

from pydantic import BaseModel


class TeamOut(BaseModel):
    id: int
    name: str
    logo_url: str

    class Config:
        from_attributes = True


class MatchSummaryOut(BaseModel):
    id: int
    home_team: TeamOut
    away_team: TeamOut
    kickoff_utc: datetime
    status: str
    home_score: int | None
    away_score: int | None
    venue: str
    stage: str
    highlight_images: list[str]
    key_events: list[str]


class EventOut(BaseModel):
    minute: int
    extra_minute: int | None
    type: str
    detail: str
    team_id: int
    player_id: int | None
    assist_player_id: int | None
    description: str

    class Config:
        from_attributes = True


class MatchStatOut(BaseModel):
    team_id: int
    possession: float | None
    shots_total: int | None
    shots_on_target: int | None
    corners: int | None
    fouls: int | None
    offsides: int | None
    yellow_cards: int | None
    red_cards: int | None
    passes_total: int | None
    pass_accuracy: float | None
    xg: float | None

    class Config:
        from_attributes = True


class MatchTimelineOut(BaseModel):
    match: MatchSummaryOut
    events: list[EventOut]
    stats: list[MatchStatOut]


class PlayerMatchStatOut(BaseModel):
    player_id: int
    player_name: str
    team_id: int
    position: str
    minutes_played: int
    goals: int
    assists: int
    shots_total: int
    shots_on_target: int
    passes_total: int
    passes_accuracy: float | None
    tackles: int
    duels_won: int
    dribbles_success: int
    fouls_committed: int
    yellow_cards: int
    red_cards: int
    rating: float | None


class PlayerTournamentStatOut(BaseModel):
    player_id: int
    player_name: str
    team_id: int
    position: str
    matches_played: int
    minutes_played: int
    goals: int
    assists: int
    shots_total: int
    shots_on_target: int
    passes_total: int
    passes_accuracy_avg: float | None
    tackles: int
    yellow_cards: int
    red_cards: int
    rating_avg: float | None
