from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RunContext:
    mode: str
    base_bookmaker: str
    hedge_bookmakers: tuple[str, ...]
    stake: float | None = None
    boost_percent: float | None = None
    selected_leagues: tuple[str, ...] = field(default_factory=tuple)
    commence_time_from: datetime | None = None
    commence_time_to: datetime | None = None
    selected_event_ids: tuple[str, ...] = field(default_factory=tuple)
    team_keyword: str = ""
    odds_operator: str | None = None
    odds_requirement_american: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"bonus-bet", "profit-boost"}:
            raise ValueError(f"Unsupported mode: {self.mode}")
        if not self.base_bookmaker:
            raise ValueError("base_bookmaker is required")
        if self.base_bookmaker in self.hedge_bookmakers:
            raise ValueError("base bookmaker cannot also be a hedge bookmaker")
        if self.mode == "profit-boost":
            if self.stake is None or self.stake <= 0:
                raise ValueError("Profit Boost stake must be greater than zero")
            if self.boost_percent is None or self.boost_percent < 0:
                raise ValueError("Profit Boost percentage must not be negative")
            if self.odds_operator not in {None, ">=", "<="}:
                raise ValueError("odds_operator must be >= or <=")
            if self.odds_operator is not None and self.odds_requirement_american is None:
                raise ValueError("An American odds requirement is required when an operator is selected")
        elif self.odds_operator is not None or self.odds_requirement_american is not None:
            raise ValueError("Odds requirements are only supported in Profit Boost mode")


def configured_bookmakers(config) -> list[str]:
    names = list(config.platforms)
    if names:
        return names
    return list(dict.fromkeys(config.odds_api.bookmakers))


def build_run_context(
    config,
    mode: str,
    base_bookmaker: str,
    stake: float | None = None,
    boost_percent: float | None = None,
    selected_leagues: tuple[str, ...] = (),
    commence_time_from: datetime | None = None,
    commence_time_to: datetime | None = None,
    selected_event_ids: tuple[str, ...] = (),
    team_keyword: str = "",
    hedge_bookmakers: tuple[str, ...] | None = None,
    odds_operator: str | None = None,
    odds_requirement_american: float | None = None,
) -> RunContext:
    available = configured_bookmakers(config)
    if base_bookmaker not in available:
        raise ValueError(f"Unknown base bookmaker: {base_bookmaker}")
    if hedge_bookmakers is None:
        hedge = tuple(name for name in available if name != base_bookmaker)
    else:
        unknown = [name for name in hedge_bookmakers if name not in available]
        if unknown:
            raise ValueError(f"Unknown hedge bookmaker(s): {', '.join(unknown)}")
        if base_bookmaker in hedge_bookmakers:
            raise ValueError("Base bookmaker cannot be selected as a hedge bookmaker")
        if not hedge_bookmakers:
            raise ValueError("Select at least one hedge bookmaker")
        hedge = tuple(dict.fromkeys(hedge_bookmakers))
    return RunContext(
        mode=mode,
        base_bookmaker=base_bookmaker,
        hedge_bookmakers=hedge,
        stake=stake,
        boost_percent=boost_percent,
        selected_leagues=selected_leagues,
        commence_time_from=commence_time_from,
        commence_time_to=commence_time_to,
        selected_event_ids=selected_event_ids,
        team_keyword=team_keyword,
        odds_operator=odds_operator,
        odds_requirement_american=odds_requirement_american,
    )