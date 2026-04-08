from incident_env.server.simulation.fault_injector import FaultInjector
from incident_env.server.graders.hard_grader import HardGrader


class HardTask:
    task_id = "hard"
    max_steps = 20

    def __init__(self, mesh):
        self._mesh = mesh
        self._injector = FaultInjector(mesh)

    async def setup(self) -> None:
        await self._injector.inject("schema_drift")

    def get_grader(self, action_history):
        return HardGrader(self._mesh, action_history)
