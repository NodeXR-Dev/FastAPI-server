from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import get_db
from app.service.graph.graph_restore_service import GraphRestoreService

router = APIRouter(
    prefix="/graph",
    tags=["Graph"],
)

graph_restore_service = GraphRestoreService()


@router.get("")
def get_room_graph(
    room_id: UUID,
    db: Session = Depends(get_db),
):
    result = graph_restore_service.get_room_graph(
        db=db,
        room_id=room_id,
    )

    return success_response(
        code=ResponseCode.GRAPH200,
        result=result.model_dump(mode="json"),
    )
