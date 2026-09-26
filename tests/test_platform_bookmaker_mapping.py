from pathlib import Path
from types import SimpleNamespace

from promo_hedge_tool.config import load_config
from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.run_context import api_bookmaker_key, normalize_bookmaker_quotes
from promo_hedge_tool.ui import HedgeApp


CONFIG_PATH = Path(__file__).parents[1] / "config" / "config.yaml"


def test_external_platforms_use_odds_api_keys_and_remain_disabled_by_default():
    config = load_config(CONFIG_PATH)

    assert api_bookmaker_key(config, "proline") == "proline_ca_on"
    assert api_bookmaker_key(config, "bet365") == "bet365_au"
    assert api_bookmaker_key(config, "hardrock") == "hardrockbet"
    assert all(not config.platforms[name]["enabled"] for name in ("proline", "bet365", "hardrock"))
    assert all(config.platforms[name]["source"] == "odds_api" for name in ("proline", "bet365", "hardrock"))


def test_odds_api_quotes_normalize_to_configured_platform_names():
    config = load_config(CONFIG_PATH)
    quote = OddsQuote(
        sport_key="basketball_ncaaf",
        event_id="event-1",
        commence_time="2026-09-26T00:00:00Z",
        home_team="Home",
        away_team="Away",
        bookmaker_key="proline_ca_on",
        bookmaker_title="PROLINE",
        market_key="h2h",
        outcome_name="Home",
        decimal_odds=2.0,
    )

    normalized = normalize_bookmaker_quotes(config, [quote])[0]

    assert normalized.bookmaker_key == "proline"
    assert normalized.bookmaker_title == "Proline+"


def test_event_sport_title_uses_configured_title():
    app = SimpleNamespace(
        config_data=SimpleNamespace(
            sports={"ncaaf": {"sport_key": "americanfootball_ncaaf", "title": "NCAAF"}}
        )
    )

    assert HedgeApp._sport_display_title(app, "americanfootball_ncaaf") == "NCAAF"