from incident_env.server.simulation.fault_injector import FaultInjector
from incident_env.server.graders.easy_grader import EasyGrader


class EasyTask:
    task_id = "easy"
    max_steps = 10

    def __init__(self, mesh):
        self._mesh = mesh
        self._injector = FaultInjector(mesh)

    async def setup(self) -> None:
        await self._injector.inject("oom_crash")

    def get_grader(self, action_history):
        return EasyGrader(self._mesh, action_history)
