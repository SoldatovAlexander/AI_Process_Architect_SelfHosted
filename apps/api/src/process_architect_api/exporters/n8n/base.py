from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .python_code import compile_python_code_node, compile_python_service_node
from .typescript_node import compile_typescript_node, typescript_node_type


@dataclass(frozen=True)
class N8nTarget:
    minor: str
    tested_patch: str
    node_type_versions: dict[str, float] = field(default_factory=dict)
    python_runtime: str = "native_task_runner"


DEFAULT_NODE_TYPES = {
    "start": "n8n-nodes-base.manualTrigger",
    "end": "n8n-nodes-base.noOp",
    "human_task": "n8n-nodes-base.noOp",
    "system_task": "n8n-nodes-base.noOp",
    "decision": "n8n-nodes-base.if",
    "timer": "n8n-nodes-base.wait",
    "external_event": "n8n-nodes-base.webhook",
}


def _node_type(step: dict[str, Any]) -> str:
    hint = step.get("automationHint")
    return hint.get("nodeType") if hint else DEFAULT_NODE_TYPES[step["type"]]


def _unique_node_names(steps: list[dict[str, Any]]) -> dict[str, str]:
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for step in steps:
        title = step["title"]
        counts[title] = counts.get(title, 0) + 1
        occurrence = counts[title]
        names[step["id"]] = title if occurrence == 1 else f"{title} ({occurrence})"
    return names


def build_workflow(process_ir: dict[str, Any], target: N8nTarget) -> dict[str, Any]:
    step_names = _unique_node_names(process_ir["steps"])
    nodes = []
    for index, step in enumerate(process_ir["steps"]):
        node_type = _node_type(step)
        parameters = dict(step["operation"].get("parameters", {}))
        custom_logic = step.get("customLogic")
        if custom_logic and custom_logic.get("strategy") == "python_code":
            node_type = "n8n-nodes-base.code"
            parameters = compile_python_code_node(process_ir, step, target)
        elif custom_logic and custom_logic.get("strategy") == "python_service":
            node_type = "n8n-nodes-base.httpRequest"
            parameters = compile_python_service_node(process_ir, step, target)
        elif custom_logic and custom_logic.get("strategy") == "typescript_node":
            node_type = typescript_node_type(step["id"])
            parameters = compile_typescript_node(process_ir, step, target)
        node = {
                "parameters": parameters,
                "id": step["id"],
                "name": step_names[step["id"]],
                "type": node_type,
                "typeVersion": target.node_type_versions.get(node_type, 1),
                "position": [240 * (index % 5), 180 * (index // 5)],
                "notes": step["description"],
            }
        if custom_logic and custom_logic.get("strategy") == "python_service":
            node["credentials"] = {"httpHeaderAuth": {"name": "APA Python service token"}}
            node.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 1000})
        nodes.append(node)

    step_types = {step["id"]: step["type"] for step in process_ir["steps"]}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for edge in process_ir["edges"]:
        grouped.setdefault(edge["from"], []).append(edge)

    connections: dict[str, Any] = {}
    for source_id, edges in grouped.items():
        output_groups: list[list[dict[str, Any]]] = [[]]
        if step_types[source_id] == "decision":
            output_groups = [[] for _ in edges]
        for index, edge in enumerate(edges):
            output_index = index if step_types[source_id] == "decision" else 0
            output_groups[output_index].append(
                {"node": step_names[edge["to"]], "type": "main", "index": 0}
            )
        connections[step_names[source_id]] = {"main": output_groups}

    return {
        "id": str(
            uuid5(
                NAMESPACE_URL,
                f"https://ai-process-architect.local/process/{process_ir['process']['id']}",
            )
        ),
        "name": process_ir["process"]["name"],
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "tags": [],
        "meta": {
            "generatedBy": "AI Process Architect",
            "targetN8nMinor": target.minor,
            "testedPatch": target.tested_patch,
            "processIrVersion": process_ir["schemaVersion"],
        },
    }
