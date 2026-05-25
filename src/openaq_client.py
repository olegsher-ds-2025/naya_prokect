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


class OpenAQClient:
    def __init__(self, api_key: str, requests_per_second: float = 3.0) -> None:
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

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=5, max=60))
    def _get(self, path: str, params: dict | None = None) -> dict:
        # Wait if another thread triggered a global backoff
        _GLOBAL_BACKOFF.wait()
        self._throttle()

        url = f"{BASE_URL}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=30)

        if resp.status_code == 429:
            # Pause ALL threads for 30s before retrying
            logger.warning("Rate limited — pausing all threads for 30s")
            _GLOBAL_BACKOFF.clear()
            time.sleep(30)
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
            meta = data.get("meta", {})
            found = meta.get("found", "0")
            total = int(found) if str(found).isdigit() else (page + 1) * params["limit"]
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
