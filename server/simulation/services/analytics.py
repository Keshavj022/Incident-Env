from __future__ import annotations

import asyncio
import sqlite3
import time

from .base_service import BaseService


class AnalyticsService(BaseService):
    def __init__(self, transport, storage):
        super().__init__("analytics", transport, storage)
        self._db_path = storage.get_db_path("warehouse")
        self._failed_queries: int = 0

    async def _run_loop(self) -> None:
        while True:
            await self._run_query()
            await asyncio.sleep(0.25)

    async def _run_query(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            t0 = time.time()
            await loop.run_in_executor(None, self._execute_query)
            self._metrics["query_latency_ms"] = round((time.time() - t0) * 1000, 2)
            self._metrics["failed_queries"] = self._failed_queries
            self.status = "healthy"
        except Exception as exc:
            self._failed_queries += 1
            self._metrics["failed_queries"] = self._failed_queries
            self.logger.error(f"Analytics query failed: {exc}")
            self.status = "degraded"

    def _execute_query(self) -> None:
        conn = sqlite3.connect(self._db_path, timeout=2.0)
        try:
            conn.execute(
                "SELECT COUNT(*), AVG(value_normalized) FROM events_processed"
            ).fetchone()
        finally:
            conn.close()

    def fail_queries(self, reason: str) -> None:
        self.logger.error(f"Analytics query failed: {reason}")
        self.status = "degraded"
