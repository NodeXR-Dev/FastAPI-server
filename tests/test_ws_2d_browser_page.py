import asyncio
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ws_room_event import route_ws_event
from app.api.ws_test import router
from app.schema.websocket.ws_event import WSEvent


def test_ws_connect_event_returns_registration_ack_payload():
    event = WSEvent(
        event_type="WS_CONNECT",
        room_id=uuid4(),
        user_id=uuid4(),
        payload={},
    )

    ack_payload, server_events = asyncio.run(
        route_ws_event(
            db=Mock(),
            event=event,
            user_id=event.user_id,
        )
    )

    assert ack_payload == {"connected": True}
    assert server_events == []


def test_browser_test_page_contains_ws_registration_generation_and_preview_code():
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/ws-2d-test")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'event_type: "WS_CONNECT"' in response.text
    assert 'new WebSocket(elements.wsUrl.value.trim())' in response.text
    assert 'fetch("/api/2d/generate/graph"' in response.text
    assert 'event.event_type === "2D_GENERATED"' in response.text
    assert "event.payload?.img_url" in response.text
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in response.text


def test_browser_test_page_file_is_resolved_inside_app_static_directory():
    page = Path(__file__).parents[1] / "app" / "static" / "ws_2d_test.html"

    assert page.is_file()
