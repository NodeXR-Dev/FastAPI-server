from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.startup import bootstrap_infrastructure
from app.service.utterance.embedding_service import get_embedding_model
from app.service.agent.reflection_scheduler import get_reflection_scheduler

from app.api.utterance import router as utterance_router
from app.api.room import router as room_router
from app.api.feature import router as feature_router
from app.api.ws_room_event import router as ws_room_event_router
from app.api.generation import router as generation_router
from app.api.history import router as history_router
from app.api.part_node import router as part_node_router
from app.api.reference import router as reference_router
from app.api.graph import router as graph_router

from app.core.response.exceptions import (
    BaseCustomException,
    NotFoundException,
    ServerException,
)
from app.core.response.exception_handler import (
    custom_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 실행
    bootstrap_infrastructure()
    get_embedding_model()
    reflection_scheduler = get_reflection_scheduler()
    reflection_scheduler.start()

    try:
        yield
    finally:
        await reflection_scheduler.stop()


app = FastAPI(
    lifespan=lifespan,
)


# =========================
# Router
# =========================

app.include_router(
    utterance_router,
    prefix="/api",
)

app.include_router(
    room_router,
    prefix="/api",
)

app.include_router(
    feature_router,
    prefix="/api",
)

app.include_router(
    ws_room_event_router,
    prefix="/ws"
)
app.include_router(
    generation_router,
    prefix="/api"
)
app.include_router(
    history_router,
    prefix="/api"
)
app.include_router(
    part_node_router,
    prefix="/api",
)

app.include_router(
    reference_router,
    prefix="/api",
)

app.include_router(
    graph_router,
    prefix="/api",
)

# =========================
# Exception Handler
# =========================

app.add_exception_handler(
    BaseCustomException,
    custom_exception_handler,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)


@app.get("/")
def root():
    return {
        "message": "NodeXR server running"
    }
