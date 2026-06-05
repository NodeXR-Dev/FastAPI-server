# app/services/room_service.py

from uuid import UUID

from sqlalchemy.orm import Session

from app.model.room import Room, User, RoomMember
from app.model.enum import RoomMemberRole, RoomMemberState
from app.repository.room_repository import RoomRepository
from app.schema.room.request import (
    CreateRoomRequest,
    EnterRoomRequest,
)
from app.schema.room.response import (
    CreateRoomResult,
    EnterRoomResult,
    RoomListResult,
    RoomListItemResponse,
    RoomUserResponse,
    RoomInfoResult,
    RoomInfoUserResponse,
)


class RoomService:
    def __init__(self):
        self.room_repository = RoomRepository()

    # =========================
    # 회의실 생성
    # POST /api/rooms/generate
    # =========================
    def create_room(
        self,
        request: CreateRoomRequest,
        db: Session,
    ) -> CreateRoomResult:
        room = Room(
            topic=request.room_topic,
            room_password_hash=request.password,
            is_active=True,
        )
        room = self.room_repository.save_room(db, room)

        leader = User(
            nickname=request.nickname,
        )
        leader = self.room_repository.save_user(db, leader)

        room_member = RoomMember(
            room_id=room.room_id,
            user_id=leader.user_id,
            role=RoomMemberRole.LEADER,
            state=RoomMemberState.JOINED,
        )
        self.room_repository.save_room_member(db, room_member)

        db.commit()
        db.refresh(room)
        db.refresh(leader)

        return CreateRoomResult(
            room_id=room.room_id,
            room_topic=room.topic,
            password=room.room_password_hash,
            leader=leader.nickname,
            created_at=room.created_at,
        )

    # =========================
    # 회의실 목록 조회
    # GET /api/rooms/list
    # =========================
    def get_room_list(
        self,
        db: Session,
    ) -> RoomListResult:
        rooms = self.room_repository.find_rooms(db)

        room_items: list[RoomListItemResponse] = []

        for room in rooms:
            joined_members = [
                member
                for member in room.members
                if member.state == RoomMemberState.JOINED
            ]

            users = [
                RoomUserResponse(
                    user_id=member.user.user_id,
                    nickname=member.user.nickname,
                )
                for member in joined_members
            ]

            room_items.append(
                RoomListItemResponse(
                    room_id=room.room_id,
                    room_topic=room.topic,
                    users=users,
                    created_at=room.created_at,
                )
            )

        return RoomListResult(
            rooms=room_items,
        )

    # =========================
    # 회의실 상세 정보 조회
    # GET /api/rooms/{room_id}/info
    # =========================
    def get_room_info(
        self,
        db: Session,
        room_id: UUID,
    ) -> RoomInfoResult:
        room = self.room_repository.find_room_by_id(db, room_id)

        if room is None:
            raise ValueError("ROOM_NOT_FOUND")

        users = [
            RoomInfoUserResponse(
                user_id=member.user.user_id,
                nickname=member.user.nickname,
                leader=member.role == RoomMemberRole.LEADER,
            )
            for member in room.members
        ]

        return RoomInfoResult(
            room_id=room.room_id,
            room_topic=room.topic,
            users=users,
        )

    # =========================
    # 회의실 입장
    # POST /api/rooms/enter
    #
    # 최초 입장: ROOM203
    # 재입장: ROOM204
    # =========================
    def enter_room(
        self,
        db: Session,
        request: EnterRoomRequest,
    ) -> tuple[EnterRoomResult, bool]:
        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=request.room_id,
        )

        if room is None:
            raise ValueError("ROOM_NOT_FOUND")

        existing_member = self.room_repository.find_member_by_room_and_nickname(
            db=db,
            room_id=request.room_id,
            nickname=request.nickname,
        )

        # =========================
        # 재입장
        # =========================
        if existing_member is not None:
            existing_member.state = RoomMemberState.JOINED

            if not room.is_active:
                room.is_active = True

            db.commit()
            db.refresh(existing_member)
            db.refresh(existing_member.user)

            result = EnterRoomResult(
                room_id=room.room_id,
                user_id=existing_member.user_id,
            )

            return result, True

        # =========================
        # 최초 입장
        # =========================
        user = User(
            nickname=request.nickname,
        )
        user = self.room_repository.save_user(db, user)

        room_member = RoomMember(
            room_id=room.room_id,
            user_id=user.user_id,
            role=RoomMemberRole.TEAMMATE,
            state=RoomMemberState.JOINED,
        )
        self.room_repository.save_room_member(db, room_member)

        if not room.is_active:
            room.is_active = True

        db.commit()
        db.refresh(user)
        db.refresh(room_member)

        result = EnterRoomResult(
            room_id=room.room_id,
            user_id=user.user_id,
        )

        return result, False