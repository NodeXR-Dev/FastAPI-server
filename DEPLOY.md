# 배포 가이드

팀원들이 각자 집에서 Quest 로 접속할 수 있도록 서버를 상시 가동 VM 에 올린다.

여기서 만드는 것은 **주소가 바뀌지 않는 HTTPS 서버 하나**다.
Unity 클라이언트는 서버 주소를 앱 안에 구워서 빌드하므로, 주소가 바뀌면
팀원 헤드셋마다 앱을 다시 깔아야 한다. 그래서 한 번 정하면 끝나는 주소가 필요하다.

---

## 0. VM 사양

| 항목 | 최소 | 권장 | 이유 |
|---|---|---|---|
| RAM | 4 GB | 8 GB | 임베딩 모델(ko-sroberta)이 메모리에 상주한다 |
| 디스크 | 40 GB | 60 GB | 이미지 + DB + 생성된 이미지 저장 |
| vCPU | 2 | 2~4 | |
| OS | Ubuntu 22.04 이상 | | |

> 이미지에서 CUDA 라이브러리 3.4 GB 를 걷어냈다(8.89 GB → 약 2.5 GB).
> 이거 안 했으면 디스크 요구가 두 배였다.

**방화벽에서 80, 443 포트를 열어 둔다.** 클라우드 콘솔의 보안 그룹과
VM 안쪽 `ufw` 둘 다 봐야 한다. 5432(DB), 9000(MinIO)은 **열지 않는다.**
컨테이너끼리만 쓰므로 바깥에 열면 그대로 공격 대상이 된다.

---

## 1. VM 에 Docker 설치

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

`usermod` 는 다시 로그인해야 적용된다. 한 번 끊었다 붙는다.

---

## 2. 코드 받기

```bash
git clone https://github.com/NodeXR-Dev/FastAPI-server.git
cd FastAPI-server
```

---

## 3. .env 만들기

`.env.prod.example` 을 복사해서 채운다.

```bash
cp .env.prod.example .env
```

바꿔야 하는 곳:

- `SITE_ADDRESS` — VM 공인 IP 뒤에 `.sslip.io` 를 붙인다.
  IP 가 `152.67.10.20` 이면 `152.67.10.20.sslip.io`.
  도메인을 안 사도 되고, Caddy 가 여기에 Let's Encrypt 인증서를 자동 발급한다.
- `MINIO_PUBLIC_BASE_URL` — `https://` + 위와 같은 주소.
- `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` —
  개발용 `nodexr123` 을 그대로 쓰지 말 것. 인터넷에 노출되는 서버다.
  ```bash
  openssl rand -hex 24
  ```
- `DATABASE_URL` 안의 비밀번호도 `POSTGRES_PASSWORD` 와 똑같이 맞춘다. 여기 자주 틀린다.
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `MESHY_API_KEY` — 키를 넣는다.
  뒤의 둘이 비면 2D/3D 생성에서 막힌다.

---

## 4. 띄우기

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

첫 빌드는 10~20분 걸린다. torch 와 임베딩 모델을 받기 때문이다. 이후 재배포는 훨씬 빠르다.

---

## 5. DB 테이블 만들기 (빠뜨리기 쉬움)

**서버 코드는 테이블을 자동으로 만들지 않는다.** alembic 을 직접 돌려야 한다.
이걸 안 하면 서버는 멀쩡히 뜨는데 API 를 부르는 순간 "컬럼이 없다"고 터진다.

```bash
docker compose -f docker-compose.prod.yml exec backend alembic -c app/alembic.ini upgrade head
```

---

## 6. 확인

```bash
curl https://<SITE_ADDRESS>/api/rooms/list
```

`{"rooms":[]}` 같은 게 나오면 성공이다.

인증서 발급에 10~30초 걸릴 수 있다. 실패하면 Caddy 로그부터 본다.

```bash
docker compose -f docker-compose.prod.yml logs caddy --tail 50
```

---

## 7. Unity 클라이언트 주소 바꾸기

씬 3곳에 서버 주소가 들어 있다.

| 씬 | 오브젝트 | 항목 |
|---|---|---|
| `MvpLobby` | NetworkManager | `backendHost` |
| `MvpLobby` | LobbyCreateRequirementFlow | `apiHost` |
| `MVP_SH` | MvpClassroomFlow | `_backendHost` |

세 곳 모두 `https://<SITE_ADDRESS>` 로 맞춘다. 하나라도 빠지면
"방은 만들어지는데 회의실에서 노드가 안 생긴다" 같은 식으로 절반만 동작한다.

---

## 운영 메모

**환경변수를 바꿨을 때**는 재시작이 아니라 재생성이어야 한다.
`docker restart` 는 컨테이너가 처음 만들어질 때의 환경을 그대로 들고 있어서
`.env` 를 다시 읽지 않는다. 예전에 OpenAI 키를 바꿨는데 안 먹어서 한참 헤맸다.

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps backend
```

**코드를 새로 배포할 때**

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

**DB 백업**

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U nodexr nodexr > backup_$(date +%Y%m%d).sql
```
