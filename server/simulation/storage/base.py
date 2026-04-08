# incident_env/server/simulation/storage/base.py
from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def get_db_path(self, name: str) -> str:
        """Return file path (or DSN) for named database."""

    @abstractmethod
    def reset(self) -> None:
        """Delete all database files/tables and start fresh."""
