from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from incident_env.server.simulation.service_mesh import ServiceMesh


@dataclass
class GraderResult:
    score: float
    milestones_hit: List[str] = field(default_factory=list)
    feedback: str = ""


class BaseGrader(ABC):
    def __init__(self, mesh: "ServiceMesh", action_history: List[Tuple]):
        self._mesh = mesh
        self._history = action_history  # List of (IncidentAction, result_str)
        self._milestones: Dict[str, bool] = {}
        self._penalty: float = 0.0

    def _hit(self, name: str) -> None:
        self._milestones[name] = True

    def _penalize(self, amount: float) -> None:
        self._penalty += amount

    def _score(self, weights: Dict[str, float]) -> float:
        total = sum(weights.values())
        earned = sum(w for k, w in weights.items() if self._milestones.get(k))
        return max(0.0, min(1.0, round(earned / total - self._penalty, 3))) if total else 0.0

    @abstractmethod
    def grade(self) -> GraderResult:
        pass
