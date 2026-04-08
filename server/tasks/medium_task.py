from incident_env.server.simulation.fault_injector import FaultInjector
from incident_env.server.graders.medium_grader import MediumGrader


class MediumTask:
    task_id = "medium"
    max_steps = 15

    def __init__(self, mesh):
        self._mesh = mesh
        self._injector = FaultInjector(mesh)

    async def setup(self) -> None:
        await self._injector.inject("connection_exhaustion")

    def get_grader(self, action_history):
        return MediumGrader(self._mesh, action_history)
