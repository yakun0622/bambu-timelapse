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
        bed_template = self._load_template(
            bed_template_path
        )

        if head_template is None:
            return None, "喷头模板未配置"

        if bed_template is None:
            return None, "热床锚点模板未配置"

        if not history:
            return None, "RTSP 历史帧为空"

        stable_frames = max(1, int(stable_frames))
        stable_px = max(0, int(stable_px))
        bed_stable_px = max(0, int(bed_stable_px))

        candidates = []
        stable_run = []

        for item in history:
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
            bed = self._detect(
                frame_gray,
                bed_template,
                bed_roi,
            )

            valid = (
                head is not None
                and bed is not None
                and head["score"] >= float(head_match_threshold)
                and bed["score"] >= float(bed_match_threshold)
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
            return (
                None,
                "没有找到喷头和热床同时进入目标区域且连续稳定的帧",
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
