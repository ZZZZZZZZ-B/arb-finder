from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes, is_binary_market
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
        make_quote("draftkings", "spreads", "Team B", 1.9, -3.5),
        make_quote("fanduel", "spreads", "Team A", 2.1, -3.5),
        make_quote("fanduel", "spreads", "Team B", 1.8, -3.5),
    ]
    matchups = build_matchups(quotes)
    assert len(matchups) == 1
    assert set(matchups[0].quotes_by_bookmaker) == {"draftkings", "fanduel"}


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
