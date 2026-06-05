from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.service.utterance.embedding_service import get_embedding_model

from app.api.utterance import router as utterance_router
from app.api.room import router as room_router

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
    get_embedding_model()

    yield

    # 서버 종료 시 실행
    # close_something()


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