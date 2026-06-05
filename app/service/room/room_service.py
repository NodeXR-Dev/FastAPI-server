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
from app.core.security import hash_password, verify_password
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    UnauthorizedException,
    NotFoundException,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


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
        logger.info(
            "[create_room] start | topic=%s | nickname=%s",
            request.room_topic,
            request.nickname,
        )

        if not request.room_topic or not request.password or not request.nickname:
            logger.warning("[create_room] invalid request")
            raise BadRequestException(
                code=ResponseCode.ROOM400,
                message="회의실 생성 요청값이 올바르지 않습니다.",
            )

        room = Room(
            topic=request.room_topic,
            room_password_hash=hash_password(request.password),
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

        logger.info(
            "[create_room] success | room_id=%s | leader_id=%s",
            room.room_id,
            leader.user_id,
        )

        return CreateRoomResult(
            room_id=room.room_id,
            room_topic=room.topic,
            password=request.password,
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
        logger.info("[get_room_list] start")

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

        logger.info("[get_room_list] success | count=%s", len(room_items))

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
        logger.info("[get_room_info] start | room_id=%s", room_id)

        room = self.room_repository.find_room_by_id(db, room_id)

        if room is None:
            logger.warning("[get_room_info] room not found | room_id=%s", room_id)
            raise NotFoundException(
                code=ResponseCode.ROOM404,
                message="회의실을 찾을 수 없습니다.",
            )

        users = [
            RoomInfoUserResponse(
                user_id=member.user.user_id,
                nickname=member.user.nickname,
                leader=member.role == RoomMemberRole.LEADER,
            )
            for member in room.members
        ]

        logger.info(
            "[get_room_info] success | room_id=%s | user_count=%s",
            room.room_id,
            len(users),
        )

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
        logger.info(
            "[enter_room] start | room_id=%s | nickname=%s",
            request.room_id,
            request.nickname,
        )

        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=request.room_id,
        )

        if room is None:
            logger.warning("[enter_room] room not found | room_id=%s", request.room_id)
            raise NotFoundException(
                code=ResponseCode.ROOM404,
                message="회의실을 찾을 수 없습니다.",
            )

        if not verify_password(request.password, room.room_password_hash):
            logger.warning(
                "[enter_room] password mismatch | room_id=%s | nickname=%s",
                request.room_id,
                request.nickname,
            )
            raise UnauthorizedException(
                code=ResponseCode.ROOM401,
                message="회의실 비밀번호가 일치하지 않습니다.",
            )

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

            logger.info(
                "[enter_room] reenter success | room_id=%s | user_id=%s",
                room.room_id,
                existing_member.user_id,
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

        logger.info(
            "[enter_room] first enter success | room_id=%s | user_id=%s",
            room.room_id,
            user.user_id,
        )

        return result, False