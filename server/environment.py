from __future__ import annotations

import time
import uuid
from typing import Any, List, Optional, Tuple

from openenv.core.env_server import Environment

from incident_env.models import IncidentAction, IncidentObservation, IncidentState
from incident_env.server.simulation.service_mesh import ServiceMesh
from incident_env.server.simulation.alert_manager import AlertManager
from incident_env.server.tasks.task_registry import get_task

VALID_SERVICES = {"api-gateway", "payments", "data-pipeline", "analytics"}
VALID_DB_TARGETS = {"warehouse_db", "payments_db"}
DESTRUCTIVE_SQL = {"drop", "delete", "truncate", "update", "insert", "alter"}


class IncidentEnvironment(Environment[IncidentAction, IncidentObservation, IncidentState]):
    def __init__(self, base_dir: str = "/tmp/incident_env_dbs"):
        super().__init__()
        self._base_dir = base_dir
        self._mesh: Optional[ServiceMesh] = None
        self._alert_mgr: Optional[AlertManager] = None
        self._task = None
        self._state = IncidentState()
        self._action_history: List[Tuple[IncidentAction, str]] = []
        self._max_steps: int = 10

    # ── OpenEnv interface ──────────────────────────────────────────────
    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        import asyncio
        task_id = kwargs.get("task_id", "easy")
        return asyncio.get_event_loop().run_until_complete(self.async_reset(task_id=task_id))

    def step(
        self,
        action: IncidentAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.async_step(action))

    async def reset_async(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        task_id = kwargs.get("task_id", "easy")
        return await self.async_reset(task_id=task_id)

    async def step_async(
        self,
        action: IncidentAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        return await self.async_step(action)

    @property
    def state(self) -> IncidentState:
        return self._state

    # ── Async implementations ──────────────────────────────────────────
    async def async_reset(self, task_id: str = "easy") -> IncidentObservation:
        if self._mesh:
            await self._mesh.stop()
        self._mesh = ServiceMesh(base_dir=self._base_dir)
        await self._mesh.start()
        self._alert_mgr = AlertManager(self._mesh)
        self._task = get_task(task_id, self._mesh)
        await self._task.setup()
        self._action_history = []
        self._max_steps = self._task.max_steps
        self._state = IncidentState(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            task_id=task_id,
        )
        return self._build_observation(
            [], {}, None, "Incident detected. Investigate and resolve.",
            done=False, reward=None,
        )

    async def async_step(self, action: IncidentAction) -> IncidentObservation:
        # Validate target
        target_valid = (
            action.action_type == "mark_resolved"
            or action.target in VALID_SERVICES
            or action.target in VALID_DB_TARGETS
            or action.target == ""
        )
        if not target_valid:
            obs = self._build_observation(
                [], {}, None,
                f"Unknown target '{action.target}'. Valid services: {sorted(VALID_SERVICES)}",
                done=False, reward=0.0,
            )
            return obs

        # Block destructive SQL
        if action.action_type == "query_db":
            q = action.parameters.get("query", "").lower()
            if any(kw in q for kw in DESTRUCTIVE_SQL):
                self._action_history.append((action, "REJECTED: destructive SQL"))
                self._state.step_count += 1
                obs = self._build_observation(
                    [], {}, None,
                    "REJECTED: only SELECT and PRAGMA are allowed in query_db.",
                    done=False, reward=-0.10,
                )
                return obs

        logs, metrics, db_result, result_text = await self._dispatch(action)
        self._action_history.append((action, result_text))
        self._state.step_count += 1

        steps_left = max(0, self._max_steps - self._state.step_count)

        # Terminal: mark_resolved
        if action.action_type == "mark_resolved":
            grade = self._task.get_grader(self._action_history).grade()
            self._state.milestones_hit = grade.milestones_hit
            self._state.cumulative_score = grade.score
            self._state.incident_resolved = True
            obs = self._build_observation(logs, metrics, db_result, result_text,
                                          done=True, reward=grade.score)
            return obs

        # Terminal: steps exhausted
        if steps_left <= 0:
            grade = self._task.get_grader(self._action_history).grade()
            self._state.cumulative_score = grade.score
            obs = self._build_observation(logs, metrics, db_result, "Max steps reached.",
                                          done=True, reward=grade.score)
            return obs

        obs = self._build_observation(logs, metrics, db_result, result_text,
                                      done=False, reward=0.0)
        return obs

    # ── Action dispatch ────────────────────────────────────────────────
    async def _dispatch(self, action: IncidentAction):
        logs, metrics, db_result = [], {}, None
        svc = self._mesh.services.get(action.target)

        if action.action_type == "query_logs":
            if svc:
                logs = svc.get_logs(last_n=action.parameters.get("last_n", 30))
                result = f"Fetched {len(logs)} log lines from {action.target}."
            else:
                result = f"No service '{action.target}'."

        elif action.action_type == "query_metrics":
            if svc:
                metrics = {action.target: svc.get_metrics()}
                result = f"Metrics for {action.target}: {svc.get_metrics()}"
            else:
                result = f"No service '{action.target}'."

        elif action.action_type == "query_db":
            db_result, result = self._run_db_query(action)

        elif action.action_type == "restart_service":
            if svc:
                await svc.restart()
                result = f"{action.target} restarted. Status: {svc.status}"
            else:
                result = f"No service '{action.target}'."

        elif action.action_type == "kill_job":
            if action.target == "data-pipeline":
                pipeline = self._mesh.services["data-pipeline"]
                pipeline._running_job = False
                pipeline.release_held_connections()
                self._mesh.services["payments"].release_connections()
                self._mesh.services["api-gateway"].simulate_healthy()
                result = "data-pipeline job killed. Held connections released."
            else:
                result = f"No active job on '{action.target}'."

        elif action.action_type == "fix_config":
            if svc and hasattr(svc, "fix_config"):
                k = action.parameters.get("key", "")
                v = action.parameters.get("value", "")
                ok = svc.fix_config(k, v)
                result = f"Config {'applied' if ok else 'rejected'}: {k}={v}"
            else:
                result = f"Service '{action.target}' does not support fix_config."

        elif action.action_type == "run_pipeline":
            pipeline = self._mesh.services.get("data-pipeline")
            if pipeline:
                pipeline.trigger_run()
                result = "Pipeline run triggered manually."
            else:
                result = "data-pipeline not found."

        elif action.action_type == "rollback_deploy":
            if svc:
                await svc.restart()
                result = f"{action.target} rolled back to last known good state."
            else:
                result = f"No service '{action.target}'."

        elif action.action_type == "scale_service":
            result = f"Scaling {action.target} (no-op in single-container mode)."

        elif action.action_type == "mark_resolved":
            result = "Incident marked as resolved."

        else:
            result = f"Unknown action_type: {action.action_type}"

        return logs, metrics, db_result, result

    def _run_db_query(self, action: IncidentAction):
        import sqlite3
        db_name = action.target.replace("_db", "")
        db_path = self._mesh.storage.get_db_path(db_name)
        query = action.parameters.get("query", "")
        if not query:
            return None, "No query provided in parameters."
        try:
            conn = sqlite3.connect(db_path, timeout=3.0)
            cur = conn.execute(query)
            rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchmany(20)]
            conn.close()
            return rows, f"Query returned {len(rows)} rows."
        except Exception as exc:
            return None, f"Query error: {exc}"

    # ── Observation builder ────────────────────────────────────────────
    def _build_observation(
        self, logs, metrics, db_result, last_action_result,
        done: bool = False, reward: Optional[float] = None,
    ) -> IncidentObservation:
        steps_left = max(0, self._max_steps - self._state.step_count)
        obs = IncidentObservation(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            active_alerts=self._alert_mgr.evaluate() if self._alert_mgr else [],
            service_statuses=self._mesh.get_statuses() if self._mesh else {},
            service_topology=self._mesh.get_topology() if self._mesh else {},
            logs=logs,
            metrics=metrics,
            db_result=db_result,
            last_action_result=last_action_result,
            incident_resolved=self._state.incident_resolved,
            steps_remaining=steps_left,
            reward=reward,
        )
        # Override done independently of incident_resolved (e.g. for step exhaustion)
        object.__setattr__(obs, "done", done)
        return obs
