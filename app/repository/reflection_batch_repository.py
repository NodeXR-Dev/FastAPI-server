import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session


class ReflectionBatchRepository:
    """Session-scoped PostgreSQL advisory lock for one room reflection run."""

    _LOCK_NAMESPACE = b"nodexr-reflection-batch"

    @classmethod
    def lock_key(cls, room_id: UUID) -> int:
        digest = hashlib.blake2b(
            cls._LOCK_NAMESPACE + room_id.bytes,
            digest_size=8,
        ).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    def try_acquire_room_lock(self, db: Session, *, room_id: UUID) -> bool:
        connection = db.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"},
        )
        return bool(
            connection.scalar(
                select(func.pg_try_advisory_lock(self.lock_key(room_id)))
            )
        )

    def release_room_lock(self, db: Session, *, room_id: UUID) -> bool:
        connection = db.connection()
        return bool(
            connection.scalar(
                select(func.pg_advisory_unlock(self.lock_key(room_id)))
            )
        )
