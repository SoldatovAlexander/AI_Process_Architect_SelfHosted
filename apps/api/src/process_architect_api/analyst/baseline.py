import re
from copy import deepcopy
from functools import lru_cache
from typing import Any

from ..paths import WORKSPACE_ROOT
from ..process_ir import upgrade_process_ir


SCENARIOS = {
    "lead-intake": ["lead", "лид", "заявк", "crm", "срм", "продаж", "клиент"],
    "support-ticket": ["support", "поддерж", "ticket", "тикет", "обращен", "helpdesk", "инцидент"],
    "invoice-approval": ["invoice", "счет", "счёт", "оплат", "erp", "согласован", "бухгалтер", "поставщик"],
}

SYSTEM_SIGNALS = [
    ("system_crm", "amoCRM", r"\bamo\s*crm\b|\bамосрм\b"),
    ("system_crm", "Bitrix24", r"\bbitrix\s*24\b|\bбитрикс\s*24\b"),
    ("system_crm", "HubSpot", r"\bhubspot\b"),
    ("system_helpdesk", "Zendesk", r"\bzendesk\b"),
    ("system_helpdesk", "Jira Service Management", r"\bjira(?:\s+service\s+management)?\b"),
    ("system_helpdesk", "Freshdesk", r"\bfreshdesk\b"),
    ("system_erp", "1C", r"(?:\b1c\b|1с(?=\W|$))"),
    ("system_erp", "SAP", r"\bsap\b"),
    ("system_erp", "Dynamics 365", r"\bdynamics\s*365\b"),
    ("system_telegram", "Telegram", r"\btelegram\b|\bтелеграм\w*"),
    ("system_messenger", "Telegram", r"\btelegram\b|\bтелеграм\w*"),
    ("system_messenger", "Slack", r"\bslack\b"),
    ("system_messenger", "Microsoft Teams", r"\bmicrosoft\s+teams\b|\bteams\b"),
]

BLUEPRINT_FILES = {
    "lead-intake": "lead-intake.process-ir.json",
    "support-ticket": "support-ticket.process-ir.json",
    "invoice-approval": "invoice-approval.process-ir.json",
}


@lru_cache
def load_blueprints() -> dict[str, dict[str, Any]]:
    import json

    examples = WORKSPACE_ROOT / "02_architecture" / "examples"
    return {
        scenario_id: json.loads((examples / filename).read_text(encoding="utf-8"))
        for scenario_id, filename in BLUEPRINT_FILES.items()
    }


def _classify(text: str) -> dict[str, Any]:
    normalized = text.casefold()
    ranking = [
        {
            "id": scenario_id,
            "score": len(matches := [signal for signal in signals if signal in normalized]),
            "matchedSignals": matches,
        }
        for scenario_id, signals in SCENARIOS.items()
    ]
    ranking.sort(key=lambda item: item["score"], reverse=True)
    best = ranking[0]
    if best["score"] == 0:
        raise ValueError(
            "Process type is not recognized. Mention leads/CRM, support tickets, or invoice approval."
        )
    if ranking[1]["score"] == best["score"]:
        raise ValueError(
            f"Process type is ambiguous between {best['id']} and {ranking[1]['id']}."
        )
    total = sum(item["score"] for item in ranking)
    return {
        "scenarioId": best["id"],
        "confidence": round(best["score"] / total, 2),
        "matchedSignals": best["matchedSignals"],
        "ranking": [{"id": item["id"], "score": item["score"]} for item in ranking],
    }


def _apply_systems(process_ir: dict[str, Any], text: str) -> list[dict[str, str]]:
    detected: list[dict[str, str]] = []
    for system_id, name, pattern in SYSTEM_SIGNALS:
        if not re.search(pattern, text, flags=re.IGNORECASE):
            continue
        system = next(
            (candidate for candidate in process_ir["systems"] if candidate["id"] == system_id),
            None,
        )
        if system is None:
            continue
        system["name"] = name
        system["notes"] = (
            f"{name} was detected in the source description. "
            "Integration method and credentials must be confirmed."
        )
        detected.append({"systemId": system_id, "name": name})
    return detected


def _apply_lead_threshold(process_ir: dict[str, Any], text: str) -> int | None:
    match = re.search(r"(?:score|оценк\w*|балл\w*)\D{0,16}(\d{1,3})", text, re.IGNORECASE)
    if not match or not 1 <= (threshold := int(match.group(1))) <= 100:
        return None
    for step in process_ir["steps"]:
        if step["operation"]["name"] == "lead_scoring":
            step["operation"]["parameters"]["threshold"] = threshold
    for edge in process_ir["edges"]:
        if edge["from"] == "step_quality_gate" and edge["condition"]:
            edge["condition"]["right"] = threshold
    return threshold


def extract_process_ir(text: str) -> dict[str, Any]:
    source_text = text.strip()
    if len(source_text) < 20:
        raise ValueError("Process description must contain at least 20 characters.")
    analysis = _classify(source_text)
    process_ir = upgrade_process_ir(deepcopy(load_blueprints()[analysis["scenarioId"]]))
    process_ir["process"]["description"] = source_text
    process_ir["process"]["maturity"] = "draft"
    process_ir["readiness"]["overall"] = min(process_ir["readiness"]["overall"], 50)
    automation = process_ir["readiness"]["categories"]["automation"]
    automation["status"] = "blocked"
    automation["score"] = min(automation["score"], 40)
    automation["notes"].append("Generated draft requires analyst confirmation.")

    analysis["strategy"] = "blueprint-baseline"
    analysis["detectedSystems"] = _apply_systems(process_ir, source_text)
    analysis["detectedThreshold"] = (
        _apply_lead_threshold(process_ir, source_text)
        if analysis["scenarioId"] == "lead-intake"
        else None
    )
    return {"process_ir": process_ir, "analysis": analysis}
