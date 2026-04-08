from .easy_task import EasyTask
from .medium_task import MediumTask
from .hard_task import HardTask

REGISTRY = {"easy": EasyTask, "medium": MediumTask, "hard": HardTask}


def get_task(task_id: str, mesh):
    cls = REGISTRY.get(task_id)
    if cls is None:
        raise ValueError(f"Unknown task_id: {task_id!r}. Valid: {list(REGISTRY)}")
    return cls(mesh)
