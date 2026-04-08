# incident_env/server/simulation/transport/base.py
from abc import ABC, abstractmethod
from typing import Callable


class BaseMessageBus(ABC):
    @abstractmethod
    def subscribe(self, channel: str, handler: Callable) -> None:
        pass

    @abstractmethod
    async def publish(self, channel: str, message: dict) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass
