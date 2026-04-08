from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service_mesh import ServiceMesh


class FaultInjector:
    def __init__(self, mesh: "ServiceMesh"):
        self._mesh = mesh

    async def inject(self, scenario: str) -> None:
        if scenario == "oom_crash":
            await self._inject_oom_crash()
        elif scenario == "connection_exhaustion":
            await self._inject_connection_exhaustion()
        elif scenario == "schema_drift":
            await self._inject_schema_drift()
        else:
            raise ValueError(f"Unknown scenario: {scenario!r}")

    async def _inject_oom_crash(self) -> None:
        payments = self._mesh.services["payments"]
        await payments.stop()
        payments._metrics["memory_mb"] = 512
        payments.logger.error("OOMKilled: memory limit exceeded (512Mi/512Mi)")
        payments.logger.error("Container payments exited with code 137")

    async def _inject_connection_exhaustion(self) -> None:
        pipeline = self._mesh.services["data-pipeline"]
        payments = self._mesh.services["payments"]
        gateway = self._mesh.services["api-gateway"]
        analytics = self._mesh.services["analytics"]

        pipeline.exhaust_connections_to(payments._db_path)
        payments.exhaust_connections()
        gateway.simulate_degraded(rate=0.85)

        analytics._metrics["cpu_percent"] = 89.0
        analytics.logger.warning(
            "High CPU detected during scheduled report aggregation (unrelated to incident)"
        )

    async def _inject_schema_drift(self) -> None:
        pipeline = self._mesh.services["data-pipeline"]
        gateway = self._mesh.services["api-gateway"]
        analytics = self._mesh.services["analytics"]

        pipeline.inject_schema_drift()
        pipeline.trigger_run()

        gateway._metrics["memory_mb"] = 480
        gateway.logger.warning(
            "Memory usage elevated (GC pressure) — not related to incident"
        )

        analytics.fail_queries(
            "Table events_processed not found (pipeline job incomplete)"
        )
