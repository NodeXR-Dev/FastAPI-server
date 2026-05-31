# app/db/init_db.py

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine

# 모든 모델 import
from app.models.user import User
from app.models.room import Room, RoomMember
from app.models.meeting import (
    Topic,
    Episode,
    TopicEpisodeLink,
    Utterance,
    Discussion,
    DiscussionUtteranceLink,
    SemanticMemory,
)
from app.models.graph import (
    SubGraph,
    Node,
    NodeUtteranceLink,
    Edge,
    GraphSnapshot,
)
from app.models.asset import Asset, Reference
from app.models.enums import *


def init_db():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()