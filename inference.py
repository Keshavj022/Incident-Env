"""
Baseline inference script for incident_env.

Required env vars:
  API_BASE_URL  - LLM API endpoint (e.g. https://router.huggingface.co/v1)
  MODEL_NAME    - Model identifier
  HF_TOKEN      - Hugging Face API key (used as API key)
"""
from __future__ import annotations

import asyncio
import json
import os
import textwrap
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from incident_env.models import IncidentAction, IncidentObservation
from incident_env.server.environment import IncidentEnvironment

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY", "hf_placeholder")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
IMAGE_NAME = os.getenv("DOCKER_IMAGE", "incident-env:latest")
TEMPERATURE = 0.2
MAX_TOKENS = 300

BENCHMARK = "incident_env"
TASKS = [
    {"id": "easy",   "name": "OOM Crash",                     "max_steps": 10, "max_reward": 1.0},
    {"id": "medium", "name": "Connection Pool Exhaustion",     "max_steps": 15, "max_reward": 1.0},
    {"id": "hard",   "name": "Schema Drift + Pipeline Cascade", "max_steps": 20, "max_reward": 1.0},
]
SUCCESS_SCORE_THRESHOLD = 0.5

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert SRE (Site Reliability Engineer) responding to a production incident.

You have a simulated microservice mesh with 4 services:
  - api-gateway: routes requests to payments and analytics
  - payments: SQLite-backed transaction service
  - data-pipeline: runs pandas ETL jobs on the warehouse DB
  - analytics: runs SQL queries on warehouse DB

Available action_types:
  query_logs       - fetch recent logs from a service
  query_metrics    - get real-time metrics (error_rate, 5xx_rate, cpu_percent, etc.)
  query_db         - run a SQL SELECT/PRAGMA on 'warehouse_db' or 'payments_db'
  restart_service  - restart a degraded/down service
  kill_job         - terminate an in-progress pipeline job
  fix_config       - apply a config fix: {"key": "...", "value": "..."}
  run_pipeline     - manually trigger the ETL pipeline
  rollback_deploy  - rollback a service to its last known good config
  mark_resolved    - call this when the incident is fully resolved

Respond ONLY with a JSON object on a single line:
{"action_type": "...", "target": "...", "parameters": {...}}

Think step-by-step: check alerts, investigate services, find root cause, fix it, verify, resolve.
Do not guess. Query before acting.
""").strip()


# ---------------------------------------------------------------------------
# Structured Logging — [START], [STEP], [END] format
# ---------------------------------------------------------------------------

def log_start(task: str, env: str, model: str) -> None:
    print(json.dumps({
        "type": "START",
        "task": task,
        "env": env,
        "model": model,
    }), flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    print(json.dumps({
        "type": "STEP",
        "step": step,
        "action": action,
        "reward": reward,
        "done": done,
        "error": error,
    }), flush=True)


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    print(json.dumps({
        "type": "END",
        "success": success,
        "steps": steps,
        "score": round(score, 4),
        "rewards": [round(r, 4) for r in rewards],
    }), flush=True)


# ---------------------------------------------------------------------------
# Prompt Building
# ---------------------------------------------------------------------------

def build_user_prompt(obs: IncidentObservation, history: List[Tuple[str, str]]) -> str:
    alerts_text = json.dumps(obs.active_alerts, indent=2) if obs.active_alerts else "None"
    statuses_text = json.dumps(obs.service_statuses, indent=2)

    history_text = "None"
    if history:
        history_text = "\n".join(
            f"  Step {i+1}: {a} -> {r[:120]}" for i, (a, r) in enumerate(history[-6:])
        )

    logs_text = "\n".join(obs.logs[-15:]) if obs.logs else "(no logs — use query_logs to fetch)"
    metrics_text = json.dumps(obs.metrics, indent=2) if obs.metrics else "(no metrics — use query_metrics)"
    db_text = json.dumps(obs.db_result, indent=2) if obs.db_result else "(no DB result)"

    return textwrap.dedent(f"""
    === INCIDENT DASHBOARD ===
    Timestamp: {obs.timestamp}
    Steps remaining: {obs.steps_remaining}
    Last action result: {obs.last_action_result}

    ACTIVE ALERTS:
    {alerts_text}

    SERVICE STATUSES:
    {statuses_text}

    RECENT LOGS (last query):
    {logs_text}

    METRICS (last query):
    {metrics_text}

    DB RESULT (last query):
    {db_text}

    ACTION HISTORY:
    {history_text}

    Respond with a single JSON action.
    """).strip()


# ---------------------------------------------------------------------------
# Action Parsing
# ---------------------------------------------------------------------------

def parse_action(text: str) -> IncidentAction:
    """Extract JSON action from model response."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return IncidentAction(action_type="mark_resolved", target="", parameters={})
    try:
        data = json.loads(text[start:end])
        return IncidentAction(
            action_type=data.get("action_type", "mark_resolved"),
            target=data.get("target", ""),
            parameters=data.get("parameters", {}),
        )
    except json.JSONDecodeError:
        return IncidentAction(action_type="mark_resolved", target="", parameters={})


# ---------------------------------------------------------------------------
# LLM Interaction
# ---------------------------------------------------------------------------

def get_model_action(
    client: OpenAI,
    step: int,
    obs: IncidentObservation,
    history: List[Tuple[str, str]],
) -> str:
    """Ask the LLM for the next action given current observation."""
    user_prompt = build_user_prompt(obs, history)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        return completion.choices[0].message.content or ""
    except Exception as exc:
        print(f"[DEBUG] Step {step} LLM error: {exc}", flush=True)
        return '{"action_type": "mark_resolved", "target": "", "parameters": {}}'


# ---------------------------------------------------------------------------
# Main — async entry point matching competition sample
# ---------------------------------------------------------------------------

async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    # Use in-process environment (works without Docker)
    # For container mode: env = await IncidentEnv.from_docker_image(IMAGE_NAME)
    env = IncidentEnvironment()

    all_scores: Dict[str, float] = {}

    for task_cfg in TASKS:
        task_id = task_cfg["id"]
        task_name = task_cfg["name"]
        max_steps = task_cfg["max_steps"]
        max_total_reward = task_cfg["max_reward"]

        history: List[Tuple[str, str]] = []
        rewards: List[float] = []
        steps_taken = 0
        score = 0.0
        success = False

        log_start(task=task_name, env=BENCHMARK, model=MODEL_NAME)

        try:
            obs = await env.async_reset(task_id=task_id)

            for step in range(1, max_steps + 1):
                if obs.done:
                    break

                response_text = get_model_action(client, step, obs, history)
                action = parse_action(response_text)
                action_str = f"{action.action_type}({action.target})"

                obs = await env.async_step(action)
                reward = obs.reward if obs.reward is not None else 0.0
                done = obs.done
                error = None

                rewards.append(reward)
                steps_taken = step

                history.append((action_str, obs.last_action_result))

                log_step(step=step, action=action_str, reward=reward, done=done, error=error)

                if done:
                    break

            score = sum(rewards) / max_total_reward if max_total_reward > 0 else 0.0
            score = min(max(score, 0.0), 1.0)
            success = score >= SUCCESS_SCORE_THRESHOLD

        except Exception as e:
            print(f"[DEBUG] Task {task_id} error: {e}", flush=True)

        finally:
            log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

        all_scores[task_id] = score

    # Summary
    print(f"\n{'='*50}", flush=True)
    print("BASELINE RESULTS", flush=True)
    print(f"{'='*50}", flush=True)
    for task_id, s in all_scores.items():
        print(f"  {task_id:8s}: {s:.3f}", flush=True)
    avg = sum(all_scores.values()) / len(all_scores) if all_scores else 0.0
    print(f"  {'average':8s}: {avg:.3f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
