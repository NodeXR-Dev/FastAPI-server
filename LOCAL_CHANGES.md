# 로컬 서버 변경 기록 (개발자3)

NodeXR 서버(`FastAPI-server`)를 로컬에서 돌리며 **직접 바꾼 것**과 **왜 바꿨는지**를 모아둔다.
1절은 서버 애플리케이션 코드 수정이고, 2절부터는 로컬 환경·DB·설정 변경이다.

최종 갱신: 2026-08-06

---

## 0. 코드 수정 — 2D 생성 프롬프트에 "제품 하나만" 제약 추가 (2026-08-06)

### 무엇을

`app/service/generation/openai_prompt_client.py` 의 `generate_image_prompt()` 시스템 프롬프트
Rules 에 4줄을 추가했다. 기존 줄은 건드리지 않았다.

```
- Depict exactly ONE isolated product. Never a scene, workspace, studio, or collage.
- No people, hands, furniture, rooms, or background props unless the product itself is one.
- Plain neutral background (solid light gray or white). No floor, no shadows of other objects.
- Single three-quarter view of the whole product, centered, fully visible, nothing cropped.
```

### 왜

생성된 2D 이미지가 **제품 하나가 아니라 장면 전체**로 나왔다. "신발 밑창" 을 요청했는데
디자인 스튜디오에서 사람 넷이 회의하는 그림이 나오고, 그 안에 제품이 소품처럼 들어 있었다.

기존 Rules 에는 `clean, coherent, high-quality 2D concept rendering` 만 있어 배경·인물·장면을
금지하는 제약이 전혀 없었다. LLM 이 문맥에 살을 붙이는 것을 막을 근거가 없었다.

**3D 에서 특히 치명적이다.** Meshy 는 이미지에 보이는 모든 것을 메시로 만든다. 장면 이미지를
넣으면 책상·의자·사람·모니터가 통째로 3D 로 변환되고, 클라가 최장변을 기준으로 크기를
정규화하므로 정작 제품은 몇 cm 로 쪼그라든다(실측: 최장변 0.45m 로 맞추니 신발이 보이지 않음).

배경을 단색으로 강제하는 항목이 3D 품질에 가장 크게 기여한다.

### 검증

적용 후 2D 를 새로 생성해 제품 하나만 나오는지 확인할 것. 그 뒤에 3D 를 돌린다
(3D 는 호출 1회당 Meshy 과금이므로 2D 가 만족스러울 때만).

### 남은 것

`app/ai/prompts/feature_image_prompt.py`(feature 경로)에는 같은 제약을 아직 넣지 않았다.
현재 클라는 `2d/generate/graph` 만 쓰기 때문이다. 5-3 절의 프롬프트 이원화 문제와 함께 정리 필요.

---

## 1. DB 마이그레이션 적용 (2026-08-05)

### 무엇을

서버팀이 만들어둔 기존 마이그레이션 2개를 로컬 DB에 적용했다. **마이그레이션 파일 자체는 수정하지 않았다.**

```bash
cd /Users/imsohyun/Desktop/nodexr-server
./venv/bin/alembic -c app/alembic.ini upgrade head
```

| 리비전 | 파일 | 추가된 것 |
|---|---|---|
| `20260802_01` | `app/alembic/versions/20260802_01_reflection_batch_tracking.py` | `graph_events.processed_at`, 인덱스 `ix_graph_events_processed_room` / `ix_utterances_state_room`, enum `design_fact_status`에 `SUPERSEDED` |
| `20260802_02` | `app/alembic/versions/20260802_02_sub_graph_soft_delete.py` | `sub_graphs.deleted_at`, 인덱스 `ix_sub_graphs_room_deleted` |

### 왜

로컬 DB가 `Base.metadata.create_all` 계열로 만들어져 **`alembic_version` 테이블조차 없었다.** 서버 코드는 최신인데 DB만 옛 스키마라, 코드가 요구하는 컬럼이 없어 런타임에 깨졌다.

**증상 1 — 노드가 하나도 저장되지 않음 (치명적).** `NODE_CREATE` 가 올 때마다:

```
INSERT INTO sub_graphs (sub_graph_id, room_id, deleted_at) VALUES ...
psycopg.errors.UndefinedColumn: column "deleted_at" of relation "sub_graphs" does not exist
ROLLBACK
```

`graph_interaction_service._handle_node_save()` → `graph_repository.create_sub_graph()` 에서 죽고 롤백됐다.
서버 ACK 가 안 오니 클라는 로컬 임시 id 를 그대로 유지했고, 이어서 2D 생성이 그 id 로 연결을 보내
`prompt_context_builder.py:102` 에서 최종 실패했다.

```
ValueError: Input Snapshot에서 생성 Connection의 Node를 찾을 수 없습니다.
```

**즉 "2D 생성 실패"의 진짜 원인은 생성 로직이 아니라 그 앞의 노드 저장 실패였다.**

**증상 2 — 5분 리플렉션 배치가 매번 실패.**

```
[reflection_scheduler_iteration_failed]
  error=column graph_events.processed_at does not exist
```

### 안전성

두 마이그레이션 모두 `add_column` / `create_index` 뿐이라 기존 데이터는 건드리지 않는다.
적용 전 전체 덤프를 떠뒀다(5.4MB).

### 확인

```
sub_graphs.deleted_at      존재
graph_events.processed_at  존재
alembic_version            20260802_02 (head)
```

---

## 2. `.env` 변경

`.env` 는 gitignore 대상이라 저장소에 안 올라간다. 값만 기록해둔다.

### `MINIO_PUBLIC_BASE_URL`

```
(변경 전) http://localhost:9000
(변경 후) http://192.168.0.196:9100     ← 맥의 LAN IP + 포워더 포트. IP 는 DHCP 라 자주 바뀐다
```

**왜.** 이 값은 서버가 **헤드셋에게 "이 주소에서 파일을 받아가라"** 고 알려주는 문자열이다.
`localhost` 면 Quest 가 자기 자신을 가리켜 이미지·GLB 다운로드가 전부 실패한다.

```
[Generate2DController] 2D 이미지 다운로드 → http://localhost:9000/...
[Generate2DController] 2D 이미지 다운로드 실패: Cannot connect to destination host
```

**맥 브라우저로 테스트하면 루프백이라 성공해서 오진하기 쉽다.** 헤드셋에서만 실패한다.

**IP 가 바뀌면 여기도 같이 바꿔야 한다.** 서버 재시작 필요(`.env` 는 프로세스 시작 시에만 읽힘).

### MinIO 포트 포워더는 필요하다 (`tools/minio_forward.py`)

**헤드셋 테스트 시 반드시 띄워야 한다.** 안 띄우면 이미지·GLB 다운로드가 전부 실패한다.

```bash
python3 tools/minio_forward.py     # 0.0.0.0:9100 → 127.0.0.1:9000
```

**왜.** Docker Desktop 이 퍼블리시한 MinIO 9000 번은 **LAN 의 다른 기기에서 닿지 않는다.**
uvicorn(8000)은 네이티브 프로세스라 정상이므로, REST/WS 는 되는데 **이미지만 실패**하는 형태로 나타난다.

```
[GraphSyncClient] 수신(event_type=2D_GENERATED): {... "img_url":"http://192.168.0.196:9000/..."}
[Generate2DController] 2D 이미지 다운로드 → http://192.168.0.196:9000/...
[Generate2DController] 2D 이미지 다운로드 실패: Cannot connect to destination host (code=0)
```

Unity 에서는 텍스처가 안 들어가 **중앙 화면이 격자무늬(체커보드)** 로 보인다.
"이미지가 안 뜬다" 가 아니라 "격자무늬가 뜬다" 면 이 문제를 먼저 의심할 것.

**[중요] 오진하기 쉬운 지점.** 맥에서 자기 LAN IP 로 `curl` 하면 **루프백으로 돌아 HTTP 200 이 나온다.**
이건 Docker 포트 매핑을 검증한 게 아니다. `lsof` 로 `*:9000 (LISTEN)` 이 보이고 방화벽이 꺼져 있어도
LAN 도달성의 증거가 되지 않는다. **판정은 반드시 헤드셋 실기 로그로 해야 한다.**

(2026-08-05 에 위 근거들로 "포워더 불필요" 라고 판단해 9000 직결로 바꿨다가 실기에서 실패했다.
8/2 원본 진단이 옳았다.)

**근본 해결**은 서버팀이 MinIO 를 네이티브로 띄우거나 Docker 네트워크를 조정하는 것. 포워더는 임시 조치다.

---

## 3. Python 의존성 설치 (2026-08-04)

`develop` 17커밋을 받은 뒤 서버가 기동하지 않았다.

```
ModuleNotFoundError: No module named 'langchain_openai'
```

`56be3b0` 에서 `requirements.txt` 에 추가된 패키지가 venv 에 없어서였다. 설치한 것:

| 패키지 | 비고 |
|---|---|
| `langchain-openai 1.4.1` | 신규 |
| `langchain-core` | 1.4.8 → 1.5.3 (의존성으로 갱신) |
| `openai` | 2.43.0 → 2.52.0 (의존성으로 갱신) |
| `tiktoken 0.13.0` | 신규 |

`langgraph` / `langsmith` / `bcrypt==4.0.1` 은 이미 설치돼 있었다.

---

## 4. Docker 컨테이너

재부팅 여파로 `nodexr-postgres` / `nodexr-minio` 가 내려가 있어 기동했다.

```bash
docker compose up -d
docker stop nodexr-backend    # ← 아래 이유로 내림
```

**`nodexr-backend` 는 내려야 한다.** compose 에 정의돼 있어 함께 뜨는데 **8000 포트를 선점해서**
네이티브 uvicorn 과 충돌한다. 컨테이너 이미지는 최신 코드가 반영돼 있지 않을 가능성이 높다.

`nodexr-pg-tunnel`(5433) 은 `alpine/socat` 으로 `nodexr-postgres:5432` 에 그대로 포워딩할 뿐이라
**별도 DB 가 아니다.** "DB 가 섞였나" 의심할 필요 없다.

---

## 5. 서버팀에 전달할 것 (아직 미수정)

여기부터는 **수정하지 않았고 협의가 필요한 것들**이다.

### 5-1. 3D 생성 비용 — 중복 방지가 전혀 없다

`POST /api/3d/generate` 는 호출 1회당 Meshy API 과금이 발생하는데,
`model_3d_generation_service.generate()` 에 **기존 결과를 찾아보는 코드가 없다.**
같은 2D 이미지로 몇 번을 호출하든 매번 새로 만들고 매번 과금한다.

게다가 `assets` 테이블에 **`source_asset_id` 컬럼이 없어서** "이 2D 로 만든 3D 가 이미 있나"를
물어볼 방법 자체가 없다. `create_3d_asset()` 은 원본의 `graph_snapshot_id` 만 물려받는다.

제안(우선순위 순):

1. `assets.source_asset_id` 컬럼 추가 → `create_3d_asset` 에 저장
2. 생성 전 같은 `source_asset_id` 의 `MODEL_3D` 조회 → 있으면 Meshy 호출 없이 기존 `model_url` 반환
3. `job_id` 멱등 처리 (이제 `Generate3DRequest.job_id` 가 필수로 들어온다)
4. Meshy `task_id` 저장 — 폴링 타임아웃(`MESHY_POLL_TIMEOUT_SECONDS=900`) 시 **과금은 됐는데 결과를 못 받는다.**
   `task_id` 를 안 남겨서 나중에 회수도 불가능하다
5. 방/사용자별 rate limit

**현재는 클라(`Generate3DController`)에서만 막고 있다** — 진행 중 차단 + 원본 asset_id 기준 결과 캐시.
클라 캐시는 프로세스 메모리라 앱 재시작 시 사라지고 다른 참가자의 요청도 막지 못한다.

### 5-2. 생성 결과에 결정성이 없다

같은 그래프로 두 번 생성해도 전혀 다른 그림이 나온다. 2단 파이프라인 **양쪽 다 seed 가 없다.**

```python
# openai_prompt_client.py:31 — 프롬프트 텍스트 생성
response = await self.client.responses.create(
    model=settings.OPENAI_PROMPT_MODEL,
    input=[...],                       # seed 없음, temperature 없음
)

# gemini_image_client.py:105 — 이미지 생성
config=types.GenerateContentConfig(
    response_modalities=["TEXT", "IMAGE"],   # seed 없음
)
```

기본 2D 생성은 이전 이미지를 입력으로 받지도 않는다(`generate_image(prompt_text=...)` 뿐).
매번 백지에서 새로 그리므로 결과가 이어질 근거가 코드에 없다.
(이전 이미지를 참조하는 건 `edit_image_colors` — color_change 전용)

### 5-3. 프롬프트 시스템 프롬프트가 이원화돼 있다

두 생성 경로의 시스템 프롬프트가 다른 파일에 따로 있고 톤도 다르다.

| 경로 | 위치 | 톤 |
|---|---|---|
| `2d/generate/feature` | `app/ai/prompts/feature_image_prompt.py` | "child-friendly, craft or recycled materials" — 초등학생 만들기 맥락 |
| `2d/generate/graph` | `openai_prompt_client.py:71` 에 **인라인 하드코딩** | "product and concept image generation" — 범용 |

같은 방·같은 주제인데 어느 버튼을 눌렀느냐로 결과 성격이 달라진다.

### 5-4. 생성 1회당 graph_snapshot 이 2개 남는다

같은 시각으로 스냅샷이 쌍으로 생성된다(입력용 + 결과용으로 보인다).
방 31개에 스냅샷 141개는 과해 보인다. 의도된 설계인지 확인 필요.

### 5-5. 기존 스냅샷은 구형식이라 재생성이 불가능하다

`9fc276e` 로 저장 형식이 바뀌면서 `PromptContextBuilder.build_from_snapshot()` 이
`_generation_context` 키를 요구하는데, 그 이전 스냅샷에는 없다.

```python
if not isinstance(generation_context, dict):
    raise ValueError("Generation Input Snapshot에 Prompt Context가 없습니다.")
```

신규 생성은 새 형식으로 저장되니 지장 없지만 **과거 asset 의 재생성은 실패한다.**

---

## 6. 참고 — 테스트 환경 기동 순서

```bash
# 1. 인프라
docker compose up -d
docker stop nodexr-backend          # 8000 포트 선점 방지

# 2. .env 의 MINIO_PUBLIC_BASE_URL 을 현재 맥 LAN IP 로 (IP 는 매일 바뀐다)
ipconfig getifaddr en0

# 3. 서버
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Unity 씬(`MVP_SH.unity`) 쪽도 **두 곳을 같이** 바꿔야 한다.
한쪽만 바꾸면 방은 A 서버, 그래프는 B 서버로 갈라져 "코드를 찾지 못함" 이 된다.

- `MvpClassroomFlow._backendHost`
- `GraphSyncClient._host`
