from typing import Any

from ..models import ValidationResult
from ..process_ir import upgrade_process_ir


def _cell(value: Any) -> str:
    return str(value if value not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")


def _list(values: list[str]) -> str:
    return ", ".join(values) if values else "None"


def generate_spec(process_ir: dict[str, Any], validation: ValidationResult) -> str:
    process_ir = upgrade_process_ir(process_ir)
    actors = {item["id"]: item["name"] for item in process_ir["actors"]}
    systems = {item["id"]: item["name"] for item in process_ir["systems"]}
    data_names = {item["id"]: item["name"] for item in process_ir["dataObjects"]}
    step_names = {item["id"]: item["title"] for item in process_ir["steps"]}
    process = process_ir["process"]
    lines = [
        f"# {process['name']} - Implementation Spec",
        "",
        f"> Generated from Process IR {process_ir['schemaVersion']}. Structural validation: "
        f"{'passed' if validation.valid else 'failed'} "
        f"({validation.counts.errors} errors, {validation.counts.warnings} warnings).",
        "",
        "## Overview",
        "",
        process["description"] or "No description provided.",
        "",
        f"- Process ID: `{process['id']}`",
        f"- Domain: `{process['domain']}`",
        f"- Maturity: `{process['maturity']}`",
        f"- Readiness: {process_ir['readiness']['overall']}/100",
        "",
        "## Process Passport",
        "",
        f"- Goal: {process_ir['passport']['goal'] or '-'}",
        f"- Process owner: {actors.get(process_ir['passport']['ownerActorId'], '-')}",
        f"- Starts when: {process_ir['passport']['startsWhen'] or '-'}",
        f"- Ends when: {process_ir['passport']['endsWhen'] or '-'}",
        f"- In scope: {_list(process_ir['passport']['inScope'])}",
        f"- Out of scope: {_list(process_ir['passport']['outOfScope'])}",
        "",
        "## Actors",
        "",
        "| Actor | Type | Responsibilities |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {_cell(actor['name'])} | {_cell(actor['type'])} | {_cell(_list(actor['responsibilities']))} |"
        for actor in process_ir["actors"]
    )
    lines.extend(["", "## Systems", "", "| System | Type | Integration | Notes |", "| --- | --- | --- | --- |"])
    lines.extend(
        f"| {_cell(system['name'])} | {_cell(system['type'])} | {_cell(system['integrationStatus'])} | {_cell(system['notes'])} |"
        for system in process_ir["systems"]
    )
    lines.extend([
        "",
        "## Process Steps",
        "",
        "| Step | Type | Owner / System | Performed by | Autonomy | Approval | Inputs | Outputs | Operation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for step in process_ir["steps"]:
        owner = actors.get(step["actorId"]) or systems.get(step["systemId"]) or "-"
        inputs = [data_names.get(item, item) for item in step["inputs"]]
        outputs = [data_names.get(item, item) for item in step["outputs"]]
        operation = f"{step['operation']['kind']}: {step['operation']['name']}"
        execution = step["execution"]
        lines.append(
            f"| {_cell(step['title'])} | {_cell(step['type'])} | {_cell(owner)} | "
            f"{_cell(execution['performedBy'])} | {_cell(execution['autonomy'])} | "
            f"{'yes' if execution['approvalRequired'] else 'no'} | {_cell(_list(inputs))} | "
            f"{_cell(_list(outputs))} | {_cell(operation)} |"
        )
    lines.extend(["", "## Flow", ""])
    for edge in process_ir["edges"]:
        condition = "always"
        if edge["condition"]:
            item = edge["condition"]
            condition = f"{item['left']} {item['operator']} {item['right']}"
        lines.append(f"- {step_names[edge['from']]} -> {step_names[edge['to']]} ({condition})")
    lines.extend(["", "## Data", ""])
    for data_object in process_ir["dataObjects"]:
        lines.extend(
            [
                f"### {data_object['name']}",
                "",
                "| Field | Type | Required | Source |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {_cell(field['name'])} | {_cell(field['type'])} | "
            f"{'yes' if field['required'] else 'no'} | {_cell(field['source'])} |"
            for field in data_object["fields"]
        )
        lines.append("")
    lines.extend(["## States And Lifecycle", "", "| State | Data object | Initial | Terminal |", "| --- | --- | --- | --- |"])
    lines.extend(
        f"| {_cell(state['name'])} | {_cell(data_names.get(state['dataObjectId'], state['dataObjectId']))} | "
        f"{'yes' if state['initial'] else 'no'} | {'yes' if state['terminal'] else 'no'} |"
        for state in process_ir["states"]
    )
    if not process_ir["states"]:
        lines.append("| Not specified | - | - | - |")
    lines.extend(["", "## Business Rules", "", "| ID | Rule | Type | Source | Applies to |", "| --- | --- | --- | --- | --- |"])
    lines.extend(
        f"| `{rule['id']}` | {_cell(rule['name'])}: {_cell(rule['description'])} | {_cell(rule['type'])} | "
        f"{_cell(rule['source'])} | {_cell(_list([step_names.get(item, item) for item in rule['appliesToStepIds']]))} |"
        for rule in process_ir["businessRules"]
    )
    if not process_ir["businessRules"]:
        lines.append("| - | Not specified | - | - | - |")
    lines.extend(["", "## Human, System And AI Boundaries", ""])
    for step in process_ir["steps"]:
        execution = step["execution"]
        lines.append(
            f"- **{step['title']}**: {execution['performedBy']} / {execution['autonomy']}; "
            f"approval={'required' if execution['approvalRequired'] else 'not required'}; "
            f"restrictions={_list(execution['restrictions'])}."
        )
    lines.extend(["", "## Exception Handling", ""])
    if process_ir["exceptions"]:
        lines.extend(
            f"- **{step_names[item['sourceStepId']]}:** {item['trigger']} -> {item['handling']}"
            for item in process_ir["exceptions"]
        )
    else:
        lines.append("No exception handling defined.")
    lines.extend(["", "## Open Questions", ""])
    if process_ir["openQuestions"]:
        for question in process_ir["openQuestions"]:
            blocking = "blocks automation" if question["blocksAutomationReady"] else "non-blocking"
            lines.append(
                f"- **{question['priority']}:** {question['question']} "
                f"({blocking}; {question['target']['entity']}: `{question['target']['id']}`)"
            )
    else:
        lines.append("No open questions.")
    lines.extend(["", "## Readiness", "", "| Category | Score | Status | Notes |", "| --- | ---: | --- | --- |"])
    for category, readiness in process_ir["readiness"]["categories"].items():
        lines.append(
            f"| {_cell(category)} | {readiness['score']} | {_cell(readiness['status'])} | "
            f"{_cell(_list(readiness['notes']))} |"
        )
    if validation.issues:
        lines.extend(["", "## Validation Findings", ""])
        lines.extend(
            f"- **{item.severity}:** {item.message} (`{item.path}`, `{item.code}`)"
            for item in validation.issues
        )
    return "\n".join(lines).strip() + "\n"
