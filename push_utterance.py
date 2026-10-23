"""시연용: 서버에 발화를 대신 넣어 Agent 알림을 헤드셋으로 띄운다.

음성 인식이 불안정할 때 시연 진행을 위한 수동 트리거다.
클라이언트가 보내는 것과 똑같은 WS 이벤트를 보내므로 서버 경로는 실제와 동일하다.

사용법:
    python /app/push_utterance.py <room_id> "발화 내용"
    python /app/push_utterance.py <room_id> --violation     # 제약 위반 대사
    python /app/push_utterance.py <room_id> --rationale     # 근거 복기
    python /app/push_utterance.py <room_id> --image         # 이미지 생성
"""

import asyncio
import json
import sys
import uuid

import websockets
from sqlalchemy import select

from app.db.session import SessionLocal
from app.model.room import RoomMember

WS_URL = "ws://localhost:8000/ws/rooms/event"

PRESETS = {
    "--violation": "배터리랑 모터를 겉에 노출시켜서 달자.",
    "--violation2": "그냥 폭을 1미터로 키워서 한 번에 많이 담자.",
    "--rationale": "노드베어 왜 브러시로 정했는지 알려줘.",
    "--conflict": "노드베어 아까 집게 방식에 무슨 반대가 있었지?",
    "--image": "노드베어 지금 그래프대로 이미지를 만들어줘.",
    "--safe": "수거통 색깔은 초록색으로 하자.",
}


async def main(room_id: uuid.UUID, text: str) -> None:
    db = SessionLocal()
    user_id = db.scalars(
        select(RoomMember.user_id).where(RoomMember.room_id == room_id)
    ).first()
    db.close()
    if user_id is None:
        raise SystemExit(f"방에 참여자가 없다: {room_id}")

    envelope = {
        "event_type": "UTTERANCE_CREATE",
        "room_id": str(room_id),
        "user_id": str(user_id),
        "job_id": str(uuid.uuid4()),
        "payload": {
            "room_id": str(room_id),
            "user_id": str(user_id),
            "utterance": text,
        },
    }

    print(f"발화 주입: \"{text}\"")
    print(f"  room_id={room_id}  user_id={user_id}")

    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        await ws.send(json.dumps(envelope))
        print("  전송 완료. 응답 대기(최대 90초)…")

        deadline = asyncio.get_event_loop().time() + 90
        while asyncio.get_event_loop().time() < deadline:
            try:
                remaining = deadline - asyncio.get_event_loop().time()
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            message = json.loads(raw)
            event_type = message.get("event_type", "?")
            print(f"  ← {event_type}")
            if event_type == "AGENT_GUIDE":
                payload = message.get("payload", {})
                print(json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
                print("  >>> 헤드셋에도 같은 알림이 갔다.")
                return

    print("  AGENT_GUIDE 없음(위반으로 판정되지 않았거나 시간 초과).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    room = uuid.UUID(sys.argv[1])
    arg = sys.argv[2]
    main_text = PRESETS.get(arg, arg)
    asyncio.run(main(room, main_text))
