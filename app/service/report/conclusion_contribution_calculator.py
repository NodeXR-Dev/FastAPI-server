"""Topic 별 Conclusion Contribution(결론 형성 기여도) 계산.

발화 하나의 점수

    score = gate × (0.25·R + 0.55·I + 0.20·V)

    R  Conclusion Relevance   발화 ↔ 최종 결정 cosine similarity (0~1 로 자름)
    I  Reasoning Influence    Decision Journey 에서 이 발화가 맡은 역할
    V  Information Value      발화 자체의 정보량
    gate                      잡음(filler·맞장구·반복)이면 점수를 거의 지운다

가중치를 이렇게 둔 이유
- I 가 가장 크다. 배치가 confidence ≥ 0.65 로 걸러 저장한 design_fact_utterance_links
  에서 나오는 값이라 현재 데이터 중 가장 정밀한 신호다. 제약·반론처럼 결론과 문장이
  달라도 결론을 만든 발화는 R 로는 잡히지 않고 I 로만 잡힌다.
- R 은 보조다. ko-sroberta 의 주제 분리도가 AUC 0.63 수준으로 실측됐고
  (docs/topic-threshold-measurement.md), 짧은 맞장구도 결정 문장과 꽤 높은 유사도를
  보인다. 비중을 높이면 "말 많이 한 사람"이 다시 유리해진다.
- V 는 같은 역할 안에서 구체적인 발화("15도 기울이면 허리 부담이 준다")를
  모호한 발화보다 앞에 세우는 정도로만 쓴다.

참가자 점수는 그 참가자 발화 점수의 합이고, Topic 안에서 합이 100 이 되도록 정규화한다.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from app.model.enum import DialogueMove
from app.schema.report.meeting_report import (
    MeaningfulUtterance,
    ParticipantDecisionContribution,
)
from app.service.report.decision_journey_builder import UtteranceRole, UtteranceView
from app.service.utterance.noise_filter_service import (
    DROP,
    STORE_ONLY,
    NoiseFilterService,
)


CONCLUSION_RELEVANCE_WEIGHT = 0.25
REASONING_INFLUENCE_WEIGHT = 0.55
INFORMATION_VALUE_WEIGHT = 0.20

# Journey 역할별 영향력. 최종 결정을 확정한 발화가 가장 크고, 결론의 방향을 바꾼
# 제약·근거·반론이 그 다음, 출발점인 제안이 그 다음이다.
ROLE_INFLUENCE = {
    "DECISION": 1.0,
    "CONSTRAINT": 0.9,
    "RATIONALE": 0.85,
    "CONFLICT": 0.8,
    "ALTERNATIVE": 0.75,
    "PROPOSAL": 0.7,
}
# 최종이 아닌(번복·병존) 결정.
NON_FINAL_DECISION_INFLUENCE = 0.7
# 최종 결정과 링크로 이어지지 않은 곁가지 논의.
UNLINKED_ROLE_DISCOUNT = 0.5

# fact 에 연결되지 않은 발화는 utterance_annotations 의 행위 서술만 약하게 반영한다.
# 배치가 fact 로 인정하지 않은 발화이므로, 결정과 이어진 fact 근거 발화(최소 0.7)보다
# 한참 낮게 둔다. annotation 은 AGENT_GUARD_GATING_MODE=annotation 등에서만 쌓인다.
DIALOGUE_MOVE_INFLUENCE = {
    DialogueMove.DECIDE: 0.4,
    DialogueMove.PROPOSE: 0.35,
    DialogueMove.DISAGREE: 0.35,
    DialogueMove.INFORM: 0.2,
    DialogueMove.AGREE: 0.05,
    DialogueMove.ASK: 0.05,
    DialogueMove.OTHER: 0.0,
}

# 잡음 게이트
NOISE_GATE_DROP = 0.0
NOISE_GATE_LOW_VALUE = 0.2

# 이 글자 수(공백 제외)면 정보량 1.0 으로 본다.
INFORMATION_SATURATION_CHARS = 40

MEANINGFUL_UTTERANCE_LIMIT = 8
MEANINGFUL_MIN_SCORE = 0.3

ROLE_LABELS = {
    "PROPOSAL": "아이디어 제안",
    "ALTERNATIVE": "대안 제시",
    "CONSTRAINT": "제약 조건 제시",
    "CONFLICT": "반론·쟁점 제기",
    "RATIONALE": "근거 제시",
    "DECISION": "결정 확정",
}
MAX_CONTRIBUTION_ITEMS = 4


@dataclass
class UtteranceScore:
    utterance: UtteranceView
    conclusion_relevance: float
    reasoning_influence: float
    information_value: float
    gate: float
    score: float
    roles: list[UtteranceRole] = field(default_factory=list)


class ConclusionContributionCalculator:
    def __init__(self, *, noise_filter_service: NoiseFilterService | None = None) -> None:
        self.noise_filter_service = noise_filter_service or NoiseFilterService()

    def score_utterances(
        self,
        *,
        utterances: list[UtteranceView],
        similarities: dict[UUID, float],
        utterance_roles: dict[UUID, list[UtteranceRole]],
        dialogue_moves: dict[UUID, DialogueMove],
        has_decision: bool,
    ) -> list[UtteranceScore]:
        scores: list[UtteranceScore] = []
        seen_keys: set[str] = set()
        for utterance in sorted(utterances, key=lambda item: item.created_at):
            roles = utterance_roles.get(utterance.utterance_id, [])
            information_value, gate = self._information_value(
                text=utterance.text,
                seen_keys=seen_keys,
            )
            relevance = max(0.0, min(1.0, similarities.get(utterance.utterance_id, 0.0)))
            influence = self._reasoning_influence(
                roles=roles,
                dialogue_move=dialogue_moves.get(utterance.utterance_id),
                has_decision=has_decision,
            )
            score = gate * (
                CONCLUSION_RELEVANCE_WEIGHT * relevance
                + REASONING_INFLUENCE_WEIGHT * influence
                + INFORMATION_VALUE_WEIGHT * information_value
            )
            scores.append(
                UtteranceScore(
                    utterance=utterance,
                    conclusion_relevance=round(relevance, 4),
                    reasoning_influence=round(influence, 4),
                    information_value=round(information_value, 4),
                    gate=gate,
                    score=round(score, 4),
                    roles=roles,
                )
            )
        return scores

    def select_meaningful(self, scores: list[UtteranceScore]) -> list[MeaningfulUtterance]:
        # Journey 근거 발화는 점수와 무관하게 먼저 싣는다. 결론과 문장이 달라 유사도가
        # 낮은 제약·반론 발화가 목록에서 밀려나지 않게 하려는 것이다.
        selected = [
            item
            for item in scores
            if item.gate > NOISE_GATE_LOW_VALUE
            and (item.roles or item.score >= MEANINGFUL_MIN_SCORE)
        ]
        selected.sort(key=lambda item: (not item.roles, -item.score))
        selected = selected[:MEANINGFUL_UTTERANCE_LIMIT]
        selected.sort(key=lambda item: -item.score)
        return [
            MeaningfulUtterance(
                utterance_id=item.utterance.utterance_id,
                speaker_id=item.utterance.user_id,
                nickname=item.utterance.nickname,
                text=item.utterance.text,
                timestamp=item.utterance.created_at,
                score=item.score,
                conclusion_relevance=item.conclusion_relevance,
                reasoning_influence=item.reasoning_influence,
                information_value=item.information_value,
                roles=list(dict.fromkeys(role.step_type for role in item.roles)),
            )
            for item in selected
        ]

    def aggregate_contributions(
        self,
        scores: list[UtteranceScore],
    ) -> list[ParticipantDecisionContribution]:
        raw_by_user: dict[UUID, float] = defaultdict(float)
        count_by_user: dict[UUID, int] = defaultdict(int)
        nickname_by_user: dict[UUID, str] = {}
        items_by_user: dict[UUID, list[str]] = defaultdict(list)

        for item in scores:
            user_id = item.utterance.user_id
            raw_by_user[user_id] += item.score
            count_by_user[user_id] += 1
            nickname_by_user[user_id] = item.utterance.nickname
            for role in item.roles:
                items_by_user[user_id].append(
                    f"{ROLE_LABELS.get(role.step_type, role.step_type)}: {role.summary}"
                )

        percents = self._normalize_to_hundred(raw_by_user)
        contributions = [
            ParticipantDecisionContribution(
                user_id=user_id,
                nickname=nickname_by_user[user_id],
                contribution_percent=percents[user_id],
                raw_score=round(raw_by_user[user_id], 4),
                utterance_count=count_by_user[user_id],
                contributions=list(dict.fromkeys(items_by_user[user_id]))[
                    :MAX_CONTRIBUTION_ITEMS
                ],
            )
            for user_id in raw_by_user
        ]
        contributions.sort(key=lambda item: (-item.contribution_percent, item.nickname))
        return contributions

    # -------------------------

    def _information_value(self, *, text: str, seen_keys: set[str]) -> tuple[float, float]:
        """(정보량, 게이트). 잡음 판정은 실시간 경로의 NoiseFilterService 를 그대로 쓴다."""
        classification = self.noise_filter_service.classify(normalized_text=text)
        if classification == DROP:
            return 0.0, NOISE_GATE_DROP
        if classification == STORE_ONLY:
            return 0.05, NOISE_GATE_LOW_VALUE

        key = re.sub(r"[\s.,!?~…]+", "", text).casefold()
        if key in seen_keys:
            # 같은 Topic 에서 이미 나온 말을 되풀이한 것(STT 중복 포함).
            return 0.05, NOISE_GATE_LOW_VALUE
        seen_keys.add(key)

        chars = len(re.sub(r"\s", "", text))
        value = min(1.0, chars / INFORMATION_SATURATION_CHARS)
        if re.search(r"\d", text):
            # 수치가 들어간 발화는 구체적인 설계 정보를 담고 있을 가능성이 높다.
            value = min(1.0, value + 0.1)
        return max(0.1, value), 1.0

    @staticmethod
    def _reasoning_influence(
        *,
        roles: list[UtteranceRole],
        dialogue_move: DialogueMove | None,
        has_decision: bool,
    ) -> float:
        if roles:
            best = 0.0
            for role in roles:
                if role.step_type == "DECISION" and not role.is_final_decision:
                    weight = NON_FINAL_DECISION_INFLUENCE
                else:
                    weight = ROLE_INFLUENCE.get(role.step_type, 0.0)
                if has_decision and not role.linked_to_decision:
                    weight *= UNLINKED_ROLE_DISCOUNT
                best = max(best, weight)
            return best
        if dialogue_move is not None:
            return DIALOGUE_MOVE_INFLUENCE.get(dialogue_move, 0.0)
        return 0.0

    @staticmethod
    def _normalize_to_hundred(raw_by_user: dict[UUID, float]) -> dict[UUID, float]:
        """소수 첫째 자리까지, 합이 정확히 100.0 이 되게 나눈다(최대 잉여 방식)."""
        total = sum(raw_by_user.values())
        if total <= 0:
            return {user_id: 0.0 for user_id in raw_by_user}

        tenths = {user_id: raw * 1000 / total for user_id, raw in raw_by_user.items()}
        floored = {user_id: int(value) for user_id, value in tenths.items()}
        remainder = 1000 - sum(floored.values())
        by_fraction = sorted(
            tenths,
            key=lambda user_id: (tenths[user_id] - floored[user_id], str(user_id)),
            reverse=True,
        )
        for user_id in by_fraction[:remainder]:
            floored[user_id] += 1
        return {user_id: value / 10 for user_id, value in floored.items()}
