from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from promo_hedge_tool.config import Config, load_config, resolve_api_keys
from promo_hedge_tool.exporter import export_csv, export_json
from promo_hedge_tool.market_filter import build_matchups, filter_binary_quotes
from promo_hedge_tool.odds_client.client import OddsAPIClient, OddsAPIError
from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool
from promo_hedge_tool.odds_client.models import OddsQuote
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.ranker import rank_top_n
from promo_hedge_tool.logging_config import configure_logging
from promo_hedge_tool.strategies.base import HedgeResult
from promo_hedge_tool.strategies.bonus_bet_snr import BonusBetSNRStrategy


def build_strategy(config: Config):
    if config.promo.type == "bonus_bet_snr":
        bonus = config.promo.bonus_bet_snr
        return BonusBetSNRStrategy(
            amount=float(bonus.get("amount", 100)),
            min_decimal_odds=float(bonus.get("min_decimal_odds", 3.4)),
            primary_bookmaker=config.promo.primary_bookmaker,
        )
    raise ValueError(f"Unsupported promo.type: {config.promo.type}")


def build_sport_keys(config: Config, resolver: SportKeyResolver) -> dict[str, list[str]]:
    mapping = {
        "nba": ["basketball_nba"],
        "mlb": ["baseball_mlb"],
        "nfl": ["americanfootball_nfl"],
        "ncaaf": ["americanfootball_ncaaf"],
        "ufc": ["mma_mixed_martial_arts"],
    }

    sport_cfg = config.sports or {}
    tennis_cfg = sport_cfg.get("tennis_atp", {})
    soccer_cfg = sport_cfg.get("soccer", {})

    if tennis_cfg:
        mapping["tennis_atp"] = resolver.resolve_dynamic_prefix(tennis_cfg.get("dynamic_prefix", "tennis_atp_"))
    if soccer_cfg:
        soccer_leagues = soccer_cfg.get("leagues", [])
        mapping["soccer"] = resolver.resolve_whitelist(soccer_leagues)

    for logical_name, sport_key in {
        "nba": sport_cfg.get("nba", {}).get("sport_key"),
        "mlb": sport_cfg.get("mlb", {}).get("sport_key"),
        "nfl": sport_cfg.get("nfl", {}).get("sport_key"),
        "ncaaf": sport_cfg.get("ncaaf", {}).get("sport_key"),
        "ufc": sport_cfg.get("ufc", {}).get("sport_key"),
    }.items():
        if sport_key:
            mapping[logical_name] = resolver.resolve_fixed(sport_key)

    resolved = {k: v for k, v in mapping.items() if v}
    logging.getLogger(__name__).info("Resolved sport keys: %s", resolved)
    return resolved


def run_once(config_path: str | Path = "config/config.yaml") -> list[HedgeResult]:
    logger = logging.getLogger(__name__)
    config = load_config(config_path)
    logger.info("Loaded config from %s", config_path)
    api_keys = resolve_api_keys(config.odds_api.api_key_envs)
    logger.info("Resolved %d API key(s)", len(api_keys))
    key_pool = KeyPool(api_keys)
    client = OddsAPIClient(key_pool)
    resolver = SportKeyResolver(client)

    strategy = build_strategy(config)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=config.event_window_hours)
    api_bookmakers = list({config.promo.primary_bookmaker} | set(config.promo.hedge_bookmakers) & set(config.odds_api.bookmakers))
    if not api_bookmakers:
        api_bookmakers = list(config.odds_api.bookmakers[:])
    logger.info(
        "Run parameters: bookmakers=%s, event_window=%s to %s, top_n=%d",
        ",".join(api_bookmakers),
        now.isoformat(),
        window_end.isoformat(),
        config.top_n,
    )

    all_quotes: list[OddsQuote] = []
    sport_keys_by_logical_sport = build_sport_keys(config, resolver)
    soccer_sport_keys = set(sport_keys_by_logical_sport.get("soccer", []))

    for logical_sport, sport_keys in sport_keys_by_logical_sport.items():
        markets = ["draw_no_bet", "spreads", "totals"] if logical_sport == "soccer" else ["h2h", "spreads", "totals"]
        for sport_key in sport_keys:
            try:
                logger.info("Fetching odds: logical_sport=%s sport_key=%s markets=%s", logical_sport, sport_key, ",".join(markets))
                quotes = client.get_odds(sport_key, api_bookmakers, markets, now, window_end)
                all_quotes.extend(quotes)
            except AllKeysExhaustedError:
                raise
            except OddsAPIError as exc:
                logger.warning("Skipping sport=%s after API error: %s", sport_key, exc)
                continue

    logger.info("Collected quotes: %d", len(all_quotes))
    binary_quotes = filter_binary_quotes(all_quotes, soccer_sport_keys)
    logger.info("Binary market filter: %d -> %d quotes", len(all_quotes), len(binary_quotes))
    matchups = build_matchups(binary_quotes)
    logger.info("Built %d complete matchups", len(matchups))

    results: list[HedgeResult] = []
    for matchup in matchups:
        primary_pair = matchup.quotes_by_bookmaker.get(config.promo.primary_bookmaker)
        if not primary_pair:
            continue
        hedge_candidates = {
            bookmaker: matchup.quotes_by_bookmaker[bookmaker]
            for bookmaker in config.promo.hedge_bookmakers
            if bookmaker in matchup.quotes_by_bookmaker
        }
        if not hedge_candidates:
            continue
        for side in (0, 1):
            primary_quote = primary_pair[side]
            if not strategy.is_eligible(primary_quote):
                continue
            opposite = 1 - side
            candidates = [pair[opposite] for pair in hedge_candidates.values()]
            if not candidates:
                continue
            hedge_quote = max(candidates, key=lambda q: q.decimal_odds)
            result = strategy.calculate(primary_quote, hedge_quote)
            if result:
                results.append(result)

    logger.info("Calculated %d hedge result(s)", len(results))
    ranked_results = rank_top_n(results, config.top_n)
    logger.info("Ranked results: returning %d result(s)", len(ranked_results))
    output_dir = Path(config.output.get("output_dir", "./output"))
    output_dir.mkdir(exist_ok=True)
    csv_path = export_csv(ranked_results, output_dir / "hedge_results.csv")
    json_path = export_json(ranked_results, output_dir / "hedge_results.json", meta={
        "promo_type": config.promo.type,
        "primary_bookmaker": config.promo.primary_bookmaker,
        "hedge_bookmakers": config.promo.hedge_bookmakers,
        "top_n": config.top_n,
    })
    logger.info("Exported results: csv=%s json=%s", csv_path, json_path)
    return ranked_results


def main() -> None:
    configure_logging()
    try:
        run_once()
    except AllKeysExhaustedError:
        raise SystemExit("All configured API keys are exhausted for this month.")


if __name__ == "__main__":
    main()
