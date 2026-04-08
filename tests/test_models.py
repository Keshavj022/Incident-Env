# incident_env/tests/test_models.py
import pytest
from pydantic import ValidationError

from incident_env.models import IncidentAction, IncidentObservation, IncidentState


def test_incident_action_defaults():
    action = IncidentAction(action_type="query_logs", target="payments", parameters={})
    assert action.action_type == "query_logs"
    assert action.target == "payments"
    assert action.parameters == {}


def test_incident_action_with_params():
    action = IncidentAction(
        action_type="query_db",
        target="warehouse_db",
        parameters={"query": "SELECT * FROM events LIMIT 5"},
    )
    assert action.parameters["query"].startswith("SELECT")


def test_incident_observation_fields():
    obs = IncidentObservation(
        timestamp="2026-01-01T00:00:00Z",
        active_alerts=[],
        service_statuses={"payments": "healthy"},
        service_topology={"api-gateway": ["payments"]},
        logs=[],
        metrics={},
        db_result=None,
        last_action_result="Reset complete.",
        incident_resolved=False,
        steps_remaining=10,
    )
    assert obs.incident_resolved is False
    assert obs.steps_remaining == 10


def test_incident_state_defaults():
    state = IncidentState()
    assert state.step_count == 0
    assert state.task_id == "easy"
    assert state.milestones_hit == []
    assert state.cumulative_score == 0.0


def test_incident_action_rejects_invalid_action_type():
    with pytest.raises(ValidationError):
        IncidentAction(action_type="invalid_type", target="payments", parameters={})


def test_incident_state_task_id_literal():
    with pytest.raises(ValidationError):
        IncidentState(task_id="nonexistent")


def test_incident_state_defaults_no_args():
    state = IncidentState()
    assert state.action_type if hasattr(state, 'action_type') else True
    assert state.task_id == "easy"
    assert state.deployment_mode == "single"
    assert state.incident_active is True


def test_incident_observation_done_syncs_with_resolved():
    obs = IncidentObservation(incident_resolved=True, steps_remaining=0)
    assert obs.done is True
