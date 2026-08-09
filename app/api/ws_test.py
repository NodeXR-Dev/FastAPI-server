from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["WebSocket Test"])

TEST_PAGE_PATH = Path(__file__).parents[1] / "static" / "ws_2d_test.html"


@router.get("/ws-2d-test", include_in_schema=False)
def get_ws_2d_test_page() -> FileResponse:
    return FileResponse(TEST_PAGE_PATH, media_type="text/html")
