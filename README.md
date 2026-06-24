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
