from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes, is_binary_market, market_family, quotes_are_compatible
from promo_hedge_tool.odds_client.models import OddsQuote


def make_quote(bookmaker_key, market_key, outcome_name, odds, point=None, sport_key="basketball_nba"):
    return OddsQuote(
        sport_key=sport_key,
        event_id="e1",
        commence_time="2026-09-23T00:00:00Z",
        home_team="Team A",
        away_team="Team B",
        bookmaker_key=bookmaker_key,
        bookmaker_title=bookmaker_key,
        market_key=market_key,
        outcome_name=outcome_name,
        decimal_odds=odds,
        point=point,
    )


def test_binary_market_filters_soccer_h2h_without_draw():
    assert is_binary_market("h2h", False) is True
    assert is_binary_market("h2h", True) is True
    assert is_binary_market("draw_no_bet", True) is False


def test_build_matchups_groups_same_market_and_point():
    quotes = [
        make_quote("draftkings", "spreads", "Team A", 2.0, -3.5),
        make_quote("draftkings", "spreads", "Team B", 1.9, 3.5),
        make_quote("fanduel", "spreads", "Team A", 2.1, -3.5),
        make_quote("fanduel", "spreads", "Team B", 1.8, 3.5),
    ]
    matchups = build_matchups(quotes)
    assert len(matchups) == 1
    assert set(matchups[0].quotes_by_bookmaker) == {"draftkings", "fanduel"}


def test_spreads_reject_same_direction_points():
    first = make_quote("draftkings", "spreads", "Team A", 2.0, -1.5)
    second = make_quote("draftkings", "spreads", "Team B", 1.9, -1.5)

    assert quotes_are_compatible(first, second) is False
    assert build_matchups([first, second]) == []


def test_period_spreads_require_opposite_points():
    first = make_quote("draftkings", "spreads_1st_1_innings", "Team A", 2.0, -1.5)
    second = make_quote("draftkings", "spreads_1st_1_innings", "Team B", 1.9, 1.5)

    assert quotes_are_compatible(first, second) is True


def test_totals_require_one_over_and_one_under_at_same_point():
    over = make_quote("draftkings", "totals", "Over", 2.0, 5.5)
    under = make_quote("draftkings", "totals", "Under", 1.9, 5.5)
    other_over = make_quote("draftkings", "totals", "Over", 1.8, 5.5)
    different_point = make_quote("draftkings", "totals", "Under", 1.9, 6.5)

    assert quotes_are_compatible(over, under) is True
    assert quotes_are_compatible(over, other_over) is False
    assert quotes_are_compatible(over, different_point) is False


def test_filter_binary_quotes_removes_unsupported_markets():
    quotes = [
        make_quote("draftkings", "h2h", "Team A", 2.0, sport_key="soccer_epl"),
        make_quote("draftkings", "h2h", "Draw", 3.2, sport_key="soccer_epl"),
        make_quote("draftkings", "h2h", "Team B", 1.9, sport_key="soccer_epl"),
    ]
    filtered = filter_binary_quotes(quotes, {"soccer_epl"})
    assert len(filtered) == 2
    assert all(q.outcome_name != "Draw" for q in filtered)


def test_build_matchups_orders_outcomes_by_name_not_api_order():
    quotes = [
        make_quote("draftkings", "totals", "Over", 2.0, 5.5),
        make_quote("draftkings", "totals", "Under", 1.9, 5.5),
        make_quote("fanduel", "totals", "Under", 2.1, 5.5),
        make_quote("fanduel", "totals", "Over", 1.8, 5.5),
    ]
    matchups = build_matchups(quotes)
    assert matchups[0].quotes_by_bookmaker["draftkings"][0].outcome_name == "Under"
    assert matchups[0].quotes_by_bookmaker["fanduel"][0].outcome_name == "Under"


def test_market_family_recognizes_bare_alternate_markets():
    assert market_family("alternate_spreads") == "spreads"
    assert market_family("alternate_totals") == "totals"


def test_alternate_spreads_require_opposite_points():
    first = make_quote("draftkings", "alternate_spreads", "Team A", 2.0, -2.5)
    second = make_quote("draftkings", "alternate_spreads", "Team B", 1.9, 2.5)
    same_direction = make_quote("draftkings", "alternate_spreads", "Team B", 1.9, -2.5)

    assert quotes_are_compatible(first, second) is True
    assert quotes_are_compatible(first, same_direction) is False


def test_alternate_totals_require_over_and_under_at_same_point():
    over = make_quote("draftkings", "alternate_totals", "Over", 2.0, 8.5)
    under = make_quote("draftkings", "alternate_totals", "Under", 1.9, 8.5)

    assert quotes_are_compatible(over, under) is True
    assert is_binary_market("alternate_spreads", False) is True
    assert is_binary_market("alternate_totals", False) is True
