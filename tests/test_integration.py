import asyncio
import pytest
from incident_env.models import IncidentAction
from incident_env.server.environment import IncidentEnvironment


@pytest.mark.asyncio
async def test_easy_task_full_episode(tmp_path):
    env = IncidentEnvironment(base_dir=str(tmp_path))
    obs = await env.async_reset(task_id="easy")

    assert obs.steps_remaining == 10
    assert len(obs.active_alerts) > 0  # OOM fault fires alerts

    # Step 1: query logs
    obs = await env.async_step(IncidentAction(action_type="query_logs", target="payments", parameters={}))
    assert any("OOMKilled" in l or "exit code" in l for l in obs.logs)

    # Step 2: restart
    obs = await env.async_step(IncidentAction(action_type="restart_service", target="payments", parameters={}))
    assert "restart" in obs.last_action_result.lower()

    # Step 3: mark resolved
    obs = await env.async_step(IncidentAction(action_type="mark_resolved", target="", parameters={}))
    assert obs.done is True
    assert obs.reward >= 0.6  # got at least queried + restarted + healthy milestones

    await env._mesh.stop()


@pytest.mark.asyncio
async def test_medium_task_kill_job_resolves(tmp_path):
    env = IncidentEnvironment(base_dir=str(tmp_path))
    await env.async_reset(task_id="medium")

    # Kill the pipeline job
    obs = await env.async_step(IncidentAction(action_type="kill_job", target="data-pipeline", parameters={}))
    assert "released" in obs.last_action_result.lower()
    assert env._mesh.services["api-gateway"].status == "healthy"

    await env._mesh.stop()


@pytest.mark.asyncio
async def test_hard_task_schema_fix_resolves(tmp_path):
    env = IncidentEnvironment(base_dir=str(tmp_path))
    await env.async_reset(task_id="hard")
    await asyncio.sleep(0.6)  # let pipeline fail

    await env.async_step(IncidentAction(action_type="query_logs", target="data-pipeline", parameters={}))
    await env.async_step(IncidentAction(
        action_type="query_db", target="warehouse_db", parameters={"query": "PRAGMA table_info(events)"}
    ))
    await env.async_step(IncidentAction(
        action_type="fix_config", target="data-pipeline", parameters={"key": "skip_column", "value": "blob_data"}
    ))
    await env.async_step(IncidentAction(action_type="run_pipeline", target="data-pipeline", parameters={}))
    await asyncio.sleep(1.0)  # let pipeline complete

    obs = await env.async_step(IncidentAction(action_type="mark_resolved", target="", parameters={}))
    assert obs.done is True
    assert obs.reward >= 0.5

    await env._mesh.stop()
