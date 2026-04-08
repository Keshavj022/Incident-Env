# incident_env/server/simulation/transport/in_memory.py
import asyncio
from typing import Callable, Dict, List
from .base import BaseMessageBus


class InMemoryBus(BaseMessageBus):
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, channel: str, handler: Callable) -> None:
        self._subscribers.setdefault(channel, []).append(handler)

    async def publish(self, channel: str, message: dict) -> None:
        for handler in self._subscribers.get(channel, []):
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result

    def reset(self) -> None:
        self._subscribers = {}
