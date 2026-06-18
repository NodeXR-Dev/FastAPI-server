from uuid import UUID

from sqlalchemy.orm import Session

from app.model.room import Room, User, RoomMember
from app.model.enum import RoomMemberRole, RoomMemberState
from app.repository.room_repository import RoomRepository
from app.schema.room.request import (
    CreateRoomRequest,
    EnterRoomRequest,
    ExitRoomRequest,
)
from app.schema.room.response import (
    CreateRoomResult,
    EnterRoomResult,
    ExitRoomResult,
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
    # 공통: 회의실 조회
    # =========================
    def _get_room_or_404(
        self,
        db: Session,
        room_id: UUID,
    ) -> Room:
        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=room_id,
        )

        if room is None:
            logger.warning(
                "[room] room not found | room_id=%s",
                room_id,
            )
            raise NotFoundException(
                code=ResponseCode.ROOM404,
            )

        return room

    # =========================
    # 공통: 회의실 멤버 조회
    # =========================
    def _get_member_or_404(
        self,
        db: Session,
        room_id: UUID,
        nickname: str,
    ) -> RoomMember:
        member = self.room_repository.find_member_by_room_and_nickname(
            db=db,
            room_id=room_id,
            nickname=nickname,
        )

        if member is None:
            logger.warning(
                "[room] member not found "
                "| room_id=%s | nickname=%s",
                room_id,
                nickname,
            )
            raise NotFoundException(
                code=ResponseCode.ROOM_MEMBER404,
            )

        return member

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

        if (
            not request.room_topic
            or not request.password
            or not request.nickname
        ):
            logger.warning("[create_room] invalid request")
            raise BadRequestException(
                code=ResponseCode.ROOM400,
            )

        room = Room(
            topic=request.room_topic,
            room_password_hash=hash_password(request.password),
            is_active=True,
        )
        room = self.room_repository.save_room(
            db,
            room,
        )

        leader = User(
            nickname=request.nickname,
        )
        leader = self.room_repository.save_user(
            db,
            leader,
        )

        room_member = RoomMember(
            room_id=room.room_id,
            user_id=leader.user_id,
            role=RoomMemberRole.LEADER,
            state=RoomMemberState.JOINED,
        )
        self.room_repository.save_room_member(
            db,
            room_member,
        )

        db.commit()

        db.refresh(room)
        db.refresh(leader)

        logger.info(
            "[create_room] success "
            "| room_id=%s | leader_id=%s",
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

        logger.info(
            "[get_room_list] success | count=%s",
            len(room_items),
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
        logger.info(
            "[get_room_info] start | room_id=%s",
            room_id,
        )

        room = self._get_room_or_404(
            db=db,
            room_id=room_id,
        )

        # 현재 JOINED 상태인 사용자만 반환
        users = [
            RoomInfoUserResponse(
                user_id=member.user.user_id,
                nickname=member.user.nickname,
                leader=member.role == RoomMemberRole.LEADER,
            )
            for member in room.members
            if member.state == RoomMemberState.JOINED
        ]

        logger.info(
            "[get_room_info] success "
            "| room_id=%s | user_count=%s",
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
            "[enter_room] start "
            "| room_id=%s | nickname=%s",
            request.room_id,
            request.nickname,
        )

        room = self._get_room_or_404(
            db=db,
            room_id=request.room_id,
        )

        if not verify_password(
            request.password,
            room.room_password_hash,
        ):
            logger.warning(
                "[enter_room] password mismatch "
                "| room_id=%s | nickname=%s",
                request.room_id,
                request.nickname,
            )
            raise UnauthorizedException(
                code=ResponseCode.ROOM401,
            )

        existing_member = (
            self.room_repository.find_member_by_room_and_nickname(
                db=db,
                room_id=request.room_id,
                nickname=request.nickname,
            )
        )

        # =========================
        # 재입장
        # =========================
        if existing_member is not None:
            existing_member.state = RoomMemberState.JOINED
            room.is_active = True

            db.commit()

            db.refresh(existing_member)
            db.refresh(room)

            result = EnterRoomResult(
                room_id=room.room_id,
                user_id=existing_member.user_id,
            )

            logger.info(
                "[enter_room] reenter success "
                "| room_id=%s | user_id=%s",
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
        user = self.room_repository.save_user(
            db,
            user,
        )

        room_member = RoomMember(
            room_id=room.room_id,
            user_id=user.user_id,
            role=RoomMemberRole.TEAMMATE,
            state=RoomMemberState.JOINED,
        )
        self.room_repository.save_room_member(
            db,
            room_member,
        )

        room.is_active = True

        db.commit()

        db.refresh(user)
        db.refresh(room_member)
        db.refresh(room)

        result = EnterRoomResult(
            room_id=room.room_id,
            user_id=user.user_id,
        )

        logger.info(
            "[enter_room] first enter success "
            "| room_id=%s | user_id=%s",
            room.room_id,
            user.user_id,
        )

        return result, False

    # =========================
    # 회의실 퇴장
    # POST /api/rooms/exit
    # =========================
    def exit_room(
        self,
        request: ExitRoomRequest,
        db: Session,
    ) -> ExitRoomResult:
        logger.info(
            "[exit_room] start "
            "| room_id=%s | nickname=%s",
            request.room_id,
            request.nickname,
        )

        room = self._get_room_or_404(
            db=db,
            room_id=request.room_id,
        )

        existing_member = self._get_member_or_404(
            db=db,
            room_id=request.room_id,
            nickname=request.nickname,
        )

        # 해당 사용자의 room_members.state를 LEFT로 변경
        existing_member.state = RoomMemberState.LEFT

        # 퇴장하는 사용자를 제외하고 JOINED 상태인 멤버가
        # 한 명이라도 남아 있는지 확인
        has_joined_member = any(
            member.user_id != existing_member.user_id
            and member.state == RoomMemberState.JOINED
            for member in room.members
        )

        # 남은 사용자가 없다면 방 비활성화
        room.is_active = has_joined_member

        db.commit()

        db.refresh(existing_member)
        db.refresh(room)

        logger.info(
            "[exit_room] success "
            "| room_id=%s | user_id=%s | is_active=%s",
            room.room_id,
            existing_member.user_id,
            room.is_active,
        )

        return ExitRoomResult(
            room_id=room.room_id,
            user_id=existing_member.user_id,
        )