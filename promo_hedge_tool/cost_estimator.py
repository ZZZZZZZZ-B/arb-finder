from __future__ import annotations

import math
from dataclasses import dataclass, field

from promo_hedge_tool.config import Config
from promo_hedge_tool.engine import (
    fetch_all_event_sport_pairs,
    resolve_full_game_optional_market_keys,
    resolve_period_market_keys,
    resolve_sport_keys,
)
from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.run_context import RunContext, api_bookmaker_key
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class CostEstimate:
    total: int
    lines: list[str] = field(default_factory=list)


def regions_factor(bookmaker_count: int) -> int:
    return max(1, math.ceil(bookmaker_count / 10))


def estimate_run_cost(config: Config, context: RunContext, client: OddsAPIClient) -> CostEstimate:
    """Replicates The Odds API's cost = markets x regions [x events] formula, using only free /events calls."""
    platform_names = [context.base_bookmaker, *context.hedge_bookmakers]
    bookmakers = [api_bookmaker_key(config, name) for name in platform_names]
    regions = regions_factor(len(bookmakers))
    total = 0
    lines: list[str] = []

    if context.period == "full-game":
        resolver = SportKeyResolver(client)
        sport_keys = resolve_sport_keys(config, resolver, context.selected_leagues)
        flat_sport_keys = [sport_key for keys in sport_keys.values() for sport_key in keys]
        core_markets = list(config.full_game_markets.get("core_markets", ["h2h", "spreads", "totals"]))
        bulk_cost = len(flat_sport_keys) * len(core_markets) * regions
        total += bulk_cost
        lines.append(f"Full game core markets: {len(flat_sport_keys)} sport(s) x {len(core_markets)} market(s) x {regions} region(s) = {bulk_cost}")

        optional_market_keys = resolve_full_game_optional_market_keys(config, context.selected_markets)
        if optional_market_keys:
            if context.selected_event_sports:
                event_count = len(context.selected_event_sports)
            else:
                start = context.commence_time_from or datetime.now(timezone.utc)
                end = context.commence_time_to or start + timedelta(hours=config.event_window_hours)
                event_count = len(fetch_all_event_sport_pairs(client, flat_sport_keys, start, end))
            event_cost = len(optional_market_keys) * regions * event_count
            total += event_cost
            lines.append(
                f"Alternate markets: {event_count} event(s) x {len(optional_market_keys)} market(s) x {regions} region(s) = {event_cost}"
            )
    else:
        market_keys = resolve_period_market_keys(config, context.period, context.selected_markets)
        event_count = len(context.selected_event_sports)
        event_cost = len(market_keys) * regions * event_count
        total += event_cost
        lines.append(
            f"Period markets: {event_count} event(s) x {len(market_keys)} market(s) x {regions} region(s) = {event_cost}"
        )

    return CostEstimate(total=total, lines=lines)


def get_credit_thresholds(config: Config) -> tuple[int, int]:
    """Returns (core_market_threshold, alt_market_threshold) confirmation thresholds."""
    thresholds = config.full_game_markets.get("credit_thresholds", {})
    return int(thresholds.get("core_market", 20)), int(thresholds.get("alt_market", 50))


def estimate_core_market_cost(config: Config, context: RunContext, client: OddsAPIClient) -> CostEstimate:
    """Estimates the cost of the core full-game bulk /odds call only (no alt-market component)."""
    platform_names = [context.base_bookmaker, *context.hedge_bookmakers]
    bookmakers = [api_bookmaker_key(config, name) for name in platform_names]
    regions = regions_factor(len(bookmakers))
    resolver = SportKeyResolver(client)
    sport_keys = resolve_sport_keys(config, resolver, context.selected_leagues)
    flat_sport_keys = [sport_key for keys in sport_keys.values() for sport_key in keys]
    core_markets = list(config.full_game_markets.get("core_markets", ["h2h", "spreads", "totals"]))
    cost = len(flat_sport_keys) * len(core_markets) * regions
    lines = [f"Full game core markets: {len(flat_sport_keys)} sport(s) x {len(core_markets)} market(s) x {regions} region(s) = {cost}"]
    return CostEstimate(total=cost, lines=lines)


def estimate_alt_market_cost_for_events(
    config: Config, context: RunContext, event_sports: tuple[tuple[str, str], ...]
) -> CostEstimate:
    """Estimates alt-market cost from an already-known (prefiltered) event list -- no network calls."""
    platform_names = [context.base_bookmaker, *context.hedge_bookmakers]
    bookmakers = [api_bookmaker_key(config, name) for name in platform_names]
    regions = regions_factor(len(bookmakers))
    optional_market_keys = resolve_full_game_optional_market_keys(config, context.selected_markets)
    cost = len(event_sports) * len(optional_market_keys) * regions
    lines = [
        f"Alternate markets: {len(event_sports)} event(s) x {len(optional_market_keys)} market(s) x {regions} region(s) = {cost}"
    ]
    return CostEstimate(total=cost, lines=lines)
