from __future__ import annotations

from typing import Iterable

from promo_hedge_tool.strategies.base import HedgeResult


def rank_top_n(results: Iterable[HedgeResult], top_n: int, key: str = "conversion_rate_pct") -> list[HedgeResult]:
    ordered = sorted(results, key=lambda result: getattr(result, key), reverse=True)
    return ordered[:top_n]
