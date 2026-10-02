import pytest

from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.run_context import RunContext
from promo_hedge_tool.strategies.no_sweat import NoSweatStrategy


def quote(bookmaker_key: str, outcome_name: str, odds: float) -> OddsQuote:
    return OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-10-02T00:00:00Z",
        home_team="Home",
        away_team="Away",
        bookmaker_key=bookmaker_key,
        bookmaker_title=bookmaker_key,
        market_key="h2h",
        outcome_name=outcome_name,
        decimal_odds=odds,
    )


def test_no_sweat_equalizes_win_and_loss_profit():
    strategy = NoSweatStrategy(stake=100, bonus_value_ratio=0.7)
    result = strategy.calculate(quote("draftkings", "Away", 3.0), quote("fanduel", "Home", 1.5))

    assert result is not None
    assert result.hedge_stake == 153.33
    assert result.locked_profit == 46.67
    assert result.conversion_rate_pct == 46.67
    win_profit = 100 * 2.0 - result.hedge_stake
    loss_profit = -100 + 70 + result.hedge_stake * 0.5
    assert win_profit == pytest.approx(loss_profit, abs=0.02)


def test_no_sweat_applies_american_odds_requirement():
    strategy = NoSweatStrategy(stake=100, odds_operator=">=", odds_requirement_american=300)

    assert strategy.calculate(quote("draftkings", "Away", 3.0), quote("fanduel", "Home", 1.5)) is None
    assert strategy.calculate(quote("draftkings", "Away", 4.5), quote("fanduel", "Home", 1.5)) is not None


def test_no_sweat_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        NoSweatStrategy(stake=0)
    with pytest.raises(ValueError):
        NoSweatStrategy(stake=100, bonus_value_ratio=0)
    with pytest.raises(ValueError):
        NoSweatStrategy(stake=100, bonus_value_ratio=1.1)


def test_no_sweat_context_requires_positive_stake():
    with pytest.raises(ValueError, match="No Sweat stake"):
        RunContext(mode="no-sweat", base_bookmaker="fanduel", hedge_bookmakers=("draftkings",))
    context = RunContext(mode="no-sweat", base_bookmaker="fanduel", hedge_bookmakers=("draftkings",), stake=100)
    assert context.stake == 100
