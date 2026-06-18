# app/repositories/room_repository.py

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.model.enum import RoomMemberState
from app.model.room import Room, RoomMember, User


class RoomRepository:
    def save_room(self, db: Session, room: Room) -> Room:
        db.add(room)
        db.flush()
        db.refresh(room)
        return room

    def save_user(self, db: Session, user: User) -> User:
        db.add(user)
        db.flush()
        db.refresh(user)
        return user

    def save_room_member(self, db: Session, room_member: RoomMember) -> RoomMember:
        db.add(room_member)
        db.flush()
        db.refresh(room_member)
        return room_member

    def find_room_by_id(self, db: Session, room_id: UUID) -> Room | None:
        stmt = (
            select(Room)
            .where(Room.room_id == room_id)
            .options(
                selectinload(Room.members).selectinload(RoomMember.user)
            )
        )
        return db.scalar(stmt)

    def find_rooms(self, db: Session) -> list[Room]:
        stmt = (
            select(Room)
            .order_by(Room.created_at.desc())
            .options(
                selectinload(Room.members).selectinload(RoomMember.user)
            )
        )
        return list(db.scalars(stmt).all())

    def find_member_by_room_and_nickname(
        self,
        db: Session,
        room_id: UUID,
        nickname: str,
    ) -> RoomMember | None:
        stmt = (
            select(RoomMember)
            .join(User, RoomMember.user_id == User.user_id)
            .where(
                RoomMember.room_id == room_id,
                User.nickname == nickname,
            )
            .options(selectinload(RoomMember.user))
        )
        return db.scalar(stmt)
    
    def count_joined_members(
        self,
        db: Session,
        room_id: UUID,
    ) -> int:
        statement = (
            select(func.count(RoomMember.user_id))
            .where(
                RoomMember.room_id == room_id,
                RoomMember.state == RoomMemberState.JOINED,
            )
        )

        return db.scalar(statement) or 0