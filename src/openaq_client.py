"""OpenAQ v3 API client with thread-safe rate limiting, global backoff, and retry."""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any, Iterator

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2
PM10_PARAMETER_ID = 1

# Global backoff: when any thread hits 429, all threads pause together
_GLOBAL_BACKOFF = threading.Event()
_GLOBAL_BACKOFF.set()  # set = "no backoff active, proceed"

# Set this to interrupt all sleeping worker threads (e.g. on KeyboardInterrupt)
_SHUTDOWN_EVENT = threading.Event()


class OpenAQClient:
    def __init__(self, api_key: str, requests_per_second: float = 0.5) -> None:
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})
        self._min_interval = 1.0 / requests_per_second
        self._last_call = 0.0
        self._lock = threading.Lock()  # ensures only one thread calls at a time

    def _throttle(self) -> None:
        """Block until the minimum interval since last request has passed.
        Lock is held for the full check+sleep+update to prevent races."""
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=120))
    def _get(self, path: str, params: dict | None = None) -> dict:
        if _SHUTDOWN_EVENT.is_set():
            raise InterruptedError("Shutdown requested")

        # Wait if another thread triggered a global backoff (interruptible)
        while not _GLOBAL_BACKOFF.wait(timeout=1.0):
            if _SHUTDOWN_EVENT.is_set():
                raise InterruptedError("Shutdown requested")

        self._throttle()

        url = f"{BASE_URL}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=30)

        if resp.status_code == 429:
            # Honour the server's Retry-After header; fall back to 60s
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited — backing off {retry_after}s")
            _GLOBAL_BACKOFF.clear()
            _SHUTDOWN_EVENT.wait(timeout=float(retry_after))
            _GLOBAL_BACKOFF.set()
            resp.raise_for_status()  # triggers tenacity retry

        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: dict | None = None) -> Iterator[dict]:
        """Yield every result record across all pages."""
        params = dict(params or {})
        params.setdefault("limit", 1000)
        page = 1
        while True:
            params["page"] = page
            data = self._get(path, params)
            results = data.get("results", [])
            if not results:
                break
            yield from results
            # Stop if this page was not full — no more pages exist.
            # Also parse meta.found defensively (API may return ">1000" strings).
            if len(results) < params["limit"]:
                break
            meta = data.get("meta", {})
            found_raw = str(meta.get("found", "0")).lstrip(">").strip()
            total = int(found_raw) if found_raw.isdigit() else (page + 1) * params["limit"]
            if page * params["limit"] >= total:
                break
            page += 1

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def get_countries(self, parameters_id: int = PM25_PARAMETER_ID) -> list[dict]:
        """Return all countries that have data for the given parameter."""
        logger.info(f"Fetching countries with parameter_id={parameters_id}")
        return list(self._paginate("countries", {"parameters_id": parameters_id}))

    def get_locations(
        self,
        country_code: str | None = None,
        parameters_id: int = PM25_PARAMETER_ID,
        only_active: bool = True,
        monitor_only: bool = True,
    ) -> list[dict]:
        """Return monitoring locations, optionally filtered by country.

        monitor_only=True restricts to government/reference monitors,
        excluding low-cost sensors — reduces sensor count ~10x.
        """
        params: dict[str, Any] = {"parameters_id": parameters_id, "limit": 1000}
        if country_code:
            params["iso"] = country_code
        if monitor_only:
            params["monitor"] = True
        locs = list(self._paginate("locations", params))
        if only_active:
            locs = [l for l in locs if l.get("datetimeLast")]
        return locs

    def get_sensor_measurements(
        self,
        sensor_id: int,
        date_from: date | str,
        date_to: date | str,
        limit: int = 1000,
    ) -> list[dict]:
        """Return all hourly measurements for a sensor in a date range."""
        params = {
            "datetime_from": str(date_from) + "T00:00:00Z" if isinstance(date_from, date) else date_from,
            "datetime_to":   str(date_to)   + "T23:59:59Z" if isinstance(date_to, date)   else date_to,
            "limit": limit,
        }
        return list(self._paginate(f"sensors/{sensor_id}/measurements", params))
