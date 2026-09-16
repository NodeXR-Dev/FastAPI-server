"""TOPIC_SIMILARITY_THRESHOLD 스윕.

실제 TopicRoutingService를 실제 DB에 대고 돌린다. 오프라인 복제본은
원본 알고리즘과 어긋날 수 있어 쓰지 않는다.

라벨이 붙은 회의 발화를 threshold별로 라우팅시키고, 사람이 매긴
topic 구분과 얼마나 일치하는지 pairwise F1으로 잰다.
"""

import json
import os
from datetime import datetime, timezone
from itertools import combinations
from uuid import UUID

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

from sqlalchemy import select

from app.db.session import SessionLocal
from app.model.room import Room, RoomMember, User
from app.repository.utterance_repository import UtteranceRepository
from app.schema.room.request import CreateRoomRequest
from app.service.room.room_service import RoomService
from app.service.utterance.embedding_service import EmbeddingService
from app.service.utterance.topic_routing_service import TopicRoutingService

# (발화, 정답 topic 라벨, 짧은 리액션인가)
# 실제 중학생 팀 회의를 모사. 주제가 3번 바뀌고, 사이사이에 내용이 없는
# 리액션 발화가 섞인다. 리액션은 어느 주제와도 유사도가 낮아 새 topic을
# 만들기 쉬운데, 이게 과분할의 주원인이다.
MEETING = [
    ("자전거 거치대를 어디에 세울지부터 정하자.",                 "위치", False),
    ("운동장 옆은 공이 날아와서 위험할 것 같아.",                 "위치", False),
    ("후문 쪽이 그늘도 지고 지나다니기도 편해.",                  "위치", False),
    ("응 그게 낫겠다.",                                          "위치", True),
    ("그럼 후문 쪽으로 하자.",                                    "위치", False),
    ("근데 비 오면 자전거가 다 젖잖아.",                          "지붕", False),
    ("지붕을 씌우는 건 어때?",                                    "지붕", False),
    ("투명한 아크릴로 하면 안이 환하게 보일 거야.",               "지붕", False),
    ("아크릴은 한 장에 이만 원쯤 한대.",                          "지붕", False),
    ("그건 좀 비싼데.",                                          "지붕", True),
    ("그러면 천막 천으로 하는 게 싸지 않을까?",                   "지붕", False),
    ("좋아 천막으로 가자.",                                       "지붕", False),
    ("자물쇠는 어떻게 걸게 할지도 정해야 해.",                     "잠금", False),
    ("고리를 위쪽에 하나 더 달면 편할 것 같아.",                   "잠금", False),
    ("맞아 그거 좋다.",                                          "잠금", True),
    ("체인 자물쇠도 걸리게 고리를 굵게 만들자.",                   "잠금", False),
    ("고리가 굵으면 작은 자물쇠는 안 들어갈 수도 있어.",           "잠금", False),
    ("그럼 굵은 고리랑 얇은 고리를 하나씩 달자.",                  "잠금", False),
]

INVENTION = [
    ("이번 발명품은 우산에 묻은 물기를 제거하는 스탠드로 하자.", "우산", False),
    ("감전 위험이 있으니까 전기는 절대 쓰지 말자.", "우산", False),
    ("그러면 발판을 밟아서 작동하는 방식으로 만들자.", "우산", False),
    ("통 안쪽에는 물을 빨아들이는 흡수 패드를 붙이자.", "우산", False),
    ("패드가 젖으면 못 쓰니까 교체할 수 있게 만들어야 해.", "우산", False),
    ("패드는 손으로 뽑아서 갈아끼우는 구조로 하자.", "우산", False),
    ("우산마다 굵기가 다르니까 패드 뒤에 스프링을 넣자.", "우산", False),
    ("스프링이 있으면 얇은 우산도 꽉 눌러줄 수 있겠다.", "우산", False),
    ("스프링 방식으로 확정하자.", "우산", False),
]

THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.75]


def create_room(label: str) -> tuple[UUID, UUID]:
    service = RoomService()
    db = SessionLocal()
    try:
        created = service.create_room(
            CreateRoomRequest(
                room_name=f"topic-sweep-{label}-{datetime.now(timezone.utc):%H%M%S%f}",
                room_topic="자전거 거치대",
                nickname="민준",
            ),
            db,
        )
        room_id = created.room_id
    finally:
        db.close()
    db = SessionLocal()
    try:
        leader = db.scalar(
            select(User)
            .join(RoomMember, RoomMember.user_id == User.user_id)
            .where(RoomMember.room_id == room_id, User.nickname == "민준")
        )
        return room_id, leader.user_id
    finally:
        db.close()


def route_all_for(meeting: list, threshold: float, embeddings: list[list[float]]) -> list[str]:
    """threshold 하나로 회의 전체를 라우팅하고 topic_id 순서를 돌려준다."""
    room_id, user_id = create_room(f"{threshold:.2f}")
    routing = TopicRoutingService(similarity_threshold=threshold)
    utterance_repository = UtteranceRepository()
    assigned: list[str] = []

    for (text, _label, _reaction), embedding in zip(meeting, embeddings):
        db = SessionLocal()
        try:
            utterance = utterance_repository.create(
                db,
                room_id=room_id,
                user_id=user_id,
                original_text=text,
                normalized_text=text,
                embedding=embedding,
            )
            topic_id = routing.route_topic(
                db,
                room_id=room_id,
                utterance_id=utterance.utterance_id,
                normalized_text=text,
                embedding=embedding,
            )
            db.commit()
            assigned.append(str(topic_id))
        finally:
            db.close()
    return assigned


def pairwise_f1(truth: list[str], predicted: list[str]) -> dict:
    """같은 주제로 묶여야 할 발화 쌍이 실제로 같이 묶였는가."""
    tp = fp = fn = 0
    for i, j in combinations(range(len(truth)), 2):
        same_truth = truth[i] == truth[j]
        same_pred = predicted[i] == predicted[j]
        if same_truth and same_pred:
            tp += 1
        elif not same_truth and same_pred:
            fp += 1
        elif same_truth and not same_pred:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate(name: str, meeting: list, thresholds: list) -> list[dict]:
    truth = [label for _text, label, _reaction in meeting]
    expected = len(set(truth))
    service = EmbeddingService()
    embeddings = [service.embed_text(text) for text, _l, _r in meeting]

    print(f"\n{'='*84}")
    print(f"[{name}] 발화 {len(meeting)}건, 정답 topic {expected}개")
    print(f"{'='*84}")
    print(f"{'threshold':>10} {'topic수':>8} {'F1':>7} {'정밀도':>8} {'재현율':>8}")

    results = []
    for threshold in thresholds:
        predicted = route_all_for(meeting, threshold, embeddings)
        score = pairwise_f1(truth, predicted)
        results.append(
            {
                "dataset": name,
                "threshold": threshold,
                "topic_count": len(set(predicted)),
                "expected_topics": expected,
                **score,
            }
        )
        print(
            f"{threshold:>10.2f} {len(set(predicted)):>8d} {score['f1']:>7.3f} "
            f"{score['precision']:>8.3f} {score['recall']:>8.3f}"
        )
    return results


def main() -> None:
    all_results = []
    all_results += evaluate("다주제 회의 (자전거 거치대)", MEETING, THRESHOLDS)
    all_results += evaluate("단일주제 회의 (우산 물기제거기)", INVENTION, THRESHOLDS)

    print(f"\n{'='*84}")
    print("두 데이터셋 종합 (F1 평균)")
    print(f"{'='*84}")
    by_threshold = {}
    for item in all_results:
        by_threshold.setdefault(item["threshold"], []).append(item)
    print(f"{'threshold':>10} {'다주제 F1':>10} {'다주제 topic':>12} {'단일 F1':>9} {'단일 topic':>10} {'평균 F1':>9}")
    rows = []
    for threshold, items in sorted(by_threshold.items()):
        multi = next(i for i in items if i["dataset"].startswith("다주제"))
        single = next(i for i in items if i["dataset"].startswith("단일"))
        mean_f1 = (multi["f1"] + single["f1"]) / 2
        rows.append((threshold, multi, single, mean_f1))
        print(
            f"{threshold:>10.2f} {multi['f1']:>10.3f} {multi['topic_count']:>12d} "
            f"{single['f1']:>9.3f} {single['topic_count']:>10d} {mean_f1:>9.3f}"
        )
    best = max(rows, key=lambda r: r[3])
    print(f"\n평균 F1 최고: threshold={best[0]:.2f} (평균 {best[3]:.3f}, "
          f"다주제 {best[1]['topic_count']}/{best[1]['expected_topics']}개, "
          f"단일 {best[2]['topic_count']}/{best[2]['expected_topics']}개)")

    out = "/private/tmp/claude-501/-Users-jeongsoeun-Desktop-Life-coding-Project-nodexr-FastAPI-server/4c60a681-59a2-4695-a198-c1c3e0a5c4a7/scratchpad/topic_sweep_result.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(all_results, handle, ensure_ascii=False, indent=2)
    print(f"\n저장: {out}")


main()
