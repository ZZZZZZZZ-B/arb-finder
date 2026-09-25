from __future__ import annotations

from threading import RLock

from promo_hedge_tool.odds_client.models import OddsQuote


class OddsCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._quotes: tuple[OddsQuote, ...] = ()

    def clear(self) -> None:
        with self._lock:
            self._quotes = ()

    def replace(self, quotes: list[OddsQuote]) -> None:
        with self._lock:
            self._quotes = tuple(quotes)

    def get(self) -> list[OddsQuote]:
        with self._lock:
            return list(self._quotes)


odds_cache = OddsCache()