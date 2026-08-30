import json
from collections import defaultdict, deque
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from .models import ValidationCounts, ValidationIssue, ValidationResult
from .paths import PROCESS_IR_SCHEMA_PATH
from .process_ir import upgrade_process_ir


def _pointer(parts: Any) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


@lru_cache
def _schema_validator() -> Draft202012Validator:
    schema = json.loads(PROCESS_IR_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _issue(severity: str, code: str, message: str, path: str) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        path=path,
    )


def _reachable(start_ids: list[str], adjacency: dict[str, list[str]]) -> set[str]:
    visited: set[str] = set()
    queue = deque(start_ids)
    while queue:
        step_id = queue.popleft()
        if step_id in visited:
            continue
        visited.add(step_id)
        queue.extend(adjacency.get(step_id, []))
    return visited


def _semantic_issues(process_ir: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    steps = process_ir.get("steps")
    edges = process_ir.get("edges")
    if not isinstance(steps, list) or not isinstance(edges, list):
        return issues

    step_index = {
        step.get("id"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    }
    collections = {
        "actors": process_ir.get("actors", []),
        "systems": process_ir.get("systems", []),
        "dataObjects": process_ir.get("dataObjects", []),
        "states": process_ir.get("states", []),
        "stateTransitions": process_ir.get("stateTransitions", []),
        "businessRules": process_ir.get("businessRules", []),
        "steps": steps,
        "edges": edges,
        "exceptions": process_ir.get("exceptions", []),
        "openQuestions": process_ir.get("openQuestions", []),
    }
    indexes: dict[str, dict[str, dict[str, Any]]] = {}
    for collection, items in collections.items():
        index: dict[str, dict[str, Any]] = {}
        for item_position, item in enumerate(items):
            item_id = item.get("id")
            if item_id in index:
                issues.append(
                    _issue(
                        "error",
                        "duplicate_id",
                        f"Duplicate id: {item_id}.",
                        f"/{collection}/{item_position}/id",
                    )
                )
            if isinstance(item_id, str):
                index[item_id] = item
        indexes[collection] = index

    passport_owner = process_ir.get("passport", {}).get("ownerActorId")
    if passport_owner and passport_owner not in indexes["actors"]:
        issues.append(
            _issue(
                "error",
                "unknown_process_owner",
                f"Unknown process owner actor: {passport_owner}.",
                "/passport/ownerActorId",
            )
        )

    for index, step in enumerate(steps):
        actor_id = step.get("actorId")
        system_id = step.get("systemId")
        if actor_id and actor_id not in indexes["actors"]:
            issues.append(
                _issue("error", "unknown_actor", f"Unknown actorId: {actor_id}.", f"/steps/{index}/actorId")
            )
        if system_id and system_id not in indexes["systems"]:
            issues.append(
                _issue("error", "unknown_system", f"Unknown systemId: {system_id}.", f"/steps/{index}/systemId")
            )
        for field in ("inputs", "outputs"):
            for data_id in step.get(field, []):
                if data_id not in indexes["dataObjects"]:
                    issues.append(
                        _issue(
                            "error",
                            "unknown_data_object",
                            f"Unknown data object: {data_id}.",
                            f"/steps/{index}/{field}",
                        )
                    )
        agent_config = step.get("agentConfig")
        if isinstance(agent_config, dict):
            for state_id in agent_config.get("allowedStateIds", []):
                if state_id not in indexes["states"]:
                    issues.append(
                        _issue(
                            "error",
                            "unknown_agent_allowed_state",
                            f"Unknown allowed agent state: {state_id}.",
                            f"/steps/{index}/agentConfig/allowedStateIds",
                        )
                    )
        if step.get("type") == "human_task" and not actor_id:
            issues.append(
                _issue("warning", "human_task_without_actor", "Human task has no responsible actor.", f"/steps/{index}/actorId")
            )
        operation_kind = step.get("operation", {}).get("kind")
        custom_logic = step.get("customLogic")
        if isinstance(custom_logic, dict):
            for rule_id in custom_logic.get("businessRuleIds", []):
                rule = indexes["businessRules"].get(rule_id)
                if not rule:
                    issues.append(_issue("error", "unknown_custom_logic_rule", f"Unknown custom logic rule: {rule_id}.", f"/steps/{index}/customLogic/businessRuleIds"))
                elif step.get("id") not in rule.get("appliesToStepIds", []):
                    issues.append(_issue("error", "custom_logic_rule_step_mismatch", f"Rule {rule_id} does not apply to step {step.get('id')}.", f"/steps/{index}/customLogic/businessRuleIds"))
            if custom_logic.get("strategy") == "python_code" and (step.get("automationHint") or {}).get("nodeType") not in {None, "n8n-nodes-base.code"}:
                issues.append(_issue("error", "custom_logic_node_conflict", "Python custom logic conflicts with the selected n8n node type.", f"/steps/{index}/automationHint/nodeType"))
        if step.get("type") == "system_task" and not system_id and operation_kind != "ai_task":
            issues.append(
                _issue("warning", "system_task_without_system", "System task has no target system.", f"/steps/{index}/systemId")
            )
    starts = [step for step in steps if step.get("type") == "start"]
    ends = [step for step in steps if step.get("type") == "end"]

    if len(starts) != 1:
        issues.append(
            _issue(
                "error",
                "invalid_start_count",
                f"Process must have exactly one start step; found {len(starts)}.",
                "/steps",
            )
        )
    if not ends:
        issues.append(
            _issue("error", "missing_end", "Process must have at least one end step.", "/steps")
        )

    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, edge in enumerate(edges):
        source = edge.get("from")
        target = edge.get("to")
        if source not in step_index:
            issues.append(
                _issue(
                    "error",
                    "unknown_edge_source",
                    f"Unknown edge source: {source}.",
                    f"/edges/{index}/from",
                )
            )
        if target not in step_index:
            issues.append(
                _issue(
                    "error",
                    "unknown_edge_target",
                    f"Unknown edge target: {target}.",
                    f"/edges/{index}/to",
                )
            )
        if source in step_index and target in step_index:
            outgoing[source].append(edge)
            incoming[target].append(edge)

    for index, step in enumerate(steps):
        step_id = step.get("id")
        step_type = step.get("type")
        in_edges = incoming.get(step_id, [])
        out_edges = outgoing.get(step_id, [])

        if step_type == "start" and in_edges:
            issues.append(
                _issue("error", "start_has_incoming", "Start step cannot have incoming edges.", f"/steps/{index}")
            )
        if step_type != "start" and not in_edges:
            issues.append(
                _issue("error", "step_without_incoming", "Non-start step must have an incoming edge.", f"/steps/{index}")
            )
        if step_type == "end" and out_edges:
            issues.append(
                _issue("error", "end_has_outgoing", "End step cannot have outgoing edges.", f"/steps/{index}")
            )
        if step_type != "end" and not out_edges:
            issues.append(
                _issue("error", "step_without_outgoing", "Non-end step must have an outgoing edge.", f"/steps/{index}")
            )
        if step_type == "decision":
            if len(out_edges) < 2:
                issues.append(
                    _issue("error", "decision_without_branches", "Decision must have at least two outgoing branches.", f"/steps/{index}")
                )
            if any(edge.get("condition") is None for edge in out_edges):
                issues.append(
                    _issue("warning", "unconditional_decision_branch", "Every decision branch should have a condition.", f"/steps/{index}")
                )

    if len(starts) == 1:
        adjacency = {
            step_id: [edge["to"] for edge in outgoing.get(step_id, [])]
            for step_id in step_index
        }
        reachable = _reachable([starts[0]["id"]], adjacency)
        reverse = {
            step_id: [edge["from"] for edge in incoming.get(step_id, [])]
            for step_id in step_index
        }
        can_reach_end = _reachable([step["id"] for step in ends], reverse)

        for index, step in enumerate(steps):
            step_id = step.get("id")
            if step_id not in reachable:
                issues.append(
                    _issue("error", "unreachable_step", f"Step is unreachable from start: {step_id}.", f"/steps/{index}")
                )
            if step_id not in can_reach_end:
                issues.append(
                    _issue("error", "no_path_to_end", f"Step has no path to an end: {step_id}.", f"/steps/{index}")
                )

    for index, system in enumerate(process_ir.get("systems", [])):
        if system.get("integrationStatus") == "unknown":
            issues.append(
                _issue(
                    "warning",
                    "unknown_integration",
                    f"Integration details are unknown for {system.get('name', system.get('id'))}.",
                    f"/systems/{index}/integrationStatus",
                )
            )

    for index, exception in enumerate(process_ir.get("exceptions", [])):
        if exception.get("sourceStepId") not in step_index:
            issues.append(
                _issue(
                    "error",
                    "unknown_exception_source",
                    f"Unknown exception source: {exception.get('sourceStepId')}.",
                    f"/exceptions/{index}/sourceStepId",
                )
            )

    rule_ids = {item.get("id") for item in process_ir.get("businessRules", [])}
    state_ids = {item.get("id") for item in process_ir.get("states", [])}
    data_ids = set(indexes["dataObjects"])
    for index, rule in enumerate(process_ir.get("businessRules", [])):
        for step_id in rule.get("appliesToStepIds", []):
            if step_id not in step_index:
                issues.append(
                    _issue(
                        "error",
                        "unknown_rule_step",
                        f"Business rule references unknown step: {step_id}.",
                        f"/businessRules/{index}/appliesToStepIds",
                    )
                )
    for index, edge in enumerate(edges):
        for rule_id in edge.get("ruleIds", []):
            if rule_id not in rule_ids:
                issues.append(
                    _issue(
                        "error",
                        "unknown_edge_rule",
                        f"Edge references unknown business rule: {rule_id}.",
                        f"/edges/{index}/ruleIds",
                    )
                )
    for index, state in enumerate(process_ir.get("states", [])):
        if state.get("dataObjectId") not in data_ids:
            issues.append(
                _issue(
                    "error",
                    "unknown_state_data_object",
                    f"State references unknown data object: {state.get('dataObjectId')}.",
                    f"/states/{index}/dataObjectId",
                )
            )
    for index, transition in enumerate(process_ir.get("stateTransitions", [])):
        references = [transition.get("toStateId")]
        if transition.get("fromStateId"):
            references.append(transition["fromStateId"])
        if any(state_id not in state_ids for state_id in references):
            issues.append(
                _issue(
                    "error",
                    "unknown_transition_state",
                    "State transition references an unknown state.",
                    f"/stateTransitions/{index}",
                )
            )
        if transition.get("dataObjectId") not in data_ids:
            issues.append(
                _issue(
                    "error",
                    "unknown_transition_data_object",
                    f"State transition references unknown data object: {transition.get('dataObjectId')}.",
                    f"/stateTransitions/{index}/dataObjectId",
                )
            )
        for rule_id in transition.get("ruleIds", []):
            if rule_id not in rule_ids:
                issues.append(
                    _issue(
                        "error",
                        "unknown_transition_rule",
                        f"State transition references unknown business rule: {rule_id}.",
                        f"/stateTransitions/{index}/ruleIds",
                    )
                )

    target_collections = {
        "actor": "actors",
        "system": "systems",
        "dataObject": "dataObjects",
        "state": "states",
        "stateTransition": "stateTransitions",
        "businessRule": "businessRules",
        "step": "steps",
        "edge": "edges",
        "exception": "exceptions",
    }
    blocking_targets: set[str] = set()
    for index, question in enumerate(process_ir.get("openQuestions", [])):
        target = question.get("target", {})
        entity = target.get("entity")
        target_id = target.get("id")
        if question.get("blocksAutomationReady") and isinstance(target_id, str):
            blocking_targets.add(target_id)
        if entity in {"process", "passport"}:
            valid_target = target_id == process_ir.get("process", {}).get("id")
        else:
            collection = target_collections.get(entity)
            valid_target = bool(collection and target_id in indexes[collection])
        if not valid_target:
            issues.append(
                _issue(
                    "error",
                    "unknown_question_target",
                    f"Unknown {entity or 'question'} target: {target_id}.",
                    f"/openQuestions/{index}/target",
                )
            )

    for index, step in enumerate(steps):
        missing_fields = step.get("missingFields", [])
        if missing_fields and step.get("id") not in blocking_targets and step.get("systemId") not in blocking_targets:
            issues.append(
                _issue(
                    "warning",
                    "missing_field_without_question",
                    f"Missing fields are not covered by a blocking question: {', '.join(missing_fields)}.",
                    f"/steps/{index}/missingFields",
                )
            )

    blocking_questions = [
        question
        for question in process_ir.get("openQuestions", [])
        if question.get("blocksAutomationReady")
    ]
    automation_status = (
        process_ir.get("readiness", {})
        .get("categories", {})
        .get("automation", {})
        .get("status")
    )
    if blocking_questions and automation_status != "blocked":
        issues.append(
            _issue(
                "warning",
                "readiness_inconsistent",
                "Automation readiness should be blocked while blocking questions remain.",
                "/readiness/categories/automation/status",
            )
        )

    return issues


def validate_process_ir(process_ir: dict[str, Any]) -> ValidationResult:
    process_ir = upgrade_process_ir(process_ir)
    schema_issues = [
        _issue("error", "schema_validation", error.message, _pointer(error.absolute_path))
        for error in sorted(_schema_validator().iter_errors(process_ir), key=lambda item: list(item.absolute_path))
    ]
    issues = schema_issues
    if not schema_issues:
        issues.extend(_semantic_issues(process_ir))

    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    return ValidationResult(
        valid=errors == 0,
        counts=ValidationCounts(errors=errors, warnings=warnings),
        issues=issues,
    )
