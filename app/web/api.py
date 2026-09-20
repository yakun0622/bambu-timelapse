from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.events import event_bus
from app.integrations.yi.camera import camera
from app.services.capture_service import capture_service
from app.services.print_service import print_service
from app.storage.database import db

router = APIRouter(prefix="/api")


@router.get("/status")
def status():
    current = print_service.status()
    job = db.get_job(current["job_id"]) if current.get("job_id") else None
    return {
        "printer": current,
        "camera": {
            "ip": settings.yi_ip,
        },
        "job": job,
        "events": event_bus.recent(20),
    }


@router.get("/printer")
def printer():
    return print_service.status()


@router.get("/camera")
def camera_info():
    return {
        "ip": settings.yi_ip,
        "user": settings.yi_user,
        "configured": bool(settings.yi_ip),
    }


@router.post("/camera/test")
def camera_test():
    return camera.test()


@router.post("/camera/snapshot")
def manual_snapshot():
    job_id = print_service.current_job_id
    job_dir = print_service.current_job_dir
    layer = print_service.state.get("layer_num")

    if not job_id or not job_dir or not isinstance(layer, int):
        raise HTTPException(status_code=409, detail="No active print job")

    manual_path = Path(job_dir) / f"manual_{layer:04d}.jpg"
    ok, duration_ms, error = camera.snapshot(manual_path)
    if not ok:
        raise HTTPException(status_code=502, detail=error or "Snapshot failed")

    event_bus.emit(
        "SNAPSHOT_SUCCESS",
        f"Manual snapshot saved for layer {layer}",
        {"job_id": job_id, "layer": layer, "path": str(manual_path), "manual": True},
    )
    return {"ok": True, "path": str(manual_path), "duration_ms": duration_ms}


@router.get("/jobs")
def jobs():
    return db.list_jobs()


@router.get("/jobs/{job_id}")
def job(job_id: int):
    value = db.get_job(job_id)
    if not value:
        raise HTTPException(status_code=404, detail="Job not found")
    return value


@router.get("/jobs/{job_id}/frames/{filename}")
def frame(job_id: int, filename: str):
    job_data = db.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    safe_name = Path(filename).name
    path = Path(job_data["output_dir"]) / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path)


@router.get("/jobs/{job_id}/video")
def video(job_id: int):
    job_data = db.get_job(job_id)
    if not job_data or not job_data.get("video_path"):
        raise HTTPException(status_code=404, detail="Video not found")

    path = Path(job_data["video_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/settings")
def get_settings():
    return {
        "bambu": {
            "mqtt_host": settings.mqtt_host,
            "mqtt_port": settings.mqtt_port,
            "user_id_configured": bool(settings.bambu_user_id),
            "access_token_configured": bool(settings.bambu_access_token),
            "device_id": settings.bambu_device_id,
        },
        "camera": {
            "ip": settings.yi_ip,
            "user": settings.yi_user,
            "password_configured": bool(settings.yi_password),
        },
        "capture": {
            "auto_capture": settings.auto_capture,
            "snapshot_delay": settings.snapshot_delay,
            "snapshot_retries": settings.snapshot_retries,
            "capture_every_layers": settings.capture_every_layers,
        },
        "video": {
            "auto_generate_video": settings.auto_generate_video,
            "fps": settings.timelapse_fps,
            "directory": str(settings.timelapse_dir),
        },
    }
