from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from promo_hedge_tool.odds_client.models import OddsQuote


@dataclass(frozen=True)
class HedgeResult:
    event_id: str
    event_name: str
    commence_time_local: str
    sport_key: str
    promo_type: str
    market_key: str
    primary_bookmaker: str
    primary_selection: str
    primary_odds_decimal: float
    hedge_platform: str
    hedge_selection: str
    hedge_odds_decimal: float
    hedge_stake: float
    locked_profit: float
    conversion_rate_pct: float


class PromoStrategy(ABC):
    @abstractmethod
    def is_eligible(self, primary_quote: OddsQuote) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calculate(self, primary_quote: OddsQuote, hedge_quote: OddsQuote) -> Optional[HedgeResult]:
        raise NotImplementedError
