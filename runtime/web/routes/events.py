from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

HEARTBEAT_SECONDS = 15.0


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/events/stream")
async def events_stream(request: Request) -> StreamingResponse:
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        raise HTTPException(status_code=404, detail="Realtime is disabled")

    route = request.query_params.get("route", "home")
    project_id = request.query_params.get("project_id", "")

    async def event_generator():
        queue = bus.create_subscription()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    change = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield _format_sse("heartbeat", {})
                    continue
                if change is None:
                    break
                yield _format_sse(
                    "data_changed",
                    {
                        "scope": route,
                        "project_id": project_id,
                        "db_path": str(change.db_path),
                    },
                )
        finally:
            bus.remove_subscription(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
