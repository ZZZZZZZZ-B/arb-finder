from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Iterable

from promo_hedge_tool.odds_client.models import OddsQuote

NO_DRAW_MARKET_KEYS = {"h2h", "spreads", "totals"}
SOCCER_BINARY_MARKET_KEYS = {"h2h", "spreads", "totals"}


def market_family(market_key: str) -> str:
    if market_key == "h2h" or market_key.startswith("h2h_"):
        return "h2h"
    if (
        market_key in ("spreads", "alternate_spreads")
        or market_key.startswith("spreads_")
        or market_key.startswith("alternate_spreads_")
    ):
        return "spreads"
    if (
        market_key in ("totals", "alternate_totals")
        or market_key.startswith("totals_")
        or market_key.startswith("alternate_totals_")
    ):
        return "totals"
    return market_key


@dataclass(frozen=True)
class Matchup:
    event_id: str
    market_key: str
    quotes_by_bookmaker: dict[str, tuple[OddsQuote, OddsQuote]] = field(default_factory=dict)


def is_binary_market(market_key: str, is_soccer: bool) -> bool:
    allowed = SOCCER_BINARY_MARKET_KEYS if is_soccer else NO_DRAW_MARKET_KEYS
    return market_key in allowed or market_family(market_key) in {"spreads", "totals"}


def filter_binary_quotes(quotes: Iterable[OddsQuote], soccer_sport_keys: set[str]) -> list[OddsQuote]:
    filtered: list[OddsQuote] = []
    for quote in quotes:
        is_soccer = quote.sport_key in soccer_sport_keys
        is_draw_outcome = quote.outcome_name.strip().casefold() == "draw"
        if is_binary_market(quote.market_key, is_soccer) and not (is_soccer and quote.market_key == "h2h" and is_draw_outcome):
            filtered.append(quote)
    return filtered


def quotes_are_compatible(first: OddsQuote, second: OddsQuote) -> bool:
    if first.event_id != second.event_id or first.market_key != second.market_key:
        return False
    family = market_family(first.market_key)
    if family == "h2h":
        return _normalized_outcome(first.outcome_name) != _normalized_outcome(second.outcome_name)
    if family == "spreads":
        return (
            first.point is not None
            and second.point is not None
            and math.isclose(abs(first.point), abs(second.point))
            and first.point * second.point < 0
            and _normalized_outcome(first.outcome_name) != _normalized_outcome(second.outcome_name)
        )
    if family == "totals":
        return (
            first.point is not None
            and second.point is not None
            and math.isclose(first.point, second.point)
            and {_total_direction(first.outcome_name), _total_direction(second.outcome_name)} == {"over", "under"}
        )
    return False


def build_matchups(quotes: list[OddsQuote]) -> list[Matchup]:
    grouped: dict[tuple[str, str, float | None], list[OddsQuote]] = {}
    for quote in quotes:
        key = (
            quote.event_id,
            quote.market_key,
            None
            if market_family(quote.market_key) == "h2h"
            else abs(quote.point) if market_family(quote.market_key) == "spreads" and quote.point is not None else quote.point,
        )
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
            entries_for_bookmaker = [entry for entry in entries if entry.bookmaker_key == bookmaker]
            compatible = next(
                (
                    (first, second)
                    for index, first in enumerate(entries_for_bookmaker)
                    for second in entries_for_bookmaker[index + 1 :]
                    if quotes_are_compatible(first, second)
                ),
                None,
            )
            if compatible is not None:
                prepared[bookmaker] = tuple(sorted(compatible, key=lambda quote: _outcome_sort_key(quote.outcome_name)))
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


def _normalized_outcome(outcome_name: str) -> str:
    return re.sub(r"\s+", " ", outcome_name.strip().casefold())


def _total_direction(outcome_name: str) -> str:
    normalized = _normalized_outcome(outcome_name)
    if normalized.startswith("over"):
        return "over"
    if normalized.startswith("under"):
        return "under"
    return normalized
