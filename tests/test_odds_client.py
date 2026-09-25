from promo_hedge_tool.odds_client.client import mask_api_key


def test_mask_api_key_shows_first_three_and_last_character():
    assert mask_api_key("abcdefghijkl") == "abc...l"


def test_mask_api_key_hides_short_keys():
    assert mask_api_key("abcd") == "****"