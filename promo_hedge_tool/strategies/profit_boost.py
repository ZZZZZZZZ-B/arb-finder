from __future__ import annotations

from typing import Optional

from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_rules import meets_american_requirement
from promo_hedge_tool.strategies.base import HedgeResult, PromoStrategy


class ProfitBoostStrategy(PromoStrategy):
    """Calculate a two-sided hedge for a cash wager with an odds boost."""

    def __init__(self, stake: float, boost_percent: float, odds_operator: str | None = None, odds_requirement_american: float | None = None):
        if stake <= 0:
            raise ValueError("stake must be greater than zero")
        if boost_percent < 0:
            raise ValueError("boost_percent must not be negative")
        self.stake = float(stake)
        self.boost_percent = float(boost_percent)
        self.boost = self.boost_percent / 100.0
        self.odds_operator = odds_operator
        self.odds_requirement_american = odds_requirement_american

    def is_eligible(self, primary_quote: OddsQuote) -> bool:
        return primary_quote.decimal_odds > 1.0 and meets_american_requirement(
            primary_quote.decimal_odds,
            self.odds_operator,
            self.odds_requirement_american,
        )

    def calculate(self, primary_quote: OddsQuote, hedge_quote: OddsQuote) -> Optional[HedgeResult]:
        if not self.is_eligible(primary_quote) or hedge_quote.decimal_odds <= 1.0:
            return None

        boosted_profit = self.stake * (primary_quote.decimal_odds - 1.0) * (1.0 + self.boost)
        hedge_stake = (self.stake + boosted_profit) / hedge_quote.decimal_odds
        locked_profit = boosted_profit - hedge_stake
        conversion_rate = locked_profit / self.stake * 100.0

        return HedgeResult(
            event_id=primary_quote.event_id,
            event_name=f"{primary_quote.away_team} vs {primary_quote.home_team}",
            commence_time_local=primary_quote.commence_time,
            sport_key=primary_quote.sport_key,
            promo_type="profit_boost",
            market_key=primary_quote.market_key,
            primary_bookmaker=primary_quote.bookmaker_key,
            primary_selection=primary_quote.outcome_name,
            primary_odds_decimal=primary_quote.decimal_odds,
            hedge_platform=hedge_quote.bookmaker_key,
            hedge_selection=hedge_quote.outcome_name,
            hedge_odds_decimal=hedge_quote.decimal_odds,
            hedge_stake=round(hedge_stake, 2),
            locked_profit=round(locked_profit, 2),
            conversion_rate_pct=round(conversion_rate, 2),
        )