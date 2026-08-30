import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class RuntimeVerificationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RuntimeVerification:
    code: str
    detected_version: str | None = None


def resolve_secret(secret_ref: str) -> str:
    name = secret_ref.removeprefix("env:")
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeVerificationError("secret_not_configured")
    return value


def validate_egress_target(endpoint_url: str) -> None:
    hostname = urlparse(endpoint_url).hostname
    if not hostname:
        raise RuntimeVerificationError("invalid_endpoint")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise RuntimeVerificationError("host_not_found") from error
    for value in addresses:
        address = ipaddress.ip_address(value)
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise RuntimeVerificationError("egress_target_blocked")


def _json_object(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeVerificationError("invalid_runtime_response") from error
    if not isinstance(payload, dict):
        raise RuntimeVerificationError("invalid_runtime_response")
    return payload


async def verify_runtime_connection(profile, *, transport: httpx.AsyncBaseTransport | None = None) -> RuntimeVerification:
    validate_egress_target(profile.endpoint_url)
    token = resolve_secret(profile.secret_ref)
    timeout = httpx.Timeout(8.0, connect=3.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
            if profile.kind == "n8n":
                response = await client.get(
                    f"{profile.endpoint_url}/api/v1/workflows?limit=1",
                    headers={"X-N8N-API-KEY": token, "Accept": "application/json"},
                )
                response.raise_for_status()
                version = response.headers.get("X-N8N-Version")
                if not version:
                    settings_response = await client.get(
                        f"{profile.endpoint_url}/rest/settings",
                        headers={"X-N8N-API-KEY": token, "Accept": "application/json"},
                    )
                    settings_response.raise_for_status()
                    settings = _json_object(settings_response)
                    data = settings.get("data") if isinstance(settings.get("data"), dict) else settings
                    version = data.get("versionCli") or data.get("version")
                if not isinstance(version, str) or not version.startswith(f"{profile.n8n_minor}."):
                    raise RuntimeVerificationError("n8n_version_mismatch")
                return RuntimeVerification("connection_verified", version[:64])

            response = await client.get(
                profile.endpoint_url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = _json_object(response)
            identity = str(payload.get("runtime") or payload.get("kind") or payload.get("name") or "").lower()
            if profile.kind not in identity:
                raise RuntimeVerificationError("runtime_identity_mismatch")
            version = payload.get("version")
            return RuntimeVerification("connection_verified", str(version)[:64] if version else None)
    except RuntimeVerificationError:
        raise
    except httpx.TimeoutException as error:
        raise RuntimeVerificationError("connection_timeout") from error
    except httpx.HTTPStatusError as error:
        code = "authentication_failed" if error.response.status_code in {401, 403} else "runtime_unavailable"
        raise RuntimeVerificationError(code) from error
    except httpx.HTTPError as error:
        raise RuntimeVerificationError("runtime_unavailable") from error
