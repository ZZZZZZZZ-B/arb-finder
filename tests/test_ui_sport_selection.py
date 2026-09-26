from types import SimpleNamespace

from promo_hedge_tool.ui import HedgeApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_ui():
    return SimpleNamespace(
        period=Value("full-game"),
        league=Value("tennis_atp"),
        config_data=SimpleNamespace(
            periods={},
            sports={"tennis_atp": {"dynamic_prefix": "tennis_atp_"}},
        ),
    )


def test_dynamic_league_resolves_for_event_query():
    class Resolver:
        def resolve_dynamic_prefix(self, prefix, include_inactive=False):
            assert prefix == "tennis_atp_"
            assert include_inactive is True
            return ["tennis_atp_us_open", "tennis_atp_china_open"]

    assert HedgeApp._sport_keys(make_ui(), Resolver()) == [
        "tennis_atp_us_open",
        "tennis_atp_china_open",
    ]


def test_dynamic_league_name_is_preserved_for_analysis_context():
    assert HedgeApp._sport_keys(make_ui()) == ["tennis_atp"]