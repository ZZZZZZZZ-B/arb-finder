from __future__ import annotations

from typing import Optional

from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_rules import meets_american_requirement
from promo_hedge_tool.strategies.base import HedgeResult, PromoStrategy, describe_quote


class NoSweatStrategy(PromoStrategy):
    """Cash stake that refunds a same-value bonus bet on loss, valued at a fraction of cash."""

    def __init__(
        self,
        stake: float,
        bonus_value_ratio: float = 0.7,
        odds_operator: str | None = None,
        odds_requirement_american: float | None = None,
    ):
        if stake <= 0:
            raise ValueError("stake must be greater than zero")
        if not 0 < bonus_value_ratio <= 1:
            raise ValueError("bonus_value_ratio must be in (0, 1]")
        self.stake = float(stake)
        self.bonus_value_ratio = float(bonus_value_ratio)
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

        odds = primary_quote.decimal_odds
        hedge_stake = self.stake * (odds - self.bonus_value_ratio) / hedge_quote.decimal_odds
        locked_profit = self.stake * (odds - 1.0) - hedge_stake
        conversion_rate = locked_profit / self.stake * 100.0

        return HedgeResult(
            event_id=primary_quote.event_id,
            event_name=f"{primary_quote.away_team} vs {primary_quote.home_team}",
            commence_time_local=primary_quote.commence_time,
            sport_key=primary_quote.sport_key,
            promo_type="no_sweat",
            market_key=primary_quote.market_key,
            primary_bookmaker=primary_quote.bookmaker_key,
            primary_selection=primary_quote.outcome_name,
            primary_odds_decimal=odds,
            hedge_platform=hedge_quote.bookmaker_key,
            hedge_selection=hedge_quote.outcome_name,
            hedge_odds_decimal=hedge_quote.decimal_odds,
            hedge_stake=round(hedge_stake, 2),
            locked_profit=round(locked_profit, 2),
            conversion_rate_pct=round(conversion_rate, 2),
            primary_point=primary_quote.point,
            hedge_point=hedge_quote.point,
            primary_bet_description=describe_quote(primary_quote),
            hedge_bet_description=describe_quote(hedge_quote),
            primary_stake=round(self.stake, 2),
            primary_return=round(self.stake * odds, 2),
            hedge_return=round(hedge_stake * hedge_quote.decimal_odds, 2),
            total_cash_staked=round(self.stake + hedge_stake, 2),
        )
