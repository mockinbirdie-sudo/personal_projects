import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Match, MatchEvent, MatchStat, PlayerMatchStat, PlayerTournamentStat
from ingestion.normalize import (
    recompute_tournament_stats,
    upsert_events,
    upsert_fixture,
    upsert_match_stats,
    upsert_player_match_stats,
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _load(name: str):
    return json.loads((SAMPLE_DIR / name).read_text())


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_upsert_fixture_creates_match_and_teams(db):
    fixture_json = _load("sample_fixture.json")
    match = upsert_fixture(db, fixture_json)
    db.commit()

    stored = db.get(Match, 999001)
    assert stored is not None
    assert stored.home_score == 3
    assert stored.away_score == 3
    assert stored.home_team.name == "Argentina"
    assert stored.away_team.name == "France"
    assert match.stage == "Final"


def test_upsert_events_creates_goal_events(db):
    upsert_fixture(db, _load("sample_fixture.json"))
    upsert_events(db, 999001, _load("sample_events.json"))
    db.commit()

    events = db.query(MatchEvent).filter(MatchEvent.match_id == 999001).all()
    assert len(events) == 3
    assert {e.minute for e in events} == {23, 36, 80}
    assert all(e.type == "Goal" for e in events)


def test_upsert_match_stats_parses_percentages(db):
    upsert_fixture(db, _load("sample_fixture.json"))
    upsert_match_stats(db, 999001, _load("sample_stats.json"))
    db.commit()

    arg_stats = db.query(MatchStat).filter(MatchStat.match_id == 999001, MatchStat.team_id == 26).one()
    assert arg_stats.possession == 53.0
    assert arg_stats.pass_accuracy == 85.0
    assert arg_stats.shots_total == 14


def test_upsert_player_stats_and_tournament_aggregation(db):
    upsert_fixture(db, _load("sample_fixture.json"))
    upsert_player_match_stats(db, 999001, _load("sample_player_stats.json"))
    recompute_tournament_stats(db)
    db.commit()

    messi_match = db.query(PlayerMatchStat).filter(PlayerMatchStat.player_id == 154).one()
    assert messi_match.goals == 2
    assert messi_match.assists == 1
    assert messi_match.rating == 8.5

    messi_tournament = db.get(PlayerTournamentStat, 154)
    assert messi_tournament.matches_played == 1
    assert messi_tournament.goals == 2
