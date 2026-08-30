from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET


NODE_STYLES = {
    "start": "ellipse;aspect=fixed;whiteSpace=wrap;html=1;fillColor=#e8f5e9;strokeColor=#438269;",
    "end": "ellipse;aspect=fixed;whiteSpace=wrap;html=1;fillColor=#e8f5e9;strokeColor=#438269;strokeWidth=3;",
    "human_task": "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#f4eff9;strokeColor=#795b9b;",
    "system_task": "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#e8f4f8;strokeColor=#2785a1;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#fff4e6;strokeColor=#a86420;",
    "timer": "ellipse;aspect=fixed;whiteSpace=wrap;html=1;fillColor=#eef3f5;strokeColor=#627680;",
    "external_event": "ellipse;aspect=fixed;whiteSpace=wrap;html=1;fillColor=#eef3f5;strokeColor=#627680;",
}
EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=24;html=1;"
    "endArrow=blockThin;endFill=1;strokeWidth=1.5;fontSize=11;fontStyle=1;"
    "labelBackgroundColor=#f8fafb;fontColor=#263238;"
)


@dataclass(frozen=True)
class LayoutNode:
    x: int
    y: int
    width: int
    height: int
    rank: int

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def bottom(self) -> int:
        return self.y + self.height


def _node_size(step_type: str) -> tuple[int, int]:
    if step_type in {"start", "end", "timer", "external_event"}:
        return 58, 58
    if step_type == "decision":
        return 108, 108
    return 220, 76


def _ranks(process_ir: dict[str, Any]) -> dict[str, int]:
    steps = process_ir["steps"]
    indexes = {step["id"]: index for index, step in enumerate(steps)}
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in process_ir["edges"]:
        if indexes[edge["from"]] < indexes[edge["to"]]:
            incoming[edge["to"]].append(edge["from"])

    ranks = {step["id"]: 0 for step in steps if step["type"] == "start"}
    max_rank = 0
    for step in steps:
        if step["type"] in {"start", "end"}:
            continue
        sources = [source for source in incoming[step["id"]] if source in ranks]
        rank = max((ranks[source] + 1 for source in sources), default=max_rank + 1)
        ranks[step["id"]] = rank
        max_rank = max(max_rank, rank)
    for step in steps:
        if step["type"] == "end":
            ranks[step["id"]] = max_rank + 1
    return ranks


def _layout(process_ir: dict[str, Any]) -> tuple[dict[str, LayoutNode], int, int]:
    ranks = _ranks(process_ir)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for step in process_ir["steps"]:
        grouped[ranks[step["id"]]].append(step)
    max_row_size = max((len(steps) for steps in grouped.values()), default=1)
    return_count = sum(
        ranks[edge["to"]] <= ranks[edge["from"]]
        for edge in process_ir["edges"]
    )
    bypass_count = sum(
        ranks[edge["to"]] - ranks[edge["from"]] > 1
        for edge in process_ir["edges"]
    )
    side_margin = 180 + max(return_count, bypass_count) * 28
    content_width = 220 + (max_row_size - 1) * 300
    canvas_width = max(1200, content_width + side_margin * 2)
    center_x = canvas_width // 2
    layout = {}
    for rank, steps in grouped.items():
        for column, step in enumerate(steps):
            width, height = _node_size(step["type"])
            node_center_x = center_x + round((column - (len(steps) - 1) / 2) * 300)
            layout[step["id"]] = LayoutNode(
                x=node_center_x - width // 2,
                y=70 + rank * 220,
                width=width,
                height=height,
                rank=rank,
            )
    canvas_height = 220 + (max(grouped, default=0) + 1) * 220
    return layout, canvas_width, canvas_height


def _condition_label(condition: dict[str, Any] | None) -> str:
    if not condition:
        return ""
    if condition["left"] == "route":
        return str(condition["right"])
    subject = str(condition["left"]).replace("_", " ").strip()
    subject = subject[:1].upper() + subject[1:]
    operator = condition["operator"]
    value = condition["right"]
    if operator == "==" and value is True:
        label = subject
    elif operator == "==" and value is False:
        label = f"Не: {subject.lower()}"
    else:
        label = f"{subject} {operator} {value}"
    return label if len(label) <= 42 else label[:41].rstrip() + "…"


def _add_waypoints(geometry: ET.Element, points: list[tuple[int, int]]) -> None:
    if not points:
        return
    array = ET.SubElement(geometry, "Array", {"as": "points"})
    for x, y in points:
        ET.SubElement(array, "mxPoint", {"x": str(x), "y": str(y)})


def generate_drawio(process_ir: dict[str, Any]) -> str:
    process = process_ir["process"]
    layout, canvas_width, canvas_height = _layout(process_ir)
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "agent": "AI Process Architect",
            "type": "device",
            "compressed": "false",
        },
    )
    diagram = ET.SubElement(
        mxfile,
        "diagram",
        {"id": f"diagram_{process['id']}", "name": process["name"]},
    )
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": str(canvas_width),
            "pageHeight": str(canvas_height),
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for step in process_ir["steps"]:
        node = layout[step["id"]]
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": step["id"],
                "value": step["title"],
                "style": NODE_STYLES[step["type"]] + "fontSize=12;fontStyle=1;spacing=8;",
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": str(node.x),
                "y": str(node.y),
                "width": str(node.width),
                "height": str(node.height),
                "as": "geometry",
            },
        )

    return_index = 0
    bypass_index = 0
    content_left = min(node.x for node in layout.values())
    content_right = max(node.x + node.width for node in layout.values())
    rank_bottom = {
        rank: max(node.bottom for node in layout.values() if node.rank == rank)
        for rank in {node.rank for node in layout.values()}
    }
    rank_top = {
        rank: min(node.y for node in layout.values() if node.rank == rank)
        for rank in {node.rank for node in layout.values()}
    }
    adjacent_counts: dict[tuple[int, int], int] = defaultdict(int)
    for edge in process_ir["edges"]:
        source = layout[edge["from"]]
        target = layout[edge["to"]]
        if target.rank - source.rank == 1 and source.center_x != target.center_x:
            adjacent_counts[(source.rank, target.rank)] += 1
    adjacent_indexes: dict[tuple[int, int], int] = defaultdict(int)
    for edge in process_ir["edges"]:
        source = layout[edge["from"]]
        target = layout[edge["to"]]
        points: list[tuple[int, int]] = []
        if target.rank <= source.rank:
            channel_x = content_left - 60 - return_index * 28
            return_index += 1
            points = [
                (source.x - 30, source.center_y),
                (channel_x, source.center_y),
                (channel_x, target.center_y),
                (target.x - 30, target.center_y),
            ]
        elif target.rank - source.rank > 1:
            channel_x = content_right + 60 + bypass_index * 28
            bypass_index += 1
            points = [
                (source.center_x, source.bottom + 34),
                (channel_x, source.bottom + 34),
                (channel_x, target.y - 34),
                (target.center_x, target.y - 34),
            ]
        elif source.center_x != target.center_x:
            rank_pair = (source.rank, target.rank)
            lane_index = adjacent_indexes[rank_pair]
            adjacent_indexes[rank_pair] += 1
            lane_count = adjacent_counts[rank_pair]
            gap_start = rank_bottom[source.rank]
            gap_size = rank_top[target.rank] - gap_start
            middle_y = gap_start + round((lane_index + 1) * gap_size / (lane_count + 1))
            points = [
                (source.center_x, middle_y),
                (target.center_x, middle_y),
            ]
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": edge["id"],
                "value": _condition_label(edge["condition"]),
                "style": EDGE_STYLE,
                "edge": "1",
                "parent": "1",
                "source": edge["from"],
                "target": edge["to"],
            },
        )
        geometry = ET.SubElement(
            cell,
            "mxGeometry",
            {"x": "0", "y": "0", "relative": "1", "as": "geometry"},
        )
        ET.SubElement(geometry, "mxPoint", {"as": "offset"})
        _add_waypoints(geometry, points)
    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True) + "\n"
