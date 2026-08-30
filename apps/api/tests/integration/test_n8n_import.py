import json
import os
import subprocess

import pytest

from mvp_scenarios import MVP_SCENARIOS
from process_architect_api.exporters.n8n import export_n8n
from process_architect_api.exporters.n8n.registry import TARGETS


RUN_CONTAINERS = os.getenv("RUN_N8N_CONTAINER_TESTS") == "1"
@pytest.mark.integration
@pytest.mark.skipif(not RUN_CONTAINERS, reason="RUN_N8N_CONTAINER_TESTS=1 is required")
@pytest.mark.parametrize("target_minor", ["2.32", "2.31", "2.30"])
@pytest.mark.parametrize("scenario", MVP_SCENARIOS, ids=lambda item: item.id)
def test_workflow_imports_into_supported_n8n_container(tmp_path, target_minor, scenario):
    process_ir = scenario.load_process_ir()
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        json.dumps(export_n8n(process_ir, target_minor), ensure_ascii=False),
        encoding="utf-8",
    )
    image = f"n8nio/n8n:{TARGETS[target_minor].tested_patch}"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            "N8N_USER_FOLDER=/tmp/n8n",
            "-v",
            f"{tmp_path}:/data:ro",
            image,
            "import:workflow",
            "--input=/data/workflow.json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
