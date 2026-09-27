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
    if (quote.market_key in ("totals", "alternate_totals") or quote.market_key.startswith("totals_")) and quote.point is not None:
        return f"{selection} {quote.point:g}"
    if (quote.market_key in ("spreads", "alternate_spreads") or quote.market_key.startswith("spreads_")) and quote.point is not None:
        return f"{selection} {quote.point:+g}"
    return selection


def describe_market(market_key: str) -> str:
    labels = {
        "h2h": "Moneyline",
        "spreads": "Spread",
        "totals": "Total",
        "alternate_spreads": "Alternate Spread",
        "alternate_totals": "Alternate Total",
        "spreads_1st_1_innings": "1st inning Run Line",
        "totals_1st_1_innings": "1st inning Total Runs",
    }
    return labels.get(market_key, market_key.replace("_", " ").title())


class PromoStrategy(ABC):
    @abstractmethod
    def is_eligible(self, primary_quote: OddsQuote) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calculate(self, primary_quote: OddsQuote, hedge_quote: OddsQuote) -> Optional[HedgeResult]:
        raise NotImplementedError
