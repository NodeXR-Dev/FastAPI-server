from dataclasses import dataclass
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ClientConnection:
    """
    WebSocket 연결 하나에 대한 메타데이터.

    websocket: 실제 Unity Client와 연결된 WebSocket 객체
    user_id: 이 연결이 어떤 user의 연결인지
    """
    websocket: WebSocket
    user_id: UUID | None = None


class RoomConnectionManager:
    """
    room_id 기준으로 현재 살아있는 WebSocket 연결을 관리한다.

    active_connections 예시:
    {
        "room-1": [
            ClientConnection(websocket=A_ws, user_id=A),
            ClientConnection(websocket=B_ws, user_id=B),
        ]
    }

    주의:
    - 이건 DB가 아니라 서버 메모리 데이터다.
    - 현재 살아있는 WebSocket 연결 객체는 DB에 저장할 수 없다.
    """

    def __init__(self):
        self.active_connections: dict[str, list[ClientConnection]] = defaultdict(list)

    async def connect(
        self,
        *,
        room_id: UUID,
        websocket: WebSocket,
        user_id: UUID | None = None,
    ) -> None:
        """
        Unity Client가 WebSocket에 접속했을 때 호출한다.
        """
        await websocket.accept()

        room_key = str(room_id)

        self.active_connections[room_key].append(
            ClientConnection(
                websocket=websocket,
                user_id=user_id,
            )
        )

        logger.info(
            "[ws_connect] room_id=%s | user_id=%s | active_count=%d",
            room_id,
            user_id,
            len(self.active_connections[room_key]),
        )

    def disconnect(self, room_id: UUID, websocket: WebSocket):
        """
        Unity Client 연결이 끊겼을 때 호출한다.
        """
        room_key = str(room_id)

        if room_key not in self.active_connections:
            return

        self.active_connections[room_key] = [
            conn
            for conn in self.active_connections[room_key]
            if conn.websocket is not websocket
        ]

        if not self.active_connections[room_key]:
            del self.active_connections[room_key]
            logger.info("[ws_disconnect] room_id=%s | room removed", room_id)
            return

        logger.info(
            "[ws_disconnect] room_id=%s | active_count=%d",
            room_id,
            len(self.active_connections[room_key]),
        )

    async def send_personal_message(
        self,
        websocket: WebSocket,
        message: dict,
    ):
        """
        특정 WebSocket 연결 하나에만 메시지를 보낸다.

        사용 예:
        - 연결 성공 응답
        - 요청자에게 ERROR 전달
        """
        await websocket.send_json(message)

    async def send_to_user(
        self,
        room_id: UUID,
        user_id: UUID,
        message: dict,
    ) -> bool:
        """
        특정 room 안의 특정 user에게만 메시지를 보낸다.

        현재 최종 정책에서는 주로 ERROR fallback이나 특수한 개인 메시지에만 사용한다.
        2D/3D/AGENT_GUIDE/GRAPH_UPDATED는 room broadcast로 보낸다.
        """
        room_key = str(room_id)

        if room_key not in self.active_connections:
            logger.info(
                "[ws_send_to_user_skip] no active room | room_id=%s | user_id=%s",
                room_id,
                user_id,
            )
            return False

        disconnected: list[ClientConnection] = []
        sent = False

        for conn in list(self.active_connections[room_key]):
            if conn.user_id != user_id:
                continue

            try:
                await conn.websocket.send_json(message)
                sent = True

                logger.info(
                    "[ws_send_to_user] room_id=%s | user_id=%s | event_type=%s",
                    room_id,
                    user_id,
                    message.get("event_type"),
                )

            except Exception as e:
                logger.warning(
                    "[ws_send_to_user_failed] room_id=%s | user_id=%s | error=%s",
                    room_id,
                    user_id,
                    str(e),
                )
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(room_id, conn.websocket)

        if not sent:
            logger.info(
                "[ws_send_to_user_not_found] room_id=%s | user_id=%s",
                room_id,
                user_id,
            )

        return sent

    async def broadcast_to_room(
        self,
        room_id: UUID,
        message: dict,
    ):
        room_key = str(room_id)

        if room_key not in self.active_connections:
            logger.info(
                "[ws_broadcast_skip] no active clients | room_id=%s | event_type=%s",
                room_id,
                message.get("event_type"),
            )
            return

        disconnected: list[ClientConnection] = []
        receiver_count = 0

        for conn in list(self.active_connections[room_key]):
            try:
                await conn.websocket.send_json(message)
                receiver_count += 1
            except Exception as e:
                logger.warning(
                    "[ws_broadcast_failed] room_id=%s | event_type=%s | error=%s",
                    room_id,
                    message.get("event_type"),
                    str(e),
                )
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(room_id, conn.websocket)

        logger.info(
            "[ws_broadcast] room_id=%s | event_type=%s | receiver_count=%d",
            room_id,
            message.get("event_type"),
            receiver_count,
        )
        
    def register(
        self,
        *,
        room_id: UUID,
        websocket: WebSocket,
        user_id: UUID | None = None,
    ) -> None:
        """
        이미 accept된 WebSocket을 room에 등록한다.
        """
        room_key = str(room_id)

        self.active_connections[room_key].append(
            ClientConnection(
                websocket=websocket,
                user_id=user_id,
            )
        )

        logger.info(
            "[ws_register] room_id=%s | user_id=%s | active_count=%d",
            room_id,
            user_id,
            len(self.active_connections[room_key]),
        )


room_ws_manager = RoomConnectionManager()