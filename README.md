# incident_env

An OpenEnv SRE incident response environment where AI agents diagnose and remediate real production failures in a simulated microservice mesh.

No hardcoded data. No mocked services. Real SQLite databases, real asyncio service loops, real connection pools, real pandas ETL, and real fault injection.

## What This Is

A Gymnasium-style environment (`reset()`/`step()`/`state`) built on the [OpenEnv](https://github.com/openenv-ai/openenv) framework. An agent receives an incident alert, investigates a 4-service microservice mesh, identifies root causes (including red herrings), and remediates -- all scored by milestone-based graders that verify actual service state.

### The 4 Services

| Service | What It Does | Backing Store |
|---------|-------------|---------------|
| **api-gateway** | Routes requests to payments + analytics, tracks rolling 5xx rate | In-memory deque |
| **payments** | SQLite-backed transaction service with `asyncio.Semaphore(5)` connection pool | SQLite (`payments.db`) |
| **data-pipeline** | Pandas ETL: reads `events` table, normalizes, writes `events_processed` | SQLite (`warehouse.db`) |
| **analytics** | Runs `SELECT COUNT(*), AVG(value_normalized) FROM events_processed` every 250ms | SQLite (`warehouse.db`) |

### The 3 Tasks

#### Easy: OOM Crash (max 10 steps)
- **Fault:** Payments service killed (OOMKilled, exit code 137)
- **Solution:** Query logs -> identify OOM -> restart payments
- **Grading milestones:** queried_payments_logs (0.15), identified_oom (0.25), restarted_payments (0.35), service_healthy (0.25)

#### Medium: Connection Pool Exhaustion (max 15 steps)
- **Fault:** Data-pipeline holds 15 connections to payments DB, payments semaphore drained to 0, gateway 5xx rate spiked to 85%
- **Red herring:** Analytics CPU at 89% (unrelated)
- **Solution:** Trace gateway degradation -> payments pool exhaustion -> data-pipeline as source -> kill pipeline job
- **Grading milestones:** gateway_degradation (0.10), payments_pool_error (0.20), traced_to_pipeline (0.20), killed_pipeline_job (0.30), gateway_resolved (0.20)
- **Penalty:** -0.05 per action on analytics (the red herring)

#### Hard: Schema Drift + Pipeline Cascade (max 20 steps)
- **Fault:** Pipeline's `events` table gets a `blob_data BLOB` column with 100 rows of 512KB blobs. ETL raises `MemoryError`. Analytics loses `events_processed` table and degrades.
- **Red herrings:** Gateway memory elevated (GC pressure), analytics failure message
- **Solution:** Query pipeline logs -> inspect schema (PRAGMA) -> fix_config skip_column=blob_data -> re-trigger pipeline -> verify analytics recovers
- **Grading milestones:** pipeline_memoryerror (0.10), schema_inspection (0.20), correct_config_fix (0.25), retriggered (0.20), pipeline_completed (0.15), analytics_healthy (0.10)
- **Penalty:** -0.05 per action on api-gateway (the red herring)

---

## Project Structure

```
incident_env/
├── openenv.yaml              # OpenEnv task definitions
├── pyproject.toml             # Package config + dependencies
├── models.py                  # IncidentAction, IncidentObservation, IncidentState (Pydantic v2)
├── client.py                  # WebSocket client (IncidentEnv extends EnvClient)
├── inference.py               # Baseline ReAct-style LLM agent (OpenAI client)
├── server/
│   ├── app.py                 # FastAPI app via create_fastapi_app()
│   ├── environment.py         # IncidentEnvironment (reset/step/state)
│   ├── Dockerfile             # Single-container deployment
│   ├── requirements.txt       # Server runtime deps
│   ├── simulation/
│   │   ├── service_mesh.py    # Orchestrates all 4 services
│   │   ├── fault_injector.py  # Injects OOM, connection exhaustion, schema drift
│   │   ├── alert_manager.py   # 5 alert rules (ServiceDown, HighErrorRate, etc.)
│   │   ├── transport/
│   │   │   ├── base.py        # BaseMessageBus ABC
│   │   │   └── in_memory.py   # InMemoryBus (async pub/sub)
│   │   ├── storage/
│   │   │   ├── base.py        # BaseStorage ABC
│   │   │   └── sqlite.py      # SQLiteStorage (real sqlite3 DBs)
│   │   └── services/
│   │       ├── base_service.py    # BaseService (start/stop/restart, log capture, metrics)
│   │       ├── api_gateway.py     # Rolling 5xx rate, degraded simulation
│   │       ├── payments.py        # Real connection pool (asyncio.Semaphore)
│   │       ├── data_pipeline.py   # Real pandas ETL, schema drift injection
│   │       └── analytics.py       # Real SQL queries, cascade degradation
│   ├── graders/
│   │   ├── base_grader.py     # Milestone-based scoring engine
│   │   ├── easy_grader.py     # OOM task grader
│   │   ├── medium_grader.py   # Connection pool grader (with red herring penalty)
│   │   └── hard_grader.py     # Schema drift grader (with red herring penalty)
│   └── tasks/
│       ├── task_registry.py   # get_task(task_id, mesh) factory
│       ├── easy_task.py       # OOM crash setup
│       ├── medium_task.py     # Connection exhaustion setup
│       └── hard_task.py       # Schema drift setup
├── tests/
│   ├── test_models.py         # 8 tests - Pydantic model validation
│   ├── test_services.py       # 19 tests - all 4 services + storage + transport
│   ├── test_alert_manager.py  # 5 tests - alert rules + mesh lifecycle
│   ├── test_fault_injector.py # 4 tests - all 3 fault scenarios
│   ├── test_graders.py        # 4 tests - scoring for all tasks
│   ├── test_environment.py    # 6 tests - reset/step/state/validation
│   └── test_integration.py    # 3 tests - full episodes for all 3 tasks
└── k8s/                       # Kubernetes manifests (distributed mode)
    ├── namespace.yaml
    ├── postgres.yaml
    ├── redis.yaml
    ├── api-gateway-deployment.yaml
    ├── payments-deployment.yaml
    ├── data-pipeline-deployment.yaml
    ├── analytics-deployment.yaml
    └── envoy-config.yaml
```

---

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker (for container deployment)
- An OpenAI-compatible LLM API (for running inference.py)

---

## Installation

```bash
# Clone and enter the project
cd incident_env

# Option A: Install with uv (recommended)
uv sync

# Option B: Install with pip
pip install -e ".[dev]"
```

---

## Pre-Submission Checklist

Run these commands from the **parent directory** of `incident_env/` (e.g., `~/code/Meta/`):

### 1. Run All Tests (49 tests)

```bash
python -m pytest incident_env/tests/ -v --tb=short
```

Expected output:
```
49 passed
```

This covers:
- Model validation (8 tests)
- All 4 services + storage + transport (19 tests)
- Alert manager + mesh lifecycle (5 tests)
- Fault injection for all 3 scenarios (4 tests)
- Grader scoring for all 3 tasks (4 tests)
- Environment reset/step/state (6 tests)
- Full episode integration for easy/medium/hard (3 tests)

### 2. Verify OpenEnv Compliance

```bash
cd incident_env
openenv validate
```

Expected output:
```
[OK] incident: Ready for multi-mode deployment
```

This verifies:
- `openenv.yaml` is valid
- `pyproject.toml` has correct `[project.scripts]` entry
- `uv.lock` exists
- `server/app.py` has a callable `main()` function

### 3. Verify Imports

```bash
# From the parent directory of incident_env/
python -c "from incident_env.inference import main; print('OK')"
python -c "from incident_env.server.app import app; print('OK')"
python -c "from incident_env.models import IncidentAction, IncidentObservation, IncidentState; print('OK')"
python -c "from incident_env.client import IncidentEnv; print('OK')"
```

All should print `OK`.

### 4. Docker Build (requires Docker daemon)

```bash
cd incident_env
docker build -f server/Dockerfile -t incident-env:latest .
```

### 5. Docker Run + Smoke Test

```bash
docker run -d -p 8000:8000 --name incident-test incident-env:latest
sleep 3
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" -d '{}' | python -m json.tool | head -20
docker stop incident-test && docker rm incident-test
```

Expected: JSON response with `service_statuses`, `active_alerts`, `steps_remaining`.

### 6. Run Inference (requires LLM API access)

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
export HF_TOKEN="hf_your_token_here"

cd ..  # parent directory of incident_env
python -m incident_env.inference
```

This runs all 3 tasks with structured `[START]`, `[STEP]`, `[END]` logging and prints per-task scores + average. Output is JSON-structured for automated evaluation.

---

## Running the Server

### Single-Container Mode (default, HF Spaces)

```bash
# Direct
uvicorn incident_env.server.app:app --host 0.0.0.0 --port 8000

# Or via entry point
server
```

### Distributed Mode (Kubernetes)

```bash
# Apply all manifests
kubectl apply -f incident_env/k8s/namespace.yaml
kubectl apply -f incident_env/k8s/postgres.yaml
kubectl apply -f incident_env/k8s/redis.yaml
kubectl apply -f incident_env/k8s/payments-deployment.yaml
kubectl apply -f incident_env/k8s/api-gateway-deployment.yaml
kubectl apply -f incident_env/k8s/data-pipeline-deployment.yaml
kubectl apply -f incident_env/k8s/analytics-deployment.yaml
kubectl apply -f incident_env/k8s/envoy-config.yaml
```

Set `DEPLOYMENT_MODE=distributed` to switch from SQLite to Postgres/Redis.

---

## API Reference

### Actions (what the agent can do)

| Action Type | Target | Parameters | Description |
|------------|--------|------------|-------------|
| `query_logs` | service name | `{"last_n": 30}` | Fetch recent log lines |
| `query_metrics` | service name | `{}` | Get real-time metrics |
| `query_db` | `warehouse_db` or `payments_db` | `{"query": "SELECT ..."}` | Run SQL (SELECT/PRAGMA only) |
| `restart_service` | service name | `{}` | Restart a service |
| `kill_job` | `data-pipeline` | `{}` | Kill running ETL job, release held connections |
| `fix_config` | service name | `{"key": "...", "value": "..."}` | Apply config fix |
| `run_pipeline` | `data-pipeline` | `{}` | Manually trigger ETL |
| `rollback_deploy` | service name | `{}` | Rollback to last known good state |
| `scale_service` | service name | `{}` | Scale (no-op in single-container mode) |
| `mark_resolved` | `""` | `{}` | End episode, trigger grading |

Valid service names: `api-gateway`, `payments`, `data-pipeline`, `analytics`

### Observations (what the agent sees)

Each step returns:
- `active_alerts` - fired alert rules (ServiceDown, HighErrorRate, High5xxRate, HighCPU, PipelineDegraded)
- `service_statuses` - status of all 4 services (healthy/degraded/down)
- `service_topology` - dependency graph
- `logs` - log lines from last `query_logs`
- `metrics` - metrics from last `query_metrics`
- `db_result` - rows from last `query_db`
- `last_action_result` - human-readable result of the last action
- `steps_remaining` - steps left before auto-termination
- `done` - episode complete?
- `reward` - score (0.0-1.0, only set on terminal step)

### Scoring

Scores are **milestone-based** (0.0 to 1.0):
- Each milestone has a weight (weights sum to 1.0)
- Score = earned_weight / total_weight - penalties
- Penalties apply for acting on red herring services (-0.05 each)
- Graders verify **actual service state** (not just action history)

---

## Deploying to Hugging Face Spaces

```bash
cd incident_env
openenv push
```

This packages and deploys the environment to HF Spaces. Requires `huggingface-cli login` first.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEPLOYMENT_MODE` | `single` | `single` (SQLite, one process) or `distributed` (Postgres/Redis, K8s) |
| `INCIDENT_ENV_DB_DIR` | `/tmp/incident_env_dbs` | Directory for SQLite database files |
| `PORT` | `8000` | Server listen port |
| `API_BASE_URL` | `https://router.huggingface.co/v1` | LLM API endpoint (for inference.py) |
| `MODEL_NAME` | `meta-llama/Llama-3.1-8B-Instruct` | LLM model identifier |
| `HF_TOKEN` | - | Hugging Face API token |

---

## Key Design Decisions

1. **Real faults, not mocked** - Connection pool exhaustion actually drains `asyncio.Semaphore._value` to 0. Schema drift actually runs `ALTER TABLE` and inserts 512KB blobs. OOM actually stops the service process.

2. **Milestone-based grading** - Scores verify actual service state (`payments.status == "healthy"`, `gateway._metrics["5xx_rate"] < 0.1`) rather than trusting the agent's self-reported actions.

3. **Red herrings** - Medium and hard tasks include deliberately misleading signals. Agents that chase red herrings get penalized (-0.05 per distracted action).

4. **Dual-mode deployment** - Same codebase runs as a single Docker container (HF Spaces, competition) or as distributed K8s services (production). Controlled by `DEPLOYMENT_MODE` env var.

5. **No destructive SQL** - `query_db` blocks `DROP`, `DELETE`, `TRUNCATE`, `UPDATE`, `INSERT`, `ALTER`. Only `SELECT` and `PRAGMA` are allowed. Attempting destructive SQL costs -0.10 reward and consumes a step.
