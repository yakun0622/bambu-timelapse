from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus

router = APIRouter()


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    queue = await event_bus.subscribe()

    try:
        await websocket.send_json({"type": "CONNECTED", "message": "WebSocket connected", "data": {}})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)
