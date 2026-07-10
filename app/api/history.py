from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from app.schema.history.response import HistoryResponse
from app.service.history.history_service import HistoryService
from app.db.session import get_db
from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.repository.graph_repository import GraphRepository


router = APIRouter(
    prefix="/history",
    tags=["History"],
)


def get_history_service() -> HistoryService:
    return HistoryService(
        graph_repository=GraphRepository(),
    )


@router.get("/{room_id}")
def get_graph_history(
    room_id: UUID,
    db: Session = Depends(get_db),
    history_service: HistoryService = Depends(get_history_service),
):
    result = history_service.get_graph_history(
        db=db,
        room_id=room_id,
    )

    return success_response(
        code=ResponseCode.HISTORY200,
        message="노드 그래프 히스토리 조회 성공",
        result=result,
    )