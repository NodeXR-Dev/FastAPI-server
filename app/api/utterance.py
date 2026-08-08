import time

from app.core.response.code import ResponseCode
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.response import success_response
from app.db.session import get_db
from app.schema.utterance.request import CreateNodeUtteranceRequest
from app.service.utterance.button_utterance_service import ButtonUtteranceService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/utterances",
    tags=["Utterances"],
)

button_utterance_service = ButtonUtteranceService()


@router.post("")
def create_node_from_utterance(
    request: CreateNodeUtteranceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):

    stage = "api_utterance_create_node_from_utterance"
    start_time = time.perf_counter()

    logger.info(
        "[api_utterance_create_node_utterance] request_start | room_id=%s | user_id=%s | parent_node_id=%s | utterance_length=%s",
        request.room_id,
        request.user_id,
        request.parent_node_id,
        len(request.utterance),
    )

    
    result = button_utterance_service.create_node_graph_from_utterance(
        db=db,
        request=request,
        background_tasks=background_tasks,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    avg_ms = performance_tracker.record(stage, elapsed_ms)

    logger.info(
        "[api_utterance_create_node_utterance] request_done | elapsed_ms=%.2f | avg_ms=%.2f | room_id=%s | graph_version=%s ",
        elapsed_ms,
        avg_ms,
        result.room_id,
        result.graph_version,
    )

    return success_response(
        code=ResponseCode.BTUTT200,
        result=result.model_dump(mode="json"),
    )
