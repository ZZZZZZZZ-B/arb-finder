import pytest

from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool


def test_round_robin_uses_next_key_and_skips_exhausted():
    pool = KeyPool(["k1", "k2", "k3"])
    assert pool.next_key() == "k1"
    assert pool.next_key() == "k2"
    pool.report_quota("k2", 0)
    assert pool.next_key() == "k3"


def test_exhausted_key_reports_status():
    pool = KeyPool(["k1", "k2"])
    pool.report_quota("k1", 0)
    assert pool.status()["k1"] == 0
    assert "k1" in pool._exhausted


def test_all_exhausted_raises():
    pool = KeyPool(["k1"])
    pool.report_quota("k1", 0)
    with pytest.raises(AllKeysExhaustedError):
        pool.next_key()
