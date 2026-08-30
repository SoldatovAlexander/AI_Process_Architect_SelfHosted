from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .exporters.n8n.base import _unique_node_names
from .exporters.n8n.registry import TARGETS, export_n8n
from .n8n_importer import import_n8n_workflow


def _sha256(workflow: dict[str, Any]) -> str:
    encoded = json.dumps(workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _output_index(edge: dict[str, Any], fallback: int) -> int:
    condition = edge.get("condition")
    if isinstance(condition, dict) and condition.get("left") == "n8n_output":
        value = condition.get("right")
        if isinstance(value, int) and value >= 0:
            return value
    return fallback


def _connections(process_ir: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    step_types = {step["id"]: step["type"] for step in process_ir["steps"]}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for edge in process_ir["edges"]:
        if edge["from"] in names and edge["to"] in names:
            grouped.setdefault(edge["from"], []).append(edge)
    result: dict[str, Any] = {}
    for source_id, edges in grouped.items():
        indexed = [
            (_output_index(edge, index if step_types.get(source_id) == "decision" else 0), edge)
            for index, edge in enumerate(edges)
        ]
        outputs: list[list[dict[str, Any]]] = [[] for _ in range(max(index for index, _ in indexed) + 1)]
        for output_index, edge in indexed:
            outputs[output_index].append({"node": names[edge["to"]], "type": "main", "index": 0})
        result[names[source_id]] = {"main": outputs}
    return result


def build_roundtrip_workflow(
    process_ir: dict[str, Any],
    *,
    source_workflow: dict[str, Any],
    source_minor: str,
    target_minor: str,
    locale: str,
    perspective: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target = TARGETS[target_minor]
    source = deepcopy(source_workflow)
    source_ir, _, _, source_sha = import_n8n_workflow(source, locale, source_minor)
    exact = perspective == "as_is" and target_minor == source_minor
    if exact:
        return source, {
            "mode": "exact_source",
            "sourceMinor": source_minor,
            "targetMinor": target_minor,
            "sourceSha256": source_sha,
            "exportSha256": source_sha,
            "exactSource": True,
            "preservedSourceNodes": len(source.get("nodes", [])),
            "addedNodes": 0,
            "removedNodes": 0,
            "warnings": [],
        }

    if perspective == "as_is":
        workflow = source
        workflow["active"] = False
        workflow["meta"] = {
            **(workflow.get("meta") if isinstance(workflow.get("meta"), dict) else {}),
            "generatedBy": "AI Process Architect",
            "targetN8nMinor": target_minor,
            "testedPatch": target.tested_patch,
            "roundTripSourceSha256": source_sha,
        }
        return workflow, {
            "mode": "source_minor_conversion",
            "sourceMinor": source_minor,
            "targetMinor": target_minor,
            "sourceSha256": source_sha,
            "exportSha256": _sha256(workflow),
            "exactSource": False,
            "preservedSourceNodes": len(source.get("nodes", [])),
            "addedNodes": 0,
            "removedNodes": 0,
            "warnings": [
                "Node structure is preserved; review node type compatibility in the target n8n minor.",
                "The workflow is exported inactive and must be reviewed before publication.",
            ],
        }

    source_nodes = source.get("nodes", [])
    source_step_ids = [step["id"] for step in source_ir["steps"]]
    original_by_step = {step_id: node for step_id, node in zip(source_step_ids, source_nodes, strict=True)}
    generated = export_n8n(process_ir, target_minor)
    generated_by_id = {node["id"]: node for node in generated["nodes"]}
    names = _unique_node_names(process_ir["steps"])
    nodes: list[dict[str, Any]] = []
    preserved = 0
    added = 0
    for step in process_ir["steps"]:
        original = original_by_step.get(step["id"])
        if original is None:
            nodes.append(deepcopy(generated_by_id[step["id"]]))
            added += 1
            continue
        node = deepcopy(original)
        node["name"] = names[step["id"]]
        node["notes"] = step.get("description", "")
        generated_node = generated_by_id[step["id"]]
        if step.get("customLogic"):
            node["parameters"] = deepcopy(generated_node["parameters"])
            desired_type = generated_node["type"]
        else:
            node["parameters"] = deepcopy(step.get("operation", {}).get("parameters", {}))
            desired_type = step.get("automationHint", {}).get("nodeType") or node.get("type")
        if desired_type != node.get("type"):
            node["type"] = desired_type
            node["typeVersion"] = target.node_type_versions.get(desired_type, 1)
        nodes.append(node)
        preserved += 1

    connections = _connections(process_ir, names)
    source_names_by_step = {
        step_id: str(node.get("name")) for step_id, node in original_by_step.items()
    }
    current_ids = {step["id"] for step in process_ir["steps"]}
    for step_id, old_name in source_names_by_step.items():
        if step_id not in current_ids:
            continue
        original_groups = source.get("connections", {}).get(old_name, {})
        extra_groups = {key: deepcopy(value) for key, value in original_groups.items() if key != "main"}
        if extra_groups:
            connections.setdefault(names[step_id], {"main": []}).update(extra_groups)

    workflow = source
    workflow["name"] = process_ir["process"]["name"]
    workflow["nodes"] = nodes
    workflow["connections"] = connections
    workflow["active"] = False
    workflow["meta"] = {
        **(workflow.get("meta") if isinstance(workflow.get("meta"), dict) else {}),
        "generatedBy": "AI Process Architect",
        "targetN8nMinor": target_minor,
        "testedPatch": target.tested_patch,
        "processIrVersion": process_ir["schemaVersion"],
        "roundTripSourceSha256": source_sha,
    }
    report = {
        "mode": "source_preserving_rebuild",
        "sourceMinor": source_minor,
        "targetMinor": target_minor,
        "sourceSha256": source_sha,
        "exportSha256": _sha256(workflow),
        "exactSource": False,
        "preservedSourceNodes": preserved,
        "addedNodes": added,
        "removedNodes": len(original_by_step) - preserved,
        "warnings": [
            "The workflow is exported inactive and must be reviewed before publication."
        ],
    }
    return workflow, report
