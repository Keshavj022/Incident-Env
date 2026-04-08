from .base_grader import BaseGrader, GraderResult

WEIGHTS = {
    "identified_gateway_degradation": 0.10,
    "queried_payments_pool_error": 0.20,
    "traced_to_pipeline": 0.20,
    "killed_pipeline_job": 0.30,
    "gateway_resolved": 0.20,
}
RED_HERRING_SERVICE = "analytics"
RED_HERRING_PENALTY = 0.05


class MediumGrader(BaseGrader):
    def grade(self) -> GraderResult:
        for action, result in self._history:
            if action.action_type in ("query_metrics", "query_logs") and action.target == "api-gateway":
                if any(kw in result.lower() for kw in ("5xx", "502", "degraded", "upstream")):
                    self._hit("identified_gateway_degradation")

            if action.action_type == "query_logs" and action.target == "payments":
                if any(kw in result.lower() for kw in ("pool", "connection", "exhausted")):
                    self._hit("queried_payments_pool_error")

            if action.action_type in ("query_logs", "query_metrics") and action.target == "data-pipeline":
                self._hit("traced_to_pipeline")

            if action.action_type == "kill_job" and action.target == "data-pipeline":
                self._hit("killed_pipeline_job")

            if action.action_type in ("restart_service", "rollback_deploy", "scale_service"):
                if action.target == RED_HERRING_SERVICE:
                    self._penalize(RED_HERRING_PENALTY)
                    self._hit("red_herring_penalty")

        gw = self._mesh.services["api-gateway"]
        if gw._metrics.get("5xx_rate", 1.0) < 0.1:
            self._hit("gateway_resolved")

        score = self._score(WEIGHTS)
        hits = [k for k, v in self._milestones.items() if v]
        return GraderResult(score=score, milestones_hit=hits)
