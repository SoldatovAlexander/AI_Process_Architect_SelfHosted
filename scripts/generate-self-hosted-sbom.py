#!/usr/bin/env python3
"""Generate a deterministic CycloneDX SBOM for a self-hosted source tree."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path


def revision(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return (root / "SELF_HOSTED_SOURCE_REVISION").read_text(encoding="utf-8").strip()


def python_components(root: Path) -> list[dict]:
    components: list[dict] = []
    for manifest in ("apps/api/pyproject.toml", "apps/license_control_plane/pyproject.toml"):
        path = root / manifest
        if not path.exists():
            continue
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        for dependency in project.get("dependencies", []):
            name = dependency.split("[", 1)[0].split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].strip()
            components.append({"type": "library", "name": name, "version": dependency.removeprefix(name).strip() or "unspecified", "purl": f"pkg:pypi/{name.lower()}", "properties": [{"name": "apa:manifest", "value": manifest}]})
    return components


def web_components(root: Path) -> list[dict]:
    lockfile = root / "apps/web/package-lock.json"
    if not lockfile.exists():
        return []
    packages = json.loads(lockfile.read_text(encoding="utf-8")).get("packages", {})
    result: list[dict] = []
    for location, item in sorted(packages.items()):
        if not location.startswith("node_modules/") or not item.get("version"):
            continue
        name = location.removeprefix("node_modules/")
        result.append({"type": "library", "name": name, "version": item["version"], "purl": f"pkg:npm/{name}@{item['version']}", "properties": [{"name": "apa:manifest", "value": "apps/web/package-lock.json"}]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    components = sorted(python_components(root) + web_components(root), key=lambda item: (item["purl"], item["version"]))
    document = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "serialNumber": f"urn:uuid:ai-process-architect-{revision(root)}",
        "version": 1,
        "metadata": {"timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "component": {"type": "application", "name": "AI Process Architect self-hosted", "version": revision(root)}},
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"sbom_components={len(components)}")


if __name__ == "__main__":
    main()
