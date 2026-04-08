import asyncio
import pytest
from incident_env.models import IncidentAction
from incident_env.server.simulation.service_mesh import ServiceMesh
from incident_env.server.simulation.fault_injector import FaultInjector
from incident_env.server.graders.easy_grader import EasyGrader
from incident_env.server.graders.medium_grader import MediumGrader
from incident_env.server.graders.hard_grader import HardGrader


@pytest.mark.asyncio
async def test_easy_grader_perfect_score(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    fi = FaultInjector(mesh)
    await fi.inject("oom_crash")

    history = [
        (IncidentAction(action_type="query_logs", target="payments"), "OOMKilled: memory limit exceeded"),
        (IncidentAction(action_type="restart_service", target="payments"), "payments restarted"),
    ]
    # Simulate restart restoring health
    mesh.services["payments"].status = "healthy"

    grader = EasyGrader(mesh, history)
    result = grader.grade()
    assert result.score == 1.0
    await mesh.stop()


@pytest.mark.asyncio
async def test_easy_grader_partial_no_restart(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    await FaultInjector(mesh).inject("oom_crash")

    history = [
        (IncidentAction(action_type="query_logs", target="payments"), "OOMKilled: exit code 137"),
    ]
    grader = EasyGrader(mesh, history)
    result = grader.grade()
    assert 0.0 < result.score < 1.0


@pytest.mark.asyncio
async def test_medium_grader_red_herring_penalty(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    await FaultInjector(mesh).inject("connection_exhaustion")

    history = [
        (IncidentAction(action_type="restart_service", target="analytics"), "analytics restarted"),
    ]
    grader = MediumGrader(mesh, history)
    result = grader.grade()
    assert "red_herring_penalty" in result.milestones_hit
    await mesh.stop()


@pytest.mark.asyncio
async def test_hard_grader_full_path(tmp_path):
    mesh = ServiceMesh(base_dir=str(tmp_path))
    await mesh.start()
    await FaultInjector(mesh).inject("schema_drift")
    await asyncio.sleep(0.6)

    history = [
        (IncidentAction(action_type="query_logs", target="data-pipeline"), "MemoryError: blob_data column"),
        (IncidentAction(action_type="query_db", target="warehouse_db",
                        parameters={"query": "PRAGMA table_info(events)"}), "blob_data BLOB"),
        (IncidentAction(action_type="fix_config", target="data-pipeline",
                        parameters={"key": "skip_column", "value": "blob_data"}), "Config updated"),
        (IncidentAction(action_type="run_pipeline", target="data-pipeline"), "Pipeline run triggered"),
    ]
    mesh.services["data-pipeline"].status = "healthy"
    mesh.services["analytics"].status = "healthy"

    grader = HardGrader(mesh, history)
    result = grader.grade()
    assert result.score >= 0.9
    await mesh.stop()
