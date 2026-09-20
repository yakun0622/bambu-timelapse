from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.events import event_bus
from app.integrations.bambu.mqtt import mqtt_state
from app.integrations.yi.camera import camera
from app.services.auth_service import auth_service
from app.services.print_service import print_service
from app.storage.database import db


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _session_cookie(request: Request):
    return request.cookies.get(auth_service.COOKIE_NAME)


def require_user(request: Request):
    user = auth_service.authenticate(_session_cookie(request))

    if not user:
        raise HTTPException(
            status_code=401,
            detail="请先登录",
        )

    return user


def require_ready_user(request: Request):
    user = require_user(request)

    if user["must_change_password"]:
        raise HTTPException(
            status_code=403,
            detail="首次登录必须修改默认密码",
            headers={"X-Password-Change-Required": "1"},
        )

    return user


auth_router = APIRouter(prefix="/api/auth")


@auth_router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    token, user = auth_service.login(
        payload.username.strip(),
        payload.password,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="账号或密码错误",
        )

    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=token,
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )

    return {"user": user}


@auth_router.get("/me")
def me(user=Depends(require_user)):
    return {"user": user}


@auth_router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user=Depends(require_user),
):
    ok, error = auth_service.change_password(
        user["id"],
        payload.current_password,
        payload.new_password,
    )

    if not ok:
        raise HTTPException(
            status_code=400,
            detail=error,
        )

    token, updated_user = auth_service.login(
        user["username"],
        payload.new_password,
    )

    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=token,
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )

    return {
        "ok": True,
        "user": updated_user,
    }


@auth_router.post("/logout")
def logout(request: Request, response: Response):
    auth_service.logout(_session_cookie(request))
    response.delete_cookie(
        auth_service.COOKIE_NAME,
        path="/",
    )
    return {"ok": True}


router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_ready_user)],
)


@router.get("/status")
def status():
    current = print_service.status()
    job = (
        db.get_job(current["job_id"])
        if current.get("job_id")
        else None
    )

    latest_snapshot = db.get_latest_snapshot(
        current.get("job_id")
    )

    if latest_snapshot:
        latest_snapshot = {
            **latest_snapshot,
            "url": (
                f"/api/jobs/{latest_snapshot['job_id']}/frames/"
                f"{Path(latest_snapshot['file_path']).name}"
            ),
        }

    return {
        "printer": {
            **current,
            "online": bool(mqtt_state["connected"]),
            "last_message_at": mqtt_state["last_message_at"],
        },
        "camera": {
            "ip": settings.yi_ip,
            "configured": bool(settings.yi_ip),
            "capture_source": settings.capture_source,
            "rtsp": camera.rtsp_status(),
        },
        "job": job,
        "latest_snapshot": latest_snapshot,
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
        raise HTTPException(
            status_code=409,
            detail="当前没有活动打印任务",
        )

    manual_path = (
        Path(job_dir)
        / f"manual_{layer:04d}.jpg"
    )

    (
        ok,
        duration_ms,
        error,
        source,
        frame_age_ms,
        rewind_ms,
        frame_before_trigger_ms,
    ) = camera.snapshot(
        manual_path,
        rewind_ms=0,
    )

    if not ok:
        raise HTTPException(
            status_code=502,
            detail=error or "抓拍失败",
        )

    event_bus.emit(
        "SNAPSHOT_SUCCESS",
        f"已手动抓拍第 {layer} 层",
        {
            "job_id": job_id,
            "layer": layer,
            "path": str(manual_path),
            "manual": True,
            "source": source,
            "duration_ms": duration_ms,
            "frame_age_ms": frame_age_ms,
            "rewind_ms": rewind_ms,
            "frame_before_trigger_ms": frame_before_trigger_ms,
        },
    )

    return {
        "ok": True,
        "path": str(manual_path),
        "duration_ms": duration_ms,
        "source": source,
        "frame_age_ms": frame_age_ms,
        "rewind_ms": rewind_ms,
        "frame_before_trigger_ms": frame_before_trigger_ms,
    }


@router.get("/jobs")
def jobs():
    return db.list_jobs()


@router.get("/jobs/{job_id}")
def job(job_id: int):
    value = db.get_job(job_id)

    if not value:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    return value


@router.get("/jobs/{job_id}/frames/{filename}")
def frame(job_id: int, filename: str):
    job_data = db.get_job(job_id)

    if not job_data:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    safe_name = Path(filename).name
    path = Path(job_data["output_dir"]) / safe_name

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="图片不存在",
        )

    return FileResponse(path)


@router.get("/jobs/{job_id}/video")
def video(job_id: int):
    job_data = db.get_job(job_id)

    if not job_data or not job_data.get("video_path"):
        raise HTTPException(
            status_code=404,
            detail="视频不存在",
        )

    path = Path(job_data["video_path"])

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="视频文件不存在",
        )

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name,
    )


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
            "capture_source": settings.capture_source,
            "rtsp_port": settings.yi_rtsp_port,
            "rtsp_path": settings.yi_rtsp_path,
            "rtsp_url_configured": bool(settings.yi_rtsp_url),
            "rtsp_display_url": camera.rtsp_display_url,
        },
        "capture": {
            "auto_capture": settings.auto_capture,
            "snapshot_delay": settings.snapshot_delay,
            "snapshot_retries": settings.snapshot_retries,
            "capture_every_layers": settings.capture_every_layers,
            "rtsp_capture_timeout": settings.rtsp_capture_timeout,
            "rtsp_frame_rate": settings.rtsp_frame_rate,
            "rtsp_frame_max_age": settings.rtsp_frame_max_age,
            "rtsp_history_frames": settings.rtsp_history_frames,
            "capture_rewind_ms": settings.capture_rewind_ms,
        },
        "video": {
            "auto_generate_video": settings.auto_generate_video,
            "fps": settings.timelapse_fps,
            "directory": str(settings.timelapse_dir),
        },
    }
