from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OddsQuote:
    sport_key: str
    event_id: str
    commence_time: str
    home_team: str
    away_team: str
    bookmaker_key: str
    bookmaker_title: str
    market_key: str
    outcome_name: str
    decimal_odds: float
    point: Optional[float] = None
    last_update: Optional[str] = None


@dataclass(frozen=True)
class SportInfo:
    key: str
    group: str
    title: str
    active: bool
    has_outrights: bool
