from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import get_db
from app.schema.graph.part_node_request import (
    CreatePartNodeRequest,
    DeletePartNodeRequest,
    ModifyPartNodeRequest,
)
from app.service.graph.part_node_service import PartNodeService

router = APIRouter(
    prefix="/part_node",
    tags=["Part Node"],
)

part_node_service = PartNodeService()


@router.post("/generate")
def create_part_node(
    request: CreatePartNodeRequest,
    db: Session = Depends(get_db),
):
    result = part_node_service.create_part_node(
        request=request,
        db=db,
    )

    return success_response(
        code=ResponseCode.PART_NODE200,
        result=result.model_dump(mode="json"),
    )


@router.patch("/modify")
def modify_part_node(
    request: ModifyPartNodeRequest,
    db: Session = Depends(get_db),
):
    result = part_node_service.modify_part_node(
        request=request,
        db=db,
    )

    return success_response(
        code=ResponseCode.PART_NODE201,
        result=result.model_dump(mode="json"),
    )


@router.delete("/delete")
def delete_part_node(
    request: DeletePartNodeRequest,
    db: Session = Depends(get_db),
):
    result = part_node_service.delete_part_node(
        request=request,
        db=db,
    )

    return success_response(
        code=ResponseCode.PART_NODE202,
        result=result.model_dump(mode="json"),
    )
