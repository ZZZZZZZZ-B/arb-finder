from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from promo_hedge_tool.ui import HedgeApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DateValue:
    def __init__(self, value):
        self.value = value

    def get_date(self):
        return self.value


def make_ui(start_hour="09", start_minute="35", end_hour="17", end_minute="10"):
    return SimpleNamespace(
        from_date=DateValue(date(2026, 10, 4)),
        to_date=DateValue(date(2026, 10, 4)),
        start_hour=Value(start_hour),
        start_minute=Value(start_minute),
        end_hour=Value(end_hour),
        end_minute=Value(end_minute),
    )


def test_query_window_uses_local_hours_and_minutes_then_converts_to_utc():
    ui = make_ui()

    start, end = HedgeApp._query_window(ui)

    expected_start = datetime.combine(date(2026, 10, 4), time(9, 35)).astimezone(timezone.utc)
    expected_end = datetime.combine(date(2026, 10, 4), time(17, 10)).astimezone(timezone.utc)
    assert start == expected_start
    assert end == expected_end


def test_query_window_rejects_end_time_before_start_time():
    with pytest.raises(ValueError, match="End date and time"):
        HedgeApp._query_window(make_ui(start_hour="18", start_minute="00", end_hour="17", end_minute="59"))
