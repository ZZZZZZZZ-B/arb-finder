from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from promo_hedge_tool.odds_client.key_pool import AllKeysExhaustedError, KeyPool
from promo_hedge_tool.odds_client.models import OddsQuote, SportInfo


logger = logging.getLogger(__name__)


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return f"{api_key[:3]}...{api_key[-1]}"


class OddsAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class OddsAPIClient:
    def __init__(
        self,
        key_pool: KeyPool,
        base_url: str = "https://api.the-odds-api.com",
        max_retries: int = 3,
        backoff_base_seconds: float = 2.0,
        session: Optional[requests.Session] = None,
    ):
        self._key_pool = key_pool
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.session = session or requests.Session()

    def _isoformat(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _request(self, method: str, path: str, params: dict[str, Any]) -> requests.Response:
        last_error: Optional[Exception] = None
        for retry in range(self.max_retries + 1):
            try:
                key = self._key_pool.next_key()
            except AllKeysExhaustedError:
                raise

            request_params = dict(params)
            request_params["apiKey"] = key
            url = f"{self.base_url}{path}"
            try:
                response = self.session.request(method=method, url=url, params=request_params, timeout=30)
            except requests.RequestException as exc:  # pragma: no cover - network-level fallback path
                last_error = exc
                if retry >= self.max_retries:
                    raise OddsAPIError(f"Request failed for {path}: {exc}") from exc
                time.sleep(self.backoff_base_seconds * (2**retry))
                continue

            remaining = response.headers.get("x-requests-remaining")
            requests_used = response.headers.get("x-requests-used")
            requests_last = response.headers.get("x-requests-last")
            if remaining is not None:
                try:
                    self._key_pool.report_quota(key, int(remaining))
                except ValueError:
                    self._key_pool.report_quota(key, None)
            logger.info(
                "Odds API quota: key=%s, used=%s, remaining=%s, last_request=%s",
                mask_api_key(key),
                requests_used if requests_used is not None else "unknown",
                remaining if remaining is not None else "unknown",
                requests_last if requests_last is not None else "unknown",
            )

            if response.status_code == 429:
                if retry >= self.max_retries:
                    raise OddsAPIError("The Odds API rate-limited the request after retries.", status_code=429, response=response.text)
                time.sleep(self.backoff_base_seconds * (2**retry))
                continue

            if response.status_code == 401 or response.status_code == 403:
                self._key_pool.mark_exhausted(key)
                if retry >= self.max_retries:
                    raise OddsAPIError("The configured API key is invalid or exhausted.", status_code=response.status_code, response=response.text)
                continue

            if 400 <= response.status_code < 500:
                logger.error(
                    "Odds API client error: status=%d path=%s params=%s response=%s",
                    response.status_code,
                    path,
                    {name: value for name, value in request_params.items() if name != "apiKey"},
                    response.text,
                )
                raise OddsAPIError(
                    f"Odds API client error for {path}: {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    response=response.text,
                )

            if 200 <= response.status_code < 300:
                return response

            if retry >= self.max_retries:
                raise OddsAPIError(
                    f"Unexpected API response for {path}: {response.status_code}",
                    status_code=response.status_code,
                    response=response.text,
                )
            time.sleep(self.backoff_base_seconds * (2**retry))
            continue

        if last_error is not None:
            raise OddsAPIError(f"Last request failed for {path}: {last_error}")
        raise OddsAPIError(f"Request failed for {path} without response.")

    def get_sports(self, include_inactive: bool = False) -> list[SportInfo]:
        params = {"all": "true"} if include_inactive else {}
        payload = self._request("GET", "/v4/sports", params)
        data = payload.json() if payload.content else []
        sports: list[SportInfo] = []
        for item in data:
            if not include_inactive and not item.get("active", True):
                continue
            sports.append(
                SportInfo(
                    key=item.get("key", ""),
                    group=item.get("group", ""),
                    title=item.get("title", ""),
                    active=bool(item.get("active", True)),
                    has_outrights=bool(item.get("has_outrights", False)),
                )
            )
        logger.info("Sports API returned %d sports (active_only=%s)", len(sports), not include_inactive)
        return sports

    def get_odds(
        self,
        sport_key: str,
        bookmakers: list[str],
        markets: list[str],
        commence_time_from: Optional[datetime] = None,
        commence_time_to: Optional[datetime] = None,
        odds_format: str = "decimal",
        date_format: str = "iso",
    ) -> list[OddsQuote]:
        params: dict[str, Any] = {
            "bookmakers": ",".join(bookmakers),
            "markets": ",".join(markets),
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        if commence_time_from is not None:
            params["commenceTimeFrom"] = self._isoformat(commence_time_from)
        if commence_time_to is not None:
            params["commenceTimeTo"] = self._isoformat(commence_time_to)

        response = self._request("GET", f"/v4/sports/{sport_key}/odds", params)
        payload = response.json() if response.content else []
        quotes = self._parse_odds_payload(payload, sport_key)
        logger.info(
            "Odds API returned sport=%s events=%d quotes=%d bookmakers=%s markets=%s",
            sport_key,
            len(payload) if isinstance(payload, list) else 0,
            len(quotes),
            ",".join(bookmakers),
            ",".join(markets),
        )
        return quotes

    def get_event_odds(
        self,
        sport_key: str,
        event_id: str,
        bookmakers: list[str],
        markets: list[str],
        odds_format: str = "decimal",
        date_format: str = "iso",
    ) -> list[OddsQuote]:
        params: dict[str, Any] = {
            "bookmakers": ",".join(bookmakers),
            "markets": ",".join(markets),
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        response = self._request("GET", f"/v4/sports/{sport_key}/events/{event_id}/odds", params)
        payload = response.json() if response.content else {}
        quotes = self._parse_odds_payload(payload, sport_key)
        logger.info(
            "Event odds API returned sport=%s event=%s quotes=%d bookmakers=%s markets=%s",
            sport_key,
            event_id,
            len(quotes),
            ",".join(bookmakers),
            ",".join(markets),
        )
        return quotes

    def _parse_odds_payload(self, payload: Any, sport_key: str) -> list[OddsQuote]:
        events = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) and payload else []
        quotes: list[OddsQuote] = []

        for event in events:
            event_id = event.get("id") or event.get("event_id") or ""
            commence_time = event.get("commence_time") or event.get("commenceTime")
            home_team = event.get("home_team") or ""
            away_team = event.get("away_team") or ""
            for bookmaker in event.get("bookmakers", []):
                bookmaker_key = bookmaker.get("key", "")
                bookmaker_title = bookmaker.get("title", "")
                for market in bookmaker.get("markets", []):
                    market_key = market.get("key", "")
                    for outcome in market.get("outcomes", []):
                        quote = OddsQuote(
                            sport_key=sport_key,
                            event_id=event_id,
                            commence_time=str(commence_time or ""),
                            home_team=home_team,
                            away_team=away_team,
                            bookmaker_key=bookmaker_key,
                            bookmaker_title=bookmaker_title,
                            market_key=market_key,
                            outcome_name=outcome.get("name", ""),
                            decimal_odds=float(outcome.get("price", 0.0) or 0.0),
                            point=outcome.get("point"),
                            last_update=event.get("last_update"),
                        )
                        quotes.append(quote)
        return quotes

    def get_events(self, sport_key: str, **kwargs) -> list[dict]:
        response = self._request("GET", f"/v4/sports/{sport_key}/events", kwargs)
        payload = response.json() if response.content else []
        events = payload if isinstance(payload, list) else []
        logger.info("Events API returned sport=%s events=%d", sport_key, len(events))
        return events
