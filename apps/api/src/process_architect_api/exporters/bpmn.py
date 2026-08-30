from collections import defaultdict, deque
from typing import Any
from xml.etree import ElementTree as ET


NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


ELEMENTS = {
    "start": "startEvent",
    "end": "endEvent",
    "human_task": "userTask",
    "system_task": "serviceTask",
    "decision": "exclusiveGateway",
    "timer": "intermediateCatchEvent",
    "external_event": "intermediateCatchEvent",
}


def _q(namespace: str, tag: str) -> str:
    return f"{{{NS[namespace]}}}{tag}"


def _condition_text(condition: dict[str, Any]) -> str:
    return f"{condition['left']} {condition['operator']} {condition['right']}"


def _positions(process_ir: dict[str, Any]) -> dict[str, tuple[int, int]]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming_count = {step["id"]: 0 for step in process_ir["steps"]}
    for edge in process_ir["edges"]:
        outgoing[edge["from"]].append(edge["to"])
        incoming_count[edge["to"]] += 1
    starts = [step["id"] for step in process_ir["steps"] if step["type"] == "start"]
    depth = {step_id: 0 for step_id in starts}
    queue = deque(starts)
    while queue:
        source = queue.popleft()
        for target in outgoing[source]:
            if target not in depth:
                depth[target] = depth[source] + 1
                queue.append(target)
    rows: dict[int, int] = defaultdict(int)
    result = {}
    for step in process_ir["steps"]:
        column = depth.get(step["id"], 0)
        row = rows[column]
        rows[column] += 1
        result[step["id"]] = (100 + column * 220, 100 + row * 140)
    return result


def generate_bpmn(process_ir: dict[str, Any]) -> str:
    process_id = process_ir["process"]["id"]
    definitions = ET.Element(
        _q("bpmn", "definitions"),
        {
            "id": f"definitions_{process_id}",
            "targetNamespace": "https://ai-process-architect.local/bpmn",
        },
    )
    process = ET.SubElement(
        definitions,
        _q("bpmn", "process"),
        {"id": process_id, "name": process_ir["process"]["name"], "isExecutable": "false"},
    )
    for step in process_ir["steps"]:
        element = ET.SubElement(
            process,
            _q("bpmn", ELEMENTS[step["type"]]),
            {"id": step["id"], "name": step["title"]},
        )
        documentation = ET.SubElement(element, _q("bpmn", "documentation"))
        documentation.text = step["description"]
        if step["type"] == "timer":
            ET.SubElement(element, _q("bpmn", "timerEventDefinition"))
        if step["type"] == "external_event":
            ET.SubElement(element, _q("bpmn", "messageEventDefinition"))

    for edge in process_ir["edges"]:
        sequence = ET.SubElement(
            process,
            _q("bpmn", "sequenceFlow"),
            {"id": edge["id"], "sourceRef": edge["from"], "targetRef": edge["to"]},
        )
        if edge["condition"]:
            expression = ET.SubElement(
                sequence,
                _q("bpmn", "conditionExpression"),
                {_q("xsi", "type"): "bpmn:tFormalExpression"},
            )
            expression.text = _condition_text(edge["condition"])

    positions = _positions(process_ir)
    diagram = ET.SubElement(definitions, _q("bpmndi", "BPMNDiagram"), {"id": f"diagram_{process_id}"})
    plane = ET.SubElement(
        diagram,
        _q("bpmndi", "BPMNPlane"),
        {"id": f"plane_{process_id}", "bpmnElement": process_id},
    )
    for step in process_ir["steps"]:
        x, y = positions[step["id"]]
        shape = ET.SubElement(
            plane,
            _q("bpmndi", "BPMNShape"),
            {"id": f"shape_{step['id']}", "bpmnElement": step["id"]},
        )
        is_event = step["type"] in {"start", "end", "timer", "external_event"}
        width, height = (44, 44) if is_event else (140, 80)
        ET.SubElement(
            shape,
            _q("dc", "Bounds"),
            {"x": str(x), "y": str(y), "width": str(width), "height": str(height)},
        )
    for edge in process_ir["edges"]:
        source_x, source_y = positions[edge["from"]]
        target_x, target_y = positions[edge["to"]]
        diagram_edge = ET.SubElement(
            plane,
            _q("bpmndi", "BPMNEdge"),
            {"id": f"diagram_{edge['id']}", "bpmnElement": edge["id"]},
        )
        ET.SubElement(diagram_edge, _q("di", "waypoint"), {"x": str(source_x + 140), "y": str(source_y + 40)})
        ET.SubElement(diagram_edge, _q("di", "waypoint"), {"x": str(target_x), "y": str(target_y + 40)})

    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", xml_declaration=True) + "\n"
