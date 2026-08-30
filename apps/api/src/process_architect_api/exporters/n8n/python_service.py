from __future__ import annotations

import json
from typing import Any

from .base import N8nTarget
from .python_code import validate_python_code_artifact


DEPENDENCY_CATALOG_VERSION = "python-service-dependencies/1.0"
BASE_PACKAGES = {
    "annotated-doc": "0.0.5", "annotated-types": "0.8.0", "click": "8.4.2",
    "fastapi": "0.141.1", "h11": "0.16.0", "pydantic": "2.13.4",
    "pydantic-core": "2.46.4", "starlette": "1.3.1", "typing-extensions": "4.16.0",
    "typing-inspection": "0.4.2", "uvicorn": "0.52.1",
}
DEPENDENCY_PROFILES = {
    "core": {"description": "Standard-library transformation only", "modules": [], "packages": {}},
    "dates": {
        "description": "Parsing and calendar calculations with python-dateutil",
        "modules": ["dateutil"],
        "packages": {"python-dateutil": "2.9.0.post0", "six": "1.17.0"},
    },
    "validation": {
        "description": "JSON Schema validation with jsonschema",
        "modules": ["jsonschema"],
        "packages": {
            "attrs": "26.1.0", "jsonschema": "4.26.0", "jsonschema-specifications": "2025.9.1",
            "referencing": "0.37.0", "rpds-py": "2026.6.3",
        },
    },
}


def dependency_artifacts(profile_id: str) -> tuple[str, str, str]:
    try:
        profile = DEPENDENCY_PROFILES[profile_id]
    except KeyError as error:
        raise ValueError(f"unknown Python service dependency profile: {profile_id}") from error
    packages = {**BASE_PACKAGES, **profile["packages"]}
    requirements = "".join(f"{name}=={version}\n" for name, version in sorted(packages.items()))
    manifest = json.dumps({
        "catalogVersion": DEPENDENCY_CATALOG_VERSION,
        "profile": profile_id,
        "description": profile["description"],
        "allowedModules": profile["modules"],
        "packages": [{"name": name, "version": version} for name, version in sorted(packages.items())],
        "updatePolicy": "review catalog, rebuild image, scan image, rerun fixtures, approve a new Process IR revision",
    }, ensure_ascii=False, indent=2) + "\n"
    sbom = json.dumps({
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {"type": "application", "name": "apa-python-service", "version": "1.0"}},
        "components": [
            {"type": "library", "name": name, "version": version, "purl": f"pkg:pypi/{name}@{version}"}
            for name, version in sorted(packages.items())
        ],
    }, ensure_ascii=False, indent=2) + "\n"
    return requirements, manifest, sbom


def python_service_files(process_ir: dict[str, Any], target: N8nTarget) -> dict[str, str]:
    files: dict[str, str] = {}
    for step in process_ir.get("steps", []):
        logic = step.get("customLogic") or {}
        if logic.get("strategy") != "python_service":
            continue
        manifest = validate_python_code_artifact(process_ir, step, target)
        profile_id = logic.get("dependencyProfile", "core")
        requirements, dependency_manifest, sbom = dependency_artifacts(profile_id)
        root = f"python-services/{step['id']}"
        files[f"{root}/app/logic.py"] = logic["source"].rstrip() + "\n"
        files[f"{root}/app/main.py"] = '''import hmac
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .logic import transform


class ExecuteRequest(BaseModel):
    items: list[dict[str, Any]]


app = FastAPI(title="AI Process Architect Python Service", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute")
def execute(payload: ExecuteRequest, x_process_token: str = Header(default="")) -> list[dict[str, Any]]:
    expected = os.environ.get("PROCESS_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(x_process_token, expected):
        raise HTTPException(status_code=401, detail="invalid service token")
    return transform(payload.items)
'''
        files[f"{root}/app/__init__.py"] = ""
        files[f"{root}/requirements.lock"] = requirements
        files[f"{root}/dependency-manifest.json"] = dependency_manifest
        files[f"{root}/sbom.cdx.json"] = sbom
        files[f"{root}/Dockerfile"] = '''FROM python:3.13-slim
WORKDIR /service
RUN useradd --create-home --uid 10001 service
COPY requirements.lock .
RUN pip install --no-cache-dir --requirement requirements.lock
COPY app ./app
USER service
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
'''
        files[f"{root}/compose.yaml"] = '''services:
  process-service:
    build: .
    restart: unless-stopped
    environment:
      PROCESS_SERVICE_TOKEN: ${PROCESS_SERVICE_TOKEN:?set PROCESS_SERVICE_TOKEN}
    ports:
      - "127.0.0.1:8080:8080"
    read_only: true
    tmpfs:
      - /tmp:size=16m,noexec,nosuid
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
'''
        files[f"{root}/.env.example"] = "PROCESS_SERVICE_TOKEN=replace-with-a-long-random-token\n"
        files[f"{root}/contract.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/tests/test_logic.py"] = f'''import unittest

from app.logic import transform


class LogicTest(unittest.TestCase):
    def test_confirmed_example(self):
        self.assertEqual(transform({logic["inputExample"]!r}), {logic["outputExample"]!r})

    def test_malformed_example(self):
        with self.assertRaises({logic["expectedError"]}):
            transform({logic["errorExample"]!r})
'''
        files[f"{root}/README.md"] = f'''# Python service for {step["title"]}

Dependency profile: **{profile_id}**. Packages are pinned in `requirements.lock`; approved modules and update policy are recorded in `dependency-manifest.json`; `sbom.cdx.json` is a CycloneDX inventory for image scanning.

1. Copy `.env.example` to `.env` and replace the token with a long random value.
2. Run `docker compose up --build -d`.
3. Set `APA_PYTHON_SERVICE_URL` in the n8n environment to the URL reachable from n8n, without `/execute`.
4. In n8n create a **Header Auth** credential: name `X-Process-Token`, value equal to `PROCESS_SERVICE_TOKEN`.
5. Open the generated HTTP Request node and select that credential.
6. Call `/health`, then execute the workflow with the confirmed fixture before activation.

The archive never contains the real token. Do not add packages directly to `requirements.lock`: select an approved profile or update the catalog through code review. TLS termination, network policy, scaling, logs, image scanning, dependency updates, and secret rotation remain deployment responsibilities. The service runs read-only without Linux capabilities; deploy it on a network reachable only by n8n.
'''
    return files
