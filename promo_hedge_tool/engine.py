from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from promo_hedge_tool.config import Config, resolve_api_keys
from promo_hedge_tool.exporter import export_csv, export_json
from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes, quotes_are_compatible
from promo_hedge_tool.odds_client.client import OddsAPIClient, OddsAPIError
from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool
from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.odds_cache import odds_cache
from promo_hedge_tool.ranker import rank_top_n
from promo_hedge_tool.run_context import RunContext
from promo_hedge_tool.strategies.base import HedgeResult
from promo_hedge_tool.strategies.bonus_bet_snr import BonusBetSNRStrategy
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
        elif values.get("dynamic_prefix") and (not selected_set or logical_name in selected_set):
            result[logical_name] = resolver.resolve_dynamic_prefix(values["dynamic_prefix"])
    return {name: keys for name, keys in result.items() if keys}


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


def _calculate(
    config: Config,
    context: RunContext,
    all_quotes: list[OddsQuote],
    soccer_keys: set[str],
    output_dir: str | Path | None = None,
) -> list[HedgeResult]:
    strategy = build_strategy(config, context)
    if context.selected_event_ids:
        all_quotes = [quote for quote in all_quotes if quote.event_id in context.selected_event_ids]
    filtered = filter_binary_quotes(all_quotes, soccer_keys)
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

    ranked = rank_top_n(results, config.top_n, key="locked_profit" if context.mode == "profit-boost" else "conversion_rate_pct")
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
        bookmakers = [context.base_bookmaker, *context.hedge_bookmakers]
        all_quotes: list[OddsQuote] = []
        if context.period == "full-game":
            resolver = SportKeyResolver(client)
            sport_keys = resolve_sport_keys(config, resolver, context.selected_leagues)
            soccer_keys = set(sport_keys.get("soccer", []))
            start = context.commence_time_from or datetime.now(timezone.utc)
            end = context.commence_time_to or start + timedelta(hours=config.event_window_hours)
            for _logical_name, keys in sport_keys.items():
                for sport_key in keys:
                    try:
                        all_quotes.extend(client.get_odds(
                            sport_key,
                            bookmakers,
                            ["h2h", "spreads", "totals"],
                            start,
                            end,
                            odds_format=config.odds_api.odds_format,
                            date_format=config.odds_api.date_format,
                        ))
                    except AllKeysExhaustedError:
                        raise
                    except OddsAPIError as exc:
                        logger.warning("Skipping sport %s: %s", sport_key, exc)
        else:
            market_keys = resolve_period_market_keys(config, context.period, context.selected_markets)
            event_sports = context.selected_event_sports
            if not event_sports:
                raise ValueError("Selected event sport keys are required for period markets")
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
                        all_quotes.extend(quotes)
                    else:
                        skipped += 1
                except AllKeysExhaustedError:
                    raise
                except OddsAPIError as exc:
                    skipped += 1
                    logger.warning("Skipping event %s (%s): %s", event_id, sport_key, exc)
            if skipped:
                logger.warning("Skipped %d period event(s) without usable odds", skipped)
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