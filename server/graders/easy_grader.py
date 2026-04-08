from .base_grader import BaseGrader, GraderResult

WEIGHTS = {
    "queried_payments_logs": 0.15,
    "identified_oom": 0.25,
    "restarted_payments": 0.35,
    "service_healthy": 0.25,
}


class EasyGrader(BaseGrader):
    def grade(self) -> GraderResult:
        for action, result in self._history:
            if action.action_type == "query_logs" and action.target == "payments":
                self._hit("queried_payments_logs")
            if action.action_type in ("query_logs", "query_metrics"):
                if any(kw in result.lower() for kw in ("oomkilled", "memory limit", "exit code 137")):
                    self._hit("identified_oom")
            if action.action_type == "restart_service" and action.target == "payments":
                self._hit("restarted_payments")

        if self._mesh.services["payments"].status == "healthy":
            self._hit("service_healthy")

        score = self._score(WEIGHTS)
        hits = [k for k, v in self._milestones.items() if v]
        return GraderResult(score=score, milestones_hit=hits)
