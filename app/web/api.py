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
from app.services.timelapse_service import timelapse_service
from app.services.vision_service import vision_selector
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
    bed_match_threshold: float
    bed_locator_mode: str
    aruco_id: int
    aruco_dictionary: str
    reference_similarity_threshold: float
    reference_start_layer: int
    reference_max_shift_px: int
    motion_max_px: float
    motion_stable_frames: int
    sharpness_min: float
    model_roi_x: int
    model_roi_y: int
    model_roi_w: int
    model_roi_h: int
    stable_px: int
    bed_stable_px: int
    stable_frames: int
    align_enabled: bool
    align_max_shift_px: int
    roi_x: int
    roi_y: int
    roi_w: int
    roi_h: int
    target_x: int
    target_y: int
    target_w: int
    target_h: int
    bed_roi_x: int
    bed_roi_y: int
    bed_roi_w: int
    bed_roi_h: int
    bed_target_x: int
    bed_target_y: int
    bed_target_w: int
    bed_target_h: int


class VisionTemplateRequest(BaseModel):
    snapshot_id: int
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


@router.post("/jobs/{job_id}/video/generate")
def generate_video(job_id: int):
    job_data = db.get_job(job_id)

    if not job_data:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    job_dir = Path(job_data["output_dir"])
    images = sorted(job_dir.glob("layer_*.jpg"))

    if len(images) < 2:
        raise HTTPException(
            status_code=409,
            detail="至少需要 2 张抓拍图片才能生成视频",
        )

    started = timelapse_service.generate_async(
        job_id,
        job_dir,
        force=True,
    )

    if not started:
        raise HTTPException(
            status_code=409,
            detail="该任务的视频正在生成中",
        )

    return {
        "ok": True,
        "job_id": job_id,
        "frames": len(images),
        "message": "已开始生成延时视频",
    }


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

    if mode not in {"frame", "time", "vision"}:
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

    if mode not in {"frame", "time", "vision"}:
        raise HTTPException(
            status_code=400,
            detail="抓拍定位模式必须为 frame、time 或 vision",
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
            "vision_bed_match_threshold",
            "vision_bed_locator_mode",
            "vision_aruco_id",
            "vision_aruco_dictionary",
            "vision_reference_similarity_threshold",
            "vision_reference_start_layer",
            "vision_reference_max_shift_px",
            "vision_motion_max_px",
            "vision_motion_stable_frames",
            "vision_sharpness_min",
            "vision_model_roi_x",
            "vision_model_roi_y",
            "vision_model_roi_w",
            "vision_model_roi_h",
            "vision_stable_px",
            "vision_bed_stable_px",
            "vision_stable_frames",
            "vision_align_enabled",
            "vision_align_max_shift_px",
            "vision_roi_x",
            "vision_roi_y",
            "vision_roi_w",
            "vision_roi_h",
            "vision_target_x",
            "vision_target_y",
            "vision_target_w",
            "vision_target_h",
            "vision_bed_roi_x",
            "vision_bed_roi_y",
            "vision_bed_roi_w",
            "vision_bed_roi_h",
            "vision_bed_target_x",
            "vision_bed_target_y",
            "vision_bed_target_w",
            "vision_bed_target_h",
        )
    )

    return {
        "lookback_ms": max(
            500,
            int(values.get("vision_lookback_ms", "8000")),
        ),
        "match_threshold": min(
            1.0,
            max(
                0.0,
                float(values.get("vision_match_threshold", "0.78")),
            ),
        ),
        "bed_match_threshold": min(
            1.0,
            max(
                0.0,
                float(values.get("vision_bed_match_threshold", "0.78")),
            ),
        ),
        "bed_locator_mode": values.get(
            "vision_bed_locator_mode",
            "reference",
        ).strip().lower(),
        "aruco_id": max(
            0,
            int(values.get("vision_aruco_id", "23")),
        ),
        "aruco_dictionary": values.get(
            "vision_aruco_dictionary",
            "DICT_4X4_50",
        ).strip().upper(),
        "reference_similarity_threshold": min(
            1.0,
            max(
                0.0,
                float(
                    values.get(
                        "vision_reference_similarity_threshold",
                        "0.50",
                    )
                ),
            ),
        ),
        "reference_start_layer": max(
            2,
            int(
                values.get(
                    "vision_reference_start_layer",
                    "2",
                )
            ),
        ),
        "reference_max_shift_px": max(
            1,
            int(
                values.get(
                    "vision_reference_max_shift_px",
                    "60",
                )
            ),
        ),
        "motion_max_px": max(
            0.0,
            float(
                values.get(
                    "vision_motion_max_px",
                    "2.5",
                )
            ),
        ),
        "motion_stable_frames": max(
            1,
            int(
                values.get(
                    "vision_motion_stable_frames",
                    "2",
                )
            ),
        ),
        "sharpness_min": max(
            0.0,
            float(
                values.get(
                    "vision_sharpness_min",
                    "60",
                )
            ),
        ),
        "model_roi": {
            "x": max(0, int(values.get("vision_model_roi_x", "80"))),
            "y": max(0, int(values.get("vision_model_roi_y", "150"))),
            "w": max(1, int(values.get("vision_model_roi_w", "1120"))),
            "h": max(1, int(values.get("vision_model_roi_h", "520"))),
        },
        "stable_px": max(
            0,
            int(values.get("vision_stable_px", "8")),
        ),
        "bed_stable_px": max(
            0,
            int(values.get("vision_bed_stable_px", "8")),
        ),
        "stable_frames": max(
            1,
            int(values.get("vision_stable_frames", "2")),
        ),
        "align_enabled": values.get(
            "vision_align_enabled",
            "true",
        ).lower() in {"1", "true", "yes", "on"},
        "align_max_shift_px": max(
            0,
            int(values.get("vision_align_max_shift_px", "30")),
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
            "w": max(1, int(values.get("vision_target_w", "180"))),
            "h": max(1, int(values.get("vision_target_h", "100"))),
        },
        "bed_roi": {
            "x": max(0, int(values.get("vision_bed_roi_x", "0"))),
            "y": max(0, int(values.get("vision_bed_roi_y", "250"))),
            "w": max(1, int(values.get("vision_bed_roi_w", "1280"))),
            "h": max(1, int(values.get("vision_bed_roi_h", "470"))),
        },
        "bed_target": {
            "x": max(0, int(values.get("vision_bed_target_x", "0"))),
            "y": max(0, int(values.get("vision_bed_target_y", "250"))),
            "w": max(1, int(values.get("vision_bed_target_w", "1280"))),
            "h": max(1, int(values.get("vision_bed_target_h", "470"))),
        },
    }


@router.post("/settings/vision-test")
def test_vision():
    latest = camera.get_latest_rtsp_frame()

    if not latest:
        raise HTTPException(
            status_code=409,
            detail="当前没有可用的 RTSP 实时帧",
        )

    config = _vision_capture_settings()
    template_path = _vision_template_path()
    bed_template_path = _vision_bed_template_path()

    if config["bed_locator_mode"] == "reference":
        current = print_service.status()
        job_id = current.get("job_id")
        reference = (
            db.get_latest_snapshot(job_id)
            if job_id
            else None
        )

        if not reference or not reference.get("file_path"):
            return {
                "ok": False,
                "mode": "reference",
                "reason": "当前任务还没有上一张成功抓拍，暂时无法测试上一帧相似度",
                "frame_age_ms": latest["age_ms"],
                "frame_seq": latest["seq"],
            }

        result, error = vision_selector.select_reference(
            history=[
                {
                    "seq": latest["seq"],
                    "at": latest["at"],
                    "data": latest["data"],
                }
            ],
            trigger_at=latest["at"],
            reference_path=reference["file_path"],
            model_roi=config["model_roi"],
            head_template_path=template_path,
            head_roi=config["roi"],
            head_target=config["target"],
            head_match_threshold=config["match_threshold"],
            similarity_threshold=config[
                "reference_similarity_threshold"
            ],
            max_shift_px=config[
                "reference_max_shift_px"
            ],
            motion_max_px=config["motion_max_px"],
            motion_stable_frames=1,
            sharpness_min=config["sharpness_min"],
            align_enabled=False,
        )

        return {
            "ok": bool(result),
            "mode": "reference",
            "reason": (
                "当前画面满足上一帧相似度与清晰度条件"
                if result
                else error
            ),
            "head_score": (
                result.get("head_score")
                if result
                else None
            ),
            "similarity_score": (
                result.get("similarity_score")
                if result
                else None
            ),
            "motion_px": (
                result.get("motion_px")
                if result
                else None
            ),
            "sharpness": (
                result.get("sharpness")
                if result
                else None
            ),
            "reference_layer": reference.get("layer"),
            "frame_age_ms": latest["age_ms"],
            "frame_seq": latest["seq"],
        }

    result = vision_selector.diagnose_frame(
        frame_data=latest["data"],
        head_template_path=template_path,
        head_roi=config["roi"],
        head_target=config["target"],
        bed_template_path=bed_template_path,
        bed_roi=config["bed_roi"],
        bed_target=config["bed_target"],
        bed_locator_mode=config["bed_locator_mode"],
        aruco_id=config["aruco_id"],
        aruco_dictionary=config["aruco_dictionary"],
        head_match_threshold=config["match_threshold"],
        bed_match_threshold=config["bed_match_threshold"],
    )

    return {
        **result,
        "mode": config["bed_locator_mode"],
        "frame_age_ms": latest["age_ms"],
        "frame_seq": latest["seq"],
    }


@router.put("/settings/vision-capture")
def update_vision_capture(payload: VisionCaptureRequest):
    if payload.lookback_ms < 500 or payload.lookback_ms > 30000:
        raise HTTPException(
            status_code=400,
            detail="视觉搜索历史范围必须在 500 到 30000 ms 之间",
        )

    if not 0 <= payload.match_threshold <= 1:
        raise HTTPException(
            status_code=400,
            detail="喷头模板匹配阈值必须在 0 到 1 之间",
        )

    if not 0 <= payload.bed_match_threshold <= 1:
        raise HTTPException(
            status_code=400,
            detail="热床模板匹配阈值必须在 0 到 1 之间",
        )

    if not 0 <= payload.reference_similarity_threshold <= 1:
        raise HTTPException(
            status_code=400,
            detail="上一帧相似度阈值必须在 0 到 1 之间",
        )

    if payload.reference_start_layer < 2 or payload.reference_start_layer > 100:
        raise HTTPException(
            status_code=400,
            detail="上一帧匹配启用层必须在 2 到 100 之间",
        )

    if payload.reference_max_shift_px < 1 or payload.reference_max_shift_px > 300:
        raise HTTPException(
            status_code=400,
            detail="上一帧最大位移必须在 1 到 300 px 之间",
        )

    if payload.motion_max_px < 0 or payload.motion_max_px > 100:
        raise HTTPException(
            status_code=400,
            detail="运动阈值必须在 0 到 100 px 之间",
        )

    if payload.motion_stable_frames < 1 or payload.motion_stable_frames > 10:
        raise HTTPException(
            status_code=400,
            detail="连续静止帧数必须在 1 到 10 之间",
        )

    if payload.sharpness_min < 0 or payload.sharpness_min > 10000:
        raise HTTPException(
            status_code=400,
            detail="清晰度阈值必须在 0 到 10000 之间",
        )

    bed_locator_mode = payload.bed_locator_mode.strip().lower()

    if bed_locator_mode not in {"reference", "aruco", "template"}:
        raise HTTPException(
            status_code=400,
            detail="视觉定位方式必须为 reference、aruco 或 template",
        )

    allowed_dictionaries = {
        "DICT_4X4_50",
        "DICT_4X4_100",
        "DICT_5X5_50",
    }
    aruco_dictionary = payload.aruco_dictionary.strip().upper()

    if aruco_dictionary not in allowed_dictionaries:
        raise HTTPException(
            status_code=400,
            detail="不支持的 ArUco 字典",
        )

    if payload.aruco_id < 0 or payload.aruco_id > 999:
        raise HTTPException(
            status_code=400,
            detail="ArUco ID 必须在 0 到 999 之间",
        )

    if not 0 <= payload.stable_px <= 200:
        raise HTTPException(
            status_code=400,
            detail="喷头稳定允许位移必须在 0 到 200 px 之间",
        )

    if not 0 <= payload.bed_stable_px <= 200:
        raise HTTPException(
            status_code=400,
            detail="热床稳定允许位移必须在 0 到 200 px 之间",
        )

    if not 1 <= payload.stable_frames <= 20:
        raise HTTPException(
            status_code=400,
            detail="连续稳定帧数必须在 1 到 20 之间",
        )

    if not 0 <= payload.align_max_shift_px <= 300:
        raise HTTPException(
            status_code=400,
            detail="最大画面对齐位移必须在 0 到 300 px 之间",
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
        payload.bed_roi_x,
        payload.bed_roi_y,
        payload.bed_roi_w,
        payload.bed_roi_h,
        payload.bed_target_x,
        payload.bed_target_y,
        payload.bed_target_w,
        payload.bed_target_h,
        payload.model_roi_x,
        payload.model_roi_y,
        payload.model_roi_w,
        payload.model_roi_h,
    )

    if any(value < 0 for value in rect_values):
        raise HTTPException(
            status_code=400,
            detail="视觉区域参数不能为负数",
        )

    size_values = (
        payload.roi_w,
        payload.roi_h,
        payload.target_w,
        payload.target_h,
        payload.bed_roi_w,
        payload.bed_roi_h,
        payload.bed_target_w,
        payload.bed_target_h,
        payload.model_roi_w,
        payload.model_roi_h,
    )

    if min(size_values) < 1:
        raise HTTPException(
            status_code=400,
            detail="视觉区域宽高必须大于 0",
        )

    db.set_app_settings(
        {
            "vision_lookback_ms": payload.lookback_ms,
            "vision_match_threshold": payload.match_threshold,
            "vision_bed_match_threshold": payload.bed_match_threshold,
            "vision_bed_locator_mode": bed_locator_mode,
            "vision_aruco_id": payload.aruco_id,
            "vision_aruco_dictionary": aruco_dictionary,
            "vision_reference_similarity_threshold": payload.reference_similarity_threshold,
            "vision_reference_start_layer": payload.reference_start_layer,
            "vision_reference_max_shift_px": payload.reference_max_shift_px,
            "vision_motion_max_px": payload.motion_max_px,
            "vision_motion_stable_frames": payload.motion_stable_frames,
            "vision_sharpness_min": payload.sharpness_min,
            "vision_model_roi_x": payload.model_roi_x,
            "vision_model_roi_y": payload.model_roi_y,
            "vision_model_roi_w": payload.model_roi_w,
            "vision_model_roi_h": payload.model_roi_h,
            "vision_stable_px": payload.stable_px,
            "vision_bed_stable_px": payload.bed_stable_px,
            "vision_stable_frames": payload.stable_frames,
            "vision_align_enabled": (
                "true" if payload.align_enabled else "false"
            ),
            "vision_align_max_shift_px": payload.align_max_shift_px,
            "vision_roi_x": payload.roi_x,
            "vision_roi_y": payload.roi_y,
            "vision_roi_w": payload.roi_w,
            "vision_roi_h": payload.roi_h,
            "vision_target_x": payload.target_x,
            "vision_target_y": payload.target_y,
            "vision_target_w": payload.target_w,
            "vision_target_h": payload.target_h,
            "vision_bed_roi_x": payload.bed_roi_x,
            "vision_bed_roi_y": payload.bed_roi_y,
            "vision_bed_roi_w": payload.bed_roi_w,
            "vision_bed_roi_h": payload.bed_roi_h,
            "vision_bed_target_x": payload.bed_target_x,
            "vision_bed_target_y": payload.bed_target_y,
            "vision_bed_target_w": payload.bed_target_w,
            "vision_bed_target_h": payload.bed_target_h,
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


def _vision_bed_template_path():
    value = db.get_app_setting("vision_bed_template_path")

    if value:
        return Path(value)

    return (
        settings.database_path.parent
        / "vision"
        / "bed-template.jpg"
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

    latest = db.get_snapshot(payload.snapshot_id)

    if not latest or not latest.get("file_path"):
        raise HTTPException(
            status_code=404,
            detail="用于生成模板的抓拍图片不存在",
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


@router.get("/settings/vision-bed-template")
def vision_bed_template():
    path = _vision_bed_template_path()

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="尚未生成热床锚点模板",
        )

    return FileResponse(path)


@router.post("/settings/vision-bed-template")
def update_vision_bed_template(payload: VisionTemplateRequest):
    from PIL import Image

    latest = db.get_snapshot(payload.snapshot_id)

    if not latest or not latest.get("file_path"):
        raise HTTPException(
            status_code=404,
            detail="用于生成热床模板的抓拍图片不存在",
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
            detail="热床模板区域太小",
        )

    with Image.open(source) as image:
        width, height = image.size

        x = max(0, min(payload.x, width - 1))
        y = max(0, min(payload.y, height - 1))
        w = max(1, min(payload.w, width - x))
        h = max(1, min(payload.h, height - y))

        target = _vision_bed_template_path()
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
            "vision_bed_template_path": str(target),
            "vision_bed_template_x": x,
            "vision_bed_template_y": y,
            "vision_bed_template_w": w,
            "vision_bed_template_h": h,
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
            "url": "/api/settings/vision-bed-template",
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
            "vision_bed_template_x",
            "vision_bed_template_y",
            "vision_bed_template_w",
            "vision_bed_template_h",
        )
    )
    template_path = _vision_template_path()
    bed_template_path = _vision_bed_template_path()

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
                "bed_template": {
                    "configured": bed_template_path.is_file(),
                    "x": int(template_values.get("vision_bed_template_x", "0")),
                    "y": int(template_values.get("vision_bed_template_y", "0")),
                    "w": int(template_values.get("vision_bed_template_w", "0")),
                    "h": int(template_values.get("vision_bed_template_h", "0")),
                    "url": (
                        "/api/settings/vision-bed-template"
                        if bed_template_path.is_file()
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
