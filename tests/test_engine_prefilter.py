from pathlib import Path

from promo_hedge_tool.config import load_config
from promo_hedge_tool.engine import select_prefilter_event_sports
from promo_hedge_tool.run_context import RunContext
from promo_hedge_tool.strategies.base import HedgeResult


CONFIG_PATH = Path(__file__).parents[1] / "config" / "config.yaml"


def make_result(event_id: str, sport_key: str, locked_profit: float) -> HedgeResult:
    return HedgeResult(
        event_id=event_id,
        event_name=f"Event {event_id}",
        commence_time_local="2026-09-27 12:00",
        sport_key=sport_key,
        promo_type="profit-boost",
        market_key="spreads",
        primary_bookmaker="fanduel",
        primary_selection="Team A",
        primary_odds_decimal=2.0,
        hedge_platform="draftkings",
        hedge_selection="Team B",
        hedge_odds_decimal=1.9,
        hedge_stake=100.0,
        locked_profit=locked_profit,
        conversion_rate_pct=10.0,
    )


def make_context(**overrides) -> RunContext:
    defaults = dict(
        mode="profit-boost",
        base_bookmaker="fanduel",
        hedge_bookmakers=("draftkings",),
        stake=100.0,
        boost_percent=30.0,
    )
    defaults.update(overrides)
    return RunContext(**defaults)


def test_select_prefilter_event_sports_keeps_best_result_per_event():
    config = load_config(CONFIG_PATH)
    context = make_context()
    core_results = [
        make_result("e1", "baseball_mlb", locked_profit=5.0),
        make_result("e1", "baseball_mlb", locked_profit=9.0),
        make_result("e2", "baseball_mlb", locked_profit=1.0),
    ]

    event_sports = select_prefilter_event_sports(config, context, core_results)

    assert event_sports == (("baseball_mlb", "e1"), ("baseball_mlb", "e2"))


def test_select_prefilter_event_sports_respects_top_n(monkeypatch):
    config = load_config(CONFIG_PATH)
    config.full_game_markets["alt_market_prefilter"]["top_n"] = 1
    context = make_context()
    core_results = [
        make_result("e1", "baseball_mlb", locked_profit=5.0),
        make_result("e2", "baseball_mlb", locked_profit=9.0),
    ]

    event_sports = select_prefilter_event_sports(config, context, core_results)

    assert event_sports == (("baseball_mlb", "e2"),)


def test_select_prefilter_event_sports_empty_when_no_core_results():
    config = load_config(CONFIG_PATH)
    context = make_context()

    assert select_prefilter_event_sports(config, context, []) == ()
