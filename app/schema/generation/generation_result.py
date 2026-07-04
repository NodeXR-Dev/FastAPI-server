from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class ConnectionPromptInfo:
    part_node_id: UUID
    part_node_text: str
    node_id: UUID
    node_chain_texts: list[str]
    sub_graph_id: UUID | None


@dataclass
class PromptContext:
    room_id: UUID
    topic: str
    features: list[str] = field(default_factory=list)
    grouped_connections: dict[UUID | None, list[ConnectionPromptInfo]] = field(default_factory=dict)

    def to_text(self) -> str:
        lines: list[str] = []

        lines.append("[ROOM TOPIC]")
        lines.append(self.topic if self.topic else "(empty)")
        lines.append("")

        lines.append("[FEATURE REQUIREMENTS]")
        if self.features:
            for idx, feature in enumerate(self.features, start=1):
                lines.append(f"{idx}. {feature}")
        else:
            lines.append("(none)")
        lines.append("")

        lines.append("[GRAPH CONTEXT]")
        if not self.grouped_connections:
            lines.append("(none)")
        else:
            for sub_graph_id, connections in self.grouped_connections.items():
                lines.append(f"SubGraph: {sub_graph_id}")

                for idx, connection in enumerate(connections, start=1):
                    lines.append(f"  Connection {idx}")
                    lines.append(f"    - emphasized_part: {connection.part_node_text}")
                    lines.append("    - node_chain_from_root_to_selected_node:")

                    for node_text in connection.node_chain_texts:
                        lines.append(f"      * {node_text}")

                lines.append("")

        return "\n".join(lines)


@dataclass
class GeneratedImageBinary:
    image_bytes: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None


@dataclass
class StoredObjectInfo:
    bucket_name: str
    object_name: str
    public_url: str


@dataclass
class Generated2DAssetResult:
    asset_id: UUID
    mime_type: str
    width: int | None
    height: int | None
    img_url: str