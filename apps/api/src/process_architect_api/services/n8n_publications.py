import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import N8nImportArtifact
from ..exporters.n8n import export_n8n
from ..n8n_roundtrip import build_roundtrip_workflow
from .runtime_connections import RuntimeVerificationError, resolve_secret, validate_egress_target, verify_runtime_connection


class N8nPublicationError(RuntimeError):
    def __init__(self, code: str, remote_workflow_id: str | None = None):
        super().__init__(code)
        self.code = code
        self.remote_workflow_id = remote_workflow_id


@dataclass(frozen=True)
class PreparedN8nPublication:
    payload: dict[str, Any]
    workflow_sha256: str
    node_count: int
    connection_count: int
    source_mode: str


def _connection_count(value: Any) -> int:
    if isinstance(value, dict):
        return (1 if isinstance(value.get("node"), str) else 0) + sum(_connection_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_connection_count(item) for item in value)
    return 0


def _api_payload(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(workflow.get("name") or "Untitled workflow")[:128],
        "nodes": workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else [],
        "connections": workflow.get("connections") if isinstance(workflow.get("connections"), dict) else {},
        "settings": workflow.get("settings") if isinstance(workflow.get("settings"), dict) else {},
    }


def prepare_n8n_publication(db: Session, project, revision, profile) -> PreparedN8nPublication:
    artifact = db.scalar(
        select(N8nImportArtifact)
        .where(N8nImportArtifact.project_id == project.id)
        .order_by(N8nImportArtifact.created_at)
        .limit(1)
    )
    if artifact is None:
        workflow = export_n8n(revision.process_ir, profile.n8n_minor)
        source_mode = "generated"
    else:
        workflow, _ = build_roundtrip_workflow(
            revision.process_ir,
            source_workflow=artifact.source_workflow,
            source_minor=artifact.source_minor,
            target_minor=profile.n8n_minor,
            locale=project.default_locale,
            perspective=revision.perspective,
        )
        source_mode = "round_trip"
    payload = _api_payload(workflow)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return PreparedN8nPublication(
        payload=payload,
        workflow_sha256=hashlib.sha256(encoded).hexdigest(),
        node_count=len(payload["nodes"]),
        connection_count=_connection_count(payload["connections"]),
        source_mode=source_mode,
    )


def _error_code(error: Exception) -> str:
    if isinstance(error, RuntimeVerificationError):
        return error.code
    if isinstance(error, httpx.TimeoutException):
        return "publication_timeout"
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return "authentication_failed"
        return "n8n_publication_rejected"
    if isinstance(error, (httpx.HTTPError, ValueError)):
        return "n8n_unavailable"
    return "n8n_publication_failed"


async def publish_inactive_workflow(profile, prepared: PreparedN8nPublication, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    remote_id = None
    try:
        await verify_runtime_connection(profile, transport=transport)
        validate_egress_target(profile.endpoint_url)
        token = resolve_secret(profile.secret_ref)
        headers = {"X-N8N-API-KEY": token, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=3.0), follow_redirects=False, transport=transport) as client:
            created = await client.post(f"{profile.endpoint_url}/api/v1/workflows", headers=headers, json=prepared.payload)
            created.raise_for_status()
            created_payload = created.json()
            if not isinstance(created_payload, dict) or not created_payload.get("id"):
                raise ValueError("n8n did not return a workflow id")
            remote_id = str(created_payload["id"])[:255]
            inspected = await client.get(f"{profile.endpoint_url}/api/v1/workflows/{remote_id}", headers=headers)
            inspected.raise_for_status()
            inspected_payload = inspected.json()
            if not isinstance(inspected_payload, dict) or inspected_payload.get("active") is not False:
                if isinstance(inspected_payload, dict) and inspected_payload.get("active") is True:
                    await client.post(f"{profile.endpoint_url}/api/v1/workflows/{remote_id}/deactivate", headers=headers)
                await client.delete(f"{profile.endpoint_url}/api/v1/workflows/{remote_id}", headers=headers)
                raise N8nPublicationError("remote_workflow_not_inactive", remote_id)
            return remote_id
    except N8nPublicationError:
        raise
    except Exception as error:
        raise N8nPublicationError(_error_code(error), remote_id) from error


async def delete_inactive_workflow(profile, remote_workflow_id: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    try:
        validate_egress_target(profile.endpoint_url)
        token = resolve_secret(profile.secret_ref)
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=3.0), follow_redirects=False, transport=transport) as client:
            response = await client.delete(
                f"{profile.endpoint_url}/api/v1/workflows/{remote_workflow_id}",
                headers={"X-N8N-API-KEY": token, "Accept": "application/json"},
            )
            if response.status_code != 404:
                response.raise_for_status()
    except Exception as error:
        raise N8nPublicationError(_error_code(error)) from error
