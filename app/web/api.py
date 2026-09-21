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


class CaptureTimingRequest(BaseModel):
    mode: str
    frames: int
    milliseconds: int


class DebugCaptureRequest(BaseModel):
    enabled: bool
    start_ms: int
    end_ms: int
    interval_ms: int


class VisionCaptureRequest(BaseModel):
    lookback_ms: int
    match_threshold: float
    stable_px: int
    stable_frames: int
    roi_x: int
    roi_y: int
    roi_w: int
    roi_h: int
    target_x: int
    target_y: int
    target_w: int
    target_h: int


class VisionTemplateRequest(BaseModel):
    x: int
    y: int
    w: int
    h: int


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
        frame_offset,
        rewind_ms,
        frame_before_trigger_ms,
    ) = camera.snapshot(
        manual_path,
        rewind_mode="time",
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
            "frame_offset": frame_offset,
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
        "frame_offset": frame_offset,
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


@router.get("/jobs/{job_id}/debug-frames/{debug_id}")
def debug_frame(job_id: int, debug_id: int):
    value = db.get_debug_snapshot(debug_id)

    if not value or value["job_id"] != job_id:
        raise HTTPException(
            status_code=404,
            detail="调试图片不存在",
        )

    path = Path(value["file_path"])

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="调试图片文件不存在",
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


def _capture_timing_settings():
    values = db.get_app_settings(
        (
            "capture_rewind_mode",
            "capture_rewind_frames",
            "capture_rewind_ms",
        )
    )

    mode = values.get(
        "capture_rewind_mode",
        settings.capture_rewind_mode,
    ).strip().lower()

    if mode not in {"frame", "time"}:
        mode = "time"

    return {
        "mode": mode,
        "frames": max(
            0,
            int(
                values.get(
                    "capture_rewind_frames",
                    settings.capture_rewind_frames,
                )
            ),
        ),
        "milliseconds": max(
            0,
            int(
                values.get(
                    "capture_rewind_ms",
                    settings.capture_rewind_ms,
                )
            ),
        ),
    }


@router.put("/settings/capture-timing")
def update_capture_timing(payload: CaptureTimingRequest):
    mode = payload.mode.strip().lower()

    if mode not in {"frame", "time"}:
        raise HTTPException(
            status_code=400,
            detail="回溯模式必须为 frame 或 time",
        )

    if payload.frames < 0 or payload.frames > 300:
        raise HTTPException(
            status_code=400,
            detail="回溯帧数必须在 0 到 300 之间",
        )

    if payload.milliseconds < 0 or payload.milliseconds > 30000:
        raise HTTPException(
            status_code=400,
            detail="回溯时间必须在 0 到 30000 ms 之间",
        )

    db.set_app_settings(
        {
            "capture_rewind_mode": mode,
            "capture_rewind_frames": payload.frames,
            "capture_rewind_ms": payload.milliseconds,
        }
    )

    return {
        "ok": True,
        "capture_timing": _capture_timing_settings(),
    }


def _debug_capture_settings():
    values = db.get_app_settings(
        (
            "debug_capture_enabled",
            "debug_capture_start_ms",
            "debug_capture_end_ms",
            "debug_capture_interval_ms",
        )
    )

    return {
        "enabled": values.get(
            "debug_capture_enabled",
            "false",
        ).lower() in {"1", "true", "yes", "on"},
        "start_ms": max(
            0,
            int(values.get("debug_capture_start_ms", "3000")),
        ),
        "end_ms": max(
            0,
            int(values.get("debug_capture_end_ms", "0")),
        ),
        "interval_ms": max(
            50,
            int(values.get("debug_capture_interval_ms", "500")),
        ),
    }


@router.put("/settings/debug-capture")
def update_debug_capture(payload: DebugCaptureRequest):
    if payload.start_ms < 0 or payload.start_ms > 30000:
        raise HTTPException(
            status_code=400,
            detail="调试开始时间必须在 0 到 30000 ms 之间",
        )

    if payload.end_ms < 0 or payload.end_ms > 30000:
        raise HTTPException(
            status_code=400,
            detail="调试结束时间必须在 0 到 30000 ms 之间",
        )

    if payload.interval_ms < 50 or payload.interval_ms > 5000:
        raise HTTPException(
            status_code=400,
            detail="调试采样间隔必须在 50 到 5000 ms 之间",
        )

    db.set_app_settings(
        {
            "debug_capture_enabled": "true" if payload.enabled else "false",
            "debug_capture_start_ms": payload.start_ms,
            "debug_capture_end_ms": payload.end_ms,
            "debug_capture_interval_ms": payload.interval_ms,
        }
    )

    return {
        "ok": True,
        "debug_capture": _debug_capture_settings(),
    }


def _vision_capture_settings():
    values = db.get_app_settings(
        (
            "vision_lookback_ms",
            "vision_match_threshold",
            "vision_stable_px",
            "vision_stable_frames",
            "vision_roi_x",
            "vision_roi_y",
            "vision_roi_w",
            "vision_roi_h",
            "vision_target_x",
            "vision_target_y",
            "vision_target_w",
            "vision_target_h",
        )
    )

    return {
        "lookback_ms": max(
            500,
            int(values.get("vision_lookback_ms", "6000")),
        ),
        "match_threshold": min(
            1.0,
            max(
                0.0,
                float(values.get("vision_match_threshold", "0.78")),
            ),
        ),
        "stable_px": max(
            0,
            int(values.get("vision_stable_px", "8")),
        ),
        "stable_frames": max(
            1,
            int(values.get("vision_stable_frames", "2")),
        ),
        "roi": {
            "x": max(0, int(values.get("vision_roi_x", "700"))),
            "y": max(0, int(values.get("vision_roi_y", "0"))),
            "w": max(1, int(values.get("vision_roi_w", "580"))),
            "h": max(1, int(values.get("vision_roi_h", "260"))),
        },
        "target": {
            "x": max(0, int(values.get("vision_target_x", "760"))),
            "y": max(0, int(values.get("vision_target_y", "20"))),
            "w": max(1, int(values.get("vision_target_w", "450"))),
            "h": max(1, int(values.get("vision_target_h", "180"))),
        },
    }


@router.put("/settings/vision-capture")
def update_vision_capture(payload: VisionCaptureRequest):
    if payload.lookback_ms < 500 or payload.lookback_ms > 30000:
        raise HTTPException(
            status_code=400,
            detail="视觉搜索历史范围必须在 500 到 30000 ms 之间",
        )

    if payload.match_threshold < 0 or payload.match_threshold > 1:
        raise HTTPException(
            status_code=400,
            detail="模板匹配阈值必须在 0 到 1 之间",
        )

    if payload.stable_px < 0 or payload.stable_px > 200:
        raise HTTPException(
            status_code=400,
            detail="稳定允许位移必须在 0 到 200 px 之间",
        )

    if payload.stable_frames < 1 or payload.stable_frames > 20:
        raise HTTPException(
            status_code=400,
            detail="连续稳定帧数必须在 1 到 20 之间",
        )

    rect_values = (
        payload.roi_x,
        payload.roi_y,
        payload.roi_w,
        payload.roi_h,
        payload.target_x,
        payload.target_y,
        payload.target_w,
        payload.target_h,
    )

    if any(value < 0 for value in rect_values):
        raise HTTPException(
            status_code=400,
            detail="ROI 和目标区域参数不能为负数",
        )

    if min(
        payload.roi_w,
        payload.roi_h,
        payload.target_w,
        payload.target_h,
    ) < 1:
        raise HTTPException(
            status_code=400,
            detail="ROI 和目标区域宽高必须大于 0",
        )

    db.set_app_settings(
        {
            "vision_lookback_ms": payload.lookback_ms,
            "vision_match_threshold": payload.match_threshold,
            "vision_stable_px": payload.stable_px,
            "vision_stable_frames": payload.stable_frames,
            "vision_roi_x": payload.roi_x,
            "vision_roi_y": payload.roi_y,
            "vision_roi_w": payload.roi_w,
            "vision_roi_h": payload.roi_h,
            "vision_target_x": payload.target_x,
            "vision_target_y": payload.target_y,
            "vision_target_w": payload.target_w,
            "vision_target_h": payload.target_h,
        }
    )

    return {
        "ok": True,
        "vision_capture": _vision_capture_settings(),
    }


def _vision_template_path():
    value = db.get_app_setting("vision_template_path")

    if value:
        return Path(value)

    return (
        settings.database_path.parent
        / "vision"
        / "head-template.jpg"
    )


@router.get("/settings/vision-calibration-image")
def vision_calibration_image():
    latest = db.get_latest_snapshot()

    if not latest or not latest.get("file_path"):
        raise HTTPException(
            status_code=404,
            detail="暂无可用于视觉标定的抓拍图片",
        )

    path = Path(latest["file_path"])

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="标定图片文件不存在",
        )

    return {
        "job_id": latest["job_id"],
        "layer": latest["layer"],
        "snapshot_id": latest["id"],
        "url": (
            f"/api/jobs/{latest['job_id']}/frames/"
            f"{path.name}"
        ),
    }


@router.get("/settings/vision-template")
def vision_template():
    path = _vision_template_path()

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="尚未生成喷头模板",
        )

    return FileResponse(path)


@router.post("/settings/vision-template")
def update_vision_template(payload: VisionTemplateRequest):
    from PIL import Image

    latest = db.get_latest_snapshot()

    if not latest or not latest.get("file_path"):
        raise HTTPException(
            status_code=404,
            detail="暂无可用于生成模板的抓拍图片",
        )

    source = Path(latest["file_path"])

    if not source.is_file():
        raise HTTPException(
            status_code=404,
            detail="源抓拍图片不存在",
        )

    if min(payload.w, payload.h) < 8:
        raise HTTPException(
            status_code=400,
            detail="模板区域太小",
        )

    with Image.open(source) as image:
        width, height = image.size

        x = max(0, min(payload.x, width - 1))
        y = max(0, min(payload.y, height - 1))
        w = max(1, min(payload.w, width - x))
        h = max(1, min(payload.h, height - y))

        target = _vision_template_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        image.crop(
            (x, y, x + w, y + h)
        ).convert("RGB").save(
            target,
            "JPEG",
            quality=95,
        )

    db.set_app_settings(
        {
            "vision_template_path": str(target),
            "vision_template_x": x,
            "vision_template_y": y,
            "vision_template_w": w,
            "vision_template_h": h,
        }
    )

    return {
        "ok": True,
        "template": {
            "configured": True,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "url": "/api/settings/vision-template",
        },
    }


@router.get("/settings")
def get_settings():
    capture_timing = _capture_timing_settings()
    debug_capture = _debug_capture_settings()
    vision_capture = _vision_capture_settings()
    template_values = db.get_app_settings(
        (
            "vision_template_x",
            "vision_template_y",
            "vision_template_w",
            "vision_template_h",
        )
    )
    template_path = _vision_template_path()

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
            "snapshot_retries": settings.snapshot_retries,
            "capture_every_layers": settings.capture_every_layers,
            "rtsp_frame_rate": settings.rtsp_frame_rate,
            "rtsp_frame_max_age": settings.rtsp_frame_max_age,
            "rtsp_history_frames": settings.rtsp_history_frames,
            "capture_rewind_mode": capture_timing["mode"],
            "capture_rewind_frames": capture_timing["frames"],
            "capture_rewind_ms": capture_timing["milliseconds"],
            "debug_capture": debug_capture,
            "vision_capture": {
                **vision_capture,
                "template": {
                    "configured": template_path.is_file(),
                    "x": int(template_values.get("vision_template_x", "0")),
                    "y": int(template_values.get("vision_template_y", "0")),
                    "w": int(template_values.get("vision_template_w", "0")),
                    "h": int(template_values.get("vision_template_h", "0")),
                    "url": (
                        "/api/settings/vision-template"
                        if template_path.is_file()
                        else None
                    ),
                },
            },
        },
        "video": {
            "auto_generate_video": settings.auto_generate_video,
            "fps": settings.timelapse_fps,
            "directory": str(settings.timelapse_dir),
        },
    }
