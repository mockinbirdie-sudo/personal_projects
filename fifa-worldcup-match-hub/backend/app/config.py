from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # TheSportsDB is the primary data source: fixtures, timeline, basic match stats, and all
    # images. "3" is TheSportsDB's public free test key (generous limits, no signup required).
    sportsdb_key: str = "3"
    sportsdb_host: str = "www.thesportsdb.com"
    sportsdb_league_id: int = 4429  # FIFA World Cup

    # API-Football is an optional enhancement layer: when its key is set and working, it adds
    # richer per-match/per-player stats (passes, tackles, ratings) on top of the TheSportsDB
    # data. The app fully functions without it.
    api_football_key: str = ""
    api_football_host: str = "v3.football.api-sports.io"

    # Optional: enables pulling comments from the match's highlight video for sentiment scoring.
    # Without it, sentiment falls back to Google News RSS headlines only (no key needed there).
    youtube_api_key: str = ""

    # Optional: Google Custom Search (reuses youtube_api_key as the API key — same Google Cloud
    # project, just needs the Custom Search API enabled on it too) for real match photos from a
    # curated list of football/news domains, supplementing TheSportsDB's images. Skipped entirely
    # when search_engine_id is unset.
    search_engine_id: str = ""

    database_url: str = "sqlite:///./worldcup.db"
    admin_reset_token: str = ""
    wc_league_id: int = 1
    wc_season: int = 2026
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
