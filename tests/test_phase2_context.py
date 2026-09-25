import pytest

from promo_hedge_tool.event_selection import filter_events, local_event_time, normalize_team_text
from promo_hedge_tool.run_context import build_run_context


class ConfigStub:
    platforms = {"draftkings": {}, "fanduel": {}, "proline": {}}
    odds_api = type("Odds", (), {"bookmakers": ["draftkings", "fanduel"]})()


def test_runtime_context_uses_all_other_configured_platforms_as_hedges():
    context = build_run_context(
        ConfigStub(),
        "bonus-bet",
        "fanduel",
        bonus_amount=100,
        odds_operator=">=",
        odds_requirement_american=240,
    )
    assert context.hedge_bookmakers == ("draftkings", "proline")


def test_bonus_bet_context_requires_ui_parameters():
    with pytest.raises(ValueError, match="Bonus Bet amount"):
        build_run_context(ConfigStub(), "bonus-bet", "fanduel")


def test_bonus_bet_context_accepts_american_odds_requirement():
    context = build_run_context(
        ConfigStub(),
        "bonus-bet",
        "fanduel",
        bonus_amount=100,
        odds_operator=">=",
        odds_requirement_american=240,
    )
    assert context.odds_requirement_american == 240


def test_bonus_bet_context_requires_american_value_when_operator_is_selected():
    with pytest.raises(ValueError, match="American odds requirement"):
        build_run_context(ConfigStub(), "bonus-bet", "fanduel", bonus_amount=100, odds_operator=">=")


def test_runtime_context_uses_selected_hedge_platforms():
    context = build_run_context(ConfigStub(), "profit-boost", "draftkings", 100, 30, hedge_bookmakers=("proline",))
    assert context.hedge_bookmakers == ("proline",)


def test_team_keyword_matches_home_or_away_team():
    events = [
        {"id": "1", "home_team": "Boston Celtics", "away_team": "Los Angeles Lakers"},
        {"id": "2", "home_team": "Miami Heat", "away_team": "New York Knicks"},
    ]
    assert [event["id"] for event in filter_events(events, " lakers ")] == ["1"]
    assert normalize_team_text("  Los   Angeles Lakers ") == "los angeles lakers"


def test_event_time_cell_contains_local_time_without_timezone_suffix():
    value = local_event_time({"commence_time": "2026-09-23T00:00:00Z"})
    assert "(" not in value
    assert len(value) == 16


def test_profit_boost_context_requires_positive_stake():
    with pytest.raises(ValueError):
        build_run_context(ConfigStub(), "profit-boost", "draftkings", stake=0, boost_percent=30)


def test_profit_boost_context_accepts_optional_odds_requirement():
    context = build_run_context(
        ConfigStub(),
        "profit-boost",
        "draftkings",
        stake=100,
        boost_percent=30,
        odds_operator=">=",
        odds_requirement_american=-200,
    )
    assert context.odds_requirement_american == -200