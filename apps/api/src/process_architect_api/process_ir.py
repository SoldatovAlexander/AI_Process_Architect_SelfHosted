from copy import deepcopy
from typing import Any


CURRENT_SCHEMA_VERSION = "0.2"


def _execution_for_step(step: dict[str, Any]) -> dict[str, Any]:
    step_type = step.get("type")
    operation_kind = step.get("operation", {}).get("kind")
    if operation_kind == "ai_task":
        performed_by = "ai"
        autonomy = "assist"
        approval_required = True
    elif step_type == "human_task" or (
        step_type == "decision" and step.get("actorId") and not step.get("systemId")
    ):
        performed_by = "human"
        autonomy = "manual"
        approval_required = False
    elif step_type in {"system_task", "decision"}:
        performed_by = "system"
        autonomy = "autonomous"
        approval_required = False
    else:
        performed_by = "system"
        autonomy = "manual"
        approval_required = False
    return {
        "performedBy": performed_by,
        "autonomy": autonomy,
        "approvalRequired": approval_required,
        "restrictions": [],
    }


def _rule_id(edge_id: str, used: set[str]) -> str:
    base = f"rule_{edge_id.removeprefix('edge_')}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def upgrade_process_ir(process_ir: dict[str, Any]) -> dict[str, Any]:
    """Return a v0.2 view without mutating an immutable stored revision."""
    upgraded = deepcopy(process_ir)
    if upgraded.get("schemaVersion") != "0.1":
        return upgraded
    process_value = upgraded.get("process", {})
    actors_value = upgraded.get("actors", [])
    steps_value = upgraded.get("steps", [])
    edges_value = upgraded.get("edges", [])
    process = process_value if isinstance(process_value, dict) else {}
    actors = actors_value if isinstance(actors_value, list) else []
    steps = steps_value if isinstance(steps_value, list) else []
    edges = edges_value if isinstance(edges_value, list) else []

    owner = next(
        (
            actor.get("id")
            for actor in actors
            if isinstance(actor, dict) and actor.get("type") in {"human", "team"}
        ),
        None,
    )
    starts = [
        step.get("title", "")
        for step in steps
        if isinstance(step, dict) and step.get("type") == "start"
    ]
    ends = [
        step.get("title", "")
        for step in steps
        if isinstance(step, dict) and step.get("type") == "end"
    ]
    upgraded.setdefault(
        "passport",
        {
            "goal": process.get("description", ""),
            "ownerActorId": owner,
            "startsWhen": starts[0] if starts else "",
            "endsWhen": "; ".join(item for item in ends if item),
            "inScope": [],
            "outOfScope": [],
            "successMetrics": [],
        },
    )
    upgraded.setdefault("states", [])
    upgraded.setdefault("stateTransitions", [])
    rules_value = upgraded.setdefault("businessRules", [])
    rules = rules_value if isinstance(rules_value, list) else []
    used_rule_ids = {
        item.get("id") for item in rules if isinstance(item, dict)
    }

    for step in steps:
        if not isinstance(step, dict):
            continue
        step.setdefault("execution", _execution_for_step(step))

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        rule_ids = edge.setdefault("ruleIds", [])
        condition = edge.get("condition")
        if not isinstance(rule_ids, list) or not isinstance(condition, dict) or rule_ids:
            continue
        edge_id = edge.get("id")
        rule_id = _rule_id(edge_id if isinstance(edge_id, str) else "condition", used_rule_ids)
        rule_ids.append(rule_id)
        rules.append(
            {
                "id": rule_id,
                "name": f"Condition for {edge.get('from', 'process step')}",
                "description": (
                    f"{condition.get('left')} {condition.get('operator')} "
                    f"{condition.get('right')}"
                ),
                "type": "deterministic",
                "source": "Process interview",
                "appliesToStepIds": [edge.get("from")],
            }
        )

    upgraded["schemaVersion"] = CURRENT_SCHEMA_VERSION
    return upgraded
