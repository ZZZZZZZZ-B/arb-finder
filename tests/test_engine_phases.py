from pathlib import Path

from promo_hedge_tool import engine
from promo_hedge_tool.config import load_config
from promo_hedge_tool.odds_client.client import OddsAPIClient
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


CORE_ODDS_PAYLOAD = [
    {
        "id": "e1",
        "sport_key": "baseball_mlb",
        "commence_time": "2026-09-27T00:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": "2026-09-27T00:00:00Z",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Home", "price": 2.0}, {"name": "Away", "price": 1.9}]}],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-09-27T00:00:00Z",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Home", "price": 1.8}, {"name": "Away", "price": 3.0}]}],
            },
        ],
    }
]

ALT_ODDS_PAYLOAD = {
    "id": "e1",
    "sport_key": "baseball_mlb",
    "commence_time": "2026-09-27T00:00:00Z",
    "home_team": "Home",
    "away_team": "Away",
    "bookmakers": [
        {
            "key": "fanduel",
            "title": "FanDuel",
            "markets": [
                {
                    "key": "alternate_spreads",
                    "last_update": "2026-09-27T00:00:00Z",
                    "outcomes": [{"name": "Home", "price": 1.95, "point": -1.5}, {"name": "Away", "price": 1.85, "point": 1.5}],
                }
            ],
        },
        {
            "key": "draftkings",
            "title": "DraftKings",
            "markets": [
                {
                    "key": "alternate_spreads",
                    "last_update": "2026-09-27T00:00:00Z",
                    "outcomes": [{"name": "Home", "price": 1.85, "point": -1.5}, {"name": "Away", "price": 1.95, "point": 1.5}],
                }
            ],
        },
    ],
}


class FakeSession:
    def __init__(self):
        self.event_odds_calls: list[dict] = []

    def request(self, method, url, params, timeout):
        if url.endswith("/v4/sports"):
            return FakeResponse([{"key": "baseball_mlb", "group": "Baseball", "title": "MLB", "active": True}])
        if url.endswith("/v4/sports/baseball_mlb/odds"):
            return FakeResponse(CORE_ODDS_PAYLOAD)
        if url.endswith("/v4/sports/baseball_mlb/events/e1/odds"):
            self.event_odds_calls.append(params)
            return FakeResponse(ALT_ODDS_PAYLOAD)
        raise AssertionError(f"Unexpected request to {url}")


def make_context(**overrides) -> RunContext:
    defaults = dict(
        mode="profit-boost",
        base_bookmaker="fanduel",
        hedge_bookmakers=("draftkings",),
        stake=100.0,
        boost_percent=30.0,
        selected_leagues=("mlb",),
        selected_markets=("alternate_spreads",),
    )
    defaults.update(overrides)
    return RunContext(**defaults)


def patch_client(monkeypatch, session: FakeSession) -> None:
    def factory(key_pool):
        return OddsAPIClient(key_pool, session=session)

    monkeypatch.setattr(engine, "OddsAPIClient", factory)


def test_run_core_phase_fetches_and_ranks_without_exporting(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEYS", "test-key")
    config = load_config(CONFIG_PATH)
    config.output["output_dir"] = str(tmp_path)
    patch_client(monkeypatch, FakeSession())
    context = make_context()

    core_phase = engine.run_core_phase(config, context)

    assert len(core_phase.all_quotes) == 4
    assert core_phase.core_results
    assert all(result.event_id == "e1" for result in core_phase.core_results)
    assert list(tmp_path.glob("*.csv")) == []


def test_finalize_core_only_exports_core_results_without_alt_call(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEYS", "test-key")
    config = load_config(CONFIG_PATH)
    config.output["output_dir"] = str(tmp_path)
    session = FakeSession()
    patch_client(monkeypatch, session)
    context = make_context()
    core_phase = engine.run_core_phase(config, context)

    results = engine.finalize_core_only(config, context, core_phase)

    assert results == core_phase.core_results
    assert len(list(tmp_path.glob("*.csv"))) == 1
    assert session.event_odds_calls == []


def test_run_alt_phase_fetches_prefiltered_events_and_merges_quotes(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEYS", "test-key")
    config = load_config(CONFIG_PATH)
    config.output["output_dir"] = str(tmp_path)
    session = FakeSession()
    patch_client(monkeypatch, session)
    context = make_context()
    core_phase = engine.run_core_phase(config, context)
    event_sports = engine.select_prefilter_event_sports(config, context, core_phase.core_results)
    assert event_sports == (("baseball_mlb", "e1"),)

    results = engine.run_alt_phase(config, context, core_phase, event_sports)

    assert len(session.event_odds_calls) == 1
    assert len(list(tmp_path.glob("*.csv"))) == 1
    assert any(result.market_key == "alternate_spreads" for result in results)
