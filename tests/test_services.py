# incident_env/tests/test_services.py
import asyncio
import os
import pytest
from incident_env.server.simulation.storage.sqlite import SQLiteStorage
from incident_env.server.simulation.transport.in_memory import InMemoryBus


def test_sqlite_storage_creates_db_dir(tmp_path):
    storage = SQLiteStorage(base_dir=str(tmp_path))
    db_path = storage.get_db_path("payments")
    assert db_path.endswith("payments.db")
    assert str(tmp_path) in db_path


def test_sqlite_storage_reset_deletes_db_files(tmp_path):
    storage = SQLiteStorage(base_dir=str(tmp_path))
    db_path = storage.get_db_path("payments")
    # Create a file to simulate existing DB
    open(db_path, "w").close()
    assert os.path.exists(db_path)
    storage.reset()
    assert not os.path.exists(db_path)


@pytest.mark.asyncio
async def test_in_memory_bus_publish_subscribe():
    bus = InMemoryBus()
    received = []

    async def handler(msg):
        received.append(msg)

    bus.subscribe("payments", handler)
    await bus.publish("payments", {"event": "transaction"})
    await asyncio.sleep(0.05)
    assert received == [{"event": "transaction"}]


@pytest.mark.asyncio
async def test_in_memory_bus_reset_clears_subscribers():
    bus = InMemoryBus()
    bus.subscribe("payments", lambda m: None)
    bus.reset()
    assert bus._subscribers == {}


import asyncio
import pytest
from incident_env.server.simulation.services.base_service import BaseService
from incident_env.server.simulation.transport.in_memory import InMemoryBus
from incident_env.server.simulation.storage.sqlite import SQLiteStorage


class DummyService(BaseService):
    async def _run_loop(self):
        for _ in range(3):
            self.logger.info("tick")
            self._metrics["ticks"] = self._metrics.get("ticks", 0) + 1
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_base_service_starts_healthy(tmp_path):
    svc = DummyService("dummy", InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await svc.start()
    await asyncio.sleep(0.05)
    assert svc.status == "healthy"
    await svc.stop()


@pytest.mark.asyncio
async def test_base_service_logs_captured(tmp_path):
    svc = DummyService("dummy", InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await svc.start()
    await asyncio.sleep(0.05)
    logs = svc.get_logs()
    assert any("tick" in line for line in logs)
    await svc.stop()


@pytest.mark.asyncio
async def test_base_service_restart(tmp_path):
    svc = DummyService("dummy", InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await svc.start()
    await svc.restart()
    assert svc.status == "healthy"
    await svc.stop()


from incident_env.server.simulation.services.payments import PaymentsService


@pytest.mark.asyncio
async def test_payments_initializes_db(tmp_path):
    import os
    storage = SQLiteStorage(str(tmp_path))
    svc = PaymentsService(InMemoryBus(), storage)
    assert os.path.exists(storage.get_db_path("payments"))


@pytest.mark.asyncio
async def test_payments_fault_exhausts_connections(tmp_path):
    storage = SQLiteStorage(str(tmp_path))
    svc = PaymentsService(InMemoryBus(), storage)
    await svc.start()
    svc.exhaust_connections()
    assert svc.status == "degraded"
    assert svc._metrics.get("error_rate", 0) == 1.0
    await svc.stop()


@pytest.mark.asyncio
async def test_payments_release_restores_health(tmp_path):
    storage = SQLiteStorage(str(tmp_path))
    svc = PaymentsService(InMemoryBus(), storage)
    await svc.start()
    svc.exhaust_connections()
    svc.release_connections()
    assert svc.status == "healthy"
    assert svc._metrics.get("error_rate", 0) == 0.0
    await svc.stop()


from incident_env.server.simulation.services.data_pipeline import DataPipelineService


@pytest.mark.asyncio
async def test_pipeline_initializes_warehouse(tmp_path):
    import os
    storage = SQLiteStorage(str(tmp_path))
    svc = DataPipelineService(InMemoryBus(), storage)
    assert os.path.exists(storage.get_db_path("warehouse"))


@pytest.mark.asyncio
async def test_pipeline_inject_schema_drift(tmp_path):
    import sqlite3 as _sqlite3
    storage = SQLiteStorage(str(tmp_path))
    svc = DataPipelineService(InMemoryBus(), storage)
    svc.inject_schema_drift()
    conn = _sqlite3.connect(storage.get_db_path("warehouse"))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()]
    conn.close()
    assert "blob_data" in cols
    assert svc._schema_version == 2


@pytest.mark.asyncio
async def test_pipeline_fix_config(tmp_path):
    storage = SQLiteStorage(str(tmp_path))
    svc = DataPipelineService(InMemoryBus(), storage)
    svc.inject_schema_drift()
    result = svc.fix_config("skip_column", "blob_data")
    assert result is True
    assert svc._schema_version == 3


@pytest.mark.asyncio
async def test_pipeline_etl_v3_writes_events_processed(tmp_path):
    import sqlite3 as _sqlite3
    storage = SQLiteStorage(str(tmp_path))
    svc = DataPipelineService(InMemoryBus(), storage)
    svc.inject_schema_drift()
    svc.fix_config("skip_column", "blob_data")
    await svc.start()
    svc.trigger_run()
    await asyncio.sleep(1.5)
    conn = _sqlite3.connect(storage.get_db_path("warehouse"))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "events_processed" in tables
    await svc.stop()


from incident_env.server.simulation.services.analytics import AnalyticsService


@pytest.mark.asyncio
async def test_analytics_healthy_when_table_exists(tmp_path):
    import sqlite3 as _sqlite3
    storage = SQLiteStorage(str(tmp_path))
    conn = _sqlite3.connect(storage.get_db_path("warehouse"))
    conn.execute("CREATE TABLE events_processed (id INTEGER, value_normalized REAL)")
    conn.commit()
    conn.close()
    svc = AnalyticsService(InMemoryBus(), storage)
    await svc.start()
    await asyncio.sleep(0.4)
    assert svc.status == "healthy"
    await svc.stop()


@pytest.mark.asyncio
async def test_analytics_degraded_when_table_missing(tmp_path):
    import sqlite3 as _sqlite3
    storage = SQLiteStorage(str(tmp_path))
    _sqlite3.connect(storage.get_db_path("warehouse")).close()
    svc = AnalyticsService(InMemoryBus(), storage)
    await svc.start()
    await asyncio.sleep(0.4)
    assert svc.status == "degraded"
    await svc.stop()


from incident_env.server.simulation.services.api_gateway import APIGatewayService


@pytest.mark.asyncio
async def test_gateway_tracks_5xx_rate(tmp_path):
    gw = APIGatewayService(InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await gw.start()
    gw.record_upstream_failure("payments")
    gw.record_upstream_failure("payments")
    gw.record_upstream_success("payments")
    assert gw._metrics.get("5xx_rate", 0) > 0
    await gw.stop()


@pytest.mark.asyncio
async def test_gateway_simulate_degraded(tmp_path):
    gw = APIGatewayService(InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await gw.start()
    gw.simulate_degraded(rate=0.85)
    assert gw._metrics["5xx_rate"] > 0.5
    assert gw.status == "degraded"
    await gw.stop()


@pytest.mark.asyncio
async def test_gateway_simulate_healthy(tmp_path):
    gw = APIGatewayService(InMemoryBus(), SQLiteStorage(str(tmp_path)))
    await gw.start()
    gw.simulate_degraded(rate=0.85)
    gw.simulate_healthy()
    assert gw._metrics["5xx_rate"] == 0.0
    await gw.stop()
