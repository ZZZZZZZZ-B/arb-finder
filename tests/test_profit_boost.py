import pytest

from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.strategies.profit_boost import ProfitBoostStrategy


def quote(bookmaker_key: str, outcome_name: str, odds: float) -> OddsQuote:
    return OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Home",
        away_team="Away",
        bookmaker_key=bookmaker_key,
        bookmaker_title=bookmaker_key,
        market_key="h2h",
        outcome_name=outcome_name,
        decimal_odds=odds,
    )


def test_profit_boost_uses_cash_stake_in_strict_lock_formula():
    strategy = ProfitBoostStrategy(stake=100, boost_percent=30)
    result = strategy.calculate(quote("draftkings", "Away", 3.0), quote("fanduel", "Home", 2.0))

    assert result is not None
    assert result.hedge_stake == 180.0
    assert result.locked_profit == 80.0
    assert result.conversion_rate_pct == 80.0


def test_profit_boost_keeps_negative_results():
    strategy = ProfitBoostStrategy(stake=100, boost_percent=0)
    result = strategy.calculate(quote("draftkings", "Away", 1.5), quote("fanduel", "Home", 1.5))

    assert result is not None
    assert result.locked_profit < 0


def test_profit_boost_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        ProfitBoostStrategy(stake=0, boost_percent=30)
    with pytest.raises(ValueError):
        ProfitBoostStrategy(stake=100, boost_percent=-1)




def test_profit_boost_applies_american_base_odds_requirement():
    strategy = ProfitBoostStrategy(stake=100, boost_percent=30, odds_operator=">=", odds_requirement_american=-200)
    assert strategy.is_eligible(quote("draftkings", "Away", 1.5))
    assert not strategy.is_eligible(quote("draftkings", "Away", 1.4))


def test_profit_boost_supports_reverse_american_odds_requirement():
    strategy = ProfitBoostStrategy(stake=100, boost_percent=30, odds_operator="<=", odds_requirement_american=-200)
    assert strategy.is_eligible(quote("draftkings", "Away", 1.4))
    assert not strategy.is_eligible(quote("draftkings", "Away", 1.6))