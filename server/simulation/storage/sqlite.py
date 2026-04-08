# incident_env/server/simulation/storage/sqlite.py
import glob
import os
from .base import BaseStorage


class SQLiteStorage(BaseStorage):
    def __init__(self, base_dir: str = "/tmp/incident_env_dbs"):
        self._base_dir = base_dir
        os.makedirs(self._base_dir, exist_ok=True)

    def get_db_path(self, name: str) -> str:
        return os.path.join(self._base_dir, f"{name}.db")

    def reset(self) -> None:
        for db_file in glob.glob(os.path.join(self._base_dir, "*.db")):
            os.remove(db_file)
