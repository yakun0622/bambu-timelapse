import math
from pathlib import Path

import cv2
import numpy as np


class VisionSelector:
    def _decode_gray(self, data: bytes):
        array = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)

    def _load_template(self, path: Path):
        if not path or not path.is_file():
            return None

        return cv2.imread(
            str(path),
            cv2.IMREAD_GRAYSCALE,
        )

    def _detect(self, frame, template, roi):
        frame_h, frame_w = frame.shape[:2]

        x = max(0, min(int(roi["x"]), frame_w - 1))
        y = max(0, min(int(roi["y"]), frame_h - 1))
        w = max(1, min(int(roi["w"]), frame_w - x))
        h = max(1, min(int(roi["h"]), frame_h - y))

        crop = frame[y:y + h, x:x + w]

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

        head_x = x + max_loc[0]
        head_y = y + max_loc[1]
        center_x = head_x + template_w / 2.0
        center_y = head_y + template_h / 2.0

        return {
            "score": float(score),
            "x": int(head_x),
            "y": int(head_y),
            "center_x": float(center_x),
            "center_y": float(center_y),
            "w": int(template_w),
            "h": int(template_h),
        }

    def _in_target(self, detection, target):
        x1 = int(target["x"])
        y1 = int(target["y"])
        x2 = x1 + int(target["w"])
        y2 = y1 + int(target["h"])

        return (
            x1 <= detection["center_x"] <= x2
            and y1 <= detection["center_y"] <= y2
        )

    def _target_bonus(self, detection, target):
        center_x = int(target["x"]) + int(target["w"]) / 2.0
        center_y = int(target["y"]) + int(target["h"]) / 2.0

        dx = detection["center_x"] - center_x
        dy = detection["center_y"] - center_y
        distance = math.hypot(dx, dy)

        diagonal = max(
            1.0,
            math.hypot(
                int(target["w"]),
                int(target["h"]),
            ),
        )

        normalized = min(1.0, distance / diagonal)
        return (1.0 - normalized) * 0.25

    def select(
        self,
        history,
        trigger_at,
        template_path,
        roi,
        target,
        match_threshold=0.78,
        stable_px=8,
        stable_frames=2,
    ):
        template = self._load_template(
            Path(template_path)
            if template_path
            else None
        )

        if template is None:
            return None, "喷头模板未配置"

        if not history:
            return None, "RTSP 历史帧为空"

        stable_frames = max(1, int(stable_frames))
        stable_px = max(0, int(stable_px))
        match_threshold = float(match_threshold)

        candidates = []
        previous = None
        stable_run = 0

        for item in history:
            frame = self._decode_gray(item["data"])

            if frame is None:
                previous = None
                stable_run = 0
                continue

            detection = self._detect(
                frame,
                template,
                roi,
            )

            if (
                detection is None
                or detection["score"] < match_threshold
                or not self._in_target(detection, target)
            ):
                previous = None
                stable_run = 0
                continue

            if previous is None:
                stable_run = 1
            else:
                move = math.hypot(
                    detection["center_x"]
                    - previous["center_x"],
                    detection["center_y"]
                    - previous["center_y"],
                )

                if move <= stable_px:
                    stable_run += 1
                else:
                    stable_run = 1

            previous = detection

            before_trigger_ms = int(
                (trigger_at - item["at"]) * 1000
            )

            stable = stable_run >= stable_frames

            final_score = (
                detection["score"]
                + self._target_bonus(
                    detection,
                    target,
                )
                + min(
                    stable_run,
                    stable_frames,
                ) / stable_frames * 0.35
            )

            candidates.append(
                {
                    "item": item,
                    "detection": detection,
                    "match_score": detection["score"],
                    "stable": stable,
                    "stable_count": stable_run,
                    "before_trigger_ms": before_trigger_ms,
                    "final_score": final_score,
                }
            )

        if not candidates:
            return None, "历史帧中没有找到符合目标区域的喷头"

        stable_candidates = [
            item
            for item in candidates
            if item["stable"]
        ]

        pool = stable_candidates or candidates
        best = max(
            pool,
            key=lambda item: item["final_score"],
        )

        return {
            "frame": best["item"]["data"],
            "seq": best["item"]["seq"],
            "at": best["item"]["at"],
            "before_trigger_ms": best["before_trigger_ms"],
            "match_score": round(
                best["match_score"],
                4,
            ),
            "final_score": round(
                best["final_score"],
                4,
            ),
            "stable": best["stable"],
            "stable_count": best["stable_count"],
            "x": best["detection"]["x"],
            "y": best["detection"]["y"],
            "w": best["detection"]["w"],
            "h": best["detection"]["h"],
        }, None


vision_selector = VisionSelector()
