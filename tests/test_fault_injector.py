import asyncio
import pytest
from incident_env.server.simulation.service_mesh import ServiceMesh
from incident_env.server.simulation.fault_injector import FaultInjector


@pytest.mark.asyncio
async def test_fault_oom_crash_stops_payments(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    fi = FaultInjector(mesh)
    await fi.inject("oom_crash")
    assert mesh.services["payments"].status == "down"
    logs = mesh.services["payments"].get_logs()
    assert any("OOMKilled" in l or "exit code 137" in l for l in logs)
    await mesh.stop()


@pytest.mark.asyncio
async def test_fault_connection_exhaustion_degrades_payments(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    fi = FaultInjector(mesh)
    await fi.inject("connection_exhaustion")
    assert mesh.services["payments"].status == "degraded"
    assert mesh.services["api-gateway"].status == "degraded"
    await mesh.stop()


@pytest.mark.asyncio
async def test_fault_schema_drift_sets_schema_version(tmp_path):
    import sqlite3
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    fi = FaultInjector(mesh)
    await fi.inject("schema_drift")
    pipeline = mesh.services["data-pipeline"]
    assert pipeline._schema_version == 2
    conn = sqlite3.connect(mesh.storage.get_db_path("warehouse"))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    conn.close()
    assert "blob_data" in cols
    await mesh.stop()


@pytest.mark.asyncio
async def test_fault_unknown_scenario_raises(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    fi = FaultInjector(mesh)
    with pytest.raises(ValueError, match="Unknown scenario"):
        await fi.inject("nonexistent")
    await mesh.stop()
