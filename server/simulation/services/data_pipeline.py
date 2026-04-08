from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import List

import pandas as pd

from .base_service import BaseService


class DataPipelineService(BaseService):
    def __init__(self, transport, storage):
        super().__init__("data-pipeline", transport, storage)
        self._db_path = storage.get_db_path("warehouse")
        self._schema_version: int = 1
        self._running_job: bool = False
        self._held_conns_to_payments: List[sqlite3.Connection] = []
        self._initialize_warehouse()

    def _initialize_warehouse(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                event_type TEXT,
                value REAL,
                created_at REAL
            )
        """)
        for i in range(50):
            conn.execute(
                "INSERT INTO events (user_id, event_type, value, created_at) VALUES (?,?,?,?)",
                (f"user_{i}", "purchase", float(i * 2 + 1), time.time()),
            )
        conn.commit()
        conn.close()

    async def _run_loop(self) -> None:
        while True:
            if self._running_job:
                await self._execute_pipeline()
            await asyncio.sleep(0.5)

    async def _execute_pipeline(self) -> None:
        self.logger.info("Pipeline job started")
        self.status = "running"
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._etl_job)
            self.logger.info("Pipeline job completed successfully")
            self.status = "healthy"
        except MemoryError as exc:
            self.logger.error(f"MemoryError: {exc}")
            self.status = "degraded"
        except Exception as exc:
            self.logger.error(f"Pipeline job failed: {exc}")
            self.status = "degraded"
        finally:
            self._running_job = False

    def _etl_job(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            df = pd.read_sql("SELECT * FROM events", conn)
            if self._schema_version == 2:
                raise MemoryError(
                    "Unable to allocate array for blob_data column (schema version 2 unsupported)"
                )
            if "blob_data" in df.columns:
                df = df.drop(columns=["blob_data"])
            std_val = df["value"].std()
            df["value_normalized"] = (
                (df["value"] - df["value"].mean()) / std_val
                if std_val and std_val > 0
                else 0.0
            )
            df.to_sql("events_processed", conn, if_exists="replace", index=False)
            self.logger.info(f"Wrote {len(df)} rows to events_processed")
        finally:
            conn.close()

    def inject_schema_drift(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("ALTER TABLE events ADD COLUMN blob_data BLOB")
            large_data = b"x" * (1024 * 512)
            for i in range(100):
                conn.execute(
                    "INSERT INTO events (user_id, event_type, value, created_at, blob_data) "
                    "VALUES (?,?,?,?,?)",
                    (f"blob_user_{i}", "ingest", 0.0, time.time(), large_data),
                )
            conn.commit()
            self._schema_version = 2
            self.logger.warning(
                "Schema version 2 detected: new blob_data column ingested (100 rows, ~50MB)"
            )
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    def fix_config(self, key: str, value: str) -> bool:
        if key == "skip_column" and value == "blob_data":
            self._schema_version = 3
            self.logger.info(f"Config updated: {key}={value} — pipeline will skip blob_data column")
            return True
        self.logger.warning(f"Unknown config key: {key}={value}")
        return False

    def trigger_run(self) -> None:
        self._running_job = True
        self.logger.info("Pipeline run triggered manually")

    def exhaust_connections_to(self, db_path: str) -> None:
        self._held_conns_to_payments = [
            sqlite3.connect(db_path) for _ in range(15)
        ]
        self.logger.error(
            f"Pipeline holding 15 open connections to {db_path} — pool may be exhausted"
        )

    def release_held_connections(self) -> None:
        for conn in self._held_conns_to_payments:
            try:
                conn.close()
            except Exception:
                pass
        self._held_conns_to_payments = []
