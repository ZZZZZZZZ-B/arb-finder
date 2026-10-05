from types import SimpleNamespace

from promo_hedge_tool.ui import HedgeApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_ui():
    ui = SimpleNamespace(
        period=Value("full-game"),
        league=Value("tennis_atp"),
        config_data=SimpleNamespace(
            periods={},
            sports={"tennis_atp": {"dynamic_prefix": "tennis_atp_"}},
        ),
    )
    ui._selected_league_name = lambda selection: HedgeApp._selected_league_name(ui, selection)
    return ui


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


def test_all_events_scope_uses_only_sports_with_discovered_events():
    ui = SimpleNamespace(
        period=Value("full-game"),
        league=Value("All"),
        config_data=SimpleNamespace(
            periods={},
            sports={
                "nba": {"sport_key": "basketball_nba"},
                "mlb": {"sport_key": "baseball_mlb"},
                "tennis_atp": {"dynamic_prefix": "tennis_atp_"},
            },
        ),
    )
    ui._selected_league_name = lambda selection: HedgeApp._selected_league_name(ui, selection)
    ui._sport_keys = lambda: HedgeApp._sport_keys(ui)

    result = HedgeApp._sport_keys_for_discovered_events(
        ui, {"basketball_nba", "tennis_atp_china_open"}
    )

    assert result == ("basketball_nba", "tennis_atp_china_open")


def test_league_dropdown_uses_titles_but_resolves_api_sport_key():
    ui = SimpleNamespace(
        period=Value("full-game"),
        league=Value("NCAAF"),
        config_data=SimpleNamespace(
            periods={},
            sports={
                "ncaaf": {"sport_key": "americanfootball_ncaaf", "title": "NCAAF"},
                "tennis_atp": {"dynamic_prefix": "tennis_atp_", "title": "Tennis ATP"},
            },
        ),
    )
    ui._selected_league_name = lambda selection: HedgeApp._selected_league_name(ui, selection)

    assert HedgeApp._league_names(ui) == ["NCAAF", "Tennis ATP"]
    assert HedgeApp._sport_keys(ui) == ["americanfootball_ncaaf"]