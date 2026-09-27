from pathlib import Path

from promo_hedge_tool.config import load_config
from promo_hedge_tool.cost_estimator import (
    estimate_alt_market_cost_for_events,
    estimate_core_market_cost,
    estimate_run_cost,
    get_credit_thresholds,
    regions_factor,
)
from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.key_pool import KeyPool
from promo_hedge_tool.run_context import RunContext


CONFIG_PATH = Path(__file__).parents[1] / "config" / "config.yaml"


class FakeResponse:
    status_code = 200
    headers = {"x-requests-remaining": "499"}
    text = ""

    def __init__(self, payload):
        self._payload = payload
        self.content = b"1"

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, event_counts_by_sport: dict[str, int]):
        self._event_counts_by_sport = event_counts_by_sport

    def request(self, method, url, params, timeout):
        if url.endswith("/v4/sports"):
            return FakeResponse([{"key": "baseball_mlb", "group": "Baseball", "title": "MLB", "active": True}])
        for sport_key, count in self._event_counts_by_sport.items():
            if url.endswith(f"/v4/sports/{sport_key}/events"):
                return FakeResponse([{"id": f"e{i}"} for i in range(count)])
        raise AssertionError(f"Unexpected request to {url}")


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


def test_regions_factor_groups_bookmakers_by_ten():
    assert regions_factor(2) == 1
    assert regions_factor(10) == 1
    assert regions_factor(11) == 2


def test_full_game_bulk_only_cost():
    config = load_config(CONFIG_PATH)
    client = OddsAPIClient(KeyPool(["key"]), session=FakeSession({"baseball_mlb": 0}))
    context = make_context(selected_leagues=("mlb",))

    estimate = estimate_run_cost(config, context, client)

    assert estimate.total == 3  # 1 sport x 3 core markets x 1 region


def test_full_game_optional_markets_use_free_events_call_when_no_selection():
    config = load_config(CONFIG_PATH)
    client = OddsAPIClient(KeyPool(["key"]), session=FakeSession({"baseball_mlb": 2}))
    context = make_context(selected_leagues=("mlb",), selected_markets=("alternate_spreads",))

    estimate = estimate_run_cost(config, context, client)

    assert estimate.total == 3 + 2  # bulk (3) + 1 market x 1 region x 2 events


def test_full_game_optional_markets_use_selected_event_count():
    config = load_config(CONFIG_PATH)
    client = OddsAPIClient(KeyPool(["key"]), session=FakeSession({"baseball_mlb": 999}))
    context = make_context(
        selected_leagues=("mlb",),
        selected_event_sports=(("baseball_mlb", "e1"), ("baseball_mlb", "e2"), ("baseball_mlb", "e3")),
        selected_markets=("alternate_spreads", "alternate_totals"),
    )

    estimate = estimate_run_cost(config, context, client)

    assert estimate.total == 3 + (3 * 2)  # bulk (3) + 3 events x 2 markets x 1 region


def test_period_market_cost():
    config = load_config(CONFIG_PATH)
    client = OddsAPIClient(KeyPool(["key"]), session=FakeSession({}))
    context = make_context(
        period="first_inning",
        selected_event_ids=("e1",),
        selected_event_sports=(("baseball_mlb", "e1"),),
        selected_markets=("run_line", "total_runs"),
    )

    estimate = estimate_run_cost(config, context, client)

    assert estimate.total == 2  # 1 event x 2 markets x 1 region


def test_get_credit_thresholds_reads_config_defaults():
    config = load_config(CONFIG_PATH)

    assert get_credit_thresholds(config) == (20, 50)


def test_estimate_core_market_cost_matches_bulk_component_only():
    config = load_config(CONFIG_PATH)
    client = OddsAPIClient(KeyPool(["key"]), session=FakeSession({"baseball_mlb": 0}))
    context = make_context(selected_leagues=("mlb",), selected_markets=("alternate_spreads",))

    estimate = estimate_core_market_cost(config, context, client)

    assert estimate.total == 3  # 1 sport x 3 core markets x 1 region


def test_estimate_alt_market_cost_for_events_uses_given_event_count():
    config = load_config(CONFIG_PATH)
    context = make_context(selected_markets=("alternate_spreads", "alternate_totals"))

    estimate = estimate_alt_market_cost_for_events(config, context, (("baseball_mlb", "e1"), ("baseball_mlb", "e2")))

    assert estimate.total == 2 * 2  # 2 events x 2 markets x 1 region
