"""Thin client for the official FPL API."""

from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://fantasy.premierleague.com/api/"
USER_AGENT = "fpl-analytics/0.1 (+personal research)"


class FPLAPIError(RuntimeError):
    pass


class FPLClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        retries: int = 3,
        backoff: float = 1.0,
        min_interval: float = 0.0,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )
        self._retries = retries
        self._backoff = backoff
        self._min_interval = min_interval
        self._last_request = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FPLClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                resp = self._client.get(path)
            except httpx.TransportError as exc:
                last_exc = exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                # 429/5xx are retryable; the API also returns 503 during updates.
                if resp.status_code != 429 and resp.status_code < 500:
                    raise FPLAPIError(f"GET {path} -> {resp.status_code}")
                last_exc = FPLAPIError(f"GET {path} -> {resp.status_code}")
            if attempt < self._retries:
                time.sleep(self._backoff * 2**attempt)
        raise FPLAPIError(f"GET {path} failed after {self._retries + 1} attempts") from last_exc

    def bootstrap_static(self) -> dict[str, Any]:
        return self._get("bootstrap-static/")

    def fixtures(self) -> list[dict[str, Any]]:
        return self._get("fixtures/")

    def element_summary(self, element_id: int) -> dict[str, Any]:
        return self._get(f"element-summary/{element_id}/")

    def event_live(self, gameweek: int) -> dict[str, Any]:
        return self._get(f"event/{gameweek}/live/")

    def entry(self, entry_id: int) -> dict[str, Any]:
        return self._get(f"entry/{entry_id}/")

    def entry_history(self, entry_id: int) -> dict[str, Any]:
        return self._get(f"entry/{entry_id}/history/")

    def entry_picks(self, entry_id: int, gameweek: int) -> dict[str, Any]:
        return self._get(f"entry/{entry_id}/event/{gameweek}/picks/")

    def entry_transfers(self, entry_id: int) -> list[dict[str, Any]]:
        return self._get(f"entry/{entry_id}/transfers/")
