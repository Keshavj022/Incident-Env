import os
from openenv.core.env_server import create_app
from incident_env.models import IncidentAction, IncidentObservation
from incident_env.server.environment import IncidentEnvironment

BASE_DIR = os.getenv("INCIDENT_ENV_DB_DIR", "/tmp/incident_env_dbs")

# Shared singleton — HTTP endpoints create a new instance per request,
# so we return the SAME instance to preserve state between reset() and step().
_shared_env = IncidentEnvironment(base_dir=BASE_DIR)


def _make_env() -> IncidentEnvironment:
    return _shared_env


app = create_app(_make_env, IncidentAction, IncidentObservation, env_name="incident_env")


def main():
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
