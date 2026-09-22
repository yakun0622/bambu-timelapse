import math
from pathlib import Path

import cv2
import numpy as np


class VisionSelector:
    def _decode(self, data: bytes, grayscale=False):
        array = np.frombuffer(data, dtype=np.uint8)
        flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        return cv2.imdecode(array, flag)

    def _load_template(self, path):
        if not path:
            return None

        path = Path(path)
        if not path.is_file():
            return None

        return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

    def _clip_rect(self, rect, frame_w, frame_h):
        x = max(0, min(int(rect["x"]), frame_w - 1))
        y = max(0, min(int(rect["y"]), frame_h - 1))
        w = max(1, min(int(rect["w"]), frame_w - x))
        h = max(1, min(int(rect["h"]), frame_h - y))
        return x, y, w, h

    def _detect(self, frame_gray, template, roi):
        frame_h, frame_w = frame_gray.shape[:2]
        x, y, w, h = self._clip_rect(
            roi,
            frame_w,
            frame_h,
        )
        crop = frame_gray[y:y + h, x:x + w]
        template_h, template_w = template.shape[:2]

        if (
            crop.shape[0] < template_h
            or crop.shape[1] < template_w
        ):
            return None

        result = cv2.matchTemplate(
            crop,
            template,
            cv2.TM_CCOEFF_NORMED,
        )
        _, score, _, max_loc = cv2.minMaxLoc(result)

        found_x = x + max_loc[0]
        found_y = y + max_loc[1]

        return {
            "score": float(score),
            "x": int(found_x),
            "y": int(found_y),
            "center_x": float(found_x + template_w / 2.0),
            "center_y": float(found_y + template_h / 2.0),
            "w": int(template_w),
            "h": int(template_h),
        }

    def _aruco_dictionary(self, name):
        dictionaries = {
            "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
            "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
            "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
        }
        dictionary_id = dictionaries.get(
            str(name).upper(),
            cv2.aruco.DICT_4X4_50,
        )
        return cv2.aruco.getPredefinedDictionary(
            dictionary_id
        )

    def _detect_aruco(
        self,
        frame_gray,
        roi,
        marker_id,
        dictionary_name="DICT_4X4_50",
    ):
        if not hasattr(cv2, "aruco"):
            return None

        frame_h, frame_w = frame_gray.shape[:2]
        x, y, w, h = self._clip_rect(
            roi,
            frame_w,
            frame_h,
        )
        crop = frame_gray[y:y + h, x:x + w]
        dictionary = self._aruco_dictionary(
            dictionary_name
        )

        if hasattr(cv2.aruco, "ArucoDetector"):
            detector = cv2.aruco.ArucoDetector(
                dictionary,
                cv2.aruco.DetectorParameters(),
            )
            corners, ids, _ = detector.detectMarkers(
                crop
            )
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(
                crop,
                dictionary,
            )

        if ids is None:
            return None

        for corner, detected_id in zip(
            corners,
            ids.flatten(),
        ):
            if int(detected_id) != int(marker_id):
                continue

            points = corner.reshape(-1, 2).astype(
                np.float32
            )
            points[:, 0] += x
            points[:, 1] += y

            min_x = float(points[:, 0].min())
            min_y = float(points[:, 1].min())
            max_x = float(points[:, 0].max())
            max_y = float(points[:, 1].max())

            center_x = float(points[:, 0].mean())
            center_y = float(points[:, 1].mean())

            edge_lengths = [
                float(
                    np.linalg.norm(
                        points[(index + 1) % 4]
                        - points[index]
                    )
                )
                for index in range(4)
            ]

            return {
                "score": 1.0,
                "x": int(round(min_x)),
                "y": int(round(min_y)),
                "center_x": center_x,
                "center_y": center_y,
                "w": int(round(max_x - min_x)),
                "h": int(round(max_y - min_y)),
                "marker_id": int(detected_id),
                "marker_size_px": round(
                    sum(edge_lengths) / 4.0,
                    2,
                ),
            }

        return None

    def _in_target(self, detection, target):
        x1 = int(target["x"])
        y1 = int(target["y"])
        x2 = x1 + int(target["w"])
        y2 = y1 + int(target["h"])

        return (
            x1 <= detection["center_x"] <= x2
            and y1 <= detection["center_y"] <= y2
        )

    def _distance(self, a, b):
        return math.hypot(
            a["center_x"] - b["center_x"],
            a["center_y"] - b["center_y"],
        )

    def _target_center(self, target):
        return (
            int(target["x"]) + int(target["w"]) / 2.0,
            int(target["y"]) + int(target["h"]) / 2.0,
        )

    def _target_bonus(self, detection, target, weight=0.15):
        center_x, center_y = self._target_center(target)
        distance = math.hypot(
            detection["center_x"] - center_x,
            detection["center_y"] - center_y,
        )
        diagonal = max(
            1.0,
            math.hypot(
                int(target["w"]),
                int(target["h"]),
            ),
        )
        normalized = min(1.0, distance / diagonal)
        return (1.0 - normalized) * weight

    def _encode_jpeg(self, frame):
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        )
        if not ok:
            raise RuntimeError("JPEG 编码失败")
        return encoded.tobytes()

    def _align_by_bed(
        self,
        frame_data,
        bed_detection,
        bed_target,
        max_shift_px,
    ):
        frame = self._decode(frame_data, grayscale=False)
        if frame is None:
            return frame_data, 0, 0

        target_x, target_y = self._target_center(bed_target)

        dx = int(round(target_x - bed_detection["center_x"]))
        dy = int(round(target_y - bed_detection["center_y"]))

        limit = max(0, int(max_shift_px))
        if limit:
            dx = max(-limit, min(limit, dx))
            dy = max(-limit, min(limit, dy))

        if dx == 0 and dy == 0:
            return frame_data, 0, 0

        height, width = frame.shape[:2]
        matrix = np.float32(
            [
                [1, 0, dx],
                [0, 1, dy],
            ]
        )

        aligned = cv2.warpAffine(
            frame,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return self._encode_jpeg(aligned), dx, dy

    def diagnose_frame(
        self,
        frame_data,
        head_template_path,
        head_roi,
        head_target,
        bed_template_path,
        bed_roi,
        bed_target,
        bed_locator_mode="aruco",
        aruco_id=23,
        aruco_dictionary="DICT_4X4_50",
        head_match_threshold=0.78,
        bed_match_threshold=0.78,
    ):
        frame_gray = self._decode(
            frame_data,
            grayscale=True,
        )

        if frame_gray is None:
            return {
                "ok": False,
                "reason": "当前 RTSP 帧解码失败",
            }

        head_template = self._load_template(
            head_template_path
        )
        if head_template is None:
            return {
                "ok": False,
                "reason": "喷头模板未配置",
            }

        mode = str(bed_locator_mode).strip().lower()
        if mode not in {"aruco", "template"}:
            mode = "aruco"

        head = self._detect(
            frame_gray,
            head_template,
            head_roi,
        )
        head_ok = (
            head is not None
            and head["score"] >= float(head_match_threshold)
        )
        head_target_ok = (
            head_ok
            and self._in_target(head, head_target)
        )

        bed = None
        bed_detected = False
        bed_threshold_ok = False
        bed_target_ok = False

        if mode == "aruco":
            bed = self._detect_aruco(
                frame_gray,
                bed_roi,
                aruco_id,
                aruco_dictionary,
            )
            bed_detected = bed is not None
            bed_threshold_ok = bed_detected
        else:
            bed_template = self._load_template(
                bed_template_path
            )
            if bed_template is None:
                return {
                    "ok": False,
                    "reason": "热床锚点模板未配置",
                }
            bed = self._detect(
                frame_gray,
                bed_template,
                bed_roi,
            )
            bed_detected = bed is not None
            bed_threshold_ok = (
                bed_detected
                and bed["score"] >= float(
                    bed_match_threshold
                )
            )

        if bed_threshold_ok:
            bed_target_ok = self._in_target(
                bed,
                bed_target,
            )

        reasons = []
        if not head_ok:
            if head is None:
                reasons.append("喷头未识别")
            else:
                reasons.append(
                    "喷头匹配分数低于阈值"
                )
        elif not head_target_ok:
            reasons.append("喷头未进入目标区域")

        if not bed_detected:
            reasons.append(
                (
                    f"未识别 ArUco #{aruco_id}"
                    if mode == "aruco"
                    else "热床锚点未识别"
                )
            )
        elif not bed_threshold_ok:
            reasons.append("热床匹配分数低于阈值")
        elif not bed_target_ok:
            reasons.append(
                (
                    "ArUco 未进入热床目标区域"
                    if mode == "aruco"
                    else "热床锚点未进入目标区域"
                )
            )

        return {
            "ok": bool(
                head_target_ok
                and bed_target_ok
            ),
            "reason": (
                "当前画面满足喷头与热床定位条件"
                if head_target_ok and bed_target_ok
                else "；".join(reasons)
            ),
            "head": {
                "detected": head is not None,
                "score": (
                    round(head["score"], 4)
                    if head is not None
                    else None
                ),
                "threshold_ok": head_ok,
                "in_target": head_target_ok,
                "x": head["x"] if head else None,
                "y": head["y"] if head else None,
                "center_x": (
                    round(head["center_x"], 1)
                    if head else None
                ),
                "center_y": (
                    round(head["center_y"], 1)
                    if head else None
                ),
            },
            "bed": {
                "mode": mode,
                "detected": bed_detected,
                "score": (
                    round(bed["score"], 4)
                    if bed is not None
                    else None
                ),
                "in_target": bed_target_ok,
                "marker_id": (
                    bed.get("marker_id")
                    if bed is not None
                    else None
                ),
                "marker_size_px": (
                    bed.get("marker_size_px")
                    if bed is not None
                    else None
                ),
                "x": bed["x"] if bed else None,
                "y": bed["y"] if bed else None,
                "center_x": (
                    round(bed["center_x"], 1)
                    if bed else None
                ),
                "center_y": (
                    round(bed["center_y"], 1)
                    if bed else None
                ),
            },
        }

    def _crop_gray(self, frame_gray, roi):
        frame_h, frame_w = frame_gray.shape[:2]
        x, y, w, h = self._clip_rect(
            roi,
            frame_w,
            frame_h,
        )
        return frame_gray[y:y + h, x:x + w]

    def _ecc_translation(
        self,
        reference_gray,
        candidate_gray,
    ):
        if reference_gray.shape != candidate_gray.shape:
            return None

        reference = cv2.GaussianBlur(
            reference_gray,
            (5, 5),
            0,
        ).astype(np.float32) / 255.0
        candidate = cv2.GaussianBlur(
            candidate_gray,
            (5, 5),
            0,
        ).astype(np.float32) / 255.0

        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (
            cv2.TERM_CRITERIA_EPS
            | cv2.TERM_CRITERIA_COUNT,
            60,
            1e-5,
        )

        try:
            score, warp = cv2.findTransformECC(
                reference,
                candidate,
                warp,
                cv2.MOTION_TRANSLATION,
                criteria,
                None,
                1,
            )
        except cv2.error:
            return None

        return {
            "score": float(score),
            "dx": float(warp[0, 2]),
            "dy": float(warp[1, 2]),
            "warp": warp,
        }

    def _align_by_ecc(
        self,
        frame_data,
        warp,
    ):
        frame = self._decode(
            frame_data,
            grayscale=False,
        )
        if frame is None:
            return frame_data

        height, width = frame.shape[:2]
        aligned = cv2.warpAffine(
            frame,
            warp,
            (width, height),
            flags=(
                cv2.INTER_LINEAR
                | cv2.WARP_INVERSE_MAP
            ),
            borderMode=cv2.BORDER_REPLICATE,
        )
        return self._encode_jpeg(aligned)

    def _sharpness(self, gray_roi):
        return float(
            cv2.Laplacian(
                gray_roi,
                cv2.CV_64F,
            ).var()
        )

    def _motion_px(self, previous_roi, current_roi):
        motion = self._ecc_translation(
            previous_roi,
            current_roi,
        )
        if motion is None:
            return None

        return float(
            math.hypot(
                motion["dx"],
                motion["dy"],
            )
        )

    def select_reference(
        self,
        history,
        trigger_at,
        reference_path,
        model_roi,
        head_template_path,
        head_roi,
        head_target,
        head_match_threshold=0.60,
        similarity_threshold=0.80,
        max_shift_px=60,
        motion_max_px=3.0,
        motion_stable_frames=2,
        sharpness_min=60.0,
        align_enabled=True,
    ):
        if not history:
            return None, "RTSP 历史帧为空"

        reference_path = Path(reference_path)
        if not reference_path.is_file():
            return None, "上一帧参考图片不存在"

        head_template = self._load_template(
            head_template_path
        )
        if head_template is None:
            return None, "喷头模板未配置"

        reference = cv2.imread(
            str(reference_path),
            cv2.IMREAD_GRAYSCALE,
        )
        if reference is None:
            return None, "上一帧参考图片读取失败"

        reference_roi = self._crop_gray(
            reference,
            model_roi,
        )

        decoded = []
        previous_roi = None

        diagnostic = {
            "frames": 0,
            "head_detected": 0,
            "head_target": 0,
            "ecc_ok": 0,
            "max_head_score": None,
            "max_similarity": None,
            "max_sharpness": None,
            "min_motion_px": None,
            "stable_run": 0,
        }

        for index, item in enumerate(history):
            diagnostic["frames"] += 1
            frame_gray = self._decode(
                item["data"],
                grayscale=True,
            )
            if frame_gray is None:
                previous_roi = None
                continue

            candidate_roi = self._crop_gray(
                frame_gray,
                model_roi,
            )
            sharpness = self._sharpness(
                candidate_roi
            )
            diagnostic["max_sharpness"] = max(
                diagnostic["max_sharpness"]
                if diagnostic["max_sharpness"] is not None
                else sharpness,
                sharpness,
            )

            motion_px = None
            if previous_roi is not None:
                motion_px = self._motion_px(
                    previous_roi,
                    candidate_roi,
                )
                if motion_px is not None:
                    diagnostic["min_motion_px"] = min(
                        diagnostic["min_motion_px"]
                        if diagnostic["min_motion_px"] is not None
                        else motion_px,
                        motion_px,
                    )

            previous_roi = candidate_roi

            head = self._detect(
                frame_gray,
                head_template,
                head_roi,
            )
            if head is None:
                decoded.append(
                    {
                        "index": index,
                        "item": item,
                        "roi": candidate_roi,
                        "head": None,
                        "sharpness": sharpness,
                        "motion_px": motion_px,
                        "ecc": None,
                    }
                )
                continue

            diagnostic["head_detected"] += 1
            diagnostic["max_head_score"] = max(
                diagnostic["max_head_score"]
                if diagnostic["max_head_score"] is not None
                else head["score"],
                head["score"],
            )

            if (
                head["score"] < float(head_match_threshold)
                or not self._in_target(head, head_target)
            ):
                decoded.append(
                    {
                        "index": index,
                        "item": item,
                        "roi": candidate_roi,
                        "head": head,
                        "sharpness": sharpness,
                        "motion_px": motion_px,
                        "ecc": None,
                    }
                )
                continue

            diagnostic["head_target"] += 1

            ecc = self._ecc_translation(
                reference_roi,
                candidate_roi,
            )
            if ecc is not None:
                diagnostic["ecc_ok"] += 1
                diagnostic["max_similarity"] = max(
                    diagnostic["max_similarity"]
                    if diagnostic["max_similarity"] is not None
                    else ecc["score"],
                    ecc["score"],
                )

            decoded.append(
                {
                    "index": index,
                    "item": item,
                    "roi": candidate_roi,
                    "head": head,
                    "sharpness": sharpness,
                    "motion_px": motion_px,
                    "ecc": ecc,
                }
            )

        eligible = []
        fallback_pool = []

        for candidate in decoded:
            head = candidate["head"]
            ecc = candidate["ecc"]

            if head is None or ecc is None:
                continue

            if (
                head["score"] < float(head_match_threshold)
                or not self._in_target(head, head_target)
                or abs(ecc["dx"]) > float(max_shift_px)
                or abs(ecc["dy"]) > float(max_shift_px)
            ):
                continue

            candidate["similarity"] = ecc["score"]
            fallback_pool.append(candidate)

            # Similarity is no longer a hard gate. The primary goal is a
            # stationary, sharp frame; similarity only ranks otherwise
            # acceptable candidates.
            if candidate["sharpness"] >= float(sharpness_min):
                eligible.append(candidate)

        stable_required = max(
            1,
            int(motion_stable_frames),
        )
        motion_limit = max(
            0.0,
            float(motion_max_px),
        )

        stable_runs = []
        current_run = []

        for candidate in eligible:
            motion_ok = (
                candidate["motion_px"] is not None
                and candidate["motion_px"] <= motion_limit
            )

            if not motion_ok:
                if len(current_run) >= stable_required:
                    stable_runs.append(current_run)
                current_run = []
                continue

            if not current_run:
                current_run = [candidate]
                continue

            previous = current_run[-1]
            contiguous = (
                candidate["index"]
                == previous["index"] + 1
            )

            if contiguous:
                current_run.append(candidate)
            else:
                if len(current_run) >= stable_required:
                    stable_runs.append(current_run)
                current_run = [candidate]

        if len(current_run) >= stable_required:
            stable_runs.append(current_run)

        if stable_runs:
            diagnostic["stable_run"] = max(
                len(run)
                for run in stable_runs
            )

            # Prefer the longest truly stationary sequence first. Inside that
            # sequence, prefer minimum motion, then maximum sharpness, and use
            # previous-frame similarity only as the final tie-breaker.
            best_run = max(
                stable_runs,
                key=lambda run: (
                    len(run),
                    -min(
                        item["motion_px"]
                        if item["motion_px"] is not None
                        else float("inf")
                        for item in run
                    ),
                    max(item["sharpness"] for item in run),
                ),
            )

            best = min(
                best_run,
                key=lambda item: (
                    item["motion_px"]
                    if item["motion_px"] is not None
                    else float("inf"),
                    -item["sharpness"],
                    -item["similarity"],
                ),
            )
            quality_fallback = False
            quality_reason = None
            stable_count = len(best_run)

        elif fallback_pool:
            # No fully stationary sequence was found. Still avoid the old
            # fixed-time fallback and choose the least-moving, sharpest
            # candidate observed in the history window.
            best = min(
                fallback_pool,
                key=lambda item: (
                    (
                        item["motion_px"]
                        if item["motion_px"] is not None
                        else float("inf")
                    ),
                    -item["sharpness"],
                    -item["similarity"],
                ),
            )
            quality_fallback = True
            stable_count = 0

            details = []
            if best["sharpness"] < float(sharpness_min):
                details.append(
                    f"清晰度 {best['sharpness']:.2f} < "
                    f"{float(sharpness_min):.2f}"
                )
            if (
                best["motion_px"] is None
                or best["motion_px"] > motion_limit
            ):
                motion_text = (
                    "未知"
                    if best["motion_px"] is None
                    else f"{best['motion_px']:.2f}px"
                )
                details.append(
                    f"运动 {motion_text} > {motion_limit:.2f}px"
                )

            quality_reason = (
                "未找到满足静止/清晰度条件的连续帧，"
                "已选择历史窗口中运动最小且更清晰的候选帧"
            )
            if details:
                quality_reason += "（" + "；".join(details) + "）"

        else:
            head_text = (
                f"喷头最高 {diagnostic['max_head_score']:.4f}"
                if diagnostic["max_head_score"] is not None
                else "喷头未识别"
            )
            similarity_text = (
                f"上一帧最高相似度 {diagnostic['max_similarity']:.4f}"
                if diagnostic["max_similarity"] is not None
                else "没有可用的上一帧相似度结果"
            )
            return (
                None,
                f"{head_text}，喷头目标区 {diagnostic['head_target']} 帧；"
                f"{similarity_text}",
            )

        similarity_below_threshold = (
            best["similarity"] < float(similarity_threshold)
        )

        frame_data = best["item"]["data"]
        if align_enabled:
            frame_data = self._align_by_ecc(
                frame_data,
                best["ecc"]["warp"],
            )

        return {
            "frame": frame_data,
            "seq": best["item"]["seq"],
            "at": best["item"]["at"],
            "before_trigger_ms": int(
                (trigger_at - best["item"]["at"]) * 1000
            ),
            "head_score": round(
                best["head"]["score"],
                4,
            ),
            "similarity_score": round(
                best["similarity"],
                4,
            ),
            "similarity_below_threshold": similarity_below_threshold,
            "motion_px": (
                round(best["motion_px"], 2)
                if best["motion_px"] is not None
                else None
            ),
            "sharpness": round(
                best["sharpness"],
                2,
            ),
            "stable_count": stable_count,
            "quality_fallback": quality_fallback,
            "quality_reason": quality_reason,
            "align_dx": round(
                -best["ecc"]["dx"],
                2,
            ),
            "align_dy": round(
                -best["ecc"]["dy"],
                2,
            ),
            "head_x": best["head"]["x"],
            "head_y": best["head"]["y"],
        }, None

    def select(
        self,
        history,
        trigger_at,
        head_template_path,
        head_roi,
        head_target,
        bed_template_path,
        bed_roi,
        bed_target,
        bed_locator_mode="aruco",
        aruco_id=23,
        aruco_dictionary="DICT_4X4_50",
        head_match_threshold=0.78,
        bed_match_threshold=0.78,
        stable_px=8,
        bed_stable_px=8,
        stable_frames=2,
        align_enabled=True,
        align_max_shift_px=30,
    ):
        head_template = self._load_template(
            head_template_path
        )
        bed_locator_mode = (
            str(bed_locator_mode).strip().lower()
        )
        if bed_locator_mode not in {"aruco", "template"}:
            bed_locator_mode = "aruco"

        bed_template = None
        if bed_locator_mode == "template":
            bed_template = self._load_template(
                bed_template_path
            )

        if head_template is None:
            return None, "喷头模板未配置"

        if (
            bed_locator_mode == "template"
            and bed_template is None
        ):
            return None, "热床锚点模板未配置"

        if not history:
            return None, "RTSP 历史帧为空"

        stable_frames = max(1, int(stable_frames))
        stable_px = max(0, int(stable_px))
        bed_stable_px = max(0, int(bed_stable_px))

        candidates = []
        stable_run = []
        diagnostic = {
            "frames": 0,
            "head_detected": 0,
            "head_threshold": 0,
            "head_target": 0,
            "bed_detected": 0,
            "bed_target": 0,
            "max_head_score": None,
            "max_bed_score": None,
            "max_stable_run": 0,
        }

        for item in history:
            diagnostic["frames"] += 1
            frame_gray = self._decode(
                item["data"],
                grayscale=True,
            )

            if frame_gray is None:
                stable_run = []
                continue

            head = self._detect(
                frame_gray,
                head_template,
                head_roi,
            )
            if head is not None:
                diagnostic["head_detected"] += 1
                diagnostic["max_head_score"] = max(
                    diagnostic["max_head_score"]
                    if diagnostic["max_head_score"] is not None
                    else head["score"],
                    head["score"],
                )
                if head["score"] >= float(head_match_threshold):
                    diagnostic["head_threshold"] += 1
                    if self._in_target(head, head_target):
                        diagnostic["head_target"] += 1

            if bed_locator_mode == "aruco":
                bed = self._detect_aruco(
                    frame_gray,
                    bed_roi,
                    aruco_id,
                    aruco_dictionary,
                )
            else:
                bed = self._detect(
                    frame_gray,
                    bed_template,
                    bed_roi,
                )

            if bed is not None:
                diagnostic["bed_detected"] += 1
                diagnostic["max_bed_score"] = max(
                    diagnostic["max_bed_score"]
                    if diagnostic["max_bed_score"] is not None
                    else bed["score"],
                    bed["score"],
                )
                bed_threshold_ok = (
                    bed_locator_mode == "aruco"
                    or bed["score"] >= float(
                        bed_match_threshold
                    )
                )
                if (
                    bed_threshold_ok
                    and self._in_target(bed, bed_target)
                ):
                    diagnostic["bed_target"] += 1

            valid = (
                head is not None
                and bed is not None
                and head["score"] >= float(head_match_threshold)
                and (
                    bed_locator_mode == "aruco"
                    or bed["score"] >= float(
                        bed_match_threshold
                    )
                )
                and self._in_target(head, head_target)
                and self._in_target(bed, bed_target)
            )

            if not valid:
                stable_run = []
                continue

            if stable_run:
                previous = stable_run[-1]
                head_move = self._distance(
                    previous["head"],
                    head,
                )
                bed_move = self._distance(
                    previous["bed"],
                    bed,
                )

                if (
                    head_move > stable_px
                    or bed_move > bed_stable_px
                ):
                    stable_run = []

            candidate = {
                "item": item,
                "head": head,
                "bed": bed,
                "before_trigger_ms": int(
                    (trigger_at - item["at"]) * 1000
                ),
            }

            stable_run.append(candidate)
            diagnostic["max_stable_run"] = max(
                diagnostic["max_stable_run"],
                len(stable_run),
            )

            if len(stable_run) >= stable_frames:
                for run_item in stable_run:
                    run_item["stable_count"] = len(
                        stable_run
                    )

                if not candidates or (
                    len(stable_run)
                    > candidates[-1]["run_length"]
                ):
                    pass

                candidate["run_length"] = len(stable_run)
                candidates.append(
                    {
                        "frames": list(stable_run),
                        "run_length": len(stable_run),
                    }
                )

        if not candidates:
            max_head = diagnostic["max_head_score"]
            head_text = (
                f"喷头最高 {max_head:.4f}"
                if max_head is not None
                else "喷头未识别"
            )

            if bed_locator_mode == "aruco":
                bed_text = (
                    f"ArUco #{aruco_id} 已识别 "
                    f"{diagnostic['bed_detected']} 帧"
                    if diagnostic["bed_detected"]
                    else f"ArUco #{aruco_id} 未识别"
                )
            else:
                max_bed = diagnostic["max_bed_score"]
                bed_text = (
                    f"热床最高 {max_bed:.4f}"
                    if max_bed is not None
                    else "热床锚点未识别"
                )

            detail = (
                f"{head_text}，"
                f"喷头目标区 {diagnostic['head_target']} 帧；"
                f"{bed_text}，"
                f"热床目标区 {diagnostic['bed_target']} 帧；"
                f"最长稳定 {diagnostic['max_stable_run']}/"
                f"{stable_frames} 帧"
            )

            return (
                None,
                detail,
            )

        longest = max(
            candidates,
            key=lambda item: (
                item["run_length"],
                max(
                    (
                        frame["head"]["score"]
                        + frame["bed"]["score"]
                    )
                    for frame in item["frames"]
                ),
            ),
        )

        stable_frames_list = longest["frames"]
        best = stable_frames_list[
            len(stable_frames_list) // 2
        ]

        final_score = (
            best["head"]["score"]
            + best["bed"]["score"]
            + self._target_bonus(
                best["head"],
                head_target,
            )
            + self._target_bonus(
                best["bed"],
                bed_target,
            )
        ) / 2.0

        frame_data = best["item"]["data"]
        align_dx = 0
        align_dy = 0

        if align_enabled:
            frame_data, align_dx, align_dy = (
                self._align_by_bed(
                    frame_data,
                    best["bed"],
                    bed_target,
                    align_max_shift_px,
                )
            )

        return {
            "frame": frame_data,
            "seq": best["item"]["seq"],
            "at": best["item"]["at"],
            "before_trigger_ms": best["before_trigger_ms"],
            "head_score": round(
                best["head"]["score"],
                4,
            ),
            "bed_score": round(
                best["bed"]["score"],
                4,
            ),
            "bed_locator_mode": bed_locator_mode,
            "aruco_id": (
                best["bed"].get("marker_id")
                if bed_locator_mode == "aruco"
                else None
            ),
            "final_score": round(
                final_score,
                4,
            ),
            "stable": True,
            "stable_count": len(stable_frames_list),
            "head_x": best["head"]["x"],
            "head_y": best["head"]["y"],
            "bed_x": best["bed"]["x"],
            "bed_y": best["bed"]["y"],
            "align_dx": align_dx,
            "align_dy": align_dy,
        }, None


vision_selector = VisionSelector()
