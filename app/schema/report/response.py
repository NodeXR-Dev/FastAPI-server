from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ParticipantRatioResponse(BaseModel):
    user_id: UUID
    nickname: str
    ratio: float = Field(ge=0.0, le=100.0)
    # 발화 "횟수". 시안에는 "22분 9초" 처럼 시간이 적혀 있으나 utterances 에 발화 길이
    # 컬럼이 없어 시간은 산출할 수 없다. ratio 자체도 횟수 기반이므로 시간으로 표기하면
    # 실제와 다른 값을 보여주게 된다. 클라는 "N회" 로 표시한다.
    utterance_count: int = Field(ge=0)


class ReportResponse(BaseModel):
    topic: str
    participants: list[str]
    participants_ratio: list[ParticipantRatioResponse]
    final_2D_image: str | None

    # --- 아래는 리포트 화면(회의 개요 카드)용으로 추가된 필드 ---

    # 회의 시작 = 방 생성 시각. rooms 에 종료 시각 컬럼이 없어 종료는 리포트 요청 시각으로 본다.
    started_at: datetime
    ended_at: datetime
    duration_seconds: int = Field(ge=0)

    # 키워드 칩. 그래프에 쌓인 노드 텍스트에서 뽑는다.
    # 노드는 "Unity 에서 바로 시각화할 수 있는 짧은 명사구" 로 만들어지므로(keyword_prompt)
    # 별도 LLM 호출 없이 그대로 칩으로 쓸 수 있다.
    keywords: list[str]

    total_utterance_count: int = Field(ge=0)
