"""Connector contract + shared HTTP politeness (rate limit, retry with backoff, robots.txt)."""

from __future__ import annotations

import logging
import threading
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from vnecom.models import Platform, ProductSnapshot
from vnecom.settings import Settings

log = logging.getLogger(__name__)


class ConnectorNotConfigured(RuntimeError):
    """Raised when credentials are missing — orchestrators treat this as 'skip', not 'fail'."""


class RateLimiter:
    """Token-bucket-ish: at most `rps` requests per second across threads."""

    def __init__(self, rps: float) -> None:
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next - now
            self._next = max(now, self._next) + self.min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503, 504)


class Connector(ABC):
    """Yield ProductSnapshot for one capture run. Keep it stateless; orchestration owns scheduling."""

    name: ClassVar[str]
    platform: ClassVar[Platform]
    source_tier: ClassVar[str]  # official | licensed | public | synthetic
    respect_robots: ClassVar[bool] = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._limiter = RateLimiter(settings.vnecom_http_rps)
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._client: httpx.Client | None = None

    # ── lifecycle ──────────────────────────────────────────────────────
    def check_config(self) -> None:  # noqa: B027 — optional hook
        """Raise ConnectorNotConfigured if credentials are missing."""

    @abstractmethod
    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]: ...

    def close(self) -> None:
        if self._client:
            self._client.close()

    # ── http helpers ───────────────────────────────────────────────────
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.vnecom_http_timeout_s,
                headers={"User-Agent": self.settings.vnecom_http_user_agent, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self._client

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        host = urlparse(url)
        root = f"{host.scheme}://{host.netloc}"
        rp = self._robots.get(root)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{root}/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[root] = rp
        return rp.can_fetch(self.settings.vnecom_http_user_agent, url)

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential_jitter(multiplier=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get_json(self, url: str, **kwargs: Any) -> Any:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        self._limiter.wait()
        r = self.client.get(url, **kwargs)
        r.raise_for_status()
        return r.json()

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential_jitter(multiplier=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def post_json(self, url: str, **kwargs: Any) -> Any:
        self._limiter.wait()
        r = self.client.post(url, **kwargs)
        r.raise_for_status()
        return r.json()
