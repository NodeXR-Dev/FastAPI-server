# NodeXR FastAPI Server

## 아키텍처
<img width="322" height="233" alt="Screenshot 2026-05-22 at 11 22 05" src="https://github.com/user-attachments/assets/3e019e70-234e-4cd8-8afc-5cb39c238638" />    

## ERD
<img width="757" height="594" alt="Screenshot 2026-05-31 at 14 05 06" src="https://github.com/user-attachments/assets/b6538fc6-efe1-42da-adf8-6cdf9bd5fc5f" />

# NodeXR FastAPI Server

XR 협업 회의에서 발생하는 발화를 Agentic AI가 구조화하고, semantic memory와 node graph로 연결하는 AI 협업 백엔드 서버입니다.

## 1. Problem

XR 회의에서는 아이디어, 결정사항, 제약조건, 논쟁점이 빠르게 흘러가지만 회의 후 맥락이 사라지기 쉽습니다. NodeXR은 회의 발화를 실시간으로 수집하고, AI Agent가 이를 구조화해 팀이 다시 활용할 수 있는 지식으로 저장합니다.

## 2. Key Features

- Room / User / RoomMember 기반 XR 협업 세션 관리
- Utterance 수집 및 semantic memory 구조화
- Design facts, decisions, constraints, conflicts 기반 회의 맥락 저장
- Node graph 생성 및 수정 이벤트 처리
- Room 단위 WebSocket broadcast
- 2D/3D AI generation request 비동기 처리
- PostgreSQL + pgvector 기반 의미 검색 준비
- MinIO 기반 생성 자산 저장
- Docker Compose 기반 로컬 통합 실행 환경

## 3. Architecture

Unity XR Client
→ FastAPI REST API
→ Background Task / Agentic AI Pipeline
→ PostgreSQL + pgvector
→ MinIO
→ WebSocket Event Broadcast
→ Unity XR Client

## 4. Tech Stack

- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- AI: LangChain, OpenAI, Google GenAI, sentence-transformers
- DB: PostgreSQL, pgvector
- Storage: MinIO
- Infra: Docker, Docker Compose
- Realtime: WebSocket

## 5. WebSocket Events

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

## 6. My Contributions

- FastAPI 기반 room/user/utterance/graph API 구현
- SQLAlchemy + Alembic 기반 DB 모델링
- Agentic AI를 위한 semantic memory 구조 설계
- WebSocket 기반 실시간 이벤트 처리 구현
- AI 생성 요청과 결과 전달을 분리한 비동기 처리 구조 설계
- Docker Compose 기반 PostgreSQL/MinIO/Backend 통합 환경 구성
