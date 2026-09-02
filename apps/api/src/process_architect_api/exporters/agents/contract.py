from __future__ import annotations

from typing import Any


SUPPORTED_AGENT_TARGETS = ("openclaw", "hermes", "langgraph", "crewai", "agno")
OPENCLAW_SUPPORTED_VERSIONS = ("2026.7.1", "2026.8.1", "2026.8.2")
# Keep the pre-2.0 line as the API fallback for existing compatibility gateways
# that cannot yet report the underlying OpenClaw version.
OPENCLAW_LEGACY_VERSION = "2026.7.1"


def _status(score: int) -> str:
    if score >= 85:
        return "ok"
    if score >= 50:
        return "warning"
    return "blocked"


def calculate_agent_readiness(process_ir: dict[str, Any]) -> dict[str, Any]:
    passport = process_ir.get("passport", {})
    steps = process_ir.get("steps", [])
    actionable = [step for step in steps if step.get("type") not in {"start", "end"}]
    automated = [
        step for step in actionable
        if step.get("execution", {}).get("performedBy") in {"ai", "system"}
    ]
    agent_steps = [
        step for step in actionable
        if step.get("execution", {}).get("performedBy") == "ai"
    ]
    systems = process_ir.get("systems", [])
    open_questions = [
        question for question in process_ir.get("openQuestions", [])
        if question.get("blocksAutomationReady", False)
    ]

    contract_checks = [passport.get("goal"), passport.get("startsWhen"), passport.get("endsWhen")]
    contract_score = round(100 * sum(bool(value) for value in contract_checks) / len(contract_checks))
    tools_score = 0 if not agent_steps else round(
        100 * sum(
            bool(step.get("systemId")) and bool(step.get("operation", {}).get("name"))
            for step in agent_steps
        ) / len(agent_steps)
    )
    autonomy_score = 0 if not agent_steps else round(
        100 * sum(
            bool(step.get("execution", {}).get("restrictions"))
            or step.get("execution", {}).get("approvalRequired", False)
            or step.get("execution", {}).get("autonomy") in {"manual", "assist"}
            for step in agent_steps
        ) / len(agent_steps)
    )
    data_score = 0 if not agent_steps else round(
        100 * sum(bool(step.get("inputs") or step.get("outputs")) for step in agent_steps)
        / len(agent_steps)
    )
    reliability_score = min(
        100,
        (50 if process_ir.get("exceptions") else 0)
        + (50 if any(step.get("type") == "decision" for step in steps) else 0),
    )
    governance_score = (
        (50 if passport.get("ownerActorId") else 0)
        + (50 if agent_steps and all(
            step.get("execution", {}).get("approvalRequired")
            or step.get("execution", {}).get("autonomy") in {"manual", "assist"}
            for step in agent_steps
        ) else 0)
    )
    knowledge_score = 0 if not agent_steps else round(
        100 * sum(bool((step.get("agentConfig") or {}).get("knowledgeSources")) for step in agent_steps)
        / len(agent_steps)
    )
    control_score = 0 if not agent_steps else round(
        100 * sum(
            bool((step.get("agentConfig") or {}).get("stopConditions"))
            and bool((step.get("agentConfig") or {}).get("auditEvents"))
            and all((step.get("agentConfig") or {}).get("escalation", {}).get(key) for key in ("missingSource", "conflictingSources", "lowConfidence", "riskyAction"))
            for step in agent_steps
        ) / len(agent_steps)
    )
    categories = {
        "contract": contract_score,
        "tools": tools_score,
        "autonomy": autonomy_score,
        "data": data_score,
        "reliability": reliability_score,
        "governance": governance_score,
        "knowledge": knowledge_score,
        "control": control_score,
    }
    overall = round(sum(categories.values()) / len(categories))
    blockers: list[str] = []
    if not agent_steps:
        blockers.append("agent_role_not_defined")
    if contract_score < 100:
        blockers.append("process_contract_incomplete")
    if tools_score < 100:
        blockers.append("tool_mapping_incomplete")
    if autonomy_score < 100:
        blockers.append("agent_guardrails_incomplete")
    if reliability_score < 50:
        blockers.append("failure_handling_missing")
    if governance_score < 50:
        blockers.append("process_owner_missing")
    if knowledge_score < 100:
        blockers.append("knowledge_source_missing")
    if control_score < 100:
        blockers.append("agent_controls_incomplete")
    if open_questions:
        blockers.append("blocking_questions_open")
    return {
        "scope": "agent_deployment",
        "overall": overall,
        "agentReady": overall >= 85 and not blockers,
        "blockers": blockers,
        "blockingQuestionCount": len(open_questions),
        "categories": {
            key: {"score": score, "status": _status(score), "reason_codes": []}
            for key, score in categories.items()
        },
    }


def build_agent_contract(process_ir: dict[str, Any]) -> dict[str, Any]:
    actors = {item["id"]: item for item in process_ir.get("actors", [])}
    systems = {item["id"]: item for item in process_ir.get("systems", [])}
    data_objects = {item["id"]: item for item in process_ir.get("dataObjects", [])}
    passport = process_ir.get("passport", {})
    tasks = []
    for step in process_ir.get("steps", []):
        execution = step.get("execution", {})
        tasks.append({
            "id": step["id"],
            "type": step.get("type"),
            "title": step.get("title", ""),
            "description": step.get("description", ""),
            "responsible": actors.get(step.get("actorId"), {}).get("name"),
            "tool": systems.get(step.get("systemId"), {}).get("name"),
            "operation": step.get("operation", {}),
            "inputs": [data_objects.get(item, {"id": item}).get("name", item) for item in step.get("inputs", [])],
            "outputs": [data_objects.get(item, {"id": item}).get("name", item) for item in step.get("outputs", [])],
            "execution": {
                "performedBy": execution.get("performedBy", "human"),
                "autonomy": execution.get("autonomy", "manual"),
                "approvalRequired": execution.get("approvalRequired", False),
                "restrictions": execution.get("restrictions", []),
            },
        })
    agent_tasks = [task for task in tasks if task["execution"]["performedBy"] == "ai"]
    agents = []
    for task in agent_tasks:
        source_step = next(step for step in process_ir.get("steps", []) if step["id"] == task["id"])
        agent_config = source_step.get("agentConfig") or {}
        agents.append({
            "id": f"agent_{task['id']}",
            "name": f"{task['title']} Agent",
            "role": task["title"],
            "primaryGoal": task["description"] or task["title"],
            "trigger": f"Workflow reaches task {task['id']}",
            "allowedStates": agent_config.get("allowedStateIds", []),
            "resultRecipient": task["responsible"] or "process workflow",
            "completionCondition": f"Structured result for task {task['id']} passes backend validation",
            "inputs": task["inputs"],
            "outputs": task["outputs"],
            "knowledgeSources": agent_config.get("knowledgeSources", []),
            "allowedTools": [task["tool"]] if task["tool"] else [],
            "prohibitedActions": [
                "change process state directly",
                "invent business rules or sources",
                "perform actions outside this contract",
                *task["execution"]["restrictions"],
            ],
            "approvalRequired": task["execution"]["approvalRequired"],
            "stopConditions": agent_config.get("stopConditions", ["required input or tool is unavailable", "human approval is denied"]),
            "auditEvents": agent_config.get("auditEvents", ["tool_call", "human_review", "escalation", "error"]),
            "escalation": agent_config.get("escalation", {
                "missingSource": "process owner",
                "conflictingSources": "process owner",
                "lowConfidence": "human reviewer",
                "riskyAction": "human reviewer",
            }),
            "inputSchema": {
                "type": "object",
                "required": ["workflow_id", "process_state", "input_refs"],
                "properties": {
                    "workflow_id": {"type": "string"},
                    "process_state": {"type": "string"},
                    "input_refs": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "required": ["result", "source_ids", "confidence", "risk_flags", "escalation_required"],
                "properties": {
                    "result": {"type": "object"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "risk_flags": {"type": "array", "items": {"type": "string"}},
                    "escalation_required": {"type": "boolean"},
                    "escalation_reason": {"type": "string"},
                },
                "additionalProperties": False,
            },
        })
    distinct_tools = {task["tool"] for task in agent_tasks if task["tool"]}
    multi_agent_candidate = len(agent_tasks) > 1 and len(distinct_tools) > 1
    architecture_reasons = [
        f"{len(agent_tasks)} AI task(s) are explicitly defined.",
        f"{len(distinct_tools)} distinct mapped tool boundary/boundaries are present.",
        "Workflow/backend remains the owner of business state and sequence.",
    ]
    if multi_agent_candidate:
        architecture_reasons.append(
            "Distinct tasks and tool boundaries justify reviewing separate roles, permissions, and handoffs."
        )
    else:
        architecture_reasons.append(
            "No confirmed process reason currently outweighs the cost and risk of multiple agents."
        )
    return {
        "contractVersion": "1.1",
        "methodology": "Processes for People and AI",
        "process": {
            "id": process_ir["process"]["id"],
            "name": process_ir["process"]["name"],
            "purpose": passport.get("goal") or process_ir["process"].get("description", ""),
            "startsWhen": passport.get("startsWhen", ""),
            "completesWhen": passport.get("endsWhen", ""),
            "owner": actors.get(passport.get("ownerActorId"), {}).get("name"),
            "successMetrics": passport.get("successMetrics", []),
        },
        "tasks": tasks,
        "agents": agents,
        "flow": process_ir.get("edges", []),
        "businessRules": process_ir.get("businessRules", []),
        "exceptions": process_ir.get("exceptions", []),
        "tools": [
            {
                "id": system["id"],
                "name": system["name"],
                "type": system.get("type"),
                "integrationStatus": system.get("integrationStatus"),
                "notes": system.get("notes", ""),
                "credentials": "environment_only",
            }
            for system in systems.values()
        ],
        "policy": {
            "defaultAutonomy": "supervised",
            "denyByDefault": True,
            "secrets": "environment_only",
            "audit": "log tool calls, approvals, results, and failures",
            "humanApprovalTasks": [
                task["id"] for task in tasks if task["execution"]["approvalRequired"]
            ],
        },
        "orchestration": {
            "recommendedPattern": "multi_agent_review_required" if multi_agent_candidate else "single_agent",
            "stateOwner": "workflow_or_backend",
            "sequenceOwner": "workflow_or_orchestrator",
            "agentMayChangeStateDirectly": False,
            "multiAgentJustificationRequired": multi_agent_candidate,
        },
        "architectureDecision": {
            "decisionVersion": "1",
            "status": "review_required" if multi_agent_candidate else "proposed",
            "selectedTopology": "single_agent",
            "recommendedTopology": "multi_agent" if multi_agent_candidate else "single_agent",
            "activationPolicy": "explicit_human_approval",
            "reasons": architecture_reasons,
            "multiAgentCriteria": [
                "distinct competencies",
                "different permissions",
                "independent review",
                "parallel work with structured merge",
            ],
            "handoffContract": "contracts/inter-agent-message.schema.json",
        },
        "protocolBoundaries": {
            "toolsAndData": "MCP or direct API after boundary review",
            "independentAgents": "A2A only when independent agents are justified",
            "userInterface": "AG-UI or application event stream when intervention is required",
            "developmentAgent": "ACP or native client integration when relevant",
            "businessState": "workflow/backend API, never agent conversation",
        },
        "observability": {
            "identifiers": ["request_id", "agent_run_id", "workflow_id", "user_id", "trace_id"],
            "events": sorted({event for agent in agents for event in agent["auditEvents"]} | {"agent_started"}),
            "versions": ["agent_contract", "system_instruction", "model", "rules", "knowledge_base", "tool_schema"],
        },
        "openQuestions": process_ir.get("openQuestions", []),
        "readiness": calculate_agent_readiness(process_ir),
    }
