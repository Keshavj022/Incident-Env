from __future__ import annotations
from typing import Any, Dict, Optional
from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from incident_env.models import IncidentAction, IncidentObservation, IncidentState


class IncidentEnv(EnvClient[IncidentAction, IncidentObservation, IncidentState]):

    def _step_payload(self, action: IncidentAction) -> Dict[str, Any]:
        return {
            "action_type": action.action_type,
            "target": action.target,
            "parameters": action.parameters,
        }

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[IncidentObservation]:
        obs_data = payload.get("observation", payload)
        observation = IncidentObservation(
            timestamp=obs_data.get("timestamp", ""),
            active_alerts=obs_data.get("active_alerts", []),
            service_statuses=obs_data.get("service_statuses", {}),
            service_topology=obs_data.get("service_topology", {}),
            logs=obs_data.get("logs", []),
            metrics=obs_data.get("metrics", {}),
            db_result=obs_data.get("db_result"),
            last_action_result=obs_data.get("last_action_result", ""),
            incident_resolved=obs_data.get("incident_resolved", False),
            steps_remaining=obs_data.get("steps_remaining", 0),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward", 0.0),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> IncidentState:
        return IncidentState(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            task_id=payload.get("task_id", "easy"),
            deployment_mode=payload.get("deployment_mode", "single"),
            incident_active=payload.get("incident_active", True),
            milestones_hit=payload.get("milestones_hit", []),
            cumulative_score=payload.get("cumulative_score", 0.0),
            incident_resolved=payload.get("incident_resolved", False),
        )
