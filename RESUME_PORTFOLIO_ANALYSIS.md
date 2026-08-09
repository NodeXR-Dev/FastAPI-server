# 프로젝트 담당 역할 및 고도화 후보 분석

> 분석 대상: PlanWith, NodeXR, QUP  
> 기준일: 2026-08-03  
> 근거: 현재 체크아웃된 코드, Git 커밋·blame, 설정, 테스트 및 저장소 문서

## 평가 기준

- `[FACT]`: 코드·Git 이력·테스트·문서에서 직접 확인한 사실이다.
- `[HYPOTHESIS]`: 구조상 위험은 확인했으나 실제 서비스 영향은 실험이 필요한 가설이다.
- `S/A/B/C`는 구현 난도가 아니라 신입 이력서·포트폴리오에서의 매력도다.
- 측정하지 않은 성능·정확도 수치는 사용하지 않는다. 특히 PlanWith 성능 baseline은 현재 무효화 상태다.

---

# PlanWith

## 현재 구현 흐름

```text
POST /chatbot/messages
→ 사용자 요청 Redis 저장
→ LLM 의도 분석
→ LLM 일정/할 일 JSON 생성
→ DTO 검증 및 승인 토큰 발급
→ 사용자 승인
→ JPA로 일정/할 일 저장
```

## 맡은 기능 TOP

| 순위 | 실제 담당 기능 | 기술 | 코드 근거 | 추천 직무 | 등급 |
|---:|---|---|---|---|:---:|
| 1 | `[FACT]` 자연어를 일정·할 일로 변환하는 2단계 LLM 워크플로 | Spring Boot, OpenAI API, Prompt Engineering | [ChatbotController](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/controller/ChatbotController.java:30>), [ChatbotServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:83>), [ChatGPTServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatGPTServiceImpl.java:27>) | Java/Spring, AI Service | S |
| 2 | `[FACT]` 사용자·토큰 기반 Redis TTL 승인 워크플로 | Redis, JWT 사용자 문맥, TTL | [RedisChatbotUtil](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/RedisChatbotUtil.java:26>), [승인 서비스](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:199>) | Java/Spring Backend | A |
| 3 | `[FACT]` LLM 응답 파싱·검증 후 Event/Todo 도메인 저장 | Jackson, Regex, JPA, Transaction | [ChatbotMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/mapper/ChatbotMapper.java:28>), [저장 흐름](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:228>) | Java/Spring, AI Service | A |
| 4 | `[FACT]` 사용자 의도와 LLM 분류를 결합한 요청 라우팅 | Prompt, enum routing | [의도 분석](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:155>), [LLM 분류](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatGPTServiceImpl.java:54>) | AI Service | A |
| 5 | `[FACT]` Mock OpenAI·JMeter·Actuator·DB/Redis 불변식을 포함한 성능 실험 하네스 | JMeter, Mock API, Actuator | [하네스 README](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/performance/harness/README.md:1>), [실험 선정](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/performance/plans/selected-experiments.md:20>) | Java Performance, SRE | A |
| 6 | `[FACT]` S3·CodeDeploy 배포 자동화 | GitHub Actions, AWS | [gradle.yml](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/.github/workflows/gradle.yml:1>), [appspec.yml](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/appspec.yml:1>) | Backend, DevOps | B |

Git 이력에서는 초기 ChatGPT 연동부터 Redis 승인 상태, JSON·날짜 파싱, 일정·할 일 저장, 의도 분석까지 단계적으로 직접 구현한 흐름이 확인된다.

## 고도화 후보 TOP

| 순위 | ID | 도메인 문제 | 구분 | 추천 직무 | 매력도 |
|---:|---|---|---|---|:---:|
| 1 | PW-01 | 승인 토큰의 원자적 소비·멱등성 | FACT | Java/Spring | S |
| 2 | PW-02 | 다건 Event/Todo 생성의 전체 트랜잭션 | HYPOTHESIS | Java/Spring | S |
| 3 | PW-03 | 직렬·블로킹 LLM 호출의 지연 및 장애 전파 | HYPOTHESIS | Java/Spring, AI Service | S |
| 4 | PW-04 | 정규식 기반 LLM JSON 파싱 | FACT | AI Service | A |
| 5 | PW-05 | LLM 워크플로 품질 평가 데이터셋 부재 | FACT | AI Service/AX | S |
| 6 | PW-06 | 클라이언트 의도와 LLM 의도 간 라우팅 정책 | HYPOTHESIS | AI Service | A |
| 7 | PW-07 | 성능 하네스는 있으나 유효한 기준선·개선 결과 부재 | FACT | Java Performance | A |

### PW-01 — [S][FACT][State/Idempotency] 승인 토큰을 한 번만 소비하도록 만든다

- **관련 코드:** [ChatbotServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:199>), [RedisChatbotUtil](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/RedisChatbotUtil.java:43>)
- **현재 구조:** payload와 token→payload 매핑을 별도 Redis 키에 저장하며, 승인 성공 시 token을 원자적으로 소비하지 않는다. 삭제도 실제 prefix 키와 token 매핑을 일관되게 정리하지 않는다.
- **문제 조건/서비스 영향:** 재전송·두 탭 동시 승인 시 같은 일정이나 할 일이 중복 생성될 수 있다.
- **재현·지표:** 동일 token 동시 요청 N개를 보내 성공 응답 수, DB 중복 행, 잔존 Redis 키, 멱등 응답률을 측정한다.
- **대안:** Redis Lua/`GETDEL`; DB idempotency key+unique constraint; `PENDING→PROCESSING→COMPLETED` 상태 머신과 분산락.
- **포트폴리오 서사:** 가능. 재전송 위험→동시성 테스트→원자적 소비 방식 비교→중복 0건 검증→Redis 단독 복구 한계를 설명한다.
- **난이도/직무:** 중상 / Java·Spring, Redis.

### PW-02 — [S][HYPOTHESIS][Transaction] Event/Todo 다건 저장을 all-or-nothing으로 만든다

- **관련 코드:** [다건 저장](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:228>), [Todo 트랜잭션](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/todo/service/PersonalTodoServiceImpl.java:36>)
- **현재 구조:** 승인 orchestration에는 전체 트랜잭션이 없고 각 항목 생성이 개별 트랜잭션이다.
- **문제 조건/서비스 영향:** N번째 저장 실패 시 사용자는 전체 실패를 받지만 이전 항목은 커밋될 가능성이 있다.
- **재현·지표:** N번째 저장 fault injection 후 최종 행 수, 부분 커밋률, rollback 불변식을 검증한다.
- **대안:** orchestration 단일 `@Transactional`; 전체 사전 검증 후 `saveAll`; staging 상태 후 완료 시 활성화.
- **포트폴리오 서사:** 가능. 부분 커밋 재현→경계 재설계→fault injection→긴 트랜잭션의 tradeoff를 다룬다.
- **난이도/직무:** 중 / Java·Spring Backend.

### PW-03 — [S][HYPOTHESIS][Performance] 직렬 OpenAI 호출의 임계 경로를 줄인다

- **관련 코드:** [의도·생성 호출](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:155>), [RestTemplate 호출](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatGPTServiceImpl.java:36>), [OpenAIConfig](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/config/OpenAIConfig.java:14>)
- **현재 구조:** 의도 분류 후 생성 호출을 동기·직렬 수행하며 명시적 connect/read timeout, retry, circuit breaker가 없다.
- **문제 조건/서비스 영향:** 외부 API 지연·5xx와 동시 요청 증가 시 요청 스레드와 tail latency가 증가할 수 있다.
- **재현·지표:** Mock OpenAI에 지연·실패를 주입해 p50/p95/p99, 처리량, Tomcat busy thread, 회복 시간, 외부 호출 수를 측정한다.
- **대안:** 의도+결과 structured call 통합; 확실한 client intent는 분류 생략; async job; timeout·retry+jitter·circuit breaker·bulkhead.
- **포트폴리오 서사:** 매우 좋음. 기존 성능 하네스를 이용해 전후 측정이 가능하며, 호출 통합의 프롬프트 복잡도 tradeoff도 설명할 수 있다.
- **난이도/직무:** 중상 / Java Performance, AI Service.

### PW-04 — [A][FACT][Structured Output] 정규식 JSON 추출을 스키마 계약으로 교체한다

- **관련 코드:** [ChatbotMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/mapper/ChatbotMapper.java:133>)
- **현재 구조:** greedy `\{.*\}` 정규식으로 JSON처럼 보이는 부분을 추출한다.
- **문제 조건/서비스 영향:** 코드 펜스, 설명 문장, 복수 JSON, 중괄호 문자열, truncation에서 파싱 실패나 오인 가능성이 있다.
- **재현·지표:** adversarial corpus로 parse 성공률, schema validity, task exact match, repair 횟수를 측정한다.
- **대안:** provider JSON Schema; function/tool calling; bounded parser+schema validation+제한적 repair.
- **포트폴리오 서사:** 가능. 출력 계약 강화와 SDK·모델 종속성의 tradeoff를 설명한다.
- **난이도/직무:** 중 / AI Service.

### PW-05 — [S][FACT][AI Evaluation] 챗봇 품질 회귀 데이터셋을 만든다

- **관련 코드:** [생성 흐름](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:83>), [의도 분류](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatGPTServiceImpl.java:54>)
- **현재 구조:** 의도·날짜·일정·할 일 결과를 평가하는 golden dataset과 자동 품질 gate가 없다.
- **문제 조건/서비스 영향:** prompt/model 변경의 개선·회귀 여부를 재현 가능한 근거로 판단할 수 없다.
- **재현·지표:** intent macro-F1, 날짜 정확도, schema validity, item exact/partial match, hallucinated field, latency·token cost.
- **대안:** 수작업 golden set+deterministic scorer; 합성/adversarial set+사람 검수; model judge와 규칙 기반 판정 병행.
- **포트폴리오 서사:** 매우 좋음. 모델 연동 경험을 평가·운영 경험으로 발전시킨다.
- **난이도/직무:** 중상 / AI Service, AX.

### PW-06 — [A][HYPOTHESIS][Routing] 의도 분류 호출의 필요성과 우선순위를 검증한다

- **관련 코드:** [analyzeIntention](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/src/main/java/com/JAI/chatbot/service/ChatbotServiceImpl.java:155>)
- **현재 구조:** client intent와 LLM intent의 책임 경계가 혼재한다.
- **문제 조건/서비스 영향:** 둘의 판단이 다르거나 의도가 이미 명확할 때 불필요한 비용·지연 또는 오분류가 생길 수 있다.
- **재현·지표:** client-first, LLM-first, hybrid의 정확도, disagreement rate, 호출 수, latency, token cost를 비교한다.
- **대안:** client authoritative+예외 분류; LLM authoritative; 규칙/확신도 hybrid.
- **포트폴리오 서사:** 가능. 정확도와 비용·지연 사이의 정책 선택을 설명한다.
- **난이도/직무:** 중 / AI Service.

### PW-07 — [A][FACT][Performance Evidence] 실험을 유효한 전·후 결과로 완성한다

- **관련 코드:** [state.md](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/performance/state.md:1>), [baseline manifest](</Users/jeongsoeun/Desktop/Life/coding/Project/PlanWith/performance/plans/baseline-source-manifest.json:97>)
- **현재 구조:** Mock OpenAI, JMeter, Redis key ledger, DB 불변식은 있으나 baseline은 `INVALIDATED`, measured run은 미실행 상태다.
- **서비스 문제:** 실험 설계는 있으나 이력서에 쓸 실제 개선 증거가 없다.
- **재현·지표:** frozen source 기준 baseline을 만들고 PW-01/PW-03 전후 latency, throughput, error, DB/Redis invariant를 비교한다.
- **대안:** 현재 하네스 유지; Testcontainers+WireMock; k6/Gatling+Micrometer trace.
- **포트폴리오 서사:** 조건부로 매우 좋다. 유효한 반복 측정이 나온 뒤에만 숫자를 사용한다.
- **난이도/직무:** 중 / Java Performance, SRE.

---

# NodeXR

## 현재 구현 흐름

```text
WebSocket utterance
→ embedding/topic routing
→ Realtime LangGraph
→ MemoryGuard·Rationale·Conflict·Asset 병렬 분기
→ DB 저장 및 WebSocket 전송

5분 Reflection scheduler
→ 미처리 utterance/event 조회
→ retrieval·분석·검증·dedup
→ semantic memory/topic summary 원자적 저장

Generation API/Agent tool
→ process-local background task
→ OpenAI prompt/Gemini 또는 Meshy
→ MinIO
→ Asset·GraphEvent·snapshot
→ WebSocket 완료 이벤트
```

## 맡은 기능 TOP

| 순위 | 실제 담당 기능 | 기술 | 코드 근거 | 추천 직무 | 등급 |
|---:|---|---|---|---|:---:|
| 1 | `[FACT]` 다중 trigger를 병렬 실행하는 실시간 Agent Graph | FastAPI, LangGraph, structured output, asyncio | [RealtimeAgentGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/graph/realtime_agent_graph.py:25), [TriggerRouterNode](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/node/trigger_router_node.py:12) | AI Agent, Python | S |
| 2 | `[FACT]` 5분 배치 Reflection·semantic memory 파이프라인 | LangGraph, pgvector, advisory lock, provenance | [ReflectionScheduler](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/agent/reflection_scheduler.py:21), [ReflectionBatchGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/graph/reflection_batch_graph.py:23) | AI Agent/AX | S |
| 3 | `[FACT]` pgvector topic routing 및 grounded memory retrieval | PostgreSQL, pgvector | [TopicRoutingService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/utterance/topic_routing_service.py:31), [MemoryRepository](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/memory_repository.py:270) | AI Service, Python | S |
| 4 | `[FACT]` graph mutation·soft cascade·snapshot·history 복구 | SQLAlchemy, graph domain, WebSocket | [GraphInteractionService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/graph/graph_interaction_service.py:27), [GraphRepository](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/graph_repository.py:1197) | Python Backend | S |
| 5 | `[FACT]` utterance·graph·generation job WebSocket 프로토콜 | FastAPI WebSocket | [ws_room_event](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/api/ws_room_event.py:51), [ConnectionManager](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/websocket/connection_manager.py:24) | Realtime Backend | A |
| 6 | `[FACT]` OpenAI→Gemini→MinIO→graph event 2D 생성 | OpenAI, Gemini, MinIO, 보상 삭제 | [Image2DAssetGenerationService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/generation/image_2d_asset_generation_service.py:22), [GeminiImageClient](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/generation/gemini_image_client.py:27) | AI Service, Python | S |
| 7 | `[FACT]` Meshy polling·GLB 검증·MinIO 3D 생성 | httpx, polling, GLB | [Model3DGenerationService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/generation/model_3d_generation_service.py:80), [MeshyClient](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/generation/meshy_client.py:27) | AI Service, Python | S |
| 8 | `[FACT]` Part Node CRUD와 기존 graph mutation 서비스 통합 | FastAPI, SQLAlchemy | [PartNodeService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/graph/part_node_service.py:1), [공유 mutation 서비스](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/graph/graph_interaction_service.py:27) | Python Backend | A |

NodeXR의 강점은 단순 LLM 호출보다 trigger별 실패 격리, grounded ID/provenance, MinIO 보상 삭제, Reflection advisory lock, REST·WebSocket의 graph mutation 공유에 있다.

## 고도화 후보 TOP

| 순위 | ID | 도메인 문제 | 구분 | 추천 직무 | 매력도 |
|---:|---|---|---|---|:---:|
| 1 | NX-01 | process-local 장기 generation job 유실·중복·복구 | HYPOTHESIS | Python, AI Service | S |
| 2 | NX-02 | Agent 품질 평가 데이터셋·회귀 gate 부재 | FACT | AI Agent/AX | S |
| 3 | NX-03 | async WebSocket 안의 동기 SQLAlchemy | HYPOTHESIS | Python/FastAPI | S |
| 4 | NX-04 | multi-instance 메모리 기반 WebSocket 전달 | HYPOTHESIS | Python Realtime | S |
| 5 | NX-05 | graph version 생성 동시성 | HYPOTHESIS | Python Backend | S |
| 6 | NX-06 | 전체 graph JSON snapshot 선형 비용·저장 증가 | HYPOTHESIS | Python Backend | A |
| 7 | NX-07 | semantic retrieval 품질과 pgvector 확장성 | HYPOTHESIS | AI Agent/AI Infra | S |
| 8 | NX-08 | Reflection batch context·token·backlog 증가 | HYPOTHESIS | AI Agent/AX | A |

### NX-01 — [S][HYPOTHESIS][Job Reliability] generation job을 durable workflow로 만든다

- **관련 코드:** [generation API](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/api/generation.py:46), [AssetGenerationAdapter](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/agent/asset_generation_adapter.py:17), [MeshyClient](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/generation/meshy_client.py:27)
- **현재 구조:** FastAPI `BackgroundTasks`/`asyncio.create_task`를 사용하고 Agent task 참조와 Meshy task ID가 process memory에만 있다. MinIO 업로드 후 DB 실패 시 보상 삭제, timeout·GLB 검증은 이미 구현되어 있다.
- **문제 조건/서비스 영향:** 202 직후 배포, 외부 task 생성 후 재시작, DB commit 후 WS 실패, 동일 요청 재전송 시 작업 유실·중복·고아 객체가 생길 수 있다.
- **재현·지표:** 단계별 kill-point로 completion rate, recovery time, duplicate asset, orphan object, retry 횟수, WS 완료 지연을 측정한다.
- **대안:** `GenerationJob`+provider ID+lease DB worker; Celery/RQ/Arq; provider webhook; workflow engine+outbox.
- **포트폴리오 서사:** 최상. process-local 비동기→장애 재현→durable state machine→retry·보상·outbox→at-least-once tradeoff.
- **난이도/직무:** 상 / Python Backend, AI Platform.

### NX-02 — [S][FACT][Agent Evaluation] Agent graph를 단계별·종단간 평가한다

- **관련 코드:** [RealtimeAgentGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/graph/realtime_agent_graph.py:46), [MemoryGuardGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/subgraph/memory_guard_graph.py:17), [ReflectionBatchGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/graph/reflection_batch_graph.py:23)
- **현재 구조:** structured output·grounded ID·provenance 단위 테스트는 많지만 실제 대화 corpus 품질 baseline은 없다.
- **문제 조건/서비스 영향:** prompt/model 변경, 복수 trigger, 근거 없는 conflict, 잘못된 tool 실행의 회귀를 정량 판단하기 어렵다.
- **재현·지표:** trigger macro-F1, guard precision/recall, citation precision, conflict FP, relation F1, tool exact match, invalid output, latency·cost.
- **대안:** node별 deterministic eval; 전체 대화 replay; 사람 평가+model judge, ID/tool은 규칙 검증.
- **포트폴리오 서사:** 최상. Agent 구현을 품질·회귀·비용 운영 경험으로 발전시킨다.
- **난이도/직무:** 상 / AI Agent, AX.

### NX-03 — [S][HYPOTHESIS][Async Performance] WebSocket event loop에서 동기 DB 작업을 격리한다

- **관련 코드:** [ws session](</Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/api/ws_room_event.py:111>), [AutoUtteranceService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/utterance/auto_utterance_service.py:49)
- **현재 구조:** async handler에서 sync SQLAlchemy와 sync graph/repository 호출을 실행한다. embedding·Gemini·일부 retrieval은 이미 `to_thread`로 격리했다.
- **문제 조건/서비스 영향:** DB 지연과 동시 연결 증가 시 한 요청의 I/O가 다른 연결의 heartbeat·메시지 처리까지 막을 수 있다.
- **재현·지표:** DB 지연과 100~500 연결로 loop lag, WS p95/p99, throughput, missed heartbeat, pool wait를 측정한다.
- **대안:** SQLAlchemy async+asyncpg; bounded thread executor; ingress와 mutation worker queue 분리.
- **포트폴리오 서사:** 매우 좋음. 전체 async 전환과 점진적 격리의 비용을 비교한다.
- **난이도/직무:** 상 / Python·FastAPI.

### NX-04 — [S][HYPOTHESIS][Realtime Scaling] WebSocket 전달을 프로세스 경계 밖으로 확장한다

- **관련 코드:** [ConnectionManager](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/websocket/connection_manager.py:24)
- **현재 구조:** room/user별 연결 목록이 프로세스 메모리에만 있다.
- **문제 조건/서비스 영향:** worker 2개 이상, 수평 확장, job worker와 연결 프로세스가 다른 경우 이벤트가 도달하지 않을 수 있다.
- **재현·지표:** 2개 worker에 연결·mutation을 분산해 delivery rate, duplicate rate, cross-instance lag, reconnect recovery를 측정한다.
- **대안:** Redis Pub/Sub; Redis Streams/Kafka; sticky session+status polling; DB outbox+broadcaster.
- **포트폴리오 서사:** 가능. Pub/Sub 유실 가능성과 durable stream 비용을 비교한다.
- **난이도/직무:** 상 / Realtime Backend.

### NX-05 — [S][HYPOTHESIS][Graph Consistency] room 단위 graph version을 직렬화한다

- **관련 코드:** [snapshot version](</Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/graph_repository.py:1197>), [GraphSnapshot model](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/model/graph.py:244)
- **현재 구조:** `max(version)+1`이지만 room mutation lock과 `(room_id, version)` unique constraint가 없다.
- **문제 조건/서비스 영향:** 같은 room의 동시 mutation에서 중복 version, 순서 왜곡, 부정확한 history 가능성이 있다.
- **재현·지표:** barrier 동시 트랜잭션으로 duplicate version, ordering, graph invariant, retry/rollback률을 측정한다.
- **대안:** room row/advisory lock; unique+retry; `room.version` optimistic CAS; room별 mutation queue.
- **포트폴리오 서사:** 매우 좋음. isolation과 optimistic/pessimistic locking의 처리량 tradeoff를 설명한다.
- **난이도/직무:** 상 / Python Backend, Database.

### NX-06 — [A][HYPOTHESIS][Graph Performance] mutation마다 생성하는 전체 snapshot 비용을 줄인다

- **관련 코드:** [snapshot builder](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/graph_repository.py:1197), [mutation service](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/graph/graph_interaction_service.py:27)
- **현재 구조:** graph-visible mutation마다 active node/edge 전체를 읽어 JSON snapshot으로 저장한다.
- **문제 조건/서비스 영향:** 수천 node/edge와 잦은 변경에서 latency, read/write, 저장 공간이 선형 증가할 수 있다.
- **재현·지표:** 100~10,000 node/edge에서 mutation p95, SQL time, serialized bytes, storage growth, CPU를 측정한다.
- **대안:** append-only event+compaction; delta snapshot; current state/history 분리; checkpoint에서만 full snapshot.
- **포트폴리오 서사:** 가능. 읽기 단순성과 쓰기·복구 비용의 균형을 보여준다.
- **난이도/직무:** 상 / Python Backend.

### NX-07 — [S][HYPOTHESIS][Retrieval] semantic retrieval 품질과 규모 한계를 측정한다

- **관련 코드:** [MemoryRepository](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/memory_repository.py:270), [TopicRepository](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/repository/topic_repository.py:27)
- **현재 구조:** 일부 경로는 similarity cutoff 없이 최근 기억으로 top-k를 채우며 768차원 vector의 ANN index는 확인되지 않는다.
- **문제 조건/서비스 영향:** 무관한 기억이 context에 들어가 오경보를 만들거나 vector 증가 시 검색 latency가 커질 수 있다.
- **재현·지표:** Recall@k, Precision@k, MRR/nDCG, no-answer accuracy, downstream FP와 데이터 규모별 `EXPLAIN ANALYZE`·p95.
- **대안:** calibrated threshold+metadata; lexical/vector RRF; MMR/reranker; HNSW/IVFFlat와 exact search 비교.
- **포트폴리오 서사:** 최상. RAG 품질과 DB query plan을 함께 다룬다.
- **난이도/직무:** 상 / AI Agent, AI Infra.

### NX-08 — [A][HYPOTHESIS][Reflection Cost] batch context와 backlog를 통제한다

- **관련 코드:** [ReflectionBatchService](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/service/agent/reflection_batch_service.py:167), [ReflectionBatchGraph](/Users/jeongsoeun/Desktop/Life/coding/Project/nodexr/FastAPI-server/app/agent/graph/reflection_batch_graph.py:34)
- **현재 구조:** 최대 200 utterance, 200 event, 100 fact, 50 memory를 읽고 분석·repair·dedup·summary 호출을 조합한다.
- **문제 조건/서비스 영향:** 활발한 room 또는 LLM 장애 backlog에서 비용·지연이 커지고 다음 주기 이전에 끝나지 않을 수 있다.
- **재현·지표:** tokens/batch, 비용, p95, timeout, pending age, processed rate, extraction F1.
- **대안:** topic별 map-reduce; adaptive token budget; incremental processing+hierarchical summary; topic 병렬 처리.
- **포트폴리오 서사:** 가능. 비용과 memory 품질의 Pareto frontier를 만든다.
- **난이도/직무:** 상 / AI Agent, AX.

---

# QUP

## 현재 구현 흐름

```text
GET /problems/refresh
→ 백준·solved.ac 데이터 갱신
→ ProblemRefreshEvent 발행
→ @Async ranking listener
→ 기본/희귀 문제 기여도 계산
→ MyBatis score update
```

Git 이력상 본인이 직접 구현한 범위는 ranking, problem/main API, login·refresh entry point, history, MyBatis 전환, 비동기 ranking event다. 초기 crawler 전체를 단독 담당으로 주장하는 것은 피한다.

## 맡은 기능 TOP

| 순위 | 실제 담당 기능 | 기술 | 코드 근거 | 추천 직무 | 등급 |
|---:|---|---|---|---|:---:|
| 1 | `[FACT]` 문제 갱신 후 비동기 ranking 계산 이벤트 | Spring Event, `@Async`, MyBatis | [ProblemController](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/problem/controller/ProblemController.java:49>), [EventListener](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/event/ProblemRefreshEventListener.java:11>) | Java/Spring | S |
| 2 | `[FACT]` 기본·희귀 문제 기반 기여도와 ranking 계산 | Java, MyBatis, solved.ac | [RankingServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/service/RankingServiceImpl.java:97>), [RankingMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/resources/mapper/ranking/RankingMapper.xml:5>) | Java/Spring | S |
| 3 | `[FACT]` 알고리즘·티어 문제 필터 API | Spring MVC, MyBatis | [ProblemServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/problem/service/ProblemServiceImpl.java:17>), [ProblemMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/resources/mapper/problem/ProblemMapper.xml:5>) | Java Backend | A |
| 4 | `[FACT]` 학교 순위·라이벌 격차·오늘의 문제 메인 집계 | Spring Service, MyBatis | [MainPageServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/mainPage/service/MainPageServiceImpl.java:24>) | Java Backend | A |
| 5 | `[FACT]` handle 로그인 및 문제 갱신 API | Spring MVC, external refresh | [MemberController](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/member/controller/MemberController.java:21>), [ProblemController](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/problem/controller/ProblemController.java:49>) | Java Backend | A |
| 6 | `[FACT]` MyBatis 중심 쿼리 구조 전환 | MyBatis, MySQL | [RankingMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/resources/mapper/ranking/RankingMapper.xml:5>), [ProblemMapper](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/resources/mapper/problem/ProblemMapper.xml:5>) | Java/Database | A |
| 7 | `[FACT]` 일별 학교 ranking·solved history | Spring MVC, MyBatis | [HistoryController](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ewhaHistory/controller/EwhaHistoryController.java:15>) | Java Backend | B |

QUP에는 AI Agent라고 부를 구조가 없다. AI 지원 시 억지로 AI 프로젝트로 포장하지 않고 외부 API 복원력·비동기 처리·다중 저장소 일관성 사례로 사용한다.

## 고도화 후보 TOP

| 순위 | ID | 도메인 문제 | 구분 | 추천 직무 | 매력도 |
|---:|---|---|---|---|:---:|
| 1 | QUP-01 | solved.ac/백준 429·403·timeout 복원력 | FACT/HYPOTHESIS | Java/Spring | S |
| 2 | QUP-02 | `@Async` 이벤트 유실·실패 가시성 | HYPOTHESIS | Java/Spring | S |
| 3 | QUP-03 | 전체 ranking delete-then-insert 원자성 | HYPOTHESIS | Java/Database | S |
| 4 | QUP-04 | 동일 사용자 동시 refresh 멱등성·lost update | HYPOTHESIS | Java/Spring | S |
| 5 | QUP-05 | DynamoDB·MySQL·ranking 결과적 일관성 | HYPOTHESIS | Distributed Backend | S |
| 6 | QUP-06 | 외부 API contract test·관측성 부재 | FACT | Java/Spring | A |
| 7 | QUP-07 | 전체 문제 dataset 갱신 중 부분 데이터 노출 | HYPOTHESIS | Java/Data | A |

### QUP-01 — [S][FACT/HYPOTHESIS][Resilience] 외부 API 장애를 통제된 상태로 흡수한다

- **관련 코드:** [RankingServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/service/RankingServiceImpl.java:187>)
- **현재 구조:** sync `RestTemplate`과 `.block()`을 호출하며 4xx 후 개별 조회로 fallback하거나 예외 시 tier 0을 반환한다. timeout·backoff·circuit breaker는 확인되지 않는다.
- **근거/영향:** Git에 429·403 대응 반복 이력은 FACT다. 현 구조의 SLO 영향 정도는 HYPOTHESIS다.
- **재현·지표:** WireMock으로 429/403/5xx/timeout을 주고 성공률, p95, provider calls, retry amplification, stale duration, score error를 측정한다.
- **대안:** exponential backoff+jitter+`Retry-After`; Resilience4j; last-known-good cache; provider adapter/error taxonomy.
- **포트폴리오 서사:** 최상. 실제 장애 이력에서 임시 대응과 체계적 복원력을 비교한다.
- **난이도/직무:** 중상 / Java·Spring Backend.

### QUP-02 — [S][HYPOTHESIS][Async Reliability] ranking event를 durable job으로 만든다

- **관련 코드:** [EventListener](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/event/ProblemRefreshEventListener.java:11>), [EnableAsync](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/GgyuUpApplication.java:12>)
- **현재 구조:** HTTP에서 Spring event를 발행하고 기본 `@Async` executor에서 처리한다. job 상태, retry, 전용 executor, durable queue가 없다.
- **문제 조건/서비스 영향:** 응답 직후 종료, listener 예외, executor saturation 시 HTTP 성공 이후 ranking이 갱신되지 않을 수 있다.
- **재현·지표:** event 직후 kill, fault injection, burst로 completion/loss rate, queue delay, failure detection, saturation을 측정한다.
- **대안:** transactional outbox; Kafka/RabbitMQ; Spring Batch/job table; 전용 executor+`AsyncUncaughtExceptionHandler`.
- **포트폴리오 서사:** 매우 좋음. 단순 `@Async`와 신뢰할 수 있는 비동기 처리를 비교한다.
- **난이도/직무:** 상 / Java·Spring Backend.

### QUP-03 — [S][HYPOTHESIS][Atomic Rebuild] ranking 전체 재생성을 원자적으로 공개한다

- **관련 코드:** [전체 갱신](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/service/RankingServiceImpl.java:153>), [deleteScores](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/resources/mapper/ranking/RankingMapper.xml:14>)
- **현재 구조:** 기존 score 전체 삭제 후 사용자별 외부 조회와 insert를 순차 실행한다. scheduler annotation은 현재 주석 상태다.
- **문제 조건/서비스 영향:** K번째 사용자 실패 또는 rebuild 중 조회에서 빈/부분 ranking이 보일 수 있다.
- **재현·지표:** K번째 fault로 visible rows, partial window, duration, rollback/invariant를 측정한다.
- **대안:** staging/shadow table swap; 단일 transaction; versioned batch+active pointer; 완료 batch만 공개하는 upsert.
- **포트폴리오 서사:** 최상. 긴 transaction과 staging의 lock·storage·운영 복잡도를 비교한다.
- **난이도/직무:** 상 / Java, Database.

### QUP-04 — [S][HYPOTHESIS][Concurrency] 사용자 refresh를 멱등하게 처리한다

- **관련 코드:** [refresh endpoint](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/problem/controller/ProblemController.java:49>), [score update](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/service/RankingServiceImpl.java:97>)
- **현재 구조:** refresh와 async ranking의 수명 주기가 분리되고 score는 read-modify-write다. 일부 semaphore는 process-local이다.
- **문제 조건/서비스 영향:** 동일 handle 동시 요청·재시도·다중 인스턴스에서 중복 반영 또는 lost update 가능성이 있다.
- **재현·지표:** 동시 요청 후 unique solved set 기대 점수와 실제 점수, duplicate event, lost update, lock wait를 비교한다.
- **대안:** run ID+DB unique; optimistic lock/atomic SQL; DynamoDB condition; distributed lock+idempotent consumer.
- **포트폴리오 서사:** 매우 좋음. API 재시도, event, DB 동시성을 한 사례로 묶는다.
- **난이도/직무:** 상 / Java·Spring.

### QUP-05 — [S][HYPOTHESIS][Distributed Consistency] DynamoDB·MySQL을 복구 가능한 saga로 만든다

- **관련 코드:** [DataCrawlingServiceImpl](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/dataCrawling/service/DataCrawlingServiceImpl.java:235>), [RefreshService](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/dynamoDB/service/RefreshService.java:25>)
- **현재 구조:** DynamoDB, MySQL, async ranking이 분산 transaction 없이 연결되고 일부 예외는 logging 후 흐름이 계속된다.
- **문제 조건/서비스 영향:** store 중 하나 또는 event 단계 실패 시 풀이 상태·화면·ranking이 서로 달라질 수 있다.
- **재현·지표:** 단계별 fault로 divergence, false-success, recovery time, orphan refresh를 측정한다.
- **대안:** saga+보상/재시도; outbox+idempotent projection; DynamoDB Streams; 단일 source of truth+재생 가능한 projection.
- **포트폴리오 서사:** 최상급이나 범위가 크다. 초기 crawler 담당이 아니라 기존 다중 저장소 흐름의 신뢰성 개선으로 표현한다.
- **난이도/직무:** 상 / Distributed Backend.

### QUP-06 — [A][FACT][Testing/Observability] 외부 API와 ranking 회귀를 자동 검증한다

- **관련 코드:** [빈 context test](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/test/java/ggyuel/ggyuup/GgyuUpApplicationTests.java:8>), [listener](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/ranking/event/ProblemRefreshEventListener.java:11>)
- **현재 구조:** 실질 테스트가 없고 async listener도 구조화 log·job metric 없이 출력 위주다.
- **문제 조건/서비스 영향:** provider schema, 429 fallback, ranking formula 회귀를 배포 전 검출하기 어렵다.
- **재현·지표:** WireMock·Testcontainers·LocalStack으로 scenario pass, error classification, trace completeness, MTTD를 측정한다.
- **대안:** provider contract+ranking golden test; Micrometer Observation; correlation ID 구조화 log/trace.
- **포트폴리오 서사:** 가능. QUP-01~05의 검증 수단으로 결합할 때 더 강하다.
- **난이도/직무:** 중 / Java·Spring.

### QUP-07 — [A][HYPOTHESIS][Data Refresh] 문제 dataset을 last-known-good 방식으로 갱신한다

- **관련 코드:** [crawlProblems](</Users/jeongsoeun/Desktop/Life/coding/Project/Qup-backend/src/main/java/ggyuel/ggyuup/dataCrawling/service/DataCrawlingServiceImpl.java:97>)
- **현재 구조:** 기존 데이터를 삭제하고 외부 페이지를 순차 수집하며 중간 예외 후 부분 결과가 반영될 수 있다.
- **문제 조건/서비스 영향:** 페이지 N timeout/429 시 filter·ranking 기반 dataset이 부분 상태가 될 수 있다.
- **재현·지표:** 페이지 fault로 기대/실제 문제 수, completeness, stale duration, refresh time, provider calls를 측정한다.
- **대안:** staging+validation+swap; incremental diff/upsert; versioned snapshot+last-known-good.
- **포트폴리오 서사:** 가능. 팀원 기여가 큰 영역이므로 기존 crawler 고도화로 정확히 표현한다.
- **난이도/직무:** 중상 / Java Data Backend.

---

# 직무별 통합 정리

## Java/Spring 담당 역할 TOP 7

| 순위 | 프로젝트 | 담당 역할 | 등급 |
|---:|---|---|:---:|
| 1 | PlanWith | 자연어 일정·할 일 생성과 승인 Spring/OpenAI workflow | S |
| 2 | QUP | 문제 갱신 후 비동기 기여도 ranking | S |
| 3 | PlanWith | Redis TTL 사용자별 승인 상태 | A |
| 4 | QUP | 기본·희귀 문제 기여도 공식 및 MyBatis 갱신 | S |
| 5 | PlanWith | LLM 결과 검증 후 Event/Todo 저장 | A |
| 6 | QUP | 문제 filter·메인·history SQL API | A |
| 7 | PlanWith | JMeter·Mock OpenAI·DB/Redis 불변식 성능 하네스 | A |

## Java/Spring 고도화 후보 TOP 7

1. `PW-01` 승인 토큰 원자 소비와 멱등성
2. `QUP-01` 429·403·timeout 외부 API 복원력
3. `QUP-02` durable async event/job
4. `QUP-03` ranking atomic rebuild
5. `PW-02` 다건 승인 전체 트랜잭션
6. `QUP-05` DynamoDB·MySQL·ranking saga
7. `PW-03` LLM latency·thread 격리

## Python/FastAPI 담당 역할 TOP 7

1. Realtime multi-trigger LangGraph
2. Reflection·semantic memory batch
3. graph mutation·snapshot·history
4. WebSocket utterance·graph·job correlation
5. pgvector topic routing·memory retrieval
6. 2D 생성·MinIO·graph event pipeline
7. Meshy 3D polling·검증·저장 pipeline

## Python/FastAPI 고도화 후보 TOP 7

1. `NX-01` durable generation job
2. `NX-03` 동기 DB event-loop blocking
3. `NX-05` graph version 동시성
4. `NX-04` multi-instance WebSocket
5. `NX-06` graph snapshot 비용
6. `NX-07` pgvector 검색 품질·확장성
7. `NX-08` Reflection 비용·backlog

## AI Agent·AI Service·AX 담당 역할 TOP 7

| 순위 | 프로젝트 | 담당 역할 |
|---:|---|---|
| 1 | NodeXR | multi-label trigger와 병렬 subgraph Realtime Agent |
| 2 | NodeXR | 장기 대화를 semantic memory로 압축하는 Reflection Agent |
| 3 | NodeXR | grounded memory guard와 provenance 검증 |
| 4 | NodeXR | Rationale·Conflict를 graph·memory 근거와 연결 |
| 5 | NodeXR | Agent action을 기존 2D/3D pipeline에 연결 |
| 6 | NodeXR | OpenAI prompt→Gemini image→MinIO orchestration |
| 7 | PlanWith | 자연어 일정·할 일 LLM workflow |

QUP에는 적절한 AI Agent 담당 항목이 없다.

## AI Agent·AI Service·AX 고도화 후보 TOP 7

1. `NX-02` 단계별·종단간 Agent evaluation
2. `NX-07` retrieval 품질·grounding 평가
3. `PW-05` 일정·할 일 LLM golden dataset
4. `NX-01` Agent tool 실행 durable job·멱등성
5. `PW-04` structured output 계약
6. `NX-08` Reflection token·backlog 최적화
7. `PW-06` 의도 routing 정확도·비용 비교

---

# 최종 고도화 TOP 5

## 1. NX-01 — Durable AI generation job

2D·3D 외부 작업, MinIO, DB, WebSocket을 복구 가능한 job state machine으로 묶는다. Python 백엔드와 AI 서비스 모두에서 가치가 높고 장애 주입으로 유실·중복·복구 시간을 직접 측정할 수 있어 가장 강한 대표 사례다.

## 2. NX-02 — Agent evaluation platform

NodeXR는 이미 Agent 구조가 충분히 복잡하므로 기능 추가보다 평가 체계가 더 차별화된다. trigger F1, grounding, tool 정확도, relation F1, 비용을 연결하면 LangGraph 사용 경험을 넘어 운영 가능한 Agent 설계 경험이 된다.

## 3. QUP-01 — 외부 API 복원력

Git 이력에 429·403 대응이 반복되어 문제의 현실성이 높다. WireMock 장애 실험과 Resilience4j 적용으로 호출 수, tail latency, stale-data 정책을 비교하면 Java/Spring 지원에 강하다.

## 4. PW-01 — 승인 멱등성·원자적 소비

범위는 비교적 작지만 재전송·동시성·트랜잭션이라는 보편적 백엔드 문제를 명확히 보여준다. Redis Lua/GETDEL, DB unique key, 상태 머신을 비교하고 동시 승인 중복 0건을 증명하면 면접 설명력이 높다.

## 5. NX-03 — WebSocket event-loop blocking 개선

DB 지연과 동시 연결을 조절해 loop lag와 p99를 측정하고 async SQLAlchemy와 bounded executor를 비교한다. Python 비동기 처리의 실제 병목을 정량화하는 좋은 성능 사례가 된다.

> Java/Spring 지원에 더 집중한다면 5번 대신 `QUP-03 ranking atomic rebuild`를 우선한다.

---

# 검증 및 작업 상태

- NodeXR에서 `PYTHONPATH=. venv/bin/python -m pytest -q`를 실행했다.
  - 결과: **143 passed**, warning 1건.
  - warning은 Starlette TestClient/httpx 관련 deprecation이다.
- 전역 Python의 `pytest -q`는 `app`, `httpx`, `langchain_core` 미설치로 collection에 실패했다. 코드 문제가 아니라 실행 환경 문제였고 프로젝트 venv로 재검증했다.
- PlanWith와 QUP 테스트는 실행하지 않았다.
  - PlanWith 문서에는 기존 Gradle context test 실패와 invalidated baseline이 기록되어 있다.
  - QUP은 실질 검증이 없는 빈 context test만 확인됐다.
- 실제 latency, throughput, Agent 정확도, retrieval 품질은 측정 전이므로 이력서 수치로 사용하지 않는다. 먼저 위 실험으로 baseline을 만든다.
- 분석 과정에서 애플리케이션 코드는 변경하지 않았다.
