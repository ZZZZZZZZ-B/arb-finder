from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable


def normalize_team_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def event_name(event: dict) -> str:
    return f"{event.get('away_team', '')} vs {event.get('home_team', '')}"


def local_event_time(event: dict) -> str:
    raw_time = str(event.get("commence_time", ""))
    try:
        commence = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if commence.tzinfo is None:
            commence = commence.replace(tzinfo=timezone.utc)
        local_time = commence.astimezone()
        return f"{local_time:%Y-%m-%d %H:%M}"
    except ValueError:
        return "Unknown time"


def local_timezone_label() -> str:
    local_time = datetime.now().astimezone()
    offset = local_time.utcoffset() or timezone.utc.utcoffset(local_time)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute_minutes = abs(total_minutes)
    return f"UTC{sign}{absolute_minutes // 60:02d}:{absolute_minutes % 60:02d}"


def filter_events(events: Iterable[dict], keyword: str = "") -> list[dict]:
    if not keyword.strip():
        return list(events)
    needle = normalize_team_text(keyword)
    return [
        event
        for event in events
        if needle in normalize_team_text(event.get("home_team", ""))
        or needle in normalize_team_text(event.get("away_team", ""))
    ]


def parse_user_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Datetime must include a timezone, for example 2026-09-23T12:00:00+00:00")
    return parsed