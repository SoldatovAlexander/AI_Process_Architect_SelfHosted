from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .localization import normalize_locale
from .rubric import CURRENT_RUBRIC_VERSION, entry_id


SUPPORTED_MINORS = {"2.30", "2.31", "2.32"}
TRIGGER_TYPES = {"manualTrigger", "webhook", "scheduleTrigger", "cron", "emailReadImap", "formTrigger"}
DECISION_TYPES = {"if", "switch", "filter"}
TIMER_TYPES = {"wait", "scheduleTrigger", "cron"}
KNOWN_NODE_PREFIXES = ("n8n-nodes-base.", "@n8n/n8n-nodes-langchain.")


class InvalidN8nWorkflow(ValueError):
    pass


def _inline_secret_paths(value: Any, path: str = "") -> list[str]:
    sensitive = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization")
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if any(marker in str(key).casefold() for marker in sensitive) and child not in (None, "", {}, []):
                found.append(child_path)
            else:
                found.extend(_inline_secret_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_inline_secret_paths(child, f"{path}/{index}"))
    return found


def canonical_workflow(workflow: dict[str, Any]) -> tuple[dict[str, Any], str]:
    source = deepcopy(workflow)
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return source, hashlib.sha256(encoded).hexdigest()


def detect_minor(workflow: dict[str, Any], requested_minor: str | None) -> str:
    detected = workflow.get("meta", {}).get("targetN8nMinor") if isinstance(workflow.get("meta"), dict) else None
    minor = requested_minor or detected
    if minor not in SUPPORTED_MINORS:
        raise InvalidN8nWorkflow("Choose a supported n8n minor: 2.32, 2.31, or 2.30.")
    return minor


def _safe_id(prefix: str, value: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", value.strip().casefold()).strip("_") or "item"
    if not re.match(r"^[a-z]", base):
        base = f"n_{base}"
    candidate = f"{prefix}_{base}"[:120]
    suffix = 2
    while candidate in used:
        candidate = f"{prefix}_{base}_{suffix}"[:120]
        suffix += 1
    used.add(candidate)
    return candidate


def _node_suffix(node_type: str) -> str:
    return node_type.rsplit(".", 1)[-1]


def _step_type(node_type: str, outgoing_count: int, incoming_count: int) -> str:
    suffix = _node_suffix(node_type)
    if outgoing_count == 0 and incoming_count > 0:
        return "end"
    if suffix in TIMER_TYPES:
        return "timer"
    if suffix in TRIGGER_TYPES or incoming_count == 0:
        return "start"
    if suffix in DECISION_TYPES or outgoing_count > 1:
        return "decision"
    return "system_task"


def _system_name(node_type: str) -> str:
    suffix = _node_suffix(node_type)
    return re.sub(r"(?<!^)(?=[A-Z])", " ", suffix).replace("Trigger", "").strip().title() or node_type


def _localized(locale: str) -> dict[str, str]:
    return {
        "ru": {
            "description": "AS-IS схема импортирована из n8n. Бизнес-контекст требуется подтвердить в интервью.",
            "goal": "Подтвердить назначение импортированного workflow.",
            "owner": "Кто отвечает за результат этого workflow?",
            "goal_question": "Какую бизнес-цель решает этот workflow и какой результат считается успешным?",
            "scope": "Что не входит в этот процесс?",
        },
        "en": {
            "description": "AS-IS diagram imported from n8n. Business context must be confirmed in an interview.",
            "goal": "Confirm the purpose of the imported workflow.",
            "owner": "Who owns the outcome of this workflow?",
            "goal_question": "What business goal does this workflow serve, and what result counts as success?",
            "scope": "What is outside this process?",
        },
        "es": {
            "description": "Diagrama AS-IS importado de n8n. El contexto de negocio debe confirmarse en una entrevista.",
            "goal": "Confirmar el proposito del workflow importado.",
            "owner": "Quien responde por el resultado de este workflow?",
            "goal_question": "Que objetivo de negocio resuelve y que resultado se considera exitoso?",
            "scope": "Que queda fuera de este proceso?",
        },
    }[normalize_locale(locale)]


def _safe_parameters(value: Any, key: str = "") -> Any:
    sensitive = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "credential")
    if any(marker in key.casefold() for marker in sensitive):
        return "{{configure_in_n8n_credentials}}"
    if isinstance(value, dict):
        return {str(child_key): _safe_parameters(child_value, str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_safe_parameters(item, key) for item in value]
    return deepcopy(value)


def import_n8n_workflow(workflow: dict[str, Any], locale: str, requested_minor: str | None = None) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    if not isinstance(workflow, dict):
        raise InvalidN8nWorkflow("n8n workflow must be a JSON object.")
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not isinstance(nodes, list) or not nodes:
        raise InvalidN8nWorkflow("n8n workflow must contain at least one node.")
    if not isinstance(connections, dict):
        raise InvalidN8nWorkflow("n8n workflow connections must be an object.")
    if len(nodes) > 500:
        raise InvalidN8nWorkflow("n8n workflow exceeds the 500 node import limit.")
    inline_secrets = _inline_secret_paths(workflow)
    if inline_secrets:
        raise InvalidN8nWorkflow(
            "Remove inline secrets before import. Use n8n credential references instead: "
            + ", ".join(inline_secrets[:8])
        )
    minor = detect_minor(workflow, requested_minor)
    source, source_sha = canonical_workflow(workflow)
    copy = _localized(locale)
    workflow_name = str(workflow.get("name") or "Imported n8n workflow")[:200]
    names: dict[str, dict[str, Any]] = {}
    duplicate_names: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("name"), str) or not isinstance(node.get("type"), str):
            raise InvalidN8nWorkflow("Every n8n node must have string name and type fields.")
        if node["name"] in names:
            duplicate_names.append(node["name"])
        names[node["name"]] = node
    if duplicate_names:
        raise InvalidN8nWorkflow(f"Duplicate n8n node names are not supported: {', '.join(sorted(set(duplicate_names)))}")

    raw_edges: list[tuple[str, str, int]] = []
    dangling: list[dict[str, str]] = []
    for source_name, groups in connections.items():
        if source_name not in names or not isinstance(groups, dict):
            continue
        for output_index, targets in enumerate(groups.get("main", [])):
            if not isinstance(targets, list):
                continue
            for target in targets:
                target_name = target.get("node") if isinstance(target, dict) else None
                if target_name not in names:
                    dangling.append({"from": source_name, "to": str(target_name)})
                    continue
                raw_edges.append((source_name, target_name, output_index))
    incoming = {name: 0 for name in names}
    outgoing = {name: 0 for name in names}
    for source_name, target_name, _ in raw_edges:
        outgoing[source_name] += 1
        incoming[target_name] += 1

    used_ids: set[str] = set()
    step_ids = {name: _safe_id("step", str(node.get("id") or name), used_ids) for name, node in names.items()}
    system_ids: dict[str, str] = {}
    systems: list[dict[str, Any]] = []
    unknown_nodes: list[dict[str, str]] = []
    credential_references: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for name, node in names.items():
        node_type = node["type"]
        suffix = _node_suffix(node_type)
        if not node_type.startswith(KNOWN_NODE_PREFIXES):
            unknown_nodes.append({"name": name, "type": node_type})
        credentials = node.get("credentials")
        if isinstance(credentials, dict):
            credential_references.append({"node": name, "types": sorted(credentials), "names": [str(value.get("name")) for value in credentials.values() if isinstance(value, dict) and value.get("name")]})
        step_type = _step_type(node_type, outgoing[name], incoming[name])
        system_id = None
        if step_type not in {"start", "end", "decision", "timer"}:
            if node_type not in system_ids:
                system_id = _safe_id("system", node_type, used_ids)
                system_ids[node_type] = system_id
                systems.append({"id": system_id, "name": _system_name(node_type), "type": node_type, "integrationStatus": "configured" if credentials else "api_available", "notes": "Imported from n8n node type; credential values were not imported."})
            system_id = system_ids[node_type]
        steps.append({
            "id": step_ids[name], "type": step_type, "title": name, "description": str(node.get("notes") or ""),
            "actorId": None, "systemId": system_id, "inputs": [], "outputs": [],
            "operation": {"kind": "n8n_node", "name": suffix, "parameters": _safe_parameters(node.get("parameters") if isinstance(node.get("parameters"), dict) else {})},
            "missingFields": ["business_context"], "automationHint": {"target": "n8n", "nodeType": node_type},
            "execution": {"performedBy": "system", "autonomy": "autonomous", "approvalRequired": False, "restrictions": []},
        })

    edges = []
    for index, (source_name, target_name, output_index) in enumerate(raw_edges, 1):
        condition = None
        if outgoing[source_name] > 1:
            condition = {"left": "n8n_output", "operator": "==", "right": output_index}
        edges.append({"id": f"edge_import_{index}", "from": step_ids[source_name], "to": step_ids[target_name], "condition": condition, "ruleIds": []})

    process_id = f"import_{uuid5(NAMESPACE_URL, f'n8n:{source_sha}') }".replace("-", "_")
    blocked = {"score": 0, "status": "blocked", "notes": ["confirm_imported_business_context"]}
    process_ir = {
        "schemaVersion": "0.2",
        "process": {"id": process_id, "name": workflow_name, "description": copy["description"], "domain": "unknown", "maturity": "draft"},
        "passport": {"goal": copy["goal"], "ownerActorId": None, "startsWhen": "; ".join(name for name in names if incoming[name] == 0), "endsWhen": "; ".join(name for name in names if outgoing[name] == 0), "inScope": list(names), "outOfScope": [], "successMetrics": []},
        "actors": [], "systems": systems, "dataObjects": [], "states": [], "stateTransitions": [], "businessRules": [],
        "steps": steps, "edges": edges, "exceptions": [],
        "openQuestions": [
            {"id": "question_import_goal", "priority": "high", "target": {"entity": "passport", "id": process_id}, "question": copy["goal_question"], "blocksAutomationReady": True},
            {"id": "question_import_owner", "priority": "high", "target": {"entity": "passport", "id": process_id}, "question": copy["owner"], "blocksAutomationReady": True},
            {"id": "question_import_scope", "priority": "medium", "target": {"entity": "passport", "id": process_id}, "question": copy["scope"], "blocksAutomationReady": False},
        ],
        "readiness": {"overall": 0, "categories": {name: deepcopy(blocked) for name in ("structure", "actors", "systems", "data", "branches", "exceptions", "automation")}},
        "classification": {"rubricVersion": CURRENT_RUBRIC_VERSION, "status": "proposed", "entryIds": [entry_id("process_level", "process"), entry_id("business_role", "supporting"), entry_id("customer_impact", "internal"), entry_id("organizational_span", "local"), entry_id("automation_mode", "workflow"), entry_id("domain", "operations"), entry_id("risk", "medium"), entry_id("data_sensitivity", "internal"), entry_id("human_control", "review")], "classifiedAt": None, "classifiedByUserId": None},
    }
    diagnostics = {
        "status": "needs_review" if unknown_nodes or dangling else "mapped",
        "nodeCount": len(nodes), "connectionCount": len(raw_edges), "knownNodeCount": len(nodes) - len(unknown_nodes),
        "unknownNodes": unknown_nodes, "danglingConnections": dangling, "credentialReferences": credential_references,
        "warnings": ["Business meaning, owner, scope, exceptions, and success criteria require confirmation."],
    }
    return process_ir, diagnostics, minor, source_sha
