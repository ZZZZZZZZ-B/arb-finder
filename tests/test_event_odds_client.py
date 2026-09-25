from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.key_pool import KeyPool


class FakeResponse:
    status_code = 200
    headers = {"x-requests-remaining": "499", "x-requests-used": "1", "x-requests-last": "1"}
    content = b"1"
    text = ""

    def json(self):
        return {
            "id": "event-1",
            "sport_key": "baseball_mlb",
            "commence_time": "2026-09-26T00:00:00Z",
            "home_team": "Home",
            "away_team": "Away",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "spreads_1st_1_innings",
                            "outcomes": [
                                {"name": "Home", "price": 2.0, "point": 0.5},
                                {"name": "Away", "price": 1.8, "point": -0.5},
                            ],
                        }
                    ],
                }
            ],
        }


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


def test_get_event_odds_uses_single_event_endpoint_and_parses_quotes():
    session = FakeSession()
    client = OddsAPIClient(KeyPool(["key"]), session=session)

    quotes = client.get_event_odds(
        "baseball_mlb",
        "event-1",
        ["draftkings"],
        ["spreads_1st_1_innings"],
    )

    assert session.calls[0]["url"].endswith("/v4/sports/baseball_mlb/events/event-1/odds")
    assert session.calls[0]["params"]["markets"] == "spreads_1st_1_innings"
    assert len(quotes) == 2
    assert quotes[0].market_key == "spreads_1st_1_innings"
    assert quotes[0].point == 0.5
