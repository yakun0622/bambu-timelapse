from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus
from app.services.auth_service import auth_service

router = APIRouter()


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    token = websocket.cookies.get(
        auth_service.COOKIE_NAME
    )
    user = auth_service.authenticate(token)

    if not user or user["must_change_password"]:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    queue = await event_bus.subscribe()

    try:
        await websocket.send_json(
            {
                "type": "CONNECTED",
                "message": "实时连接已建立",
                "data": {},
            }
        )

        while True:
            event = await queue.get()
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass

    finally:
        event_bus.unsubscribe(queue)
