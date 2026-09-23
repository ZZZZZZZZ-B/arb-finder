from promo_hedge_tool.strategies.bonus_bet_snr import BonusBetSNRStrategy
from promo_hedge_tool.odds_client.models import OddsQuote


def test_bonus_bet_snr_calculation():
    strategy = BonusBetSNRStrategy(amount=100.0, min_decimal_odds=3.4, primary_bookmaker="draftkings")
    primary = OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Lakers",
        away_team="Celtics",
        bookmaker_key="draftkings",
        bookmaker_title="DraftKings",
        market_key="h2h",
        outcome_name="Celtics",
        decimal_odds=3.5,
    )
    hedge = OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Lakers",
        away_team="Celtics",
        bookmaker_key="fanduel",
        bookmaker_title="FanDuel",
        market_key="h2h",
        outcome_name="Lakers",
        decimal_odds=2.2,
    )

    result = strategy.calculate(primary, hedge)
    assert result is not None
    assert result.locked_profit == 136.36
    assert result.conversion_rate_pct == 136.36


def test_bonus_bet_invalid_if_primary_is_too_low():
    strategy = BonusBetSNRStrategy(amount=100.0, min_decimal_odds=3.4, primary_bookmaker="draftkings")
    primary = OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Lakers",
        away_team="Celtics",
        bookmaker_key="draftkings",
        bookmaker_title="DraftKings",
        market_key="h2h",
        outcome_name="Celtics",
        decimal_odds=3.2,
    )
    assert strategy.is_eligible(primary) is False


def test_bonus_bet_returns_none_if_hedge_is_invalid():
    strategy = BonusBetSNRStrategy(amount=100.0, min_decimal_odds=3.4, primary_bookmaker="draftkings")
    primary = OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Lakers",
        away_team="Celtics",
        bookmaker_key="draftkings",
        bookmaker_title="DraftKings",
        market_key="h2h",
        outcome_name="Celtics",
        decimal_odds=3.5,
    )
    hedge = OddsQuote(
        sport_key="basketball_nba",
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Lakers",
        away_team="Celtics",
        bookmaker_key="fanduel",
        bookmaker_title="FanDuel",
        market_key="h2h",
        outcome_name="Lakers",
        decimal_odds=1.0,
    )
    assert strategy.calculate(primary, hedge) is None
