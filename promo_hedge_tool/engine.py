from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from promo_hedge_tool.config import Config, resolve_api_keys
from promo_hedge_tool.exporter import export_csv, export_json
from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes
from promo_hedge_tool.odds_client.client import OddsAPIClient, OddsAPIError
from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool
from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.ranker import rank_top_n
from promo_hedge_tool.run_context import RunContext
from promo_hedge_tool.strategies.base import HedgeResult
from promo_hedge_tool.strategies.bonus_bet_snr import BonusBetSNRStrategy
from promo_hedge_tool.strategies.profit_boost import ProfitBoostStrategy


logger = logging.getLogger(__name__)


def build_strategy(config: Config, context: RunContext):
    if context.mode == "bonus-bet":
        bonus = config.promo.bonus_bet_snr
        return BonusBetSNRStrategy(
            amount=float(bonus.get("amount", 100)),
            min_decimal_odds=float(bonus.get("min_decimal_odds", 3.4)),
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


def execute(config: Config, context: RunContext, output_dir: str | Path | None = None) -> list[HedgeResult]:
    api_keys = resolve_api_keys(config.odds_api.api_key_envs)
    client = OddsAPIClient(KeyPool(api_keys))
    resolver = SportKeyResolver(client)
    strategy = build_strategy(config, context)
    start = context.commence_time_from or datetime.now(timezone.utc)
    end = context.commence_time_to or start + timedelta(hours=config.event_window_hours)
    sport_keys = resolve_sport_keys(config, resolver, context.selected_leagues)
    soccer_keys = set(sport_keys.get("soccer", []))
    bookmakers = [context.base_bookmaker, *context.hedge_bookmakers]
    all_quotes: list[OddsQuote] = []

    for logical_name, keys in sport_keys.items():
        markets = ["h2h", "spreads", "totals"]
        for sport_key in keys:
            try:
                all_quotes.extend(
                    client.get_odds(
                        sport_key,
                        bookmakers,
                        markets,
                        start,
                        end,
                        odds_format=config.odds_api.odds_format,
                        date_format=config.odds_api.date_format,
                    )
                )
            except AllKeysExhaustedError:
                raise
            except OddsAPIError as exc:
                logger.warning("Skipping sport %s: %s", sport_key, exc)

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
            candidates = [pair[1 - side] for pair in hedge_pairs]
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
        "base_bookmaker": context.base_bookmaker,
        "hedge_bookmakers": list(context.hedge_bookmakers),
        "selected_leagues": list(context.selected_leagues),
        "selected_event_ids": list(context.selected_event_ids),
        "stake": context.stake,
        "boost_percent": context.boost_percent,
    })
    return ranked