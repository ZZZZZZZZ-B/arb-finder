from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OddsAPIConfig:
    api_key_envs: list[str]
    key_rotation_strategy: str = "round_robin"
    odds_format: str = "decimal"
    date_format: str = "iso"
    bookmakers: list[str] = field(default_factory=list)


@dataclass
class UIConfig:
    banner_image: str = "./config/background.jpg"
    banner_height: int = 120


@dataclass
class Config:
    event_window_hours: int = 336
    top_n: int = 10
    sports: dict[str, Any] = field(default_factory=dict)
    odds_api: OddsAPIConfig = field(default_factory=OddsAPIConfig)
    platforms: dict[str, Any] = field(default_factory=dict)
    ui: UIConfig = field(default_factory=UIConfig)
    profit_boost: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    periods: dict[str, Any] = field(default_factory=dict)
    full_game_markets: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    odds = raw.get("odds_api", {})
    ui = raw.get("ui", {})
    return Config(
        event_window_hours=int(raw.get("event_window_hours", 336)),
        top_n=int(raw.get("top_n", 10)),
        sports=dict(raw.get("sports", {})),
        odds_api=OddsAPIConfig(
            api_key_envs=odds.get("api_key_envs", ["ODDS_API_KEY"]),
            key_rotation_strategy=odds.get("key_rotation_strategy", "round_robin"),
            odds_format=odds.get("odds_format", "decimal"),
            date_format=odds.get("date_format", "iso"),
            bookmakers=odds.get("bookmakers", ["draftkings", "fanduel"]),
        ),
        platforms=dict(raw.get("platforms", {})),
        ui=UIConfig(
            banner_image=str(ui.get("banner_image", "./config/background.jpg")),
            banner_height=int(ui.get("banner_height", 120)),
        ),
        profit_boost=dict(raw.get("profit_boost", {})),
        selection=dict(raw.get("selection", {})),
        output=dict(raw.get("output", {})),
        periods=dict(raw.get("periods", {})),
        full_game_markets=dict(raw.get("full_game", {})),
    )


def resolve_api_keys(env_names: list[str]) -> list[str]:
    keys: list[str] = []
    for name in env_names:
        value = os.getenv(name)
        if not value and name == "ODDS_API_KEYS":
            value = os.getenv("ODDS_API_KEY")
        if value:
            keys.extend(part.strip() for part in value.replace(";", ",").replace("\n", ",").split(",") if part.strip())
    if not keys:
        raise RuntimeError(f"No API key found in environment variables: {env_names}")
    return keys
