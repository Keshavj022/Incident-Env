from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from typing import List

from .base_service import BaseService

MAX_CONNECTIONS = 5


class PaymentsService(BaseService):
    def __init__(self, transport, storage):
        super().__init__("payments", transport, storage)
        self._db_path = storage.get_db_path("payments")
        self._held_connections: List[sqlite3.Connection] = []
        self._available = asyncio.Semaphore(MAX_CONNECTIONS)
        self._total_requests = 0
        self._failed_requests = 0
        self._initialize_db()

    def _initialize_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                amount REAL,
                status TEXT,
                created_at REAL
            )
        """)
        conn.commit()
        conn.close()

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._process_transaction()
                self._total_requests += 1
                self._metrics["transactions_total"] = self._total_requests
                self._metrics["error_rate"] = 0.0
            except Exception as exc:
                self._failed_requests += 1
                self.logger.error(f"Transaction failed: {exc}")
                total = self._total_requests + self._failed_requests
                self._metrics["error_rate"] = self._failed_requests / max(total, 1)
            await asyncio.sleep(0.2)

    async def _process_transaction(self) -> None:
        async with self._available:
            conn = sqlite3.connect(self._db_path, timeout=1.0)
            try:
                txn_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO transactions VALUES (?, ?, ?, ?)",
                    (txn_id, 100.0, "completed", time.time()),
                )
                conn.commit()
                self.logger.debug(f"Transaction {txn_id[:8]} completed")
            finally:
                conn.close()

    def exhaust_connections(self) -> None:
        self._held_connections = [
            sqlite3.connect(self._db_path) for _ in range(MAX_CONNECTIONS + 10)
        ]
        self._available._value = 0
        self.status = "degraded"
        self._metrics["error_rate"] = 1.0
        self.logger.error(
            f"FATAL: connection pool exhausted, {MAX_CONNECTIONS}/{MAX_CONNECTIONS} connections held"
        )

    def release_connections(self) -> None:
        for conn in self._held_connections:
            try:
                conn.close()
            except Exception:
                pass
        self._held_connections = []
        self._available._value = MAX_CONNECTIONS
        self.status = "healthy"
        self._metrics["error_rate"] = 0.0
        self.logger.info("Connection pool restored")
