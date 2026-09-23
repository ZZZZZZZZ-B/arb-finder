from __future__ import annotations

from typing import Optional

from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.strategies.base import HedgeResult, PromoStrategy, describe_quote


class BonusBetSNRStrategy(PromoStrategy):
    def __init__(self, amount: float, min_decimal_odds: float, primary_bookmaker: str | None = None):
        self.amount = amount
        self.min_decimal_odds = min_decimal_odds
        self.primary_bookmaker = primary_bookmaker

    def is_eligible(self, primary_quote: OddsQuote) -> bool:
        return primary_quote.decimal_odds >= self.min_decimal_odds

    def calculate(self, primary_quote: OddsQuote, hedge_quote: OddsQuote) -> Optional[HedgeResult]:
        if hedge_quote.decimal_odds <= 1.0:
            return None
        hedge_stake = self.amount * (primary_quote.decimal_odds - 1) / hedge_quote.decimal_odds
        profit = self.amount * (primary_quote.decimal_odds - 1) - hedge_stake
        conversion_rate = profit / self.amount * 100

        return HedgeResult(
            event_id=primary_quote.event_id,
            event_name=f"{primary_quote.away_team} vs {primary_quote.home_team}",
            commence_time_local=primary_quote.commence_time,
            sport_key=primary_quote.sport_key,
            promo_type="bonus_bet_snr",
            market_key=primary_quote.market_key,
            primary_bookmaker=self.primary_bookmaker or primary_quote.bookmaker_key,
            primary_selection=primary_quote.outcome_name,
            primary_odds_decimal=primary_quote.decimal_odds,
            hedge_platform=hedge_quote.bookmaker_key,
            hedge_selection=hedge_quote.outcome_name,
            hedge_odds_decimal=hedge_quote.decimal_odds,
            hedge_stake=round(hedge_stake, 2),
            locked_profit=round(profit, 2),
            conversion_rate_pct=round(conversion_rate, 2),
            primary_point=primary_quote.point,
            hedge_point=hedge_quote.point,
            primary_bet_description=describe_quote(primary_quote),
            hedge_bet_description=describe_quote(hedge_quote),
            primary_stake=0.0,
            primary_return=round(self.amount * primary_quote.decimal_odds, 2),
            hedge_return=round(hedge_stake * hedge_quote.decimal_odds, 2),
            total_cash_staked=round(hedge_stake, 2),
        )
