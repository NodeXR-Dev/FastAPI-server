# NodeXR FastAPI Server

XR 협업 회의에서 발생하는 발화를 Agentic AI가 구조화하고, semantic memory와 node graph로 연결하는 AI 협업 백엔드 서버입니다.

## 1. Problem

XR 회의에서는 아이디어, 결정사항, 제약조건, 논쟁점이 빠르게 흘러가지만 회의 후 맥락이 사라지기 쉽습니다. NodeXR은 회의 발화를 실시간으로 수집하고, AI Agent가 이를 구조화해 팀이 다시 활용할 수 있는 지식으로 저장합니다.

## 2. Key Features

- Room / User / RoomMember 기반 XR 협업 세션 관리
- Utterance 수집 및 semantic memory 구조화
- Design facts, Decisions, Constraints, Conflicts 기반 회의 맥락 저장
- 트리거 워드 기반 기능 요청 : 2D, 3D 생성 요청 / 결정, 제약 근거 요청 / 갈등 찬반 근거 요청
- 발화 가이드 : Topic Drift, 논리적 모순 발생 시
- Node graph 생성 및 수정 이벤트 처리
- 2D/3D AI generation을 통한 의견 시각화
- Node graph 히스토리 조회
  
## 3. Tech Stack
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- AI: LangChain, OpenAI, Google GenAI, MeshyAI, sentence-transformers, 
- DB: PostgreSQL, pgvector
- Storage: MinIO
- Infra: Docker, Docker Compose
- Realtime: WebSocket
  
## 4. Architecture
<img width="322" height="233" alt="Screenshot 2026-05-22 at 11 22 05" src="https://github.com/user-attachments/assets/3e019e70-234e-4cd8-8afc-5cb39c238638" />

## 5. ERD
<img width="757" height="594" alt="Screenshot 2026-05-31 at 14 05 06" src="https://github.com/user-attachments/assets/b6538fc6-efe1-42da-adf8-6cdf9bd5fc5f" />

## 6. WebSocket Events

| Direction | Event | Description |
|---|---|---|
| Client → Server | UTTERANCE_CREATE | 회의 발화 생성 |
| Client → Server | NODE_MOVE | 노드 위치 변경 |
| Client → Server | NODE_TEXT_UPDATE | 노드 텍스트 수정 |
| Client → Server | NODE_DELETE | 노드 삭제 |
| Server → Client | GRAPH_UPDATED | 그래프 변경사항 broadcast |
| Server → Client | AGENT_GUIDE | AI Agent 가이드 전달 |
| Server → Client | 2D_GENERATED | 2D 생성 완료 |
| Server → Client | 3D_GENERATED | 3D 생성 완료 |
| Server → Client | ERROR | 에러 이벤트 |

## 7. Swagger

## 8. Realtime Agent Hot Path

Unity sends an `UTTERANCE_CREATE` event to `/ws/rooms/event`. The server normalizes
and embeds the utterance, persists it, routes it to an ACTIVE topic with pgvector
cosine similarity, updates the topic centroid, and then invokes the short-lived
`RealtimeAgentGraph`.

The graph uses LangChain structured output for multi-trigger classification and
Memory Guard judgement. Rationale and conflict recall are grounded in Top-K
`semantic_memories` / `design_facts` retrieval plus SQLAlchemy relationship and
source-utterance traversal. Independent trigger branches run in parallel. 2D/3D
generation is only enqueued through the existing generation services; the graph
does not wait for the external generation job to finish.

Realtime tuning variables:

```dotenv
TOPIC_SIMILARITY_THRESHOLD=0.75
AGENT_RETRIEVAL_TOP_K=5
MEMORY_GUARD_ALERT_THRESHOLD=0.8
AGENT_LLM_MODEL=gpt-4.1-mini
AGENT_LLM_TIMEOUT_SECONDS=10
```

LangSmith tracing is optional. When it is disabled or the variables are absent,
the realtime flow continues without exporting traces.

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=NodeXR-realtime-agent
# Optional for self-hosted LangSmith
LANGSMITH_ENDPOINT=
```

The trace tree includes `RealtimeUtteranceHotPath`, `embedding`,
`topic_routing`, `RealtimeAgentGraph`, `classify_triggers`, the selected nested
subgraphs and their retrieval/LLM nodes, and `persist_and_notify`. Trace metadata
contains IDs and graph names, not a duplicate of the full utterance text.

## 9. Reflection Batch Cold Path

The application lifespan starts a five-minute Reflection scheduler. It selects
`NOREFLECT` utterances and graph events whose `processed_at` is null; selection is
not limited to the latest five minutes. A PostgreSQL advisory lock prevents two
workers from reflecting the same room concurrently.

`ReflectionBatchGraph` retrieves topic-scoped facts and memories, analyzes the
batch with structured output, validates provenance and relationship rules,
performs vector-first fact deduplication, proposes semantic memories and changed
topic summaries, then delegates all writes to one service transaction. Utterances
become `REFLECT` and graph events receive `processed_at` only after every fact,
link, memory, and topic write succeeds.

```dotenv
REFLECTION_BATCH_ENABLED=true
REFLECTION_BATCH_INTERVAL_SECONDS=300
REFLECTION_BATCH_MAX_UTTERANCES=200
REFLECTION_BATCH_MAX_GRAPH_EVENTS=200
REFLECTION_FACT_TOP_K=100
REFLECTION_MEMORY_TOP_K=50
BATCH_FACT_MIN_CONFIDENCE=0.65
BATCH_LINK_MIN_CONFIDENCE=0.65
FACT_DEDUP_SIMILARITY_THRESHOLD=0.82
```

The batch reuses `AGENT_LLM_MODEL`, `AGENT_LLM_TIMEOUT_SECONDS`, and the existing
LangSmith project. Traces are distinguished with `reflection-batch` and
`cold-path` tags.

Apply the Reflection tracking migration before enabling the scheduler:

```bash
PYTHONPATH=. alembic -c app/alembic.ini upgrade head
```
