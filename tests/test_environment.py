import asyncio
import pytest
from incident_env.models import IncidentAction
from incident_env.server.environment import IncidentEnvironment


@pytest.fixture
def env(tmp_path):
    return IncidentEnvironment(base_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_reset_returns_observation(env):
    obs = await env.async_reset(task_id="easy")
    assert obs.incident_resolved is False
    assert obs.steps_remaining == 10
    assert isinstance(obs.service_statuses, dict)
    assert isinstance(obs.active_alerts, list)


@pytest.mark.asyncio
async def test_step_query_logs(env):
    await env.async_reset(task_id="easy")
    action = IncidentAction(action_type="query_logs", target="payments")
    result = await env.async_step(action)
    assert isinstance(result.logs, list)
    assert result.steps_remaining == 9


@pytest.mark.asyncio
async def test_step_mark_resolved_ends_episode(env):
    await env.async_reset(task_id="easy")
    action = IncidentAction(action_type="mark_resolved", target="")
    result = await env.async_step(action)
    assert result.done is True
    assert 0.0 <= result.reward <= 1.0


@pytest.mark.asyncio
async def test_invalid_target_does_not_consume_step(env):
    await env.async_reset(task_id="easy")
    action = IncidentAction(action_type="query_logs", target="nonexistent_service")
    result = await env.async_step(action)
    assert result.steps_remaining == 10


@pytest.mark.asyncio
async def test_steps_exhausted_returns_done(env):
    await env.async_reset(task_id="easy")
    action = IncidentAction(action_type="query_logs", target="payments")
    result = None
    for _ in range(10):
        result = await env.async_step(action)
    assert result.done is True


@pytest.mark.asyncio
async def test_state_returns_metadata(env):
    await env.async_reset(task_id="medium")
    state = env.state
    assert state.task_id == "medium"
    assert state.step_count == 0
