import hashlib
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote
from zipfile import ZipFile

import httpx

from ..exporters.agents import build_agent_contract, generate_agent_package
from .runtime_connections import RuntimeVerificationError, resolve_secret, validate_egress_target, verify_runtime_connection


class AgentPackageDeliveryError(RuntimeError):
    def __init__(self, code: str, remote_package_id: str | None = None):
        super().__init__(code)
        self.code = code
        self.remote_package_id = remote_package_id


@dataclass(frozen=True)
class PreparedAgentPackageDelivery:
    package: bytes
    package_sha256: str
    package_size: int
    file_count: int
    process_name: str
    readiness_score: int
    blocker_count: int
    ready: bool
    runtime: str


def prepare_agent_package_delivery(process_ir: dict, runtime: str, locale: str) -> PreparedAgentPackageDelivery:
    if runtime not in {"openclaw", "hermes"}:
        raise ValueError("Agent package delivery supports only OpenClaw and Hermes.")
    contract = build_agent_contract(process_ir)
    package = generate_agent_package(process_ir, runtime, locale)
    if len(package) > 10 * 1024 * 1024:
        raise ValueError("Agent package exceeds the 10 MB delivery limit.")
    with ZipFile(BytesIO(package)) as archive:
        file_count = len(archive.infolist())
    readiness = contract["readiness"]
    return PreparedAgentPackageDelivery(
        package=package,
        package_sha256=hashlib.sha256(package).hexdigest(),
        package_size=len(package),
        file_count=file_count,
        process_name=str(contract["process"]["name"]),
        readiness_score=int(readiness["overall"]),
        blocker_count=len(readiness["blockers"]),
        ready=bool(readiness["agentReady"]),
        runtime=runtime,
    )


def _error_code(error: Exception) -> str:
    if isinstance(error, RuntimeVerificationError):
        return error.code
    if isinstance(error, httpx.TimeoutException):
        return "agent_delivery_timeout"
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return "authentication_failed"
        return "agent_package_rejected"
    if isinstance(error, (httpx.HTTPError, ValueError)):
        return "agent_runtime_unavailable"
    return "agent_delivery_failed"


def _package_url(endpoint_url: str, remote_package_id: str | None = None) -> str:
    base = f"{endpoint_url.rstrip('/')}/packages"
    return f"{base}/{quote(remote_package_id, safe='')}" if remote_package_id else base


async def store_inactive_agent_package(
    profile,
    prepared: PreparedAgentPackageDelivery,
    revision_id: str,
    idempotency_key: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    remote_id = None
    try:
        await verify_runtime_connection(profile, transport=transport)
        validate_egress_target(profile.endpoint_url)
        token = resolve_secret(profile.secret_ref)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/zip",
            "Idempotency-Key": idempotency_key,
            "X-Process-Revision-Id": revision_id,
            "X-Package-SHA256": prepared.package_sha256,
            "X-Agent-Runtime": prepared.runtime,
            "X-Activation-Policy": "manual",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0), follow_redirects=False, transport=transport) as client:
            response = await client.post(_package_url(profile.endpoint_url), headers=headers, content=prepared.package)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("id"):
                raise ValueError("Agent runtime did not return a package id.")
            remote_id = str(payload["id"])[:255]
            safe = payload.get("status") == "stored" and payload.get("active") is False
            digest_matches = payload.get("sha256") in {None, prepared.package_sha256}
            if not safe or not digest_matches:
                try:
                    await client.delete(_package_url(profile.endpoint_url, remote_id), headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
                finally:
                    raise AgentPackageDeliveryError("remote_agent_package_not_inactive", remote_id)
            return remote_id
    except AgentPackageDeliveryError:
        raise
    except Exception as error:
        raise AgentPackageDeliveryError(_error_code(error), remote_id) from error


async def delete_stored_agent_package(profile, remote_package_id: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    try:
        validate_egress_target(profile.endpoint_url)
        token = resolve_secret(profile.secret_ref)
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=3.0), follow_redirects=False, transport=transport) as client:
            response = await client.delete(
                _package_url(profile.endpoint_url, remote_package_id),
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if response.status_code != 404:
                response.raise_for_status()
    except Exception as error:
        raise AgentPackageDeliveryError(_error_code(error)) from error
