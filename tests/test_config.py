from promo_hedge_tool.config import resolve_api_keys


def test_resolve_api_keys_splits_one_environment_variable(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEYS", "first-key, second-key;third-key\nfourth-key")

    assert resolve_api_keys(["ODDS_API_KEYS"]) == [
        "first-key",
        "second-key",
        "third-key",
        "fourth-key",
    ]