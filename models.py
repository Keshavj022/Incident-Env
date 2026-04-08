# incident_env/models.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, model_validator

from openenv.core.env_server import Action, Observation, State

ActionType = Literal[
    "query_logs",
    "query_metrics",
    "query_db",
    "restart_service",
    "rollback_deploy",
    "kill_job",
    "fix_config",
    "run_pipeline",
    "scale_service",
    "mark_resolved",
]


class IncidentAction(Action):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    action_type: ActionType = "mark_resolved"
    target: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class IncidentObservation(Observation):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    timestamp: str = ""
    active_alerts: List[Dict] = Field(default_factory=list)
    service_statuses: Dict[str, str] = Field(default_factory=dict)
    service_topology: Dict[str, List[str]] = Field(default_factory=dict)
    logs: List[str] = Field(default_factory=list)
    metrics: Dict[str, Dict] = Field(default_factory=dict)
    db_result: Optional[List[Dict]] = None
    last_action_result: str = ""
    incident_resolved: bool = False
    steps_remaining: int = Field(default=10, ge=0)

    @model_validator(mode='after')
    def sync_done(self) -> 'IncidentObservation':
        object.__setattr__(self, 'done', self.incident_resolved)
        return self


class IncidentState(State):
    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    step_count: int = Field(default=0, ge=0)
    task_id: Literal["easy", "medium", "hard"] = "easy"
    deployment_mode: Literal["single", "distributed"] = "single"
    incident_active: bool = True
    milestones_hit: List[str] = Field(default_factory=list)
    cumulative_score: float = 0.0
    services_affected: List[str] = Field(default_factory=list)
    root_cause_identified: bool = False
    incident_resolved: bool = False
