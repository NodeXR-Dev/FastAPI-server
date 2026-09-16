"""리포트 HTML 에 넣을 Graph Snapshot SVG 좌표 계산.

프로젝트에 웹용 그래프 렌더러가 없어(그래프는 Unity 가 그린다) 서버에서 간단한
좌→우 트리 배치만 한다. 노드 parent_node_id 로 깊이를 정하고, 잎 노드부터 세로로
쌓은 뒤 부모는 자식들의 가운데에 둔다.
"""

from collections import defaultdict
from dataclasses import dataclass

from app.schema.report.meeting_report import ReportGraphEdge, ReportGraphNode


NODE_WIDTH = 168
NODE_HEIGHT = 40
COLUMN_GAP = 64
ROW_GAP = 16
PADDING = 20
LABEL_MAX_CHARS = 13


@dataclass(frozen=True)
class LaidOutNode:
    node_id: str
    node_type: str
    node_text: str
    label: str
    used_in_generation: bool
    x: float
    y: float


@dataclass(frozen=True)
class LaidOutEdge:
    edge_id: str
    label: str | None
    used_in_generation: bool
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class GraphLayout:
    width: float
    height: float
    node_width: float
    node_height: float
    nodes: list[LaidOutNode]
    edges: list[LaidOutEdge]


def layout_graph(
    *,
    nodes: list[ReportGraphNode],
    edges: list[ReportGraphEdge],
) -> GraphLayout | None:
    if not nodes:
        return None

    node_by_id = {node.node_id: node for node in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    for node in sorted(nodes, key=lambda item: (item.node_type, item.node_text, item.node_id)):
        if node.parent_node_id and node.parent_node_id in node_by_id:
            children[node.parent_node_id].append(node.node_id)
        else:
            roots.append(node.node_id)

    positions: dict[str, tuple[float, float]] = {}
    next_row = [0]
    visiting: set[str] = set()

    def place(node_id: str, depth: int) -> float:
        # 잘못 저장된 순환 부모 관계가 있어도 멈추지 않게 한다.
        if node_id in positions or node_id in visiting:
            return positions.get(node_id, (0.0, 0.0))[1]
        visiting.add(node_id)
        child_ids = [child for child in children[node_id] if child not in positions]
        if child_ids:
            ys = [place(child, depth + 1) for child in child_ids]
            y = (min(ys) + max(ys)) / 2
        else:
            y = PADDING + next_row[0] * (NODE_HEIGHT + ROW_GAP)
            next_row[0] += 1
        x = PADDING + depth * (NODE_WIDTH + COLUMN_GAP)
        positions[node_id] = (x, y)
        visiting.discard(node_id)
        return y

    for root_id in roots:
        place(root_id, 0)
    # 부모 체인이 순환이라 루트에서 닿지 못한 노드.
    for node in nodes:
        if node.node_id not in positions:
            place(node.node_id, 0)

    laid_out_nodes = [
        LaidOutNode(
            node_id=node.node_id,
            node_type=node.node_type,
            node_text=node.node_text,
            label=_truncate(node.node_text),
            used_in_generation=node.used_in_generation,
            x=positions[node.node_id][0],
            y=positions[node.node_id][1],
        )
        for node in nodes
    ]

    laid_out_edges: list[LaidOutEdge] = []
    for edge in edges:
        start = positions.get(edge.from_node_id)
        end = positions.get(edge.to_node_id)
        if start is None or end is None:
            continue
        laid_out_edges.append(
            LaidOutEdge(
                edge_id=edge.edge_id,
                label=edge.label,
                used_in_generation=edge.used_in_generation,
                x1=start[0] + NODE_WIDTH,
                y1=start[1] + NODE_HEIGHT / 2,
                x2=end[0],
                y2=end[1] + NODE_HEIGHT / 2,
            )
        )

    width = max(x for x, _ in positions.values()) + NODE_WIDTH + PADDING
    height = max(y for _, y in positions.values()) + NODE_HEIGHT + PADDING
    return GraphLayout(
        width=width,
        height=height,
        node_width=NODE_WIDTH,
        node_height=NODE_HEIGHT,
        nodes=laid_out_nodes,
        edges=laid_out_edges,
    )


def _truncate(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= LABEL_MAX_CHARS:
        return text
    return text[: LABEL_MAX_CHARS - 1] + "…"
