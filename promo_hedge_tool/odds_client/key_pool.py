from __future__ import annotations

from collections import deque
from typing import Optional


class AllKeysExhaustedError(Exception):
    """Raised when all configured API keys are exhausted for the month."""


class KeyPool:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("At least one API key must be configured.")
        self._keys: deque[str] = deque(api_keys)
        self._quota_remaining: dict[str, Optional[int]] = {key: None for key in api_keys}
        self._exhausted: set[str] = set()

    def next_key(self) -> str:
        for _ in range(len(self._keys)):
            key = self._keys[0]
            self._keys.rotate(-1)
            if key not in self._exhausted:
                return key
        raise AllKeysExhaustedError("All configured API keys are exhausted for this month.")

    def report_quota(self, key: str, remaining: Optional[int]) -> None:
        self._quota_remaining[key] = remaining
        if remaining is not None and remaining <= 0:
            self._exhausted.add(key)

    def mark_exhausted(self, key: str) -> None:
        self._exhausted.add(key)

    def status(self) -> dict[str, Optional[int]]:
        return dict(self._quota_remaining)
