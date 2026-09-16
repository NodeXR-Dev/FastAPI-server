from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "NodeXR"

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    DATABASE_URL: str
    DB_ECHO: bool

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_2D_ASSETS: str = "nodexr-2d-assets"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_BASE_URL: str = "http://localhost:9000"

    OPENAI_API_KEY: str
    OPENAI_PROMPT_MODEL: str = "gpt-4.1-mini"
    AGENT_LLM_MODEL: str | None = None
    AGENT_LLM_TIMEOUT_SECONDS: float = 10.0
    # 배치는 한 번에 수십~수백 발화를 보낸다. 핫 패스 타임아웃으로는 끊긴다.
    REFLECTION_BATCH_LLM_TIMEOUT_SECONDS: float = 60.0
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-image"
    MESHY_API_KEY: str | None = None
    MESHY_BASE_URL: str = "https://api.meshy.ai"
    MESHY_POLL_INTERVAL_SECONDS: float = 5.0
    MESHY_POLL_TIMEOUT_SECONDS: float = 900.0
    MESHY_HTTP_TIMEOUT_SECONDS: float = 60.0

    # Meshy 는 리메시를 켜지 않으면 원본 밀도 그대로 내보낸다.
    # 실측(2026-08-15): 삼각형 196만 개 / GLB 81MB.
    # 그중 텍스처는 2.4MB 뿐이고 나머지 78.9MB 가 전부 지오메트리였다.
    # Quest 가 씬 전체로 감당하는 양이 그 정도라 모델 하나로 예산을 다 쓰고,
    # 헤드셋이 매번 81MB 를 내려받아야 한다.
    # 0 이하로 두면 상한을 걸지 않는다(예전 동작).
    MESHY_TARGET_POLYCOUNT: int = 30000
    MESHY_TOPOLOGY: str = "triangle"


    EMBEDDING_DIM: int = 1536
    
    TOPIC_DRIFT_THRESHOLD: float = 0.55
    DISCUSSION_SIMILARITY_THRESHOLD: float = 0.78
    # 실측으로 정한 값(docs/topic-threshold-measurement.md).
    # 0.75에서는 발화마다 topic이 새로 생겨(9발화 → 8 topic) 배치와 메모리가
    # 조각났다. 임베딩의 주제 분리도가 AUC 0.63에 그쳐 어떤 값도 발화-topic
    # 배정을 제대로 하지 못하므로, 조각남이 덜한 쪽(굵은 topic)을 택했다.
    # 0.25는 단일주제 회의를 1개로 유지하면서 완전 병합은 피하는 가장 높은 값이다.
    TOPIC_SIMILARITY_THRESHOLD: float = 0.25
    AGENT_RETRIEVAL_TOP_K: int = 5
    AGENT_RETRIEVAL_FALLBACK_ENABLED: bool = False
    AGENT_RETRIEVAL_MIN_SIMILARITY: float = 0.0
    MEMORY_GUARD_ALERT_THRESHOLD: float = 0.8

    # Agent 결과를 응답에 포함(False)할지, 백그라운드 처리 후 push(True)할지.
    AGENT_ASYNC_DISPATCH_ENABLED: bool = False
    # 같은 room의 다른 참가자에게도 발화/Agent 이벤트를 전파할지.
    ROOM_EVENT_BROADCAST_ENABLED: bool = False
    # off | shadow (shadow는 판정만 로깅하고 동작을 바꾸지 않는다)
    NOISE_FILTER_MODE: str = "shadow"
    # True면 Recall/생성 요청은 호출어("노드베어")가 있는 발화에서만 수행한다.
    AGENT_WAKE_WORD_REQUIRED: bool = True
    # 일반 발화에서 memory_guard 실행 여부를 무엇으로 정할지.
    #   llm        : GUARD_TRIGGER_PROMPT가 직접 판단 (기존 동작)
    #   annotation : 발화를 서술만 시키고 dialogue_move로 코드가 판단
    AGENT_GUARD_GATING_MODE: str = "llm"
    # annotation 모드에서 guard를 실행할 dialogue_move.
    AGENT_GUARD_GATING_MOVES: list[str] = ["PROPOSE", "DECIDE"]
    # utterance_annotations.model_version에 기록할 주석 스키마 버전.
    AGENT_ANNOTATION_SCHEMA_VERSION: str = "structure-v1"
    # embedding | llm. llm은 topic 배정과 구조 서술을 한 호출로 처리한다.
    TOPIC_ROUTING_MODE: str = "embedding"
    TOPIC_ROUTING_RECENT_UTTERANCES: int = 6
    # 배치가 전체 문맥으로 이번 배치 발화의 topic을 다시 긋는다.
    BATCH_TOPIC_RESEGMENT_ENABLED: bool = False

    REFLECTION_BATCH_ENABLED: bool = True
    REFLECTION_BATCH_INTERVAL_SECONDS: float = 300.0
    REFLECTION_BATCH_MAX_CONSECUTIVE_FAILURES: int = 3
    REFLECTION_BATCH_MAX_BACKOFF_CYCLES: float = 12.0
    REFLECTION_BATCH_MAX_UTTERANCES: int = 200
    REFLECTION_BATCH_MAX_GRAPH_EVENTS: int = 200
    REFLECTION_FACT_TOP_K: int = 100
    REFLECTION_MEMORY_TOP_K: int = 50
    BATCH_FACT_MIN_CONFIDENCE: float = 0.65
    BATCH_LINK_MIN_CONFIDENCE: float = 0.65
    FACT_DEDUP_SIMILARITY_THRESHOLD: float = 0.82

    # 서버 밖(Unity, 브라우저)에서 여는 주소. 리포트 URL 을 만들 때 쓴다.
    # 예) https://1.2.3.4.sslip.io  비워 두면 종료 요청이 들어온 주소를 쓴다.
    PUBLIC_BASE_URL: str | None = None
    # GENERATING/PENDING 상태로 이 시간 넘게 멈춰 있으면(서버 재시작 등) 다시 돌린다.
    MEETING_REPORT_STALE_SECONDS: float = 600.0
    # 명시적 DECISION 이 없는 Topic 의 결론을 LLM 으로 추론할지.
    MEETING_REPORT_LLM_ENABLED: bool = True

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "NodeXR-realtime-agent"
    LANGSMITH_ENDPOINT: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
