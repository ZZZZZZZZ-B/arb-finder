from __future__ import annotations

from typing import Iterable

from promo_hedge_tool.odds_client.client import OddsAPIClient


class SportKeyResolver:
    def __init__(self, client: OddsAPIClient):
        self._client = client
        self._sports_cache: list[dict] | None = None

    def _load_sports(self) -> list[dict]:
        if self._sports_cache is None:
            sports = self._client.get_sports(include_inactive=True)
            self._sports_cache = [
                {"key": item.key, "group": item.group, "title": item.title, "active": item.active}
                for item in sports
            ]
        return self._sports_cache

    def resolve_fixed(self, sport_key: str) -> list[str]:
        for item in self._load_sports():
            if item.get("key") == sport_key and item.get("active", False):
                return [sport_key]
        return []

    def resolve_dynamic_prefix(self, prefix: str) -> list[str]:
        matches: list[str] = []
        for item in self._load_sports():
            key = item.get("key", "")
            if key.startswith(prefix) and item.get("active", False):
                matches.append(key)
        return matches

    def resolve_whitelist(self, keys: Iterable[str]) -> list[str]:
        allowed: list[str] = []
        available = {item.get("key") for item in self._load_sports() if item.get("key")}
        for key in keys:
            if key in available:
                allowed.append(key)
        return allowed
