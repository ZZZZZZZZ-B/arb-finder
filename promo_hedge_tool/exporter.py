from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from promo_hedge_tool.strategies.base import HedgeResult


def export_csv(results: Iterable[HedgeResult], output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "event_name",
        "commence_time_local",
        "primary_bookmaker",
        "primary_selection",
        "primary_odds_decimal",
        "hedge_platform",
        "hedge_selection",
        "hedge_odds_decimal",
        "hedge_stake",
        "locked_profit",
        "conversion_rate_pct",
    ]

    rows = [result.__dict__ for result in results]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "event_name": row["event_name"],
                "commence_time_local": row["commence_time_local"],
                "primary_bookmaker": row["primary_bookmaker"],
                "primary_selection": row["primary_selection"],
                "primary_odds_decimal": row["primary_odds_decimal"],
                "hedge_platform": row["hedge_platform"],
                "hedge_selection": row["hedge_selection"],
                "hedge_odds_decimal": row["hedge_odds_decimal"],
                "hedge_stake": row["hedge_stake"],
                "locked_profit": row["locked_profit"],
                "conversion_rate_pct": row["conversion_rate_pct"],
            })
    return str(path)


def export_json(results: Iterable[HedgeResult], output_path: str | Path, meta: dict | None = None) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"meta": meta or {}, "results": [result.__dict__ for result in results]}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return str(path)
