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
    primary_point: float | None = None
    hedge_point: float | None = None
    primary_bet_description: str = ""
    hedge_bet_description: str = ""
    primary_stake: float = 0.0
    primary_return: float = 0.0
    hedge_return: float = 0.0
    total_cash_staked: float = 0.0


def describe_quote(quote: OddsQuote) -> str:
    selection = quote.outcome_name
    if quote.market_key == "totals" and quote.point is not None:
        return f"{selection} {quote.point:g}"
    if quote.market_key == "spreads" and quote.point is not None:
        return f"{selection} {quote.point:+g}"
    return selection


class PromoStrategy(ABC):
    @abstractmethod
    def is_eligible(self, primary_quote: OddsQuote) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calculate(self, primary_quote: OddsQuote, hedge_quote: OddsQuote) -> Optional[HedgeResult]:
        raise NotImplementedError
