import json
from copy import deepcopy
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from ..models import ValidationResult
from ..readiness import calculate_readiness
from ..process_ir import upgrade_process_ir
from .bpmn import generate_bpmn
from .n8n.registry import TARGETS, export_n8n
from .n8n.python_code import python_code_files
from .n8n.python_service import python_service_files
from .n8n.typescript_node import typescript_node_files
from .n8n.readme import (
    generate_n8n_general_guide,
    generate_n8n_package_index,
    generate_n8n_process_guide,
)
from .resource_spec import generate_resource_spec
from .spec import generate_spec


def _zip_bytes(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return output.getvalue()


def generate_export_package(
    process_ir: dict[str, Any],
    validation: ValidationResult,
    target_minor: str,
) -> bytes:
    target = TARGETS[target_minor]
    normalized_ir = upgrade_process_ir(deepcopy(process_ir))
    readiness = calculate_readiness(normalized_ir)
    normalized_ir["readiness"] = {
        "overall": readiness.overall,
        "categories": {
            name: {
                "score": category.score,
                "status": category.status,
                "notes": category.reason_codes,
            }
            for name, category in readiness.categories.items()
        },
    }
    files = {
        "spec/process-overview.md": generate_spec(normalized_ir, validation),
        "process.bpmn": generate_bpmn(normalized_ir),
        f"workflow-n8n-{target_minor}.json": json.dumps(
            export_n8n(normalized_ir, target_minor),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    }
    files.update(python_code_files(normalized_ir, target))
    files.update(python_service_files(normalized_ir, target))
    files.update(typescript_node_files(normalized_ir, target))
    for system in normalized_ir["systems"]:
        files[f"spec/resources/{system['id']}.md"] = generate_resource_spec(
            normalized_ir,
            system["id"],
            target_minor,
        )
    manifest = {
        "formatVersion": "1",
        "processId": normalized_ir["process"]["id"],
        "processIrVersion": normalized_ir["schemaVersion"],
        "n8n": {"targetMinor": target.minor, "testedPatch": target.tested_patch},
        "readiness": {
            "overall": readiness.overall,
            "automationReady": readiness.automation_ready,
            "draftReady": readiness.draft_ready,
            "scope": readiness.readiness_scope,
            "blockingQuestionCount": readiness.blocking_question_count,
        },
        "files": sorted([*files, "manifest.json"]),
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return _zip_bytes(files)


def generate_n8n_package(
    process_ir: dict[str, Any],
    target_minor: str,
    locale: str,
    include_general_guide: bool = True,
) -> bytes:
    process_ir = upgrade_process_ir(process_ir)
    target = TARGETS[target_minor]
    workflow_name = f"workflow-n8n-{target_minor}.json"
    files = {
        workflow_name: json.dumps(
            export_n8n(process_ir, target_minor),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "README.md": generate_n8n_package_index(target, locale, include_general_guide),
        "PROCESS_SETUP.md": generate_n8n_process_guide(process_ir, target, locale),
    }
    files.update(python_code_files(process_ir, target))
    files.update(python_service_files(process_ir, target))
    files.update(typescript_node_files(process_ir, target))
    if include_general_guide:
        files["N8N_BEGINNER_GUIDE.md"] = generate_n8n_general_guide(target, locale)
    return _zip_bytes(files)


def generate_n8n_roundtrip_package(
    process_ir: dict[str, Any],
    workflow: dict[str, Any],
    report: dict[str, Any],
    target_minor: str,
    locale: str,
    include_general_guide: bool = True,
) -> bytes:
    process_ir = upgrade_process_ir(process_ir)
    target = TARGETS[target_minor]
    workflow_name = f"workflow-n8n-{target_minor}.json"
    files = {
        workflow_name: json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        "ROUND_TRIP_REPORT.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        "README.md": generate_n8n_package_index(target, locale, include_general_guide),
        "PROCESS_SETUP.md": generate_n8n_process_guide(process_ir, target, locale),
    }
    files.update(python_code_files(process_ir, target))
    files.update(python_service_files(process_ir, target))
    files.update(typescript_node_files(process_ir, target))
    if include_general_guide:
        files["N8N_BEGINNER_GUIDE.md"] = generate_n8n_general_guide(target, locale)
    return _zip_bytes(files)
