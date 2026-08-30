from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Settings, get_settings
from .database import get_session_factory
from .db_models import AgentDispatchJob, AgentRun
from .services.agent_dispatch import claim_next_job, dispatch_envelope, mark_dispatch_failure, mark_dispatched


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("agent-worker")


class RuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^accepted$")


def _runtime_config(settings: Settings, runtime: str) -> tuple[str, str]:
    if runtime == "openclaw":
        return settings.openclaw_runtime_url.strip(), settings.openclaw_runtime_token.get_secret_value() if settings.openclaw_runtime_token else ""
    return settings.hermes_runtime_url.strip(), settings.hermes_runtime_token.get_secret_value() if settings.hermes_runtime_token else ""


def deliver(settings: Settings, run: AgentRun, envelope: dict[str, Any], post: Callable[..., httpx.Response] = httpx.post) -> None:
    url, token = _runtime_config(settings, run.runtime)
    if not url:
        raise RuntimeError("runtime_not_configured")
    headers = {"Content-Type": "application/json", "Idempotency-Key": run.idempotency_key}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = post(url, json=envelope, headers=headers, timeout=min(run.timeout_seconds, 60))
    response.raise_for_status()
    RuntimeResponse.model_validate(response.json())


def process_one(worker_id: str, *, post: Callable[..., httpx.Response] = httpx.post) -> bool:
    settings = get_settings()
    if not settings.agent_worker_dispatch_enabled:
        return False
    with get_session_factory()() as db:
        job = claim_next_job(db, worker_id, settings.agent_worker_lease_seconds)
        if not job:
            return False
        run: AgentRun | None = None
        try:
            run, envelope = dispatch_envelope(db, job)
            deliver(settings, run, envelope, post)
            mark_dispatched(db, job, run)
            logger.info("agent dispatch accepted job=%s run=%s runtime=%s", job.id, run.id, run.runtime)
        except (httpx.HTTPError, RuntimeError, ValidationError, ValueError) as error:
            error_code = "runtime_response_invalid" if isinstance(error, (ValidationError, ValueError)) else str(error)[:64].lower().replace(" ", "_")
            mark_dispatch_failure(db, job, run, error_code)
            logger.warning("agent dispatch failed job=%s code=%s", job.id, error_code)
        return True


def main() -> None:
    settings = get_settings()
    worker_id = os.environ.get("AGENT_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
    logger.info("agent worker started id=%s dispatch_enabled=%s", worker_id, settings.agent_worker_dispatch_enabled)
    while True:
        worked = process_one(worker_id)
        if not worked:
            time.sleep(settings.agent_worker_poll_seconds)


if __name__ == "__main__":
    main()
