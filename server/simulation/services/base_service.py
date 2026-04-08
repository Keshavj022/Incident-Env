from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Dict, List, Optional


class _DequeHandler(logging.Handler):
    def __init__(self, buf: deque):
        super().__init__()
        self._buf = buf

    def emit(self, record: logging.LogRecord) -> None:
        self._buf.append(self.format(record))


class BaseService(ABC):
    def __init__(self, name: str, transport, storage):
        self.name = name
        self.transport = transport
        self.storage = storage
        self.status: str = "healthy"
        self._start_time: float = time.time()
        self._log_buffer: deque = deque(maxlen=1000)
        self._metrics: Dict = {}
        self._task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(f"incident_env.{name}.{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        handler = _DequeHandler(self._log_buffer)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        self.logger.addHandler(handler)
        self.logger.propagate = False

    async def start(self) -> None:
        self._start_time = time.time()
        self.status = "healthy"
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status = "down"

    async def restart(self) -> None:
        await self.stop()
        await asyncio.sleep(0.1)
        await self.start()

    def get_logs(self, last_n: int = 50) -> List[str]:
        return list(self._log_buffer)[-last_n:]

    def get_metrics(self) -> Dict:
        return {
            "uptime_seconds": round(time.time() - self._start_time, 2),
            "status": self.status,
            **self._metrics,
        }

    @abstractmethod
    async def _run_loop(self) -> None:
        pass
