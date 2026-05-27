import enum


class RoomMemberRole(str, enum.Enum):
    LEADER = "LEADER"
    TEAMMATE = "TEAMMATE"


class RoomMemberState(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"


class TopicStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class EpisodeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class DiscussionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ISSUE = "ISSUE"
    CONFLICT = "CONFLICT"
    RESOLVED = "RESOLVED"


class NodeType(str, enum.Enum):
    PROPERTY = "PROPERTY"
    REFERENCE = "REFERENCE"
    PART = "PART"


class AssetType(str, enum.Enum):
    IMAGE_2D = "IMAGE_2D"
    MODEL_3D = "MODEL_3D"
    REFERENCE = "REFERENCE"


class UtteranceType(str, enum.Enum):
    REFLECT = "REFLECT"
    NOREFLECT = "NOREFLECT"


class SemanticMemoryType(str, enum.Enum):
    SUMMARY = "SUMMARY"
    DECISION = "DECISION"
    ISSUE = "ISSUE"
    CONFLICT = "CONFLICT"
    CONTEXT = "CONTEXT"