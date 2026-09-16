from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.node.meeting_report_node import MeetingReportNode
from app.agent.schema.meeting_report_schema import (
    InferredTopicDecision,
    TopicDecisionContext,
    TopicFactContext,
)
from app.core.config import settings
from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.model.enum import DialogueMove, MeetingReportStatus
from app.model.report import MeetingReport
from app.repository.asset_repository import AssetRepository
from app.repository.graph_repository import GraphRepository
from app.repository.meeting_report_repository import MeetingReportRepository
from app.repository.report_repository import ReportRepository
from app.repository.room_repository import RoomRepository
from app.repository.topic_repository import TopicRepository
from app.schema.report.meeting_report import (
    ContributionScoring,
    FinalDecision,
    FinalOutcome,
    MeetingOverview,
    MeetingReportData,
    OverallParticipation,
    ReportGraphEdge,
    ReportGraphNode,
    TopicReport,
)
from app.schema.report.response import MeetingReportLinkResponse
from app.service.report.conclusion_contribution_calculator import (
    CONCLUSION_RELEVANCE_WEIGHT,
    INFORMATION_VALUE_WEIGHT,
    REASONING_INFLUENCE_WEIGHT,
    ConclusionContributionCalculator,
)
from app.service.report.decision_journey_builder import (
    DecisionJourneyBuilder,
    TopicDecisionAnalysis,
    UtteranceView,
)
from app.service.report.graph_snapshot_layout import GraphLayout, layout_graph
from app.service.utterance.embedding_service import EmbeddingService

logger = get_logger(__name__)

# LLM 에 Topic 하나당 넘기는 fact 상한. 긴 회의에서 프롬프트가 무한정 커지지 않게 한다.
_INFERENCE_FACT_LIMIT = 30


@dataclass
class MeetingReportInputs:
    """생성 1단계(DB 조회)의 결과. 세션을 닫은 뒤에도 쓸 수 있게 ORM 객체를 담지 않는다."""

    report_id: UUID
    room_id: UUID
    report_version: int
    room_topic: str
    started_at: datetime | None
    ended_at: datetime
    last_utterance_at: datetime | None
    participant_counts: list[tuple[UUID, str, int]]
    final_outcome: FinalOutcome | None
    utterances_by_topic: dict[UUID, list[UtteranceView]]
    analyses: list[TopicDecisionAnalysis]
    topic_centroids: dict[UUID, list[float] | None]
    dialogue_moves: dict[UUID, DialogueMove]
    inference_contexts: list[TopicDecisionContext] = field(default_factory=list)


@dataclass
class MeetingReportPage:
    report: MeetingReport
    report_url: str
    data: MeetingReportData | None
    graph_layout: GraphLayout | None


class MeetingReportService:
    def __init__(
        self,
        *,
        meeting_report_repository: MeetingReportRepository | None = None,
        topic_repository: TopicRepository | None = None,
        room_repository: RoomRepository | None = None,
        report_repository: ReportRepository | None = None,
        asset_repository: AssetRepository | None = None,
        graph_repository: GraphRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        journey_builder: DecisionJourneyBuilder | None = None,
        contribution_calculator: ConclusionContributionCalculator | None = None,
        report_node: MeetingReportNode | None = None,
    ) -> None:
        self.meeting_report_repository = (
            meeting_report_repository or MeetingReportRepository()
        )
        self.topic_repository = topic_repository or TopicRepository()
        self.room_repository = room_repository or RoomRepository()
        self.report_repository = report_repository or ReportRepository()
        self.asset_repository = asset_repository or AssetRepository()
        self.graph_repository = graph_repository or GraphRepository()
        self.embedding_service = embedding_service or EmbeddingService()
        self.journey_builder = journey_builder or DecisionJourneyBuilder()
        self.contribution_calculator = (
            contribution_calculator or ConclusionContributionCalculator()
        )
        # OpenAI 클라이언트는 실제로 추론이 필요할 때 만든다.
        self._report_node = report_node

    # =========================
    # 리포트 요청
    # GET /report/{room_id}, POST /api/rooms/{room_id}/end
    # =========================
    def request_report(
        self,
        db: Session,
        *,
        room_id: UUID,
        user_id: UUID | None,
        base_url: str | None,
        requested_at: datetime | None = None,
    ) -> MeetingReportLinkResponse:
        """리포트 행을 확보하고 URL 을 돌려준다. 생성은 BackgroundTasks 가 한다.

        중복 종료 요청 처리
        - 생성 중(PENDING/GENERATING)  → 같은 리포트를 돌려준다.
        - 실패(FAILED)                 → 같은 리포트를 PENDING 으로 되돌린다(URL 유지).
        - 완료 후 회의가 이어지지 않음 → 같은 리포트를 돌려준다.
        - 완료 후 발화/그래프가 더 생김 → report_version 을 올려 새로 만든다.
        rooms 행을 FOR UPDATE 로 잡아 같은 방의 동시 요청을 줄 세우고,
        (room_id, report_version) unique 제약이 마지막 방어선이다.

        user_id 가 없으면(GET /report/{room_id}) 멤버 확인과 완료 WS 를 생략한다.
        """
        now = requested_at or datetime.now(timezone.utc)

        room = self.topic_repository.lock_room(db, room_id=room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        if user_id is not None and not any(
            member.user_id == user_id for member in room.members
        ):
            raise NotFoundException(code=ResponseCode.ROOM_MEMBER404)

        latest = self.meeting_report_repository.find_latest_by_room(db, room_id=room_id)
        decision = "reuse"
        if latest is None:
            report = self._create_report(db, room=room, user_id=user_id, version=1, now=now)
            decision = "create"
        elif latest.status == MeetingReportStatus.FAILED:
            report = self.meeting_report_repository.reset_to_pending(
                db,
                report=latest,
                requested_by_user_id=user_id,
            )
            decision = "retry_failed"
        elif (
            latest.status == MeetingReportStatus.COMPLETED
            and self.meeting_report_repository.has_activity_after(
                db,
                room_id=room_id,
                after=latest.meeting_ended_at,
            )
        ):
            report = self._create_report(
                db,
                room=room,
                user_id=user_id,
                version=latest.report_version + 1,
                now=now,
            )
            decision = "create_next_version"
        else:
            report = latest

        db.commit()

        logger.info(
            "[meeting_report_requested] room_id=%s | user_id=%s | report_id=%s "
            "| report_version=%s | status=%s | decision=%s",
            room_id,
            user_id,
            report.meeting_report_id,
            report.report_version,
            report.status.value,
            decision,
        )
        return self._link_response(report=report, base_url=base_url)

    def get_report_link(
        self,
        db: Session,
        *,
        report_id: UUID,
        base_url: str | None,
    ) -> MeetingReportLinkResponse | None:
        report = self.meeting_report_repository.find_by_id(db, report_id=report_id)
        if report is None:
            return None
        return self._link_response(report=report, base_url=base_url)

    @staticmethod
    def build_report_url(*, report_id: UUID, base_url: str | None) -> str:
        """{PUBLIC_BASE_URL}/reports/{report_id}.

        PUBLIC_BASE_URL 이 없으면 종료 요청이 들어온 주소를 쓴다. 둘 다 없으면 상대 경로다.
        """
        base = (settings.PUBLIC_BASE_URL or base_url or "").rstrip("/")
        return f"{base}/reports/{report_id}"

    # =========================
    # 백그라운드 생성
    # =========================
    def claim_report(self, db: Session, *, report_id: UUID) -> bool:
        stale_before = datetime.now(timezone.utc) - timedelta(
            seconds=settings.MEETING_REPORT_STALE_SECONDS
        )
        claimed = self.meeting_report_repository.claim_for_generation(
            db,
            report_id=report_id,
            stale_before=stale_before,
        )
        db.commit()
        return claimed

    def load_inputs(self, db: Session, *, report_id: UUID) -> MeetingReportInputs:
        report = self.meeting_report_repository.find_by_id(db, report_id=report_id)
        if report is None:
            raise NotFoundException(code=ResponseCode.REPORT404)
        room = self.room_repository.find_room_by_id(db, report.room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        room_id = report.room_id
        started_at = room.created_at
        ended_at = report.meeting_ended_at

        participant_counts = self.report_repository.find_participant_utterance_counts(
            db=db,
            room_id=room_id,
            started_at=started_at,
            requested_at=ended_at,
            exclude_agent_commands=True,
        )
        last_utterance_at = self.report_repository.find_last_utterance_at(
            db=db,
            room_id=room_id,
            started_at=started_at,
            requested_at=ended_at,
        )

        utterance_rows = self.meeting_report_repository.find_discussion_utterances(
            db,
            room_id=room_id,
            ended_at=ended_at,
        )
        utterance_by_id: dict[UUID, UtteranceView] = {}
        utterances_by_topic: dict[UUID, list[UtteranceView]] = defaultdict(list)
        for utterance, nickname in utterance_rows:
            view = UtteranceView(
                utterance_id=utterance.utterance_id,
                topic_id=utterance.topic_id,
                user_id=utterance.user_id,
                nickname=nickname,
                text=(utterance.original_text or utterance.normalized_text or "").strip(),
                created_at=utterance.created_at,
            )
            utterance_by_id[view.utterance_id] = view
            utterances_by_topic[view.topic_id].append(view)

        facts = self.meeting_report_repository.find_facts(db, room_id=room_id)
        links = self.meeting_report_repository.find_fact_links(db, room_id=room_id)
        fact_utterance_ids: dict[UUID, list[UUID]] = defaultdict(list)
        for link in self.meeting_report_repository.find_fact_utterance_links(
            db,
            fact_ids=[fact.design_fact_id for fact in facts],
        ):
            fact_utterance_ids[link.design_fact_id].append(link.utterance_id)
        memories = self.meeting_report_repository.find_active_memories(db, room_id=room_id)
        annotations = self.meeting_report_repository.find_annotations(
            db,
            utterance_ids=list(utterance_by_id),
            model_version=settings.AGENT_ANNOTATION_SCHEMA_VERSION,
        )

        facts_by_topic: dict[UUID, list] = defaultdict(list)
        for fact in facts:
            facts_by_topic[fact.topic_id].append(fact)
        memories_by_topic: dict[UUID, list] = defaultdict(list)
        for memory in memories:
            memories_by_topic[memory.topic_id].append(memory)

        analyses: list[TopicDecisionAnalysis] = []
        topic_centroids: dict[UUID, list[float] | None] = {}
        inference_contexts: list[TopicDecisionContext] = []
        for topic in self.meeting_report_repository.find_topics(db, room_id=room_id):
            topic_facts = facts_by_topic.get(topic.topic_id, [])
            if not utterances_by_topic.get(topic.topic_id) and not topic_facts:
                continue
            analysis = self.journey_builder.build(
                topic=topic,
                facts=topic_facts,
                links=links,
                fact_utterance_ids=fact_utterance_ids,
                utterance_by_id=utterance_by_id,
                memories=memories_by_topic.get(topic.topic_id, []),
            )
            analyses.append(analysis)
            topic_centroids[topic.topic_id] = (
                [float(value) for value in topic.centroid_embedding]
                if topic.centroid_embedding is not None
                else None
            )
            if analysis.needs_inference:
                inference_contexts.append(
                    TopicDecisionContext(
                        topic_id=topic.topic_id,
                        topic_summary=topic.summary,
                        facts=[
                            TopicFactContext(
                                fact_type=fact.fact_type.value,
                                status=fact.status.value,
                                content=fact.content,
                            )
                            for fact in topic_facts[-_INFERENCE_FACT_LIMIT:]
                        ],
                    )
                )

        final_outcome = self._build_final_outcome(db, room_id=room_id, ended_at=ended_at)

        return MeetingReportInputs(
            report_id=report_id,
            room_id=room_id,
            report_version=report.report_version,
            room_topic=room.topic,
            started_at=started_at,
            ended_at=ended_at,
            last_utterance_at=last_utterance_at,
            participant_counts=participant_counts,
            final_outcome=final_outcome,
            utterances_by_topic=dict(utterances_by_topic),
            analyses=analyses,
            topic_centroids=topic_centroids,
            dialogue_moves={
                annotation.utterance_id: annotation.dialogue_move
                for annotation in annotations
            },
            inference_contexts=inference_contexts,
        )

    async def infer_missing_decisions(
        self,
        inputs: MeetingReportInputs,
    ) -> tuple[dict[UUID, InferredTopicDecision], int]:
        """명시적 결정이 없는 Topic 들만 모아 LLM 을 한 번 부른다. (결과, 호출 횟수)"""
        if not inputs.inference_contexts or not settings.MEETING_REPORT_LLM_ENABLED:
            return {}, 0

        expected_ids = {item.topic_id for item in inputs.inference_contexts}
        try:
            node = self._report_node or MeetingReportNode()
            bundle = await node.infer_decisions(inputs.inference_contexts)
        except Exception as error:
            # 결론 추론은 부가 정보다. 실패해도 리포트는 "결정 없음"으로 완성한다.
            logger.warning(
                "[meeting_report_inference_failed] report_id=%s | topic_count=%s | error=%s",
                inputs.report_id,
                len(expected_ids),
                str(error),
            )
            return {}, 1

        inferred = {
            item.topic_id: item
            for item in bundle.decisions
            if item.topic_id in expected_ids and (item.decision or "").strip()
        }
        logger.info(
            "[meeting_report_inference_completed] report_id=%s | requested_topic_count=%s "
            "| inferred_topic_count=%s",
            inputs.report_id,
            len(expected_ids),
            len(inferred),
        )
        return inferred, 1

    def complete_report(
        self,
        db: Session,
        *,
        inputs: MeetingReportInputs,
        inferred: dict[UUID, InferredTopicDecision],
        llm_call_count: int,
        generated_at: datetime | None = None,
    ) -> MeetingReportData:
        generated_at = generated_at or datetime.now(timezone.utc)
        data = self.build_report_data(
            db,
            inputs=inputs,
            inferred=inferred,
            llm_call_count=llm_call_count,
            generated_at=generated_at,
        )

        report = self.meeting_report_repository.find_by_id(db, report_id=inputs.report_id)
        if report is None:
            raise NotFoundException(code=ResponseCode.REPORT404)
        try:
            self.meeting_report_repository.mark_completed(
                db,
                report=report,
                report_data=data.model_dump_json(),
                final_asset_id=(
                    data.final_outcome.asset_id if data.final_outcome else None
                ),
                final_graph_snapshot_id=(
                    data.final_outcome.graph_snapshot_id if data.final_outcome else None
                ),
                generated_at=generated_at,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        logger.info(
            "[meeting_report_completed] report_id=%s | room_id=%s | report_version=%s "
            "| topic_count=%s | llm_call_count=%s | final_asset_id=%s",
            inputs.report_id,
            inputs.room_id,
            inputs.report_version,
            len(data.topics),
            llm_call_count,
            data.final_outcome.asset_id if data.final_outcome else None,
        )
        return data

    def build_report_data(
        self,
        db: Session,
        *,
        inputs: MeetingReportInputs,
        inferred: dict[UUID, InferredTopicDecision],
        llm_call_count: int,
        generated_at: datetime,
    ) -> MeetingReportData:
        topics: list[TopicReport] = []
        for analysis in inputs.analyses:
            utterances = inputs.utterances_by_topic.get(analysis.topic_id, [])
            final_decision = analysis.final_decision
            decision_rationale = analysis.decision_rationale
            reference_embedding = analysis.decision_embedding

            inference = inferred.get(analysis.topic_id)
            if inference is not None:
                final_decision = FinalDecision(
                    content=inference.decision.strip(),
                    source="LLM_INFERRED",
                )
                decision_rationale = decision_rationale or inference.rationale
                reference_embedding = self.embedding_service.embed_text(
                    final_decision.content
                )

            # 결정이 없는 Topic 은 Topic 중심 벡터와의 유사도로 대신한다.
            if reference_embedding is None:
                reference_embedding = inputs.topic_centroids.get(analysis.topic_id)
            similarities = (
                self.meeting_report_repository.find_utterance_similarities(
                    db,
                    utterance_ids=[item.utterance_id for item in utterances],
                    embedding=reference_embedding,
                )
                if reference_embedding is not None
                else {}
            )

            scores = self.contribution_calculator.score_utterances(
                utterances=utterances,
                similarities=similarities,
                utterance_roles=analysis.utterance_roles,
                dialogue_moves=inputs.dialogue_moves,
                has_decision=final_decision.content is not None,
            )
            topics.append(
                TopicReport(
                    topic_id=analysis.topic_id,
                    title=analysis.title,
                    final_decision=final_decision,
                    decision_rationale=decision_rationale,
                    decision_journey=analysis.journey,
                    evidence=analysis.evidence,
                    meaningful_utterances=self.contribution_calculator.select_meaningful(
                        scores
                    ),
                    decision_contributions=(
                        self.contribution_calculator.aggregate_contributions(scores)
                    ),
                    utterance_count=len(utterances),
                )
            )

        total_utterance_count = sum(count for _, _, count in inputs.participant_counts)
        ended_at = inputs.last_utterance_at or inputs.ended_at
        duration_seconds = (
            max(0, int((ended_at - inputs.started_at).total_seconds()))
            if inputs.started_at is not None
            else 0
        )
        return MeetingReportData(
            report_id=inputs.report_id,
            room_id=inputs.room_id,
            report_version=inputs.report_version,
            generated_at=generated_at,
            overview=MeetingOverview(
                room_topic=inputs.room_topic,
                started_at=inputs.started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                participants=[nickname for _, nickname, _ in inputs.participant_counts],
                total_utterance_count=total_utterance_count,
                topic_count=len(topics),
            ),
            final_outcome=inputs.final_outcome,
            topics=topics,
            overall_participation=[
                OverallParticipation(
                    user_id=user_id,
                    nickname=nickname,
                    utterance_count=count,
                    ratio=(
                        round(count * 100 / total_utterance_count, 2)
                        if total_utterance_count
                        else 0.0
                    ),
                )
                for user_id, nickname, count in inputs.participant_counts
            ],
            scoring=ContributionScoring(
                conclusion_relevance_weight=CONCLUSION_RELEVANCE_WEIGHT,
                reasoning_influence_weight=REASONING_INFLUENCE_WEIGHT,
                information_value_weight=INFORMATION_VALUE_WEIGHT,
            ),
            llm_call_count=llm_call_count,
        )

    def fail_report(self, db: Session, *, report_id: UUID, error_message: str) -> None:
        report = self.meeting_report_repository.find_by_id(db, report_id=report_id)
        if report is None:
            return
        try:
            self.meeting_report_repository.mark_failed(
                db,
                report=report,
                error_message=error_message[:1000],
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    # =========================
    # HTML 페이지
    # GET /reports/{report_id}
    # =========================
    def find_report_page(
        self,
        db: Session,
        *,
        report_id: UUID,
        base_url: str | None,
    ) -> MeetingReportPage | None:
        report = self.meeting_report_repository.find_by_id(db, report_id=report_id)
        if report is None:
            return None

        data = None
        graph_layout = None
        if report.status == MeetingReportStatus.COMPLETED and report.report_data:
            data = MeetingReportData.model_validate_json(report.report_data)
            if data.final_outcome is not None:
                graph_layout = layout_graph(
                    nodes=data.final_outcome.nodes,
                    edges=data.final_outcome.edges,
                )
        return MeetingReportPage(
            report=report,
            report_url=self.build_report_url(report_id=report_id, base_url=base_url),
            data=data,
            graph_layout=graph_layout,
        )

    # -------------------------

    def _create_report(
        self,
        db: Session,
        *,
        room,
        user_id: UUID | None,
        version: int,
        now: datetime,
    ) -> MeetingReport:
        return self.meeting_report_repository.create(
            db,
            room_id=room.room_id,
            report_version=version,
            requested_by_user_id=user_id,
            meeting_started_at=room.created_at,
            meeting_ended_at=now,
        )

    def _link_response(
        self,
        *,
        report: MeetingReport,
        base_url: str | None,
    ) -> MeetingReportLinkResponse:
        return MeetingReportLinkResponse(
            report_id=report.meeting_report_id,
            room_id=report.room_id,
            report_version=report.report_version,
            status=report.status.value,
            report_url=self.build_report_url(
                report_id=report.meeting_report_id,
                base_url=base_url,
            ),
        )

    def _build_final_outcome(
        self,
        db: Session,
        *,
        room_id: UUID,
        ended_at: datetime,
    ) -> FinalOutcome | None:
        """최종 2D 이미지와, 그 이미지를 만들 때 실제로 입력된 그래프.

        최종 이미지는 기존 리포트와 같이 "사용자에게 실제로 전달된(ws_sent_at) 마지막
        2D"다. 근거 그래프는 회의 종료 시점의 최신 스냅샷이 아니라 생성 입력
        스냅샷이다. 입력 스냅샷이 없는 생성(Feature 기반)은 생성 직후 저장된 결과
        스냅샷을 쓰는데, 그것도 생성 시점의 그래프를 담고 있다.
        """
        asset = self.asset_repository.find_latest_ws_sent_2d_asset(
            db,
            room_id=room_id,
            requested_at=ended_at,
        )
        if asset is None:
            return None

        result_snapshot = (
            self.graph_repository.find_graph_snapshot_by_id(
                db=db,
                room_id=room_id,
                graph_snapshot_id=asset.graph_snapshot_id,
            )
            if asset.graph_snapshot_id is not None
            else None
        )
        source_snapshot = None
        if result_snapshot is not None:
            source_snapshot_id = self.graph_repository.find_generation_source_snapshot_id(
                db,
                room_id=room_id,
                result_graph_snapshot_id=result_snapshot.graph_snapshot_id,
            )
            if source_snapshot_id is not None:
                source_snapshot = self.graph_repository.find_graph_snapshot_by_id(
                    db=db,
                    room_id=room_id,
                    graph_snapshot_id=source_snapshot_id,
                )
        basis_snapshot = source_snapshot or result_snapshot

        nodes: list[ReportGraphNode] = []
        edges: list[ReportGraphEdge] = []
        if basis_snapshot is not None:
            nodes, edges = self._graph_from_snapshot(
                self.graph_repository.load_snapshot_data(graph_snapshot=basis_snapshot)
            )

        logger.info(
            "[meeting_report_final_outcome] room_id=%s | asset_id=%s "
            "| source_graph_snapshot_id=%s | result_graph_snapshot_id=%s | node_count=%s",
            room_id,
            asset.asset_id,
            source_snapshot.graph_snapshot_id if source_snapshot else None,
            result_snapshot.graph_snapshot_id if result_snapshot else None,
            len(nodes),
        )
        return FinalOutcome(
            asset_id=asset.asset_id,
            image_url=asset.file_url,
            image_created_at=asset.created_at,
            graph_snapshot_id=basis_snapshot.graph_snapshot_id if basis_snapshot else None,
            graph_snapshot_version=basis_snapshot.version if basis_snapshot else None,
            graph_captured_at=basis_snapshot.created_at if basis_snapshot else None,
            result_graph_snapshot_id=(
                result_snapshot.graph_snapshot_id if result_snapshot else None
            ),
            result_graph_snapshot_version=(
                result_snapshot.version if result_snapshot else None
            ),
            nodes=nodes,
            edges=edges,
        )

    @staticmethod
    def _graph_from_snapshot(
        snapshot_data: dict,
    ) -> tuple[list[ReportGraphNode], list[ReportGraphEdge]]:
        raw_nodes = list(snapshot_data.get("part_nodes") or [])
        raw_edges: list[dict] = []
        for sub_graph in snapshot_data.get("sub_graphs") or []:
            raw_nodes.extend(sub_graph.get("nodes") or [])
            raw_edges.extend(sub_graph.get("edges") or [])

        nodes = [
            ReportGraphNode(
                node_id=str(item["node_id"]),
                node_type=str(item.get("type") or ""),
                node_text=str(item.get("node_text") or ""),
                parent_node_id=(
                    str(item["parent_node_id"]) if item.get("parent_node_id") else None
                ),
                used_in_generation=bool(item.get("used_in_generation")),
            )
            for item in raw_nodes
            if item.get("node_id")
        ]
        edges = [
            ReportGraphEdge(
                edge_id=str(item["edge_id"]),
                from_node_id=str(item["from_node_id"]),
                to_node_id=str(item["to_node_id"]),
                label=item.get("label"),
                used_in_generation=bool(item.get("used_in_generation")),
            )
            for item in raw_edges
            if item.get("edge_id") and item.get("from_node_id") and item.get("to_node_id")
        ]
        return nodes, edges
