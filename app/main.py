from contextlib import asynccontextmanager

from app.services.utterances.embedding_service import get_embedding_model
from fastapi import FastAPI

from app.api.routes.utterance import router as utterance_router

from app.core.response.exceptions import BaseCustomException, NotFoundException, ServerException
from app.core.response.exception_handler import (
    custom_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.include_router(
    utterance_router,
    prefix="/api",
)

app.add_exception_handler(BaseCustomException, custom_exception_handler)
app.add_exception_handler(NotFoundException, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 실행
    get_embedding_model()

    yield

    # 서버 종료 시 실행
    # close_something()


@app.get("/")
def root():
    return {
        "message": "NodeXR server running"
    }