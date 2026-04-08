from .base_grader import BaseGrader, GraderResult

WEIGHTS = {
    "queried_pipeline_logs_memory_error": 0.10,
    "ran_schema_inspection": 0.20,
    "applied_correct_config_fix": 0.25,
    "retriggered_pipeline": 0.20,
    "pipeline_completed": 0.15,
    "analytics_healthy": 0.10,
}
RED_HERRING_SERVICES = {"api-gateway"}
RED_HERRING_PENALTY = 0.05


class HardGrader(BaseGrader):
    def grade(self) -> GraderResult:
        for action, result in self._history:
            if action.action_type == "query_logs" and action.target == "data-pipeline":
                if any(kw in result.lower() for kw in ("memoryerror", "memory error", "blob_data")):
                    self._hit("queried_pipeline_logs_memory_error")

            if action.action_type == "query_db":
                q = action.parameters.get("query", "").lower()
                if "pragma" in q or "table_info" in q or "sqlite_master" in q:
                    self._hit("ran_schema_inspection")

            if action.action_type == "fix_config" and action.target == "data-pipeline":
                k = action.parameters.get("key", "")
                v = action.parameters.get("value", "")
                if k == "skip_column" and v == "blob_data":
                    self._hit("applied_correct_config_fix")

            if action.action_type == "run_pipeline" and action.target == "data-pipeline":
                self._hit("retriggered_pipeline")

            if action.action_type in ("restart_service", "rollback_deploy", "scale_service"):
                if action.target in RED_HERRING_SERVICES:
                    self._penalize(RED_HERRING_PENALTY)

        if self._mesh.services["data-pipeline"].status == "healthy":
            self._hit("pipeline_completed")
        if self._mesh.services["analytics"].status == "healthy":
            self._hit("analytics_healthy")

        score = self._score(WEIGHTS)
        hits = [k for k, v in self._milestones.items() if v]
        return GraderResult(score=score, milestones_hit=hits)
