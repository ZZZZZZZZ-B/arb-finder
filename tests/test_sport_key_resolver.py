from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.key_pool import KeyPool
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver


class SportsResponse:
    status_code = 200
    headers = {}
    content = b"[]"
    text = ""

    def json(self):
        return [
            {"key": "tennis_atp_active", "active": True},
            {"key": "tennis_atp_inactive", "active": False},
            {"key": "tennis_wta_active", "active": True},
        ]


class SportsSession:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return SportsResponse()


def test_get_sports_requests_all_when_including_inactive():
    session = SportsSession()
    client = OddsAPIClient(KeyPool(["key"]), session=session)

    sports = client.get_sports(include_inactive=True)

    assert len(sports) == 3
    assert session.calls[0]["params"]["all"] == "true"


def test_dynamic_prefix_can_include_inactive_sport_keys():
    session = SportsSession()
    resolver = SportKeyResolver(OddsAPIClient(KeyPool(["key"]), session=session))

    assert resolver.resolve_dynamic_prefix("tennis_atp_") == ["tennis_atp_active"]
    assert resolver.resolve_dynamic_prefix("tennis_atp_", include_inactive=True) == [
        "tennis_atp_active",
        "tennis_atp_inactive",
    ]