from __future__ import annotations

import time
import uuid
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .service_mesh import ServiceMesh

ALERT_RULES = [
    {
        "name": "ServiceDown",
        "severity": "critical",
        "condition": lambda svc: svc.status == "down",
        "message": lambda svc: f"{svc.name} is DOWN",
    },
    {
        "name": "HighErrorRate",
        "severity": "critical",
        "condition": lambda svc: svc._metrics.get("error_rate", 0) > 0.5,
        "message": lambda svc: f"{svc.name} error rate {svc._metrics.get('error_rate', 0):.0%}",
    },
    {
        "name": "High5xxRate",
        "severity": "critical",
        "condition": lambda svc: svc._metrics.get("5xx_rate", 0) > 0.5,
        "message": lambda svc: f"{svc.name} 5xx rate {svc._metrics.get('5xx_rate', 0):.0%}",
    },
    {
        "name": "HighCPU",
        "severity": "warning",
        "condition": lambda svc: svc._metrics.get("cpu_percent", 0) > 80,
        "message": lambda svc: f"{svc.name} CPU at {svc._metrics.get('cpu_percent', 0):.0f}%",
    },
    {
        "name": "PipelineDegraded",
        "severity": "warning",
        "condition": lambda svc: svc.name == "data-pipeline" and svc.status == "degraded",
        "message": lambda svc: "Data pipeline job failed or stalled",
    },
]


class AlertManager:
    def __init__(self, mesh: "ServiceMesh"):
        self._mesh = mesh
        self._fired: Dict[str, dict] = {}

    def evaluate(self) -> List[dict]:
        active = []
        for svc in self._mesh.services.values():
            for rule in ALERT_RULES:
                key = f"{rule['name']}:{svc.name}"
                try:
                    if rule["condition"](svc):
                        if key not in self._fired:
                            self._fired[key] = {
                                "alert_id": str(uuid.uuid4()),
                                "name": rule["name"],
                                "severity": rule["severity"],
                                "service": svc.name,
                                "message": rule["message"](svc),
                                "fired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            }
                        active.append(self._fired[key])
                    else:
                        self._fired.pop(key, None)
                except Exception:
                    pass
        return active

    def reset(self) -> None:
        self._fired = {}
