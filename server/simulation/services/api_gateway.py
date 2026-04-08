from __future__ import annotations

import asyncio
from collections import deque

from .base_service import BaseService

WINDOW = 20


class APIGatewayService(BaseService):
    def __init__(self, transport, storage):
        super().__init__("api-gateway", transport, storage)
        self._request_log: deque = deque(maxlen=WINDOW)

    async def _run_loop(self) -> None:
        while True:
            self._recompute_metrics()
            await asyncio.sleep(0.1)

    def _recompute_metrics(self) -> None:
        if not self._request_log:
            self._metrics["5xx_rate"] = 0.0
            self._metrics["request_count"] = 0
            return
        failures = sum(1 for ok in self._request_log if not ok)
        rate = failures / len(self._request_log)
        self._metrics["5xx_rate"] = round(rate, 3)
        self._metrics["request_count"] = len(self._request_log)
        if rate > 0.5:
            self.status = "degraded"
            self.logger.error(
                f"Upstream payments returned 502 Bad Gateway (5xx_rate={rate:.0%})"
            )
        elif self.status == "degraded":
            self.status = "healthy"

    def record_upstream_failure(self, upstream: str) -> None:
        self._request_log.append(False)
        self.logger.error(f"Upstream {upstream} returned 502 Bad Gateway")
        self._recompute_metrics()

    def record_upstream_success(self, upstream: str) -> None:
        self._request_log.append(True)
        self._recompute_metrics()

    def simulate_degraded(self, rate: float = 0.85) -> None:
        self._request_log.clear()
        n_fail = int(WINDOW * rate)
        for _ in range(n_fail):
            self._request_log.append(False)
        for _ in range(WINDOW - n_fail):
            self._request_log.append(True)
        self._recompute_metrics()

    def simulate_healthy(self) -> None:
        self._request_log.clear()
        for _ in range(WINDOW):
            self._request_log.append(True)
        self._recompute_metrics()
