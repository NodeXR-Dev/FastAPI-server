from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException
from app.core.response.response import success_response
from app.db.session import get_db
from app.schema.graph.reference_request import (
    GenerateReferenceRequest,
    ReferenceMetadataRequest,
)
from app.service.graph.reference_service import ReferenceService

router = APIRouter(
    prefix="/references",
    tags=["Reference"],
)

reference_service = ReferenceService()


@router.post("/generate")
def generate_reference(
    room_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    node_id: Annotated[UUID, Form()],
    metadata: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    image_bytes = file.file.read()

    try:
        parsed_metadata = ReferenceMetadataRequest.model_validate_json(metadata)
    except ValidationError as exc:
        raise BadRequestException(
            code=ResponseCode.REFERENCE400,
            message="metadata는 유효한 JSON 형식이어야 합니다.",
        ) from exc

    request = GenerateReferenceRequest(
        room_id=room_id,
        node_id=node_id,
        metadata=parsed_metadata,
    )

    result = reference_service.generate_reference(
        db=db,
        request=request,
        image_bytes=image_bytes,
        filename=file.filename,
        upload_content_type=file.content_type,
    )

    return success_response(
        code=ResponseCode.REFERENCE201,
        result=result.model_dump(mode="json"),
    )
