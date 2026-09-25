from __future__ import annotations

import sqlite3
from threading import RLock
from pathlib import Path

from promo_hedge_tool.odds_client.models import OddsQuote


class OddsCache:
    def __init__(self, path: str | Path = "output/odds_cache.sqlite3") -> None:
        self._lock = RLock()
        self._path = Path(path)
        self._initialize()

    def configure(self, path: str | Path) -> None:
        with self._lock:
            self._path = Path(path)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS odds_quotes (
                    sport_key TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    commence_time TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    bookmaker_key TEXT NOT NULL,
                    bookmaker_title TEXT NOT NULL,
                    market_key TEXT NOT NULL,
                    outcome_name TEXT NOT NULL,
                    decimal_odds REAL NOT NULL,
                    point REAL,
                    last_update TEXT
                )
                """
            )

    def clear(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("DELETE FROM odds_quotes")

    def replace(self, quotes: list[OddsQuote]) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("DELETE FROM odds_quotes")
                connection.executemany(
                    """
                    INSERT INTO odds_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            quote.sport_key,
                            quote.event_id,
                            quote.commence_time,
                            quote.home_team,
                            quote.away_team,
                            quote.bookmaker_key,
                            quote.bookmaker_title,
                            quote.market_key,
                            quote.outcome_name,
                            quote.decimal_odds,
                            quote.point,
                            quote.last_update,
                        )
                        for quote in quotes
                    ],
                )

    def get(self) -> list[OddsQuote]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute("SELECT * FROM odds_quotes").fetchall()
            return [
                OddsQuote(
                    sport_key=row["sport_key"],
                    event_id=row["event_id"],
                    commence_time=row["commence_time"],
                    home_team=row["home_team"],
                    away_team=row["away_team"],
                    bookmaker_key=row["bookmaker_key"],
                    bookmaker_title=row["bookmaker_title"],
                    market_key=row["market_key"],
                    outcome_name=row["outcome_name"],
                    decimal_odds=row["decimal_odds"],
                    point=row["point"],
                    last_update=row["last_update"],
                )
                for row in rows
            ]


odds_cache = OddsCache()