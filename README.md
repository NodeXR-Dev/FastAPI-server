# NodeXR FastAPI Server

## 아키텍처
<img width="322" height="233" alt="Screenshot 2026-05-22 at 11 22 05" src="https://github.com/user-attachments/assets/3e019e70-234e-4cd8-8afc-5cb39c238638" />   
     
NodeXR은 Unity 클라이언트, FastAPI 백엔드, LangChain 기반 AI 처리 계층, PostgreSQL/pgvector 저장소를 분리하여 설계했습니다.     
실시간 회의 발화와 노드 그래프 갱신은 WebSocket으로 처리하고, 무거운 AI 추론·요약·충돌 감지는 별도 서비스 계층에서 수행하도록 하여 실시간성과 확장성을 확보했습니다.     
또한 MinIO를 사용해 이미지·에셋 파일은 DB와 분리 저장하고, DB에는 메타데이터와 참조 URL만 관리하여 대용량 에셋 처리와 데이터 정합성을 쉽게 유지할 수 있도록 했습니다.     

## ERD
<img width="640" height="444" alt="R1280x0" src="https://github.com/user-attachments/assets/90e7edff-0b19-4c0c-bcb7-5eb582c1b1f6" />   
     
ERD는 회의실 중심 구조로 설계하여 users, rooms, room_members를 통해 여러 사용자가 하나의 회의 공간에서 협업할 수 있도록 했습니다.     
회의 중 발생하는 발화는 utterances에 저장하고, 이를 기반으로 topics, episodes, decisions, issues, conflicts 등을 분리해 회의 맥락을 단순 로그가 아닌 구조화된 지식으로 관리하도록 했습니다.     
노드 그래프는 nodes, edges, sub_graphs로 분리하여 시각적 표현과 의미 관계를 유연하게 확장할 수 있게 했고, 발화·결정·이슈와 연결함으로써 AI가 근거 기반으로 그래프를 생성/수정할 수 있도록 설계했습니다.     
