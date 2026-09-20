import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.events import event_bus
from app.integrations.bambu.mqtt import BambuMQTT
from app.services.capture_service import capture_service
from app.services.print_service import print_service
from app.web.api import router as api_router
from app.web.websocket import router as ws_router

mqtt_service = BambuMQTT(print_service.update)


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bus.bind_loop(asyncio.get_running_loop())
    capture_service.start()
    mqtt_service.start()
    yield
    mqtt_service.stop()
    capture_service.stop()


app = FastAPI(title="Bambu Timelapse", version="0.2.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "mqtt_connected": mqtt_service.connected,
    }


if settings.web_dist.exists():
    assets = settings.web_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        requested = settings.web_dist / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(settings.web_dist / "index.html")
