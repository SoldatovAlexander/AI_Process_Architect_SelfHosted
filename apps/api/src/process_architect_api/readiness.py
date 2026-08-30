from typing import Any

from .models import (
    BlockingQuestionResponse,
    ReadinessCategoryResponse,
    ReadinessResponse,
)
from .validation import validate_process_ir
from .process_ir import upgrade_process_ir


CATEGORY_WEIGHTS = {
    "structure": 12,
    "passport": 10,
    "actors": 8,
    "systems": 8,
    "data": 8,
    "states": 8,
    "rules": 10,
    "branches": 8,
    "exceptions": 8,
    "governance": 10,
    "automation": 10,
}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
ENTITY_ORDER = {
    "process": 0,
    "passport": 1,
    "businessRule": 2,
    "state": 3,
    "stateTransition": 4,
    "edge": 5,
    "step": 6,
    "dataObject": 7,
    "system": 8,
    "exception": 9,
    "actor": 10,
}
SYSTEM_SCORES = {
    "configured": 100,
    "api_available": 90,
    "manual": 60,
    "unknown": 40,
    "not_supported": 20,
}


def _category(score: int, reasons: list[str], *, force_blocked: bool = False) -> ReadinessCategoryResponse:
    score = max(0, min(100, round(score)))
    if force_blocked or score < 50:
        status = "blocked"
    elif score < 85:
        status = "warning"
    else:
        status = "ok"
    return ReadinessCategoryResponse(score=score, status=status, reason_codes=reasons)


def _next_question(process_ir: dict[str, Any]) -> tuple[int, BlockingQuestionResponse | None]:
    blocking = [
        (index, item)
        for index, item in enumerate(process_ir.get("openQuestions", []))
        if item.get("blocksAutomationReady")
    ]
    blocking.sort(
        key=lambda pair: (
            PRIORITY_ORDER.get(pair[1].get("priority"), 3),
            ENTITY_ORDER.get(pair[1].get("target", {}).get("entity"), 9),
            pair[0],
        )
    )
    if not blocking:
        return 0, None
    question = blocking[0][1]
    target = question["target"]
    return len(blocking), BlockingQuestionResponse(
        id=question["id"],
        priority=question["priority"],
        target_entity=target["entity"],
        target_id=target["id"],
        question=question["question"],
    )


def calculate_readiness(process_ir: dict[str, Any], revision_id: str = "preview") -> ReadinessResponse:
    process_ir = upgrade_process_ir(process_ir)
    validation = validate_process_ir(process_ir)
    steps = process_ir.get("steps", [])
    content_steps = [step for step in steps if step.get("type") not in {"start", "end"}]
    if not content_steps:
        categories = {
            "structure": _category(
                30,
                ["process_steps_missing", *(["validation_errors"] if not validation.valid else [])],
                force_blocked=True,
            ),
            "passport": _category(0, ["passport_not_assessed"], force_blocked=True),
            "actors": _category(0, ["actors_not_assessed"], force_blocked=True),
            "systems": _category(0, ["systems_not_assessed"], force_blocked=True),
            "data": _category(0, ["data_not_assessed"], force_blocked=True),
            "states": _category(0, ["states_not_assessed"], force_blocked=True),
            "rules": _category(0, ["rules_not_assessed"], force_blocked=True),
            "branches": _category(0, ["branches_not_assessed"], force_blocked=True),
            "exceptions": _category(0, ["exceptions_not_assessed"], force_blocked=True),
            "governance": _category(0, ["governance_not_assessed"], force_blocked=True),
            "automation": _category(0, ["automation_steps_missing"], force_blocked=True),
        }
        overall = round(
            sum(categories[name].score * weight for name, weight in CATEGORY_WEIGHTS.items()) / 100
        )
        return ReadinessResponse(
            revision_id=revision_id,
            overall=overall,
            draft_ready=False,
            automation_ready=False,
            blocking_question_count=0,
            next_blocking_question=None,
            categories=categories,
        )
    systems = process_ir.get("systems", [])
    data_objects = process_ir.get("dataObjects", [])
    decisions = [step for step in steps if step.get("type") == "decision"]
    blocking_count, next_question = _next_question(process_ir)

    structure_reasons = []
    structure_score = 100
    if not validation.valid:
        structure_score = max(0, 100 - validation.counts.errors * 25)
        structure_reasons.append("validation_errors")
    if not process_ir.get("process", {}).get("description", "").strip():
        structure_score -= 15
        structure_reasons.append("process_description_missing")

    passport = process_ir.get("passport", {})
    passport_checks = {
        "process_goal_missing": bool(passport.get("goal", "").strip()),
        "process_owner_missing": bool(passport.get("ownerActorId")),
        "process_start_boundary_missing": bool(passport.get("startsWhen", "").strip()),
        "process_end_boundary_missing": bool(passport.get("endsWhen", "").strip()),
        "process_scope_missing": bool(passport.get("inScope") or passport.get("outOfScope")),
        "success_metrics_missing": bool(passport.get("successMetrics")),
    }
    passport_points = {
        "process_goal_missing": 25,
        "process_owner_missing": 25,
        "process_start_boundary_missing": 15,
        "process_end_boundary_missing": 15,
        "process_scope_missing": 10,
        "success_metrics_missing": 10,
    }
    passport_score = sum(
        passport_points[code] for code, complete in passport_checks.items() if complete
    )
    passport_reasons = [code for code, complete in passport_checks.items() if not complete]
    passport_blocked = not passport_checks["process_owner_missing"] or not passport_checks["process_goal_missing"]

    human_tasks = [step for step in steps if step.get("type") == "human_task"]
    unassigned = sum(not step.get("actorId") for step in human_tasks)
    actors_score = 100 if not human_tasks else 100 - round(100 * unassigned / len(human_tasks))
    actor_reasons = ["human_tasks_without_actor"] if unassigned else []
    if any(not actor.get("responsibilities") for actor in process_ir.get("actors", [])):
        actors_score -= 15
        actor_reasons.append("actor_responsibilities_missing")

    system_scores = [SYSTEM_SCORES.get(system.get("integrationStatus"), 40) for system in systems]
    systems_score = round(sum(system_scores) / len(system_scores)) if system_scores else 100
    system_reasons = []
    if any(system.get("integrationStatus") == "unknown" for system in systems):
        system_reasons.append("unknown_integrations")
    if any(system.get("integrationStatus") == "not_supported" for system in systems):
        system_reasons.append("unsupported_integrations")

    missing_fields = sum(len(step.get("missingFields", [])) for step in steps)
    unknown_fields = sum(
        field.get("type") == "unknown"
        for data_object in data_objects
        for field in data_object.get("fields", [])
    )
    data_score = 100 - min(60, missing_fields * 12) - min(30, unknown_fields * 10)
    data_reasons = []
    if missing_fields:
        data_reasons.append("step_fields_missing")
    if unknown_fields:
        data_reasons.append("data_types_unknown")

    states = process_ir.get("states", [])
    transitions = process_ir.get("stateTransitions", [])
    states_score = 100
    state_reasons = []
    if data_objects and not states:
        states_score = 60
        state_reasons.append("object_states_missing")
    elif states:
        if not any(state.get("initial") for state in states):
            states_score -= 30
            state_reasons.append("initial_state_missing")
        if not any(state.get("terminal") for state in states):
            states_score -= 30
            state_reasons.append("terminal_state_missing")
        if len(states) > 1 and not transitions:
            states_score -= 30
            state_reasons.append("state_transitions_missing")

    decision_edges = [
        edge
        for edge in process_ir.get("edges", [])
        if edge.get("from") in {step.get("id") for step in decisions}
    ]
    unconditional = sum(edge.get("condition") is None for edge in decision_edges)
    branches_score = 100 if not decision_edges else 100 - round(100 * unconditional / len(decision_edges))
    branch_reasons = ["decision_conditions_missing"] if unconditional else []

    rules = process_ir.get("businessRules", [])
    linked_rule_ids = {
        rule_id
        for edge in decision_edges
        for rule_id in edge.get("ruleIds", [])
    }
    decision_rule_coverage = (
        sum(bool(edge.get("ruleIds")) for edge in decision_edges) / len(decision_edges)
        if decision_edges
        else 1
    )
    rules_score = round(40 + 60 * decision_rule_coverage) if decisions else 100
    rule_reasons = []
    if decisions and not rules:
        rules_score = 20
        rule_reasons.append("business_rules_missing")
    elif decision_edges and decision_rule_coverage < 1:
        rule_reasons.append("decision_rules_not_linked")
    if any(not rule.get("source", "").strip() for rule in rules if rule.get("id") in linked_rule_ids):
        rules_score -= 20
        rule_reasons.append("rule_sources_missing")

    risky_steps = [step for step in steps if step.get("type") in {"system_task", "external_event"}]
    handled = {item.get("sourceStepId") for item in process_ir.get("exceptions", [])}
    covered = sum(step.get("id") in handled for step in risky_steps)
    exceptions_score = 100 if not risky_steps else 40 + round(60 * covered / len(risky_steps))
    exception_reasons = ["exception_paths_missing"] if covered < len(risky_steps) else []

    execution_policies = [step.get("execution", {}) for step in content_steps]
    ai_steps = [step for step in content_steps if step.get("execution", {}).get("performedBy") == "ai"]
    governance_score = 100
    governance_reasons = []
    if any(not policy for policy in execution_policies):
        governance_score -= 40
        governance_reasons.append("execution_policies_missing")
    unrestricted_ai = [step for step in ai_steps if not step.get("execution", {}).get("restrictions")]
    if unrestricted_ai:
        governance_score -= 30
        governance_reasons.append("ai_restrictions_missing")
    unsafe_autonomy = [
        step
        for step in ai_steps
        if step.get("execution", {}).get("autonomy") in {"supervised", "autonomous"}
        and not step.get("execution", {}).get("approvalRequired")
    ]
    if unsafe_autonomy:
        governance_score -= 40
        governance_reasons.append("ai_approval_gate_missing")

    actionable_steps = [step for step in steps if step.get("type") not in {"start", "end", "human_task"}]
    without_hint = sum(not step.get("automationHint") for step in actionable_steps)
    automation_score = 100
    automation_score -= min(30, missing_fields * 10)
    automation_score -= min(30, blocking_count * 15)
    automation_score -= min(20, sum(system.get("integrationStatus") in {"unknown", "not_supported"} for system in systems) * 10)
    if actionable_steps:
        automation_score -= round(20 * without_hint / len(actionable_steps))
    automation_reasons = []
    if blocking_count:
        automation_reasons.append("blocking_questions_open")
    if missing_fields:
        automation_reasons.append("automation_parameters_missing")
    if without_hint:
        automation_reasons.append("automation_hints_missing")

    categories = {
        "structure": _category(structure_score, structure_reasons, force_blocked=not validation.valid),
        "passport": _category(passport_score, passport_reasons, force_blocked=passport_blocked),
        "actors": _category(actors_score, actor_reasons),
        "systems": _category(systems_score, system_reasons),
        "data": _category(data_score, data_reasons),
        "states": _category(states_score, state_reasons),
        "rules": _category(rules_score, rule_reasons, force_blocked=bool(decisions and not rules)),
        "branches": _category(branches_score, branch_reasons),
        "exceptions": _category(exceptions_score, exception_reasons),
        "governance": _category(governance_score, governance_reasons, force_blocked=bool(unsafe_autonomy)),
        "automation": _category(automation_score, automation_reasons, force_blocked=blocking_count > 0),
    }
    overall = round(
        sum(categories[name].score * weight for name, weight in CATEGORY_WEIGHTS.items()) / 100
    )
    draft_ready = (
        validation.valid
        and blocking_count == 0
        and categories["automation"].score >= 85
        and all(category.status != "blocked" for category in categories.values())
    )
    return ReadinessResponse(
        revision_id=revision_id,
        overall=overall,
        draft_ready=draft_ready,
        automation_ready=draft_ready,
        blocking_question_count=blocking_count,
        next_blocking_question=next_question,
        categories=categories,
    )
