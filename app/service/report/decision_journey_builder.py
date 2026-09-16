"""Topic 하나의 최종 결정, 근거, Decision Journey 를 기존 구조화 데이터로 조립한다.

Reflection 배치가 이미 발화를 design_facts / design_fact_links /
design_fact_utterance_links / semantic_memories 로 구조화해 두었으므로 여기서는
LLM 을 부르지 않고 그 관계를 따라가기만 한다.

DB 세션이나 ORM 에 의존하지 않는다. 필요한 속성만 가진 객체를 받는다.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    SemanticMemoryType,
)
from app.schema.report.meeting_report import (
    DecisionEvidence,
    DecisionJourneyStep,
    FinalDecision,
    ReportUtteranceEvidence,
)


# 최종 결정으로 볼 수 있는 DECISION fact 상태.
_FINAL_DECISION_STATUSES = {
    DesignFactStatus.ACTIVE,
    DesignFactStatus.CONFIRMED,
    DesignFactStatus.RESOLVED,
}

# DesignFactType → Journey 단계. PROPOSAL 은 대안 여부를 따로 판정한다.
_STEP_TYPE_BY_FACT_TYPE = {
    DesignFactType.PROPOSAL: "PROPOSAL",
    DesignFactType.DECISION: "DECISION",
    DesignFactType.CONSTRAINT: "CONSTRAINT",
    DesignFactType.CONFLICT: "CONFLICT",
    DesignFactType.ISSUE: "CONFLICT",
    DesignFactType.ARGUMENT_AGAINST: "CONFLICT",
    DesignFactType.RATIONALE: "RATIONALE",
    DesignFactType.ARGUMENT_FOR: "RATIONALE",
}

# 결정의 근거로 볼 수 있는 fact 와 링크. (source 타입 --link--> 결정)
_RATIONALE_LINK_TYPES = {DesignFactLinkType.RATIONALE_OF, DesignFactLinkType.SUPPORTS}
_RATIONALE_FACT_TYPES = {DesignFactType.RATIONALE, DesignFactType.ARGUMENT_FOR}

# 결정에서 몇 단계 떨어진 fact 까지 "결정과 이어진 논의"로 볼지.
# 2단계면 제약 → 제안 → 결정, 반론 → 쟁점 ← 결정(RESOLVES) 같은 흐름까지 잡힌다.
_DECISION_LINK_DEPTH = 2


@dataclass(frozen=True)
class UtteranceView:
    utterance_id: UUID
    topic_id: UUID
    user_id: UUID
    nickname: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class UtteranceRole:
    step_type: str
    summary: str
    linked_to_decision: bool
    is_final_decision: bool


@dataclass
class TopicDecisionAnalysis:
    topic_id: UUID
    title: str
    final_decision: FinalDecision
    decision_embedding: list[float] | None
    decision_rationale: str | None
    journey: list[DecisionJourneyStep]
    evidence: DecisionEvidence
    utterance_roles: dict[UUID, list[UtteranceRole]] = field(default_factory=dict)

    @property
    def has_decision(self) -> bool:
        return self.final_decision.content is not None

    @property
    def needs_inference(self) -> bool:
        """명시적 결정이 없지만 추론 재료(구조화된 논의)는 있는 Topic."""
        return self.final_decision.source == "NONE" and bool(self.journey)


class DecisionJourneyBuilder:
    def build(
        self,
        *,
        topic: Any,
        facts: list[Any],
        links: list[Any],
        fact_utterance_ids: dict[UUID, list[UUID]],
        utterance_by_id: dict[UUID, UtteranceView],
        memories: list[Any],
    ) -> TopicDecisionAnalysis:
        """topic 에 속한 facts / memories 만 넘겨받는다. links 는 방 전체여도 된다."""
        fact_by_id = {fact.design_fact_id: fact for fact in facts}
        topic_links = [
            link
            for link in links
            if link.from_fact_id in fact_by_id and link.to_fact_id in fact_by_id
        ]
        memory_by_type = self._latest_memory_by_type(memories)
        decision_memory = memory_by_type.get(SemanticMemoryType.DECISION)
        decision_fact = self._select_decision_fact(
            facts=facts,
            decision_memory=decision_memory,
        )

        final_decision, decision_embedding = self._final_decision(
            decision_memory=decision_memory,
            decision_fact=decision_fact,
        )

        seed_ids = self._decision_seed_ids(
            facts=facts,
            decision_fact=decision_fact,
            decision_memory=decision_memory,
        )
        linked_ids = self._connected_fact_ids(seed_ids=seed_ids, links=topic_links)

        journey = self._build_journey(
            facts=facts,
            links=topic_links,
            decision_fact=decision_fact,
            linked_ids=linked_ids,
            fact_utterance_ids=fact_utterance_ids,
            utterance_by_id=utterance_by_id,
        )

        utterance_roles: dict[UUID, list[UtteranceRole]] = defaultdict(list)
        for step in journey:
            is_final = (
                decision_fact is not None
                and step.design_fact_id == decision_fact.design_fact_id
            )
            for evidence in step.evidence:
                utterance_roles[evidence.utterance_id].append(
                    UtteranceRole(
                        step_type=step.type,
                        summary=step.summary,
                        linked_to_decision=step.linked_to_decision,
                        is_final_decision=is_final,
                    )
                )

        return TopicDecisionAnalysis(
            topic_id=topic.topic_id,
            title=(topic.summary or "").strip() or "이름 없는 주제",
            final_decision=final_decision,
            decision_embedding=decision_embedding,
            decision_rationale=self._decision_rationale(
                rationale_memory=memory_by_type.get(SemanticMemoryType.RATIONALE),
                decision_fact=decision_fact,
                fact_by_id=fact_by_id,
                links=topic_links,
            ),
            journey=journey,
            evidence=self._decision_evidence(
                decision_fact=decision_fact,
                decision_memory=decision_memory,
                rationale_memory=memory_by_type.get(SemanticMemoryType.RATIONALE),
                fact_by_id=fact_by_id,
                links=topic_links,
                fact_utterance_ids=fact_utterance_ids,
                utterance_by_id=utterance_by_id,
            ),
            utterance_roles=dict(utterance_roles),
        )

    # -------------------------
    # 최종 결정
    # -------------------------

    @staticmethod
    def _latest_memory_by_type(memories: list[Any]) -> dict[SemanticMemoryType, Any]:
        latest: dict[SemanticMemoryType, Any] = {}
        for memory in sorted(memories, key=lambda item: item.created_at, reverse=True):
            latest.setdefault(memory.memory_type, memory)
        return latest

    @staticmethod
    def _select_decision_fact(*, facts: list[Any], decision_memory: Any | None) -> Any | None:
        candidates = [
            fact
            for fact in facts
            if fact.fact_type == DesignFactType.DECISION
            and fact.status in _FINAL_DECISION_STATUSES
        ]
        if not candidates:
            return None
        # DECISION memory 가 요약한 fact 를 우선한다. 배치가 그 fact 를 근거로 메모리를
        # 갱신했으므로 memory 문장과 가장 가깝다. 그 다음은 가장 최근 결정.
        memory_id = decision_memory.semantic_memory_id if decision_memory else None
        return max(
            candidates,
            key=lambda fact: (
                memory_id is not None and fact.semantic_memory_id == memory_id,
                fact.updated_at or fact.created_at,
            ),
        )

    @staticmethod
    def _final_decision(
        *,
        decision_memory: Any | None,
        decision_fact: Any | None,
    ) -> tuple[FinalDecision, list[float] | None]:
        if decision_memory is not None:
            return (
                FinalDecision(
                    content=decision_memory.content,
                    source="SEMANTIC_MEMORY",
                    semantic_memory_id=decision_memory.semantic_memory_id,
                    design_fact_id=decision_fact.design_fact_id if decision_fact else None,
                ),
                _vector(decision_memory.embedding)
                or (_vector(decision_fact.embedding) if decision_fact else None),
            )
        if decision_fact is not None:
            return (
                FinalDecision(
                    content=decision_fact.content,
                    source="DESIGN_FACT",
                    design_fact_id=decision_fact.design_fact_id,
                ),
                _vector(decision_fact.embedding),
            )
        return FinalDecision(), None

    @staticmethod
    def _decision_seed_ids(
        *,
        facts: list[Any],
        decision_fact: Any | None,
        decision_memory: Any | None,
    ) -> set[UUID]:
        seeds: set[UUID] = set()
        if decision_fact is not None:
            seeds.add(decision_fact.design_fact_id)
        if decision_memory is not None:
            seeds.update(
                fact.design_fact_id
                for fact in facts
                if fact.semantic_memory_id == decision_memory.semantic_memory_id
            )
        return seeds

    @staticmethod
    def _connected_fact_ids(*, seed_ids: set[UUID], links: list[Any]) -> set[UUID]:
        if not seed_ids:
            return set()
        neighbors: dict[UUID, set[UUID]] = defaultdict(set)
        for link in links:
            neighbors[link.from_fact_id].add(link.to_fact_id)
            neighbors[link.to_fact_id].add(link.from_fact_id)

        visited = set(seed_ids)
        queue = deque((fact_id, 0) for fact_id in seed_ids)
        while queue:
            fact_id, depth = queue.popleft()
            if depth >= _DECISION_LINK_DEPTH:
                continue
            for neighbor in neighbors[fact_id]:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
        return visited

    # -------------------------
    # Decision Journey
    # -------------------------

    def _build_journey(
        self,
        *,
        facts: list[Any],
        links: list[Any],
        decision_fact: Any | None,
        linked_ids: set[UUID],
        fact_utterance_ids: dict[UUID, list[UUID]],
        utterance_by_id: dict[UUID, UtteranceView],
    ) -> list[DecisionJourneyStep]:
        evidence_by_fact = {
            fact.design_fact_id: self._evidence_for_fact(
                fact_id=fact.design_fact_id,
                fact_utterance_ids=fact_utterance_ids,
                utterance_by_id=utterance_by_id,
            )
            for fact in facts
        }

        def first_seen(fact: Any) -> datetime:
            evidence = evidence_by_fact[fact.design_fact_id]
            return evidence[0].timestamp if evidence else fact.created_at

        final_id = decision_fact.design_fact_id if decision_fact else None
        # 논의 순서는 fact 가 저장된 시각이 아니라 근거 발화가 나온 시각으로 정한다.
        # 배치는 몇 분씩 묶어 돌기 때문에 저장 시각은 실제 발언 순서와 다르다.
        # 최종 결정은 흐름의 결론이므로 항상 마지막에 둔다.
        ordered = sorted(
            facts,
            key=lambda fact: (
                fact.design_fact_id == final_id,
                first_seen(fact),
                str(fact.design_fact_id),
            ),
        )
        order_index = {fact.design_fact_id: index for index, fact in enumerate(ordered)}
        fact_type_by_id = {fact.design_fact_id: fact.fact_type for fact in facts}

        steps: list[DecisionJourneyStep] = []
        for fact in ordered:
            evidence = evidence_by_fact[fact.design_fact_id]
            primary = evidence[0] if evidence else None
            steps.append(
                DecisionJourneyStep(
                    type=self._step_type(
                        fact=fact,
                        links=links,
                        order_index=order_index,
                        fact_type_by_id=fact_type_by_id,
                    ),
                    fact_type=fact.fact_type,
                    fact_status=fact.status,
                    design_fact_id=fact.design_fact_id,
                    summary=fact.content,
                    linked_to_decision=fact.design_fact_id in linked_ids,
                    utterance_id=primary.utterance_id if primary else None,
                    speaker_id=primary.speaker_id if primary else None,
                    nickname=primary.nickname if primary else None,
                    timestamp=primary.timestamp if primary else None,
                    evidence=evidence,
                )
            )
        return steps

    @staticmethod
    def _step_type(
        *,
        fact: Any,
        links: list[Any],
        order_index: dict[UUID, int],
        fact_type_by_id: dict[UUID, DesignFactType],
    ) -> str:
        if fact.fact_type != DesignFactType.PROPOSAL:
            return _STEP_TYPE_BY_FACT_TYPE[fact.fact_type]
        # 먼저 나온 제안·결정과 충돌하는 제안이면 대안으로 본다.
        if fact.status in {DesignFactStatus.REJECTED, DesignFactStatus.SUPERSEDED}:
            return "ALTERNATIVE"
        for link in links:
            if link.link_type != DesignFactLinkType.CONFLICTS_WITH:
                continue
            if fact.design_fact_id not in (link.from_fact_id, link.to_fact_id):
                continue
            other_id = (
                link.to_fact_id
                if link.from_fact_id == fact.design_fact_id
                else link.from_fact_id
            )
            if fact_type_by_id.get(other_id) not in {
                DesignFactType.PROPOSAL,
                DesignFactType.DECISION,
            }:
                continue
            if order_index.get(other_id, -1) < order_index[fact.design_fact_id]:
                return "ALTERNATIVE"
        return "PROPOSAL"

    @staticmethod
    def _evidence_for_fact(
        *,
        fact_id: UUID,
        fact_utterance_ids: dict[UUID, list[UUID]],
        utterance_by_id: dict[UUID, UtteranceView],
    ) -> list[ReportUtteranceEvidence]:
        seen: set[UUID] = set()
        evidence: list[ReportUtteranceEvidence] = []
        for utterance_id in fact_utterance_ids.get(fact_id, []):
            # 회의 종료 이후 발화나 다른 Topic 으로 옮겨진 발화는 utterance_by_id 에 없다.
            utterance = utterance_by_id.get(utterance_id)
            if utterance is None or utterance_id in seen:
                continue
            seen.add(utterance_id)
            evidence.append(
                ReportUtteranceEvidence(
                    utterance_id=utterance.utterance_id,
                    speaker_id=utterance.user_id,
                    nickname=utterance.nickname,
                    text=utterance.text,
                    timestamp=utterance.created_at,
                )
            )
        return sorted(evidence, key=lambda item: item.timestamp)

    # -------------------------
    # 근거
    # -------------------------

    @staticmethod
    def _decision_rationale(
        *,
        rationale_memory: Any | None,
        decision_fact: Any | None,
        fact_by_id: dict[UUID, Any],
        links: list[Any],
    ) -> str | None:
        if rationale_memory is not None:
            return rationale_memory.content
        if decision_fact is None:
            return None
        contents = [
            fact_by_id[link.from_fact_id].content
            for link in links
            if link.to_fact_id == decision_fact.design_fact_id
            and link.link_type in _RATIONALE_LINK_TYPES
            and fact_by_id[link.from_fact_id].fact_type in _RATIONALE_FACT_TYPES
        ]
        unique = list(dict.fromkeys(contents))
        return " / ".join(unique) if unique else None

    @staticmethod
    def _decision_evidence(
        *,
        decision_fact: Any | None,
        decision_memory: Any | None,
        rationale_memory: Any | None,
        fact_by_id: dict[UUID, Any],
        links: list[Any],
        fact_utterance_ids: dict[UUID, list[UUID]],
        utterance_by_id: dict[UUID, UtteranceView],
    ) -> DecisionEvidence:
        if decision_fact is None and decision_memory is None:
            return DecisionEvidence()

        fact_ids: list[UUID] = []
        if decision_fact is not None:
            fact_ids.append(decision_fact.design_fact_id)
            for link in links:
                if link.to_fact_id == decision_fact.design_fact_id:
                    fact_ids.append(link.from_fact_id)
                elif link.from_fact_id == decision_fact.design_fact_id:
                    # RESOLVES 처럼 결정이 source 인 링크(해소한 쟁점)도 근거로 싣는다.
                    fact_ids.append(link.to_fact_id)
        if decision_memory is not None:
            fact_ids.extend(
                fact.design_fact_id
                for fact in fact_by_id.values()
                if fact.semantic_memory_id == decision_memory.semantic_memory_id
            )
        fact_ids = list(dict.fromkeys(fact_ids))

        utterance_ids = [
            utterance_id
            for fact_id in fact_ids
            for utterance_id in fact_utterance_ids.get(fact_id, [])
            if utterance_id in utterance_by_id
        ]
        memory_ids = [
            memory.semantic_memory_id
            for memory in (decision_memory, rationale_memory)
            if memory is not None
        ]
        memory_ids.extend(
            fact_by_id[fact_id].semantic_memory_id
            for fact_id in fact_ids
            if fact_by_id[fact_id].semantic_memory_id is not None
        )
        return DecisionEvidence(
            supporting_utterance_ids=list(dict.fromkeys(utterance_ids)),
            supporting_design_fact_ids=fact_ids,
            supporting_semantic_memory_ids=list(dict.fromkeys(memory_ids)),
        )


def _vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    vector = [float(item) for item in value]
    return vector or None
