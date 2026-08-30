from typing import Any


def generate_resource_spec(
    process_ir: dict[str, Any],
    system_id: str,
    target_minor: str,
) -> str:
    system = next(item for item in process_ir["systems"] if item["id"] == system_id)
    steps = [step for step in process_ir["steps"] if step.get("systemId") == system_id]
    step_ids = {step["id"] for step in steps}
    data = {item["id"]: item for item in process_ir["dataObjects"]}
    questions = [
        item
        for item in process_ir["openQuestions"]
        if item["target"]["id"] == system_id or item["target"]["id"] in step_ids
    ]
    exceptions = [item for item in process_ir["exceptions"] if item["sourceStepId"] in step_ids]
    lines = [
        f"# {system['name']} - Resource Specification",
        "",
        f"- Resource ID: `{system['id']}`",
        f"- Type: `{system['type']}`",
        f"- Integration status: `{system['integrationStatus']}`",
        f"- n8n target: `{target_minor}`",
        f"- Credential placeholder: `credential_{system['id']}`",
        "",
        "## Purpose",
        "",
        system["notes"] or "Purpose must be confirmed during implementation.",
        "",
        "## Operations",
        "",
    ]
    if not steps:
        lines.append("No Process IR step directly references this resource.")
    for step in steps:
        hint = step.get("automationHint") or {}
        lines.extend(
            [
                f"### {step['title']}",
                "",
                f"- Step ID: `{step['id']}`",
                f"- Operation: `{step['operation']['kind']}:{step['operation']['name']}`",
                f"- n8n node: `{hint.get('nodeType', 'not_mapped')}`",
                f"- Missing configuration: {', '.join(step['missingFields']) or 'None'}",
                f"- Inputs: {', '.join(data[item]['name'] for item in step['inputs']) or 'None'}",
                f"- Outputs: {', '.join(data[item]['name'] for item in step['outputs']) or 'None'}",
                "",
            ]
        )
    lines.extend(["## Data Fields", ""])
    used_data_ids = {item for step in steps for item in [*step["inputs"], *step["outputs"]]}
    if not used_data_ids:
        lines.append("No structured data mapping is defined.")
    for data_id in sorted(used_data_ids):
        item = data[data_id]
        lines.extend([f"### {item['name']}", "", "| Field | Type | Required | Source |", "| --- | --- | --- | --- |"])
        lines.extend(
            f"| {field['name']} | {field['type']} | {'yes' if field['required'] else 'no'} | {field['source']} |"
            for field in item["fields"]
        )
        lines.append("")
    lines.extend(["## Failure Handling", ""])
    lines.extend(
        f"- `{item['sourceStepId']}`: {item['trigger']} -> {item['handling']}"
        for item in exceptions
    )
    if not exceptions:
        lines.append("No failure handling is defined for this resource.")
    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- **{item['priority']}:** {item['question']}" for item in questions)
    if not questions:
        lines.append("No resource-specific open questions.")
    lines.extend(
        [
            "",
            "## Authentication",
            "",
            "Authentication method and credential ownership must be confirmed. Store only a credential reference in the workflow; never place secret values in Process IR or this specification.",
        ]
    )
    return "\n".join(lines).strip() + "\n"
