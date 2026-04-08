import asyncio
import pytest
from incident_env.server.simulation.service_mesh import ServiceMesh
from incident_env.server.simulation.alert_manager import AlertManager


@pytest.mark.asyncio
async def test_mesh_starts_all_services_healthy(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    await asyncio.sleep(0.2)
    for name, svc in mesh.services.items():
        assert svc.status in ("healthy", "running"), f"{name} not healthy: {svc.status}"
    await mesh.stop()


@pytest.mark.asyncio
async def test_mesh_reset_restores_services(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    await mesh.reset()
    await asyncio.sleep(0.2)
    for name, svc in mesh.services.items():
        assert svc.status in ("healthy", "running"), f"{name} not healthy after reset"
    await mesh.stop()


@pytest.mark.asyncio
async def test_alert_manager_fires_on_down_service(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    mesh.services["payments"].status = "down"
    alert_mgr = AlertManager(mesh)
    alerts = alert_mgr.evaluate()
    names = [a["name"] for a in alerts]
    assert "ServiceDown" in names
    await mesh.stop()


@pytest.mark.asyncio
async def test_alert_manager_clears_resolved_alerts(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    alert_mgr = AlertManager(mesh)
    mesh.services["payments"].status = "down"
    alert_mgr.evaluate()
    mesh.services["payments"].status = "healthy"
    mesh.services["payments"]._metrics["error_rate"] = 0.0
    alerts = alert_mgr.evaluate()
    names = [a["name"] for a in alerts]
    assert "ServiceDown" not in names
    await mesh.stop()


@pytest.mark.asyncio
async def test_mesh_get_statuses(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    statuses = mesh.get_statuses()
    assert set(statuses.keys()) == {"api-gateway", "payments", "data-pipeline", "analytics"}
    await mesh.stop()
