from __future__ import annotations

import asyncio
from typing import Dict

from .storage.sqlite import SQLiteStorage
from .transport.in_memory import InMemoryBus
from .services.api_gateway import APIGatewayService
from .services.payments import PaymentsService
from .services.data_pipeline import DataPipelineService
from .services.analytics import AnalyticsService

TOPOLOGY: Dict = {
    "api-gateway": ["payments", "analytics"],
    "payments": ["warehouse_db"],
    "data-pipeline": ["warehouse_db"],
    "analytics": ["warehouse_db"],
}


class ServiceMesh:
    def __init__(self, base_dir: str = "/tmp/incident_env_dbs"):
        self._base_dir = base_dir
        self.storage = SQLiteStorage(base_dir)
        self.transport = InMemoryBus()
        self.services: Dict = {}
        self._build_services()

    def _build_services(self) -> None:
        self.services = {
            "api-gateway": APIGatewayService(self.transport, self.storage),
            "payments": PaymentsService(self.transport, self.storage),
            "data-pipeline": DataPipelineService(self.transport, self.storage),
            "analytics": AnalyticsService(self.transport, self.storage),
        }

    async def start(self) -> None:
        for svc in self.services.values():
            await svc.start()
        # Seed the warehouse with events_processed so analytics starts healthy
        pipeline = self.services["data-pipeline"]
        pipeline.trigger_run()
        await asyncio.sleep(0.3)

    async def stop(self) -> None:
        for svc in self.services.values():
            await svc.stop()

    async def reset(self) -> None:
        await self.stop()
        self.storage.reset()
        self.transport.reset()
        self._build_services()
        await self.start()

    def get_topology(self) -> Dict:
        return TOPOLOGY

    def get_statuses(self) -> Dict[str, str]:
        return {name: svc.status for name, svc in self.services.items()}
