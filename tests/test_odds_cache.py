from promo_hedge_tool.odds_cache import OddsCache
from promo_hedge_tool.odds_client.models import OddsQuote


def _quote(event_id: str) -> OddsQuote:
    return OddsQuote(
        sport_key="basketball_nba",
        event_id=event_id,
        commence_time="2026-09-23T00:00:00Z",
        home_team="Home",
        away_team="Away",
        bookmaker_key="draftkings",
        bookmaker_title="DraftKings",
        market_key="h2h",
        outcome_name="Home",
        decimal_odds=2.0,
    )


def test_cache_replaces_previous_snapshot_and_returns_a_copy(tmp_path):
    cache = OddsCache(tmp_path / "odds.sqlite3")
    cache.replace([_quote("old")])
    snapshot = cache.get()
    snapshot.clear()

    assert [quote.event_id for quote in cache.get()] == ["old"]

    cache.clear()
    cache.replace([_quote("new")])
    assert [quote.event_id for quote in cache.get()] == ["new"]


def test_cache_starts_empty(tmp_path):
    assert OddsCache(tmp_path / "odds.sqlite3").get() == []


def test_cache_survives_reopening(tmp_path):
    path = tmp_path / "odds.sqlite3"
    OddsCache(path).replace([_quote("persisted")])

    assert [quote.event_id for quote in OddsCache(path).get()] == ["persisted"]