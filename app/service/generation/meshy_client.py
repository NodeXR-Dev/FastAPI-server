import asyncio
import base64
import time
from collections.abc import Awaitable, Callable

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.schema.generation.generation_result import Generated3DModelBinary

logger = get_logger(__name__)


class MeshyClientError(RuntimeError):
    pass


class MeshyTaskFailedError(MeshyClientError):
    pass


class MeshyTaskTimeoutError(MeshyClientError):
    pass


class MeshyClient:
    SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
    RUNNING_STATUSES = {"PENDING", "IN_PROGRESS"}
    FAILED_STATUSES = {"FAILED", "CANCELED"}

    def __init__(
        self,
        *,
        api_key: str | None = settings.MESHY_API_KEY,
        base_url: str = settings.MESHY_BASE_URL,
        poll_interval_seconds: float = settings.MESHY_POLL_INTERVAL_SECONDS,
        poll_timeout_seconds: float = settings.MESHY_POLL_TIMEOUT_SECONDS,
        http_timeout_seconds: float = settings.MESHY_HTTP_TIMEOUT_SECONDS,
        target_polycount: int = settings.MESHY_TARGET_POLYCOUNT,
        topology: str = settings.MESHY_TOPOLOGY,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.http_timeout_seconds = http_timeout_seconds
        self.target_polycount = target_polycount
        self.topology = topology
        self.transport = transport
        self.sleep = sleep
        self.monotonic = monotonic

    async def generate_glb(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
    ) -> Generated3DModelBinary:
        if not self.api_key:
            raise MeshyClientError("MESHY_API_KEY가 설정되지 않았습니다.")
        if mime_type not in self.SUPPORTED_IMAGE_MIME_TYPES:
            raise MeshyClientError("Meshy가 지원하지 않는 이미지 형식입니다.")
        if not image_bytes:
            raise MeshyClientError("Meshy 입력 이미지가 비어 있습니다.")

        image_data_uri = self._build_image_data_uri(
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        timeout = httpx.Timeout(self.http_timeout_seconds)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                task_id = await self._create_task(
                    client=client,
                    image_data_uri=image_data_uri,
                )
                glb_url = await self._wait_for_glb_url(
                    client=client,
                    task_id=task_id,
                )
                model_bytes = await self._download_glb(
                    client=client,
                    glb_url=glb_url,
                )
        except httpx.RequestError as exc:
            raise MeshyClientError("Meshy API 네트워크 요청에 실패했습니다.") from exc

        return Generated3DModelBinary(
            task_id=task_id,
            model_bytes=model_bytes,
        )

    async def _create_task(
        self,
        *,
        client: httpx.AsyncClient,
        image_data_uri: str,
    ) -> str:
        body: dict = {
            "image_url": image_data_uri,
            "target_formats": ["glb"],
        }

        # 폴리곤 상한. should_remesh 를 켜야 target_polycount 가 먹는다.
        # Unity(glTFast)는 어차피 삼각형으로 읽으므로 quad 로 받을 이유가 없다.
        if self.target_polycount > 0:
            body["should_remesh"] = True
            body["target_polycount"] = self.target_polycount
            body["topology"] = self.topology

        response = await client.post(
            f"{self.base_url}/openapi/v1/image-to-3d",
            headers=self._authorization_headers(),
            json=body,
        )
        self._raise_for_status(response=response)
        payload = self._parse_json(response=response)
        task_id = payload.get("result")
        if not isinstance(task_id, str) or not task_id.strip():
            raise MeshyClientError("Meshy task ID가 응답에 없습니다.")

        logger.info("[meshy_task_created] task_id=%s", task_id)
        return task_id

    async def _wait_for_glb_url(
        self,
        *,
        client: httpx.AsyncClient,
        task_id: str,
    ) -> str:
        deadline = self.monotonic() + self.poll_timeout_seconds

        while True:
            if self.monotonic() >= deadline:
                raise MeshyTaskTimeoutError(
                    f"Meshy task polling timeout: task_id={task_id}"
                )

            response = await client.get(
                f"{self.base_url}/openapi/v1/image-to-3d/{task_id}",
                headers=self._authorization_headers(),
            )
            self._raise_for_status(response=response)
            payload = self._parse_json(response=response)
            status = payload.get("status")
            progress = payload.get("progress")

            logger.info(
                "[meshy_task_polled] task_id=%s | status=%s | progress=%s",
                task_id,
                status,
                progress,
            )

            if status == "SUCCEEDED":
                model_urls = payload.get("model_urls")
                glb_url = (
                    model_urls.get("glb")
                    if isinstance(model_urls, dict)
                    else None
                )
                if not isinstance(glb_url, str) or not glb_url.strip():
                    raise MeshyClientError(
                        "성공한 Meshy task에 GLB URL이 없습니다."
                    )
                return glb_url

            if status in self.FAILED_STATUSES:
                task_error = payload.get("task_error")
                error_message = (
                    task_error.get("message")
                    if isinstance(task_error, dict)
                    else None
                )
                raise MeshyTaskFailedError(
                    f"Meshy task {status}: {error_message or 'unknown error'}"
                )

            if status not in self.RUNNING_STATUSES:
                raise MeshyClientError(f"알 수 없는 Meshy task 상태입니다: {status}")

            remaining_seconds = deadline - self.monotonic()
            if remaining_seconds <= 0:
                raise MeshyTaskTimeoutError(
                    f"Meshy task polling timeout: task_id={task_id}"
                )
            await self.sleep(min(self.poll_interval_seconds, remaining_seconds))

    async def _download_glb(
        self,
        *,
        client: httpx.AsyncClient,
        glb_url: str,
    ) -> bytes:
        response = await client.get(glb_url)
        self._raise_for_status(response=response)
        model_bytes = response.content
        if len(model_bytes) < 12 or model_bytes[:4] != b"glTF":
            raise MeshyClientError("Meshy 결과가 유효한 GLB 파일이 아닙니다.")

        logger.info("[meshy_glb_downloaded] size=%s", len(model_bytes))
        return model_bytes

    def _authorization_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_image_data_uri(*, image_bytes: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _parse_json(*, response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MeshyClientError(
                "Meshy API가 유효한 JSON을 반환하지 않았습니다."
            ) from exc
        if not isinstance(payload, dict):
            raise MeshyClientError("Meshy API 응답 형식이 올바르지 않습니다.")
        return payload

    @staticmethod
    def _raise_for_status(*, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MeshyClientError(
                f"Meshy API HTTP 오류: status={response.status_code}"
            ) from exc
