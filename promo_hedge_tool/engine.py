from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from promo_hedge_tool.config import Config, resolve_api_keys
from promo_hedge_tool.exporter import export_csv, export_json
from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes, quotes_are_compatible
from promo_hedge_tool.odds_client.client import OddsAPIClient, OddsAPIError
from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool
from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.odds_cache import odds_cache
from promo_hedge_tool.ranker import rank_top_n
from promo_hedge_tool.run_context import RunContext, api_bookmaker_key, normalize_bookmaker_quotes
from promo_hedge_tool.strategies.base import HedgeResult
from promo_hedge_tool.strategies.bonus_bet_snr import BonusBetSNRStrategy
from promo_hedge_tool.strategies.no_sweat import NoSweatStrategy
from promo_hedge_tool.strategies.profit_boost import ProfitBoostStrategy


logger = logging.getLogger(__name__)


def build_strategy(config: Config, context: RunContext):
    if context.mode == "bonus-bet":
        return BonusBetSNRStrategy(
            amount=float(context.bonus_amount),
            odds_operator=context.odds_operator,
            odds_requirement_american=context.odds_requirement_american,
            primary_bookmaker=context.base_bookmaker,
        )
    if context.mode == "no-sweat":
        return NoSweatStrategy(
            float(context.stake),
            float(config.no_sweat.get("bonus_value_ratio", 0.7)),
            context.odds_operator,
            context.odds_requirement_american,
        )
    return ProfitBoostStrategy(
        float(context.stake),
        float(context.boost_percent),
        context.odds_operator,
        context.odds_requirement_american,
    )


def resolve_sport_keys(config: Config, resolver: SportKeyResolver, selected: tuple[str, ...]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    selected_set = set(selected)
    for logical_name, values in config.sports.items():
        if logical_name == "soccer":
            keys = values.get("leagues", [])
            result[logical_name] = resolver.resolve_whitelist([key for key in keys if not selected_set or key in selected_set])
        elif values.get("sport_key") and (not selected_set or logical_name in selected_set or values["sport_key"] in selected_set):
            result[logical_name] = resolver.resolve_fixed(values["sport_key"])
        elif values.get("dynamic_prefix"):
            prefix = str(values["dynamic_prefix"])
            if not selected_set or logical_name in selected_set:
                result[logical_name] = resolver.resolve_dynamic_prefix(prefix)
            else:
                selected_dynamic = [key for key in selected if key.startswith(prefix)]
                if selected_dynamic:
                    available = set(resolver.resolve_dynamic_prefix(prefix))
                    result[logical_name] = [key for key in selected_dynamic if key in available]
    return {name: keys for name, keys in result.items() if keys}


def resolve_full_game_optional_market_keys(config: Config, selected_markets: tuple[str, ...]) -> tuple[str, ...]:
    optional_markets = config.full_game_markets.get("optional_markets", {})
    keys: list[str] = []
    for market_name in selected_markets:
        market = optional_markets.get(market_name)
        if not market:
            raise ValueError(f"Unknown full-game market {market_name!r}")
        market_key = market.get("market_key")
        if not market_key:
            raise ValueError(f"Market {market_name!r} has no API market key")
        keys.append(str(market_key))
    return tuple(dict.fromkeys(keys))


def resolve_period_market_keys(config: Config, period: str, selected_markets: tuple[str, ...]) -> tuple[str, ...]:
    definition = config.periods.get(period)
    if not definition:
        raise ValueError(f"Unknown period: {period}")
    configured_markets = definition.get("markets", {})
    keys: list[str] = []
    for market_name in selected_markets:
        market = configured_markets.get(market_name)
        if not market:
            raise ValueError(f"Unknown market {market_name!r} for period {period!r}")
        market_key = market.get("market_key")
        if not market_key:
            raise ValueError(f"Market {market_name!r} has no API market key")
        keys.append(str(market_key))
    return tuple(dict.fromkeys(keys))


def _rank(
    config: Config,
    context: RunContext,
    all_quotes: list[OddsQuote],
    soccer_keys: set[str],
) -> list[HedgeResult]:
    strategy = build_strategy(config, context)
    quotes = all_quotes
    if context.selected_event_ids:
        quotes = [quote for quote in quotes if quote.event_id in context.selected_event_ids]
    filtered = filter_binary_quotes(quotes, soccer_keys)
    results: list[HedgeResult] = []
    for matchup in build_matchups(filtered):
        base_pair = matchup.quotes_by_bookmaker.get(context.base_bookmaker)
        if not base_pair:
            continue
        hedge_pairs = [matchup.quotes_by_bookmaker[name] for name in context.hedge_bookmakers if name in matchup.quotes_by_bookmaker]
        for side, base_quote in enumerate(base_pair):
            if not strategy.is_eligible(base_quote):
                continue
            candidates = [
                pair[1 - side]
                for pair in hedge_pairs
                if quotes_are_compatible(base_quote, pair[1 - side])
            ]
            if candidates:
                result = strategy.calculate(base_quote, max(candidates, key=lambda quote: quote.decimal_odds))
                if result:
                    results.append(result)

    return rank_top_n(results, config.top_n, key="conversion_rate_pct" if context.mode == "bonus-bet" else "locked_profit")


def _export(
    config: Config,
    context: RunContext,
    ranked: list[HedgeResult],
    output_dir: str | Path | None = None,
) -> list[HedgeResult]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = Path(output_dir or config.output.get("output_dir", "./output"))
    export_csv(ranked, destination / f"hedge_results_{stamp}.csv")
    export_json(ranked, destination / f"hedge_results_{stamp}.json", meta={
        "promo_type": context.mode,
        "period": context.period,
        "selected_markets": list(context.selected_markets),
        "base_bookmaker": context.base_bookmaker,
        "hedge_bookmakers": list(context.hedge_bookmakers),
        "selected_leagues": list(context.selected_leagues),
        "selected_event_ids": list(context.selected_event_ids),
        "stake": context.stake,
        "boost_percent": context.boost_percent,
    })
    return ranked


def _calculate(
    config: Config,
    context: RunContext,
    all_quotes: list[OddsQuote],
    soccer_keys: set[str],
    output_dir: str | Path | None = None,
) -> list[HedgeResult]:
    ranked = _rank(config, context, all_quotes, soccer_keys)
    return _export(config, context, ranked, output_dir)


def fetch_all_event_sport_pairs(
    client: OddsAPIClient,
    sport_keys: Iterable[str],
    commence_time_from: datetime,
    commence_time_to: datetime,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for sport_key in sport_keys:
        events = client.get_events(
            sport_key,
            commenceTimeFrom=client._isoformat(commence_time_from),
            commenceTimeTo=client._isoformat(commence_time_to),
            dateFormat="iso",
        )
        pairs.extend((sport_key, event.get("id", "")) for event in events if event.get("id"))
    return pairs


def _fetch_event_market_quotes(
    config: Config,
    client: OddsAPIClient,
    bookmakers: list[str],
    market_keys: tuple[str, ...],
    event_sports: Iterable[tuple[str, str]],
    all_quotes: list[OddsQuote],
    skip_label: str,
) -> None:
    skipped = 0
    for sport_key, event_id in event_sports:
        try:
            quotes = client.get_event_odds(
                sport_key,
                event_id,
                bookmakers,
                list(market_keys),
                odds_format=config.odds_api.odds_format,
                date_format=config.odds_api.date_format,
            )
            if quotes:
                all_quotes.extend(normalize_bookmaker_quotes(config, quotes))
            else:
                skipped += 1
        except AllKeysExhaustedError:
            raise
        except OddsAPIError as exc:
            skipped += 1
            logger.warning("Skipping %s %s (%s): %s", skip_label, event_id, sport_key, exc)
    if skipped:
        logger.warning("Skipped %d %s event(s) without usable odds", skipped, skip_label)


@dataclass
class CorePhaseResult:
    all_quotes: list[OddsQuote]
    soccer_keys: set[str]
    core_results: list[HedgeResult]
    bookmakers: list[str] = field(default_factory=list)
    flat_sport_keys: list[str] = field(default_factory=list)


def fetch_core_quotes(
    config: Config,
    context: RunContext,
    client: OddsAPIClient,
) -> tuple[list[OddsQuote], set[str], list[str], list[str]]:
    """Fetches core full-game markets (h2h/spreads/totals) via the bulk /odds endpoint."""
    platform_names = [context.base_bookmaker, *context.hedge_bookmakers]
    bookmakers = [api_bookmaker_key(config, name) for name in platform_names]
    resolver = SportKeyResolver(client)
    sport_keys = resolve_sport_keys(config, resolver, context.selected_leagues)
    soccer_keys = set(sport_keys.get("soccer", []))
    start = context.commence_time_from or datetime.now(timezone.utc)
    end = context.commence_time_to or start + timedelta(hours=config.event_window_hours)
    core_markets = list(config.full_game_markets.get("core_markets", ["h2h", "spreads", "totals"]))
    flat_sport_keys = [sport_key for keys in sport_keys.values() for sport_key in keys]
    all_quotes: list[OddsQuote] = []
    for sport_key in flat_sport_keys:
        try:
            quotes = client.get_odds(
                sport_key,
                bookmakers,
                core_markets,
                start,
                end,
                odds_format=config.odds_api.odds_format,
                date_format=config.odds_api.date_format,
            )
            all_quotes.extend(normalize_bookmaker_quotes(config, quotes))
        except AllKeysExhaustedError:
            raise
        except OddsAPIError as exc:
            logger.warning("Skipping sport %s: %s", sport_key, exc)
    return all_quotes, soccer_keys, flat_sport_keys, bookmakers


def select_prefilter_event_sports(
    config: Config,
    context: RunContext,
    core_results: list[HedgeResult],
) -> tuple[tuple[str, str], ...]:
    """Ranks events by their best core-market result and keeps only the top N as alt-market candidates."""
    top_n = int(config.full_game_markets.get("alt_market_prefilter", {}).get("top_n", 20))
    metric = "conversion_rate_pct" if context.mode == "bonus-bet" else "locked_profit"
    best_by_event: dict[str, HedgeResult] = {}
    for result in core_results:
        current = best_by_event.get(result.event_id)
        if current is None or getattr(result, metric) > getattr(current, metric):
            best_by_event[result.event_id] = result
    ranked_events = sorted(best_by_event.values(), key=lambda result: getattr(result, metric), reverse=True)
    return tuple(dict.fromkeys((result.sport_key, result.event_id) for result in ranked_events[:top_n]))


def run_core_phase(config: Config, context: RunContext) -> CorePhaseResult:
    """Fetches and ranks core full-game markets only, without exporting results."""
    cache_path = Path(config.output.get("output_dir", "./output")) / "odds_cache.sqlite3"
    odds_cache.configure(cache_path)
    odds_cache.clear()
    api_keys = resolve_api_keys(config.odds_api.api_key_envs)
    client = OddsAPIClient(KeyPool(api_keys))
    all_quotes, soccer_keys, flat_sport_keys, bookmakers = fetch_core_quotes(config, context, client)
    core_results = _rank(config, context, all_quotes, soccer_keys)
    return CorePhaseResult(
        all_quotes=all_quotes,
        soccer_keys=soccer_keys,
        core_results=core_results,
        bookmakers=bookmakers,
        flat_sport_keys=flat_sport_keys,
    )


def finalize_core_only(
    config: Config,
    context: RunContext,
    core_phase: CorePhaseResult,
    output_dir: str | Path | None = None,
) -> list[HedgeResult]:
    """Exports the core-market-only results (used when the alt-market stage is declined)."""
    cache_path = Path(config.output.get("output_dir", "./output")) / "odds_cache.sqlite3"
    odds_cache.configure(cache_path)
    odds_cache.replace(core_phase.all_quotes)
    return _export(config, context, core_phase.core_results, output_dir)


def run_alt_phase(
    config: Config,
    context: RunContext,
    core_phase: CorePhaseResult,
    event_sports: tuple[tuple[str, str], ...],
    output_dir: str | Path | None = None,
) -> list[HedgeResult]:
    """Fetches alt markets for the prefiltered events and recalculates combined results."""
    api_keys = resolve_api_keys(config.odds_api.api_key_envs)
    client = OddsAPIClient(KeyPool(api_keys))
    optional_market_keys = resolve_full_game_optional_market_keys(config, context.selected_markets)
    combined_quotes = list(core_phase.all_quotes)
    _fetch_event_market_quotes(
        config, client, core_phase.bookmakers, optional_market_keys, event_sports, combined_quotes, "full-game alternate"
    )
    cache_path = Path(config.output.get("output_dir", "./output")) / "odds_cache.sqlite3"
    odds_cache.configure(cache_path)
    odds_cache.replace(combined_quotes)
    return _calculate(config, context, combined_quotes, core_phase.soccer_keys, output_dir)


def execute(
    config: Config,
    context: RunContext,
    output_dir: str | Path | None = None,
    fetch_latest: bool = True,
) -> list[HedgeResult]:
    soccer_keys: set[str] = set()
    if fetch_latest:
        cache_path = Path(config.output.get("output_dir", "./output")) / "odds_cache.sqlite3"
        odds_cache.configure(cache_path)
        odds_cache.clear()
        api_keys = resolve_api_keys(config.odds_api.api_key_envs)
        client = OddsAPIClient(KeyPool(api_keys))
        platform_names = [context.base_bookmaker, *context.hedge_bookmakers]
        bookmakers = [api_bookmaker_key(config, name) for name in platform_names]
        all_quotes: list[OddsQuote] = []
        if context.period == "full-game":
            all_quotes, soccer_keys, flat_sport_keys, bookmakers = fetch_core_quotes(config, context, client)
            start = context.commence_time_from or datetime.now(timezone.utc)
            end = context.commence_time_to or start + timedelta(hours=config.event_window_hours)

            optional_market_keys = resolve_full_game_optional_market_keys(config, context.selected_markets)
            if optional_market_keys:
                event_sports = context.selected_event_sports or fetch_all_event_sport_pairs(
                    client, flat_sport_keys, start, end
                )
                _fetch_event_market_quotes(
                    config, client, bookmakers, optional_market_keys, event_sports, all_quotes, "full-game alternate"
                )
        else:
            market_keys = resolve_period_market_keys(config, context.period, context.selected_markets)
            event_sports = context.selected_event_sports
            if not event_sports:
                raise ValueError("Selected event sport keys are required for period markets")
            _fetch_event_market_quotes(config, client, bookmakers, market_keys, event_sports, all_quotes, "period")
        odds_cache.replace(all_quotes)
    else:
        cache_path = Path(config.output.get("output_dir", "./output")) / "odds_cache.sqlite3"
        odds_cache.configure(cache_path)
        all_quotes = odds_cache.get()
        if not all_quotes:
            raise ValueError("No cached odds are available. Fetch the latest Odds API data first.")
        configured_soccer_keys = set(config.sports.get("soccer", {}).get("leagues", []))
        selected_soccer_keys = configured_soccer_keys.intersection(context.selected_leagues) if context.selected_leagues else configured_soccer_keys
        soccer_keys = {quote.sport_key for quote in all_quotes if quote.sport_key in selected_soccer_keys}
    return _calculate(config, context, all_quotes, soccer_keys, output_dir)