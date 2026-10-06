import pytest

from mac_assistant import Region, api_settings


@pytest.mark.parametrize("region, expected", [
    (Region("screen", 10, 20, 100, 50), True),
    (Region("screen", -1, 0, 10, 10), False),
    (Region("screen", 0, 0, 0, 10), False),
    (Region("screen", 149, 0, 10, 10), False),
    (Region("screen", "10", 0, 10, 10), False),
    (Region("screen", True, 0, 10, 10), False),
    (Region(None, 0, 0, 10, 10), False),
])
def test_region_bounds(region, expected):
    assert region.valid_for(150, 100) is expected


def test_mac_settings_do_not_require_discord(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    assert api_settings().openrouter_api_key == "test-only"


def test_mac_settings_require_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        api_settings()
