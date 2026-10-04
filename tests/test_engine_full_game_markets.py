from pathlib import Path

import pytest

from promo_hedge_tool.config import load_config
from promo_hedge_tool.engine import resolve_full_game_optional_market_keys, resolve_sport_keys


CONFIG_PATH = Path(__file__).parents[1] / "config" / "config.yaml"


def test_resolve_full_game_optional_market_keys_maps_names_to_api_keys():
    config = load_config(CONFIG_PATH)

    keys = resolve_full_game_optional_market_keys(config, ("alternate_spreads", "alternate_totals"))

    assert keys == ("alternate_spreads", "alternate_totals")


def test_resolve_full_game_optional_market_keys_rejects_unknown_market():
    config = load_config(CONFIG_PATH)

    with pytest.raises(ValueError, match="Unknown full-game market"):
        resolve_full_game_optional_market_keys(config, ("player_points",))


def test_resolve_sport_keys_keeps_only_selected_dynamic_sports():
    config = type(
        "ConfigStub",
        (),
        {"sports": {"tennis_atp": {"dynamic_prefix": "tennis_atp_"}}},
    )()

    class Resolver:
        def resolve_dynamic_prefix(self, prefix):
            assert prefix == "tennis_atp_"
            return ["tennis_atp_china_open", "tennis_atp_japan_open"]

    resolved = resolve_sport_keys(config, Resolver(), ("tennis_atp_china_open",))

    assert resolved == {"tennis_atp": ["tennis_atp_china_open"]}
