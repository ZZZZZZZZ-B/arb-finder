from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from promo_hedge_tool.odds_client.models import OddsQuote

NO_DRAW_MARKET_KEYS = {"h2h", "spreads", "totals"}
SOCCER_BINARY_MARKET_KEYS = {"draw_no_bet", "spreads", "totals"}


@dataclass(frozen=True)
class Matchup:
    event_id: str
    market_key: str
    quotes_by_bookmaker: dict[str, tuple[OddsQuote, OddsQuote]] = field(default_factory=dict)


def is_binary_market(market_key: str, is_soccer: bool) -> bool:
    allowed = SOCCER_BINARY_MARKET_KEYS if is_soccer else NO_DRAW_MARKET_KEYS
    return market_key in allowed


def filter_binary_quotes(quotes: Iterable[OddsQuote], soccer_sport_keys: set[str]) -> list[OddsQuote]:
    filtered: list[OddsQuote] = []
    for quote in quotes:
        is_soccer = quote.sport_key in soccer_sport_keys
        if is_binary_market(quote.market_key, is_soccer):
            filtered.append(quote)
    return filtered


def build_matchups(quotes: list[OddsQuote]) -> list[Matchup]:
    grouped: dict[tuple[str, str, float | None], list[OddsQuote]] = {}
    for quote in quotes:
        key = (quote.event_id, quote.market_key, None if quote.market_key in {"h2h", "draw_no_bet"} else abs(quote.point) if quote.point is not None else None)
        grouped.setdefault(key, []).append(quote)

    matchups: list[Matchup] = []
    for key, entries in grouped.items():
        quotes_by_bookmaker: dict[str, tuple[OddsQuote, OddsQuote]] = {}
        for entry in entries:
            if entry.bookmaker_key not in quotes_by_bookmaker:
                quotes_by_bookmaker[entry.bookmaker_key] = [entry, None]  # type: ignore[list-item]
            else:
                current = quotes_by_bookmaker[entry.bookmaker_key]
                if current[0] is None:
                    current[0] = entry
                elif current[1] is None:
                    current[1] = entry
        prepared = {}
        for bookmaker, pair in quotes_by_bookmaker.items():
            if pair[0] is not None and pair[1] is not None:
                prepared[bookmaker] = tuple(
                    sorted((pair[0], pair[1]), key=lambda quote: _outcome_sort_key(quote.outcome_name))
                )
        if prepared:
            matchups.append(Matchup(event_id=key[0], market_key=key[1], quotes_by_bookmaker=prepared))
    return matchups


def _outcome_sort_key(outcome_name: str) -> tuple[int, str]:
    normalized = re.sub(r"\s+", " ", outcome_name.strip().casefold())
    if normalized.startswith("under"):
        return (0, normalized)
    if normalized.startswith("over"):
        return (1, normalized)
    return (0, normalized)
