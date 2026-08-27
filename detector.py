from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[misc,assignment]

from audio import VoiceAlarm
from config import Settings
from faces import FaceManager
from notifier import notifier
from ptz import PTZController
from storage import EventStore


PPE_HELMET_OK = {"helmet", "hardhat", "hard_hat", "person_with_helmet"}
PPE_HELMET_MISSING = {"no_helmet", "nohelmet", "no_hardhat", "nohardhat"}
PPE_VEST_OK = {"vest", "safety_vest", "person_with_vest"}
PPE_VEST_MISSING = {"no_vest", "novest", "no_safety_vest", "nosafetyvest"}


def _normalize_label(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def ppe_confidence_threshold(settings: Settings, normalized_label: str) -> float:
    """Return class-specific thresholds to reduce false PPE confirmations."""
    if normalized_label in PPE_HELMET_OK:
        return settings.ppe_helmet_ok_confidence
    if normalized_label in PPE_HELMET_MISSING:
        return settings.ppe_helmet_missing_confidence
    if normalized_label in PPE_VEST_OK:
        return settings.ppe_vest_ok_confidence
    if normalized_label in PPE_VEST_MISSING:
        return settings.ppe_vest_missing_confidence
    return 1.0


def _box_area(box: tuple[int, int, int, int]) -> int:
    return max(0, box[2]) * max(0, box[3])


def _intersection_over_smaller(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    smaller = min(_box_area(first), _box_area(second))
    return intersection / smaller if smaller else 0.0


def suppress_duplicate_people(
    detections: list[dict[str, Any]], overlap_threshold: float
) -> list[dict[str, Any]]:
    """Remove partial-body duplicate detections while retaining real nearby people.

    A duplicate is defined by overlap relative to the smaller box, which catches
    a head/torso box nested inside a full-person box better than regular IoU.
    """
    ranked = sorted(
        detections,
        key=lambda item: (float(item["confidence"]), _box_area(item["box"])),
        reverse=True,
    )
    kept: list[dict[str, Any]] = []
    for candidate in ranked:
        if any(
            _intersection_over_smaller(candidate["box"], existing["box"]) >= overlap_threshold
            for existing in kept
        ):
            continue
        kept.append(candidate)
    return kept


KP_NOSE = 0
KP_LEFT_EYE = 1
KP_RIGHT_EYE = 2
KP_LEFT_EAR = 3
KP_RIGHT_EAR = 4
KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12
KP_LEFT_KNEE = 13
KP_RIGHT_KNEE = 14
KP_LEFT_ANKLE = 15
KP_RIGHT_ANKLE = 16

SKELETON_PAIRS = [
    (KP_NOSE, KP_LEFT_EYE),
    (KP_NOSE, KP_RIGHT_EYE),
    (KP_LEFT_EYE, KP_LEFT_EAR),
    (KP_RIGHT_EYE, KP_RIGHT_EAR),
    (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER),
    (KP_LEFT_SHOULDER, KP_LEFT_ELBOW),
    (KP_LEFT_ELBOW, KP_LEFT_WRIST),
    (KP_RIGHT_SHOULDER, KP_RIGHT_ELBOW),
    (KP_RIGHT_ELBOW, KP_RIGHT_WRIST),
    (KP_LEFT_SHOULDER, KP_LEFT_HIP),
    (KP_RIGHT_SHOULDER, KP_RIGHT_HIP),
    (KP_LEFT_HIP, KP_RIGHT_HIP),
    (KP_LEFT_HIP, KP_LEFT_KNEE),
    (KP_LEFT_KNEE, KP_LEFT_ANKLE),
    (KP_RIGHT_HIP, KP_RIGHT_KNEE),
    (KP_RIGHT_KNEE, KP_RIGHT_ANKLE),
]


def _has_hivis_colors(image_crop: np.ndarray | None) -> bool:
    """Validate whether an image crop contains real fluorescent safety workwear (Orange wearpack/vest or Lime/Yellow vest)."""
    if image_crop is None or image_crop.size == 0:
        return False
    try:
        hsv = cv2.cvtColor(image_crop, cv2.COLOR_BGR2HSV)
        # Real industrial Safety Orange (Wearpack / Vest): H: 3-20, S >= 85, V >= 120
        mask_orange = cv2.inRange(hsv, (3, 85, 120), (20, 255, 255))
        # Real industrial Safety Lime / Yellow (Vest): H: 22-50, S >= 75, V >= 120
        mask_yellow = cv2.inRange(hsv, (22, 75, 120), (50, 255, 255))
        total_pixels = max(1, image_crop.shape[0] * image_crop.shape[1])
        hivis_pixels = cv2.countNonZero(mask_orange) + cv2.countNonZero(mask_yellow)
        return (hivis_pixels / total_pixels) >= 0.035
    except Exception:
        return False


def _extract_valid_keypoints(
    keypoints: np.ndarray | list[Any] | None, min_conf: float
) -> dict[int, tuple[float, float]]:
    """Extract dict of {index: (x, y)} for keypoints with confidence >= min_conf."""
    if keypoints is None:
        return {}
    pts: dict[int, tuple[float, float]] = {}
    try:
        arr = np.asarray(keypoints)
        if arr.ndim >= 2 and arr.shape[0] >= 17:
            for idx in range(17):
                row = arr[idx]
                if len(row) >= 3 and float(row[2]) >= min_conf:
                    pts[idx] = (float(row[0]), float(row[1]))
                elif len(row) == 2:
                    pts[idx] = (float(row[0]), float(row[1]))
    except Exception:
        pass
    return pts


def _associate_helmet(
    item_box: tuple[int, int, int, int],
    person_box: tuple[int, int, int, int],
    valid_kps: dict[int, tuple[float, float]],
    head_radius_factor: float = 1.4,
) -> bool:
    """Associate helmet/no-helmet with person using pose keypoints or adaptive fallback."""
    ix, iy, iw, ih = item_box
    icx, icy = ix + iw / 2, iy + ih / 2
    px, py, pw, ph = person_box

    # 1. Pose-guided check (head cluster: Nose, Eyes, Ears)
    head_kps = [valid_kps[k] for k in (KP_NOSE, KP_LEFT_EYE, KP_RIGHT_EYE, KP_LEFT_EAR, KP_RIGHT_EAR) if k in valid_kps]
    if head_kps:
        hcx = sum(p[0] for p in head_kps) / len(head_kps)
        hcy = sum(p[1] for p in head_kps) / len(head_kps)

        if KP_LEFT_SHOULDER in valid_kps and KP_RIGHT_SHOULDER in valid_kps:
            ls, rs = valid_kps[KP_LEFT_SHOULDER], valid_kps[KP_RIGHT_SHOULDER]
            sh_dist = float(np.hypot(ls[0] - rs[0], ls[1] - rs[1]))
            radius = max(sh_dist * 0.45, pw * 0.30, 20.0)
        else:
            radius = max(pw * 0.35, ph * 0.18, 20.0)

        radius *= head_radius_factor
        dx = abs(icx - hcx)
        dy = icy - hcy
        if dx <= radius * 1.4 and -radius * 1.8 <= dy <= radius * 1.2:
            return True
        head_box = (int(hcx - radius), int(hcy - radius * 1.3), int(radius * 2), int(radius * 2.3))
        if _intersection_over_smaller(item_box, head_box) >= 0.20:
            return True

    # 2. Shoulder-guided check if head points occluded/turned away
    if KP_LEFT_SHOULDER in valid_kps and KP_RIGHT_SHOULDER in valid_kps:
        ls, rs = valid_kps[KP_LEFT_SHOULDER], valid_kps[KP_RIGHT_SHOULDER]
        sh_mid_x = (ls[0] + rs[0]) / 2
        sh_mid_y = (ls[1] + rs[1]) / 2
        sh_dist = max(float(np.hypot(ls[0] - rs[0], ls[1] - rs[1])), pw * 0.4)
        head_est_y = sh_mid_y - sh_dist * 0.45
        radius = sh_dist * 0.55 * head_radius_factor
        if abs(icx - sh_mid_x) <= radius * 1.4 and -radius * 1.8 <= (icy - head_est_y) <= radius * 1.2:
            return True

    # 3. Adaptive aspect ratio bounding-box fallback
    aspect_ratio = pw / max(1, ph)
    if aspect_ratio < 0.65:
        margin_x = pw * 0.15
        return (
            px - margin_x <= icx <= px + pw + margin_x
            and py <= icy <= py + ph * 0.48
        )
    else:
        margin_x = pw * 0.20
        in_horizontal = px - margin_x <= icx <= px + pw + margin_x
        in_vertical = py - ph * 0.10 <= icy <= py + ph * 0.65
        return in_horizontal and in_vertical


def _associate_vest(
    item_box: tuple[int, int, int, int],
    person_box: tuple[int, int, int, int],
    valid_kps: dict[int, tuple[float, float]],
) -> bool:
    """Associate vest/no-vest with person using torso keypoints or adaptive fallback."""
    ix, iy, iw, ih = item_box
    icx, icy = ix + iw / 2, iy + ih / 2
    px, py, pw, ph = person_box

    # 1. Pose-guided check (Torso: Shoulders & Hips)
    torso_kps = [valid_kps[k] for k in (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER, KP_LEFT_HIP, KP_RIGHT_HIP) if k in valid_kps]
    if len(torso_kps) >= 2:
        tx_min = min(p[0] for p in torso_kps)
        tx_max = max(p[0] for p in torso_kps)
        ty_min = min(p[1] for p in torso_kps)
        ty_max = max(p[1] for p in torso_kps)

        tw = max(tx_max - tx_min, pw * 0.3)
        th = max(ty_max - ty_min, ph * 0.25)
        margin_x = max(tw * 0.35, pw * 0.20)
        margin_y = max(th * 0.25, ph * 0.15)

        if (tx_min - margin_x <= icx <= tx_max + margin_x) and (ty_min - margin_y <= icy <= ty_max + margin_y):
            return True
        torso_box = (int(tx_min - margin_x), int(ty_min - margin_y), int(tw + 2 * margin_x), int(th + 2 * margin_y))
        if _intersection_over_smaller(item_box, torso_box) >= 0.25:
            return True

    # 2. If only shoulders are visible (e.g. sitting or upper body view)
    shoulders = [valid_kps[k] for k in (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER) if k in valid_kps]
    if shoulders:
        sx = sum(p[0] for p in shoulders) / len(shoulders)
        sy = min(p[1] for p in shoulders)
        span = pw * 0.6 if len(shoulders) == 1 else abs(shoulders[0][0] - shoulders[1][0])
        span = max(span, pw * 0.4)
        if (sx - span * 0.8 <= icx <= sx + span * 0.8) and (sy - ph * 0.05 <= icy <= sy + span * 1.8):
            return True

    # 3. Adaptive aspect ratio bounding-box fallback
    aspect_ratio = pw / max(1, ph)
    margin_x = pw * 0.18
    if aspect_ratio < 0.65:
        return (
            px - margin_x <= icx <= px + pw + margin_x
            and py + ph * 0.12 <= icy <= py + ph * 0.88
        )
    else:
        return (
            px - margin_x <= icx <= px + pw + margin_x
            and py + ph * 0.10 <= icy <= py + ph * 0.90
        )


def associate_ppe(
    person_box: tuple[int, int, int, int],
    detections: list[dict[str, Any]],
    keypoints: np.ndarray | list[Any] | None = None,
    min_keypoint_conf: float = 0.30,
    head_radius_factor: float = 1.4,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Associate PPE objects to one person using pose-guided keypoints or adaptive geometry."""
    valid_kps = _extract_valid_keypoints(keypoints, min_keypoint_conf)
    helmet_hits: list[dict[str, Any]] = []
    vest_hits: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    for item in detections:
        label = item["normalized_label"]
        if label in PPE_HELMET_OK | PPE_HELMET_MISSING:
            if _associate_helmet(item["box"], person_box, valid_kps, head_radius_factor):
                helmet_hits.append(item)
                matched.append(item)
        elif label in PPE_VEST_OK | PPE_VEST_MISSING:
            if _associate_vest(item["box"], person_box, valid_kps):
                vest_hits.append(item)
                matched.append(item)

    head_visible = any(k in valid_kps for k in (KP_NOSE, KP_LEFT_EYE, KP_RIGHT_EYE, KP_LEFT_EAR, KP_RIGHT_EAR))
    torso_visible = any(k in valid_kps for k in (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER, KP_LEFT_HIP, KP_RIGHT_HIP))

    def decide(hits: list[dict[str, Any]], ok_labels: set[str], missing_labels: set[str], is_visible: bool = False) -> str:
        if not hits:
            return "MISSING" if is_visible else "UNKNOWN"
        ok_hits = [h for h in hits if h["normalized_label"] in ok_labels]
        missing_hits = [h for h in hits if h["normalized_label"] in missing_labels]
        if missing_hits and not ok_hits:
            return "MISSING"
        if ok_hits and not missing_hits:
            return "OK"
        if ok_hits and missing_hits:
            max_ok = max(float(h["confidence"]) for h in ok_hits)
            max_miss = max(float(h["confidence"]) for h in missing_hits)
            if max_ok >= 0.65:
                return "OK"
            return "MISSING"
        return "MISSING" if is_visible else "UNKNOWN"

    return (
        decide(helmet_hits, PPE_HELMET_OK, PPE_HELMET_MISSING, head_visible),
        decide(vest_hits, PPE_VEST_OK, PPE_VEST_MISSING, torso_visible),
        matched,
    )


def analyze_posture(
    person_box: tuple[int, int, int, int],
    valid_kps: dict[int, tuple[float, float]] | None = None,
    face_box: tuple[int, int, int, int] | None = None,
    angle_threshold: float = 38.0,
    aspect_ratio_threshold: float = 1.35,
) -> tuple[str, float | None, bool]:
    """Analyze person posture from bounding box, anatomical keypoints, and face box.

    Returns:
        (posture_label, angle_degrees, is_lying_down)
        posture_label: 'FALLEN' | 'BENDING' | 'SITTING' | 'STANDING'
    """
    px, py, pw, ph = person_box
    aspect_ratio = float(pw) / max(1.0, float(ph))

    # If face box is present and occupies a normal upper-body proportion (e.g. webcam sitting view)
    if face_box is not None:
        fx, fy, fw, fh = face_box
        face_ratio = float(fh) / max(1.0, float(ph))
        if face_ratio >= 0.15 and fy <= py + ph * 0.50:
            return "SITTING" if aspect_ratio >= 0.65 else "STANDING", None, False

    if not valid_kps:
        if aspect_ratio >= 1.25:
            return "FALLEN", None, True
        elif aspect_ratio >= 0.65:
            return "SITTING", None, False
        return "STANDING", None, False

    shoulders = [valid_kps[k] for k in (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER) if k in valid_kps]
    hips = [valid_kps[k] for k in (KP_LEFT_HIP, KP_RIGHT_HIP) if k in valid_kps]
    head = [valid_kps[k] for k in (KP_NOSE, KP_LEFT_EYE, KP_RIGHT_EYE, KP_LEFT_EAR, KP_RIGHT_EAR) if k in valid_kps]
    wrists = [valid_kps[k] for k in (KP_LEFT_WRIST, KP_RIGHT_WRIST) if k in valid_kps]
    knees = [valid_kps[k] for k in (KP_LEFT_KNEE, KP_RIGHT_KNEE) if k in valid_kps]

    # Calculate spine angle if both shoulders and hips are available
    spine_angle = None
    if shoulders and hips:
        sx = sum(p[0] for p in shoulders) / len(shoulders)
        sy = sum(p[1] for p in shoulders) / len(shoulders)
        hx = sum(p[0] for p in hips) / len(hips)
        hy = sum(p[1] for p in hips) / len(hips)
        spine_angle = float(np.degrees(np.arctan2(abs(sy - hy), max(1e-4, abs(sx - hx)))))

    # 1. Check head-to-shoulder vertical orientation (for upright webcam / sitting view)
    if head and shoulders:
        hx = sum(p[0] for p in head) / len(head)
        hy = sum(p[1] for p in head) / len(head)
        sx = sum(p[0] for p in shoulders) / len(shoulders)
        sy = sum(p[1] for p in shoulders) / len(shoulders)
        sh_dist = abs(shoulders[0][0] - shoulders[1][0]) if len(shoulders) >= 2 else pw * 0.5
        head_vert_diff = sy - hy  # positive when head is above shoulders
        head_horiz_diff = abs(sx - hx)
        head_neck_angle = float(np.degrees(np.arctan2(max(0.0, head_vert_diff), max(1e-4, head_horiz_diff))))

        # If head is high above shoulders and upright
        if head_vert_diff > max(20.0, sh_dist * 0.25) and head_neck_angle >= 50.0:
            if hips and spine_angle is not None:
                if spine_angle <= angle_threshold:
                    return "FALLEN", spine_angle, True
                elif spine_angle <= 62.0:
                    return "BENDING", spine_angle, False
                return "STANDING", spine_angle, False
            return "SITTING", head_neck_angle, False

    # 2. Check Arm Span (Outstretched arms on floor - Prone / T-Pose fall)
    if len(wrists) >= 2 and len(shoulders) >= 2:
        wrist_span = abs(wrists[0][0] - wrists[1][0])
        shoulder_span = max(15.0, abs(shoulders[0][0] - shoulders[1][0]))
        if wrist_span >= 1.45 * shoulder_span and aspect_ratio >= 0.55:
            return "FALLEN", spine_angle if spine_angle is not None else 0.0, True

    # 3. Check Torso (Shoulders to Hips)
    if shoulders and hips and spine_angle is not None:
        if spine_angle <= angle_threshold:
            return "FALLEN", spine_angle, True

        # Prone fall along aisle: compressed vertical torso height or wide knee spread on floor
        torso_dy = abs(sum(p[1] for p in shoulders) / len(shoulders) - sum(p[1] for p in hips) / len(hips))
        if aspect_ratio >= 0.70 and (torso_dy <= max(35.0, pw * 0.40) or (len(knees) >= 2 and abs(knees[0][0] - knees[1][0]) >= 30.0)):
            return "FALLEN", spine_angle, True

        if spine_angle <= 62.0:
            return "BENDING", spine_angle, False
        return "STANDING", spine_angle, False

    # 4. Pure Aspect Ratio for fallen (Horizontal on floor)
    if aspect_ratio >= 1.25:
        return "FALLEN", spine_angle if spine_angle is not None else 0.0, True

    return "STANDING", None, False


def analyze_smoking_gesture(
    person_box: tuple[int, int, int, int],
    valid_kps: dict[int, tuple[float, float]] | None = None,
    face_box: tuple[int, int, int, int] | None = None,
    frame: np.ndarray | None = None,
) -> tuple[bool, float | None]:
    """Analyze hand-to-mouth smoking action with strict kinematic validation
    and supplementary visual cues (smoke, ember, stick).

    Detection logic:
      - Gesture alone (hand at mouth) → smoking detected
      - Gesture + visual cues (smoke/ember) → smoking detected (higher confidence)
      - Visual cues alone WITHOUT gesture → NOT detected (prevents false alarm)

    Returns:
        (is_smoking, normalized_distance)
    """
    px, py, pw, ph = person_box
    mouth_x = None
    mouth_y = None
    h_span = 40.0

    # 1. Determine Mouth & Head coordinates from Keypoints or Face Box
    if valid_kps:
        nose = valid_kps.get(KP_NOSE)
        if nose:
            eyes = [valid_kps[k] for k in (KP_LEFT_EYE, KP_RIGHT_EYE) if k in valid_kps]
            if eyes:
                eye_y = sum(p[1] for p in eyes) / len(eyes)
                mouth_y = nose[1] + max(8.0, (nose[1] - eye_y) * 0.75)
            else:
                mouth_y = nose[1] + 12.0
            mouth_x = nose[0]

            ears = [valid_kps[k] for k in (KP_LEFT_EAR, KP_RIGHT_EAR) if k in valid_kps]
            if len(ears) == 2:
                h_span = abs(ears[0][0] - ears[1][0])
            elif len(eyes) == 2:
                h_span = abs(eyes[0][0] - eyes[1][0]) * 1.8
            else:
                h_span = pw * 0.35

    if mouth_x is None and face_box is not None:
        fx, fy, fw, fh = face_box
        mouth_x = fx + fw * 0.5
        mouth_y = fy + fh * 0.78
        h_span = float(fw)

    if mouth_x is None:
        mouth_x = px + pw * 0.5
        mouth_y = py + ph * 0.25
        h_span = pw * 0.40

    h_span = max(20.0, float(h_span))

    # 2. Check Pose Kinematics (if keypoints available)
    is_gesture_smoking = False
    min_norm_dist = 999.0

    if valid_kps:
        shoulders = [valid_kps[k] for k in (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER) if k in valid_kps]
        shoulder_y = sum(p[1] for p in shoulders) / len(shoulders) if shoulders else mouth_y + 80.0
        arm_pairs = [(KP_LEFT_ELBOW, KP_LEFT_WRIST), (KP_RIGHT_ELBOW, KP_RIGHT_WRIST)]

        for e_idx, w_idx in arm_pairs:
            if w_idx not in valid_kps:
                continue
            wx, wy = valid_kps[w_idx]

            d_wrist = float(np.hypot(wx - mouth_x, wy - mouth_y))
            norm_wrist = d_wrist / h_span
            if norm_wrist < min_norm_dist:
                min_norm_dist = norm_wrist

            # Rule 1: Direct wrist near mouth raised above shoulder level
            if wy <= shoulder_y and norm_wrist <= 1.25 and wy >= mouth_y - h_span * 0.60:
                is_gesture_smoking = True
                break

            # Rule 2: Forearm reaching chin (hand near shoulder/chin level)
            if e_idx in valid_kps:
                ex, ey = valid_kps[e_idx]
                vx, vy = wx - ex, wy - ey
                if ey > wy + 20.0 and (wy <= shoulder_y + 10.0 or (wy <= shoulder_y + 20.0 and norm_wrist <= 1.02)):
                    for factor in [0.25, 0.40, 0.55]:
                        hx = wx + factor * vx
                        hy = wy + factor * vy
                        if hy <= shoulder_y:
                            dh = float(np.hypot(hx - mouth_x, hy - mouth_y)) / h_span
                            if dh < min_norm_dist:
                                min_norm_dist = dh
                            if dh <= 0.65 and ((w_idx == KP_RIGHT_WRIST and wx <= mouth_x + 30.0) or (w_idx == KP_LEFT_WRIST and wx >= mouth_x - 30.0)):
                                is_gesture_smoking = True
                                break
            if is_gesture_smoking:
                break

    # 3. Visual Analysis: Smoke, Ember, Stick (supplementary signals)
    has_smoke = False
    has_ember = False
    has_stick = False

    if frame is not None:
        fh_img, fw_img = frame.shape[:2]

        # --- A. Smoke Detection (area ABOVE mouth/nose, rising upward) ---
        # Smoke is light gray/white, low saturation, rises above head
        smoke_y1 = max(0, int(mouth_y - h_span * 1.80))  # well above head
        smoke_y2 = max(0, int(mouth_y - h_span * 0.20))   # just above nose
        smoke_x1 = max(0, int(mouth_x - h_span * 0.80))
        smoke_x2 = min(fw_img, int(mouth_x + h_span * 0.80))

        if smoke_y2 > smoke_y1 + 5 and smoke_x2 > smoke_x1 + 5:
            smoke_roi = frame[smoke_y1:smoke_y2, smoke_x1:smoke_x2]
            hsv_smoke = cv2.cvtColor(smoke_roi, cv2.COLOR_BGR2HSV)

            # Smoke characteristics: low saturation (< 60), medium-high value (120-240)
            # This captures the gray/white translucent haze of cigarette smoke
            mask_smoke = cv2.inRange(
                hsv_smoke,
                np.array([0, 0, 120]),    # any hue, very low sat, medium+ brightness
                np.array([180, 60, 240]),  # any hue, low sat, high brightness
            )

            # Apply morphological operations to filter noise
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask_smoke = cv2.morphologyEx(mask_smoke, cv2.MORPH_OPEN, kernel)

            smoke_px = cv2.countNonZero(mask_smoke)
            roi_area = smoke_roi.shape[0] * smoke_roi.shape[1]

            # Smoke typically covers 8-40% of the ROI above the head
            # Below 8% is normal background; above 40% is likely a white wall
            smoke_ratio = smoke_px / max(1, roi_area)
            if 0.08 <= smoke_ratio <= 0.45 and smoke_px >= 80:
                # Additional check: smoke has soft, blurry edges (low edge density)
                gray_smoke = cv2.cvtColor(smoke_roi, cv2.COLOR_BGR2GRAY)
                edges_smoke = cv2.Canny(gray_smoke, 50, 150)
                edge_density = cv2.countNonZero(edges_smoke) / max(1, roi_area)
                # Smoke has LOW edge density (< 0.15) because it's diffuse
                if edge_density < 0.15:
                    has_smoke = True

        # --- B. Ember Detection (glowing red/orange tip near mouth) ---
        ember_y1 = max(0, int(mouth_y - h_span * 0.40))
        ember_y2 = min(fh_img, int(mouth_y + h_span * 0.60))
        ember_x1 = max(0, int(mouth_x - h_span * 0.80))
        ember_x2 = min(fw_img, int(mouth_x + h_span * 0.80))

        if ember_y2 > ember_y1 + 5 and ember_x2 > ember_x1 + 5:
            ember_roi = frame[ember_y1:ember_y2, ember_x1:ember_x2]
            hsv_ember = cv2.cvtColor(ember_roi, cv2.COLOR_BGR2HSV)

            # Ember: bright red/orange glow (H: 0-18 or 165-180, S > 80, V > 180)
            # Tighter thresholds than before to avoid skin/lip false positives
            mask_ember = cv2.bitwise_or(
                cv2.inRange(hsv_ember, np.array([0, 80, 180]), np.array([18, 255, 255])),
                cv2.inRange(hsv_ember, np.array([165, 80, 180]), np.array([180, 255, 255])),
            )
            ember_px = cv2.countNonZero(mask_ember)
            if ember_px >= 15:
                has_ember = True

        # --- C. Stick Detection (thin white rod near mouth) ---
        stick_y1 = max(0, int(mouth_y - h_span * 0.30))
        stick_y2 = min(fh_img, int(mouth_y + h_span * 0.50))
        stick_x1 = max(0, int(mouth_x - h_span * 0.70))
        stick_x2 = min(fw_img, int(mouth_x + h_span * 0.70))

        if stick_y2 > stick_y1 + 5 and stick_x2 > stick_x1 + 5:
            stick_roi = frame[stick_y1:stick_y2, stick_x1:stick_x2]
            gray_stick = cv2.cvtColor(stick_roi, cv2.COLOR_BGR2GRAY)
            _, mask_white = cv2.threshold(gray_stick, 180, 255, cv2.THRESH_BINARY)

            # Find thin elongated contours (cigarette stick shape)
            contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 10:
                    continue
                rect = cv2.minAreaRect(cnt)
                w_rect, h_rect = rect[1]
                if min(w_rect, h_rect) < 1:
                    continue
                aspect = max(w_rect, h_rect) / min(w_rect, h_rect)
                if aspect >= 3.0 and area <= 800:  # thin elongated shape
                    has_stick = True
                    break

    # 4. Final Decision
    #    - Gesture is the PRIMARY trigger (mandatory)
    #    - Visual cues (smoke/ember/stick) are SUPPLEMENTARY boosters
    #    - Visual cues alone do NOT trigger smoking (prevents false alarms)
    dist_val = float(min_norm_dist) if min_norm_dist < 900.0 else None

    if is_gesture_smoking:
        return True, dist_val

    # If gesture is borderline (hand near but not quite at mouth), visual cues can push it over
    if valid_kps and min_norm_dist <= 1.60:
        visual_count = sum([has_smoke, has_ember, has_stick])
        # Need at least 2 visual cues AND hand reasonably close
        if visual_count >= 2 and min_norm_dist <= 1.40:
            return True, dist_val

    return False, dist_val


class PersonMonitor:
    """Low-latency RTSP monitoring with person tracking and PPE compliance."""

    def __init__(self, settings: Settings, store: EventStore) -> None:
        self.settings = settings
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._frame_seq = 0
        self._latest_jpeg: bytes | None = None
        self._status: dict[str, Any] = {
            "camera_name": settings.camera_name,
            "connected": False,
            "status": "STARTING",
            "score": 0.0,
            "updated_at": None,
            "last_error": None,
            "people_count": 0,
            "max_stay_seconds": settings.max_stay_seconds,
            "longest_stay_seconds": 0,
            "ppe_status": "STARTING",
            "helmet_ok": 0,
            "helmet_missing": 0,
            "vest_ok": 0,
            "vest_missing": 0,
            "person_model": Path(settings.yolo_model).name,
            "ppe_model": Path(settings.ppe_model).name,
            "inference_ms": 0,
            "face_recognition": "DISABLED",
            "tracks": [],
        }
        self._person_model = None
        self._ppe_model = None
        self._face_manager = FaceManager(
            yunet_model_path=self.settings.face_yunet_model,
            sface_model_path=self.settings.face_sface_model,
            known_faces_dir=self.settings.known_faces_dir,
            similarity_threshold=self.settings.face_similarity_threshold,
            enabled=self.settings.face_recognition_enabled,
        )
        if self._face_manager.enabled:
            self._status["face_recognition"] = "ENABLED"
        self._voice_alarm = VoiceAlarm(
            audio_file=self.settings.voice_alarm_audio_file,
            cooldown_seconds=self.settings.voice_alarm_cooldown_seconds,
            enabled=self.settings.voice_alarm_enabled,
        )
        if self._voice_alarm.enabled:
            self._status["voice_alarm"] = "ENABLED"
        self._detector_errors: list[str] = []
        self._load_models()
        self._tracks: dict[int, dict[str, Any]] = {}
        self._fallback_track_id = 100_000
        self._frame_number = 0
        self._person_inference_count = 0
        self._latest_ppe: list[dict[str, Any]] = []
        self._latest_ppe_frame = -1
        self._last_ppe_event_status: str | None = None
        self._last_ppe_event_time = 0.0
        self._pending_ppe_event: tuple[str, str, float] | None = None
        self._latest_fire: list[dict[str, Any]] = []
        self._fire_detected: bool = False
        self._smoke_emergency_detected: bool = False
        self._fire_first_seen: float | None = None
        self._smoke_first_seen: float | None = None
        self._fire_alert_triggered: bool = False
        self._smoke_alert_triggered: bool = False
        self.ptz = PTZController(self.settings.rtsp_url)
        self._auto_track_locked_id: int | None = None
        self._auto_track_last_seen: float = 0.0
        self._last_auto_track_time: float = 0.0
        self._last_auto_track_dir: str = "stop"

    def _load_models(self) -> None:
        if YOLO is None:
            self._detector_errors.append("Ultralytics belum terpasang pada environment server")
            return
        try:
            self._person_model = YOLO(str(self._resolve_model_path(self.settings.yolo_model)))
        except Exception as exc:
            self._detector_errors.append(f"Model person gagal dimuat: {exc}")
        try:
            ppe_path = self._resolve_model_path(self.settings.ppe_model)
            if not ppe_path.exists():
                raise FileNotFoundError(ppe_path)
            self._ppe_model = YOLO(str(ppe_path))
        except Exception as exc:
            self._detector_errors.append(f"Model PPE gagal dimuat: {exc}")
        try:
            v8n_path = self._resolve_model_path("models/ppe_yolov8n.pt")
            if v8n_path.exists() and v8n_path != ppe_path:
                self._ppe_model_v8n = YOLO(str(v8n_path))
            else:
                self._ppe_model_v8n = None
        except Exception:
            self._ppe_model_v8n = None
        try:
            pose_path = self._resolve_model_path("models/yolo11n-pose.pt")
            if pose_path.exists():
                self._pose_model = YOLO(str(pose_path))
            else:
                self._pose_model = None
        except Exception:
            self._pose_model = None
        try:
            fire_path = self._resolve_model_path(self.settings.fire_model)
            if fire_path.exists():
                self._fire_model = YOLO(str(fire_path))
            else:
                self._fire_model = None
        except Exception:
            self._fire_model = None
        if self._detector_errors:
            self._status["last_error"] = "; ".join(self._detector_errors)
        if self._person_model is None:
            self._status["status"] = "PERSON MODEL ERROR"
        if self._ppe_model is None:
            self._status["ppe_status"] = "MODEL_ERROR"

    @staticmethod
    def _resolve_model_path(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
        return path

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="imou-safety-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def latest_raw_frame(self) -> np.ndarray | None:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame.copy()
            if self.settings.rotate_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            return frame

    def _set_status(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)

    def _open_capture(self) -> cv2.VideoCapture:
        source = str(self.settings.rtsp_url).strip()
        if source.isdigit():
            cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(int(source))
            return cap
        if source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        return cv2.VideoCapture(source)

    def _run(self) -> None:
        if not self.settings.rtsp_url:
            self._set_status(last_error="IMOU_RTSP_URL belum diatur di file .env")
            return

        while not self._stop.is_set():
            capture = self._open_capture()
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cam_name = notifier.settings.get("camera_name") or self.settings.camera_name
            if not capture.isOpened():
                self._set_status(connected=False, last_error="Gagal membuka stream/kamera; mencoba ulang")
                capture.release()
                self.store.add_event(cam_name, "CAMERA_OFFLINE", 0, message="Kamera CCTV terputus/offline")
                notifier.notify_camera_status(connected=False, room_name=cam_name, error_msg="Gagal membuka stream RTSP kamera")
                self._stop.wait(5)
                continue

            self._set_status(connected=True, last_error="; ".join(self._detector_errors) or None)
            notifier.notify_camera_status(connected=True, room_name=cam_name)
            reader_stop = threading.Event()
            reader_error: list[Exception | None] = [None]
            reader = threading.Thread(
                target=self._read_latest_frames,
                args=(capture, reader_stop, reader_error),
                name="imou-rtsp-reader",
                daemon=True,
            )
            reader.start()

            ai_stop = threading.Event()
            ai_thread = threading.Thread(
                target=self._ai_inference_worker,
                args=(ai_stop,),
                name="imou-ai-worker",
                daemon=True,
            )
            ai_thread.start()

            try:
                last_render_seq = -1
                while not self._stop.is_set():
                    with self._frame_lock:
                        seq = self._frame_seq
                        frame = self._latest_frame.copy() if self._latest_frame is not None else None
                    if frame is None or seq == last_render_seq:
                        if not reader.is_alive() and reader_error[0] is not None:
                            raise reader_error[0]
                        self._stop.wait(0.005)
                        continue
                    last_render_seq = seq
                    if self.settings.rotate_180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    self._frame_number += 1
                    annotated = self._annotate(frame)
                    jpeg = self._encode_preview(annotated)
                    with self._lock:
                        self._latest_jpeg = jpeg
                    self._flush_pending_event(annotated)
                    self._publish_status(annotated)
            except Exception as exc:
                self._set_status(connected=False, last_error=str(exc))
                notifier.notify_camera_status(connected=False, room_name=cam_name, error_msg=str(exc))
            finally:
                ai_stop.set()
                ai_thread.join(timeout=2)
                reader_stop.set()
                reader.join(timeout=2)
                capture.release()
                self._tracks.clear()
            self._stop.wait(3)

    def _ai_inference_worker(
        self,
        stop_event: threading.Event,
    ) -> None:
        last_seq = -1
        while not self._stop.is_set() and not stop_event.is_set():
            with self._frame_lock:
                seq = self._frame_seq
                frame = self._latest_frame.copy() if self._latest_frame is not None else None

            if frame is None or seq == last_seq:
                stop_event.wait(0.01)
                continue
            last_seq = seq
            if self.settings.rotate_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)

            try:
                started = time.perf_counter()
                self._person_inference_count += 1

                # 1. Detect & Track People
                people = self._detect_and_track_people(frame)

                # 2. PPE Detection
                if (
                    self._ppe_model is not None
                    and self._person_inference_count % self.settings.ppe_process_interval == 0
                ):
                    self._latest_ppe = self._detect_ppe(frame)
                    self._latest_ppe_frame = self._frame_number

                # 3. Fire & Smoke Detection
                if (
                    getattr(self, "_fire_model", None) is not None
                    and self._person_inference_count % getattr(self.settings, "fire_process_interval", 2) == 0
                ):
                    self._latest_fire = self._detect_fire_and_smoke(frame)
                    self._update_fire_states(self._latest_fire, frame=frame)

                # 4. Update track states
                self._update_tracks(people, frame=frame)
                self._update_ppe_states()
                self._process_auto_tracking(frame.shape)

                inference_ms = int((time.perf_counter() - started) * 1000)
                self._set_status(inference_ms=inference_ms)
            except Exception as exc:
                logger.error("AI inference worker error: %s", exc)

    def _process_auto_tracking(self, frame_shape: tuple[int, ...]) -> None:
        """Closed-loop AI Auto-Tracking for PTZ camera following persons."""
        if not notifier.settings.get("auto_tracking_enabled", False):
            return

        now = time.time()
        # Rate limit PTZ updates to at most once every 0.25s
        if now - self._last_auto_track_time < 0.25:
            return

        h, w = frame_shape[:2]
        center_x = w / 2.0
        deadzone = w * 0.18  # ±18% of screen center

        active_tracks = [t for t in self._tracks.values() if not t.get("lost", False)]

        if not active_tracks:
            if self._auto_track_locked_id is not None:
                self._auto_track_locked_id = None
                self._auto_track_last_seen = now
                if self._last_auto_track_dir != "stop":
                    self.ptz.move("stop")
                    self._last_auto_track_dir = "stop"
                    self._last_auto_track_time = now
            elif notifier.settings.get("auto_tracking_return_home", True):
                if self._auto_track_last_seen > 0 and (now - self._auto_track_last_seen) > 15.0:
                    self.ptz.goto_preset(1)
                    self._auto_track_last_seen = 0.0
            return

        self._auto_track_last_seen = now

        # Maintain target lock on primary person or pick first active track
        primary = None
        if self._auto_track_locked_id is not None:
            primary = next((t for t in active_tracks if t.get("id") == self._auto_track_locked_id), None)

        if primary is None:
            primary = active_tracks[0]
            self._auto_track_locked_id = primary.get("id")

        box = primary.get("box", [0, 0, 0, 0])
        x1, y1, x2, y2 = box
        target_cx = (x1 + x2) / 2.0

        offset_x = target_cx - center_x
        speed = int(notifier.settings.get("auto_tracking_speed", 4))

        if abs(offset_x) <= deadzone:
            if self._last_auto_track_dir != "stop":
                self.ptz.move("stop")
                self._last_auto_track_dir = "stop"
                self._last_auto_track_time = now
        elif offset_x < -deadzone:
            # Person is on the left -> Pan Left
            if self._last_auto_track_dir != "left":
                self.ptz.move("left", speed=speed)
                self._last_auto_track_dir = "left"
                self._last_auto_track_time = now
        elif offset_x > deadzone:
            # Person is on the right -> Pan Right
            if self._last_auto_track_dir != "right":
                self.ptz.move("right", speed=speed)
                self._last_auto_track_dir = "right"
                self._last_auto_track_time = now

    def _read_latest_frames(
        self,
        capture: cv2.VideoCapture,
        stop: threading.Event,
        error: list[Exception | None],
    ) -> None:
        try:
            while not self._stop.is_set() and not stop.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError("Frame RTSP tidak terbaca")
                with self._frame_lock:
                    self._latest_frame = frame
                    self._frame_seq += 1
        except Exception as exc:
            error[0] = exc
            stop.set()

    def _detect_and_track_people(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if self._person_model is None:
            return []
        results = self._person_model.track(
            source=frame,
            conf=self.settings.yolo_confidence,
            iou=self.settings.yolo_iou,
            imgsz=self.settings.yolo_imgsz,
            device=self.settings.yolo_device,
            classes=[0],
            persist=True,
            tracker=self.settings.tracker_config,
            verbose=False,
        )
        frame_area = max(1, frame.shape[0] * frame.shape[1])
        detections: list[dict[str, Any]] = []
        for result in results:
            if result.boxes is None:
                continue
            xyxy_values = result.boxes.xyxy.cpu().numpy().astype(int)
            confidence_values = result.boxes.conf.cpu().numpy().tolist()
            ids = result.boxes.id
            track_ids = ids.int().cpu().tolist() if ids is not None else [None] * len(xyxy_values)
            has_kps = (
                hasattr(result, "keypoints")
                and result.keypoints is not None
                and hasattr(result.keypoints, "data")
                and len(result.keypoints.data) == len(xyxy_values)
            )
            kps_list = result.keypoints.data.cpu().numpy() if has_kps else [None] * len(xyxy_values)

            for idx, (xyxy, confidence, track_id) in enumerate(zip(xyxy_values, confidence_values, track_ids)):
                x1, y1, x2, y2 = xyxy.tolist()
                box = (x1, y1, x2 - x1, y2 - y1)
                area_ratio = _box_area(box) / frame_area
                if max(box[2], box[3]) < self.settings.person_min_height or area_ratio < self.settings.person_min_area_ratio:
                    continue
                if track_id is None:
                    track_id = self._fallback_track_id
                    self._fallback_track_id += 1
                detections.append({
                    "id": int(track_id),
                    "box": box,
                    "confidence": float(confidence),
                    "keypoints": kps_list[idx] if has_kps else None,
                })

        # If person model detections lack keypoints and pose model is available, predict pose
        if getattr(self, "_pose_model", None) is not None and any(d["keypoints"] is None for d in detections):
            try:
                pose_res = self._pose_model.predict(
                    source=frame,
                    conf=self.settings.yolo_confidence,
                    iou=self.settings.yolo_iou,
                    imgsz=self.settings.yolo_imgsz,
                    device=self.settings.yolo_device,
                    classes=[0],
                    verbose=False,
                )
                if pose_res and pose_res[0].keypoints is not None and hasattr(pose_res[0].keypoints, "data"):
                    pose_kps = pose_res[0].keypoints.data.cpu().numpy()
                    pose_boxes = pose_res[0].boxes.xyxy.cpu().numpy() if pose_res[0].boxes is not None else []
                    for d in detections:
                        if d["keypoints"] is None:
                            dx, dy, dw, dh = d["box"]
                            d_center = (dx + dw / 2.0, dy + dh / 2.0)
                            best_idx = None
                            min_dist = 99999.0
                            for p_idx, p_box in enumerate(pose_boxes):
                                px1, py1, px2, py2 = p_box
                                p_center = ((px1 + px2) / 2.0, (py1 + py2) / 2.0)
                                dist = float(np.hypot(d_center[0] - p_center[0], d_center[1] - p_center[1]))
                                if dist < min_dist and dist <= max(dw, dh) * 1.2:
                                    min_dist = dist
                                    best_idx = p_idx
                            if best_idx is not None and best_idx < len(pose_kps):
                                d["keypoints"] = pose_kps[best_idx]
            except Exception:
                pass

        return suppress_duplicate_people(detections, self.settings.person_duplicate_overlap)

    def _detect_ppe(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if self._ppe_model is None:
            return []

        models_to_run = [self._ppe_model]
        if getattr(self, "_ppe_model_v8n", None) is not None:
            models_to_run.append(self._ppe_model_v8n)

        detections: list[dict[str, Any]] = []
        for model in models_to_run:
            results = model.predict(
                source=frame,
                conf=self.settings.ppe_confidence,
                iou=self.settings.ppe_iou,
                imgsz=self.settings.ppe_imgsz,
                device=self.settings.yolo_device,
                verbose=False,
            )
            names = model.names
            for result in results:
                if result.boxes is None:
                    continue
                for xyxy, cls_id, confidence in zip(
                    result.boxes.xyxy.cpu().numpy().astype(int),
                    result.boxes.cls.int().cpu().tolist(),
                    result.boxes.conf.cpu().numpy().tolist(),
                ):
                    x1, y1, x2, y2 = xyxy.tolist()
                    label = str(names[int(cls_id)])
                    normalized_label = _normalize_label(label)
                    confidence = float(confidence)
                    if confidence < ppe_confidence_threshold(self.settings, normalized_label):
                        continue

                    # Dual verification for Safety Vest to eliminate false positives on civilian/side-profile clothing
                    if normalized_label in PPE_VEST_OK:
                        crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
                        if not _has_hivis_colors(crop):
                            continue

                    detections.append(
                        {
                            "box": (x1, y1, x2 - x1, y2 - y1),
                            "label": label,
                            "normalized_label": normalized_label,
                            "confidence": confidence,
                        }
                    )
        return detections

    def _detect_fire_and_smoke(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not getattr(self.settings, "fire_detection_enabled", True):
            return []
        if getattr(self, "_fire_model", None) is None:
            return []

        detections: list[dict[str, Any]] = []
        try:
            results = self._fire_model.predict(
                source=frame,
                conf=min(self.settings.fire_confidence, self.settings.smoke_confidence),
                iou=0.45,
                imgsz=self.settings.yolo_imgsz,
                device=self.settings.yolo_device,
                verbose=False,
            )
            names = self._fire_model.names
            for result in results:
                if result.boxes is None:
                    continue
                for xyxy, cls_id, conf in zip(
                    result.boxes.xyxy.cpu().numpy().astype(int),
                    result.boxes.cls.int().cpu().tolist(),
                    result.boxes.conf.cpu().numpy().tolist(),
                ):
                    raw_label = str(names[int(cls_id)]).lower()
                    label = "fire" if "fire" in raw_label else "smoke"
                    conf_thresh = self.settings.fire_confidence if label == "fire" else self.settings.smoke_confidence
                    if float(conf) < conf_thresh:
                        continue
                    x1, y1, x2, y2 = xyxy.tolist()
                    box = (x1, y1, x2 - x1, y2 - y1)
                    detections.append(
                        {
                            "box": box,
                            "label": label,
                            "confidence": float(conf),
                        }
                    )
        except Exception as exc:
            logger.error("Fire/smoke inference error: %s", exc)
        return detections

    def _update_fire_states(self, fire_detections: list[dict[str, Any]], frame: np.ndarray | None = None) -> None:
        now = time.monotonic()
        cam_name = notifier.settings.get("camera_name") or self.settings.camera_name

        has_fire = any(d["label"] == "fire" for d in fire_detections)
        has_smoke = any(d["label"] == "smoke" for d in fire_detections)

        # 1. Fire Evaluation
        fire_threshold = float(self.settings.fire_debounce_seconds if getattr(self.settings, "fire_debounce_seconds", 1.0) != 1.0 else notifier.settings.get("alert_fire_emergency_seconds", 1.0))
        if has_fire:
            if self._fire_first_seen is None:
                self._fire_first_seen = now
            fire_dur = now - self._fire_first_seen
            if fire_dur >= fire_threshold:
                self._fire_detected = True
                if not self._fire_alert_triggered:
                    self._fire_alert_triggered = True
                    best_conf = max((d["confidence"] for d in fire_detections if d["label"] == "fire"), default=1.0)
                    self.store.add_event(
                        cam_name,
                        "FIRE_EMERGENCY",
                        float(best_conf),
                        message="🚨 BAHAYA KEBAKARAN: Kobaran api terdeteksi di Ruang Elektrikal!",
                    )
                    # Trigger vocal alarm
                    if hasattr(self, "_voice_alarm") and self._voice_alarm.enabled:
                        self._voice_alarm.trigger_custom(
                            str(self.settings.fire_audio_file),
                            reason="FIRE",
                            cooldown=15.0,
                        )
        else:
            if self._fire_first_seen and (now - self._fire_first_seen > 3.0):
                self._fire_first_seen = None
                self._fire_detected = False
                self._fire_alert_triggered = False

        # 2. Dense Smoke Evaluation
        smoke_threshold = float(self.settings.smoke_emergency_debounce_seconds if getattr(self.settings, "smoke_emergency_debounce_seconds", 1.5) != 1.5 else notifier.settings.get("alert_smoke_emergency_seconds", 1.5))
        if has_smoke:
            if self._smoke_first_seen is None:
                self._smoke_first_seen = now
            smoke_dur = now - self._smoke_first_seen
            if smoke_dur >= smoke_threshold:
                self._smoke_emergency_detected = True
                if not self._smoke_alert_triggered:
                    self._smoke_alert_triggered = True
                    best_conf = max((d["confidence"] for d in fire_detections if d["label"] == "smoke"), default=1.0)
                    self.store.add_event(
                        cam_name,
                        "THICK_SMOKE_EMERGENCY",
                        float(best_conf),
                        message="⚠️ DARURAT ASAP TEBAL: Gumpalan asap kebakaran terdeteksi di Ruang Elektrikal!",
                    )
                    # Trigger vocal alarm
                    if hasattr(self, "_voice_alarm") and self._voice_alarm.enabled:
                        self._voice_alarm.trigger_custom(
                            str(self.settings.fire_audio_file),
                            reason="SMOKE_EMERGENCY",
                            cooldown=20.0,
                        )
        else:
            if self._smoke_first_seen and (now - self._smoke_first_seen > 3.0):
                self._smoke_first_seen = None
                self._smoke_emergency_detected = False
                self._smoke_alert_triggered = False

    def _update_tracks(self, people: list[dict[str, Any]], frame: np.ndarray | None = None) -> None:
        now = time.monotonic()
        seen: set[int] = set()
        for person in people:
            track_id = int(person["id"])
            seen.add(track_id)
            if track_id not in self._tracks:
                initial_name = f"Person #{track_id}"
                self._tracks[track_id] = {
                    "id": track_id,
                    "name": initial_name,
                    "face_box": None,
                    "face_checked": False,
                    "entered_at": now,
                    "last_seen": now,
                    "box": person["box"],
                    "confidence": person["confidence"],
                    "keypoints": person.get("keypoints"),
                    "overstay": False,
                    "helmet": "UNKNOWN",
                    "vest": "UNKNOWN",
                    "helmet_votes": deque(maxlen=self.settings.ppe_debounce_cycles),
                    "vest_votes": deque(maxlen=self.settings.ppe_debounce_cycles),
                    "ppe_boxes": [],
                    "posture": "STANDING",
                    "posture_angle": None,
                    "is_lying": False,
                    "lying_start_time": None,
                    "fall_alert_triggered": False,
                }
                self.store.add_event(
                    self.settings.camera_name,
                    "PERSON_ENTER",
                    person["confidence"],
                    message=f"{initial_name} (Track {track_id}) terdeteksi",
                )
            track = self._tracks[track_id]
            track.update(
                last_seen=now,
                box=person["box"],
                confidence=person["confidence"],
                keypoints=person.get("keypoints"),
            )

            # Face recognition & identity locking (run early so face_box is available for posture & smoking)
            kps = track.get("keypoints")
            valid_kps = _extract_valid_keypoints(kps, self.settings.pose_keypoint_confidence) if kps is not None else None
            if frame is not None and getattr(self, "_face_manager", None) and self._face_manager.enabled:
                if not track.get("face_checked") or self._frame_number % 6 == 0:
                    name, conf, fbox = self._face_manager.identify_person(frame, track["box"], valid_kps)
                    if fbox is not None:
                        track["name"] = name
                        track["face_box"] = fbox
                        track["face_checked"] = True

            # Posture & Fall / Unconscious detection
            face_box = track.get("face_box")
            posture, angle, is_lying = analyze_posture(
                track["box"],
                valid_kps,
                face_box=face_box,
                angle_threshold=self.settings.fall_angle_threshold,
                aspect_ratio_threshold=self.settings.fall_aspect_ratio_threshold,
            )
            track["posture_angle"] = angle
            track["is_lying"] = is_lying

            if is_lying:
                if track.get("lying_start_time") is None:
                    track["lying_start_time"] = now
                lying_duration = now - track["lying_start_time"]
                fall_threshold = float(notifier.settings.get("alert_fall_emergency_seconds", self.settings.fall_debounce_seconds))
                if lying_duration >= fall_threshold:
                    track["posture"] = "FALLEN"
                    if not track.get("fall_alert_triggered"):
                        track["fall_alert_triggered"] = True
                        p_name = track.get("name") or f"Person #{track_id}"
                        self.store.add_event(
                            self.settings.camera_name,
                            "MAN_DOWN_EMERGENCY",
                            1.0,
                            message=f"⚠️ DARURAT: {p_name} terdeteksi JATUH / PINGSAN ({int(lying_duration)}s)!",
                        )
                else:
                    track["posture"] = "SUSPECTED_FALL"
            else:
                track["posture"] = posture
                track["lying_start_time"] = None
                track["fall_alert_triggered"] = False

            # Smoking gesture & vision analysis & tracking (Rokok Batang)
            if getattr(self.settings, "smoking_detection_enabled", True):
                hand_near_mouth, dist_score = analyze_smoking_gesture(
                    track["box"],
                    valid_kps,
                    face_box=face_box,
                    frame=frame,
                )
                smoking_threshold = float(notifier.settings.get("alert_smoking_seconds", getattr(self.settings, "smoking_debounce_seconds", 2.5)))
                if hand_near_mouth:
                    if not track.get("smoking_start_time"):
                        track["smoking_start_time"] = now
                    smoking_duration = now - track["smoking_start_time"]
                    if smoking_duration >= smoking_threshold:
                        track["is_smoking"] = True
                        track["smoking_duration"] = int(smoking_duration)
                        if not track.get("smoking_alert_triggered"):
                            track["smoking_alert_triggered"] = True
                            p_name = track.get("name") or f"Person #{track_id}"
                            self.store.add_event(
                                self.settings.camera_name,
                                "SMOKING_VIOLATION",
                                1.0,
                                message=f"🔥 PELANGGARAN: {p_name} terdeteksi MEROKOK di Ruang Elektrikal ({int(smoking_duration)}s)!",
                            )
                        # Trigger vocal warning for smoking
                        if hasattr(self, "_voice_alarm") and self._voice_alarm.enabled:
                            self._voice_alarm.trigger_custom(
                                str(self.settings.smoking_audio_file),
                                reason="SMOKING",
                                cooldown=30.0,
                            )
                else:
                    if track.get("smoking_start_time") and (now - track.get("last_hand_at_mouth", now) > 2.5):
                        track["smoking_start_time"] = None
                        track["is_smoking"] = False
                        track["smoking_duration"] = 0
                        track["smoking_alert_triggered"] = False
                if hand_near_mouth:
                    track["last_hand_at_mouth"] = now

        stale = [track_id for track_id, track in self._tracks.items() if now - track["last_seen"] > 2.5]
        for track_id in stale:
            track = self._tracks.pop(track_id)
            stay = int(now - track["entered_at"])
            name = track.get("name", f"Track {track_id}")
            self.store.add_event(
                self.settings.camera_name,
                "PERSON_EXIT",
                1.0,
                message=f"{name} keluar setelah {stay} detik",
            )

        for track in self._tracks.values():
            stay = now - track["entered_at"]
            if stay >= self.settings.max_stay_seconds and not track["overstay"]:
                track["overstay"] = True
                name = track.get("name", f"Track {track['id']}")
                self.store.add_event(
                    self.settings.camera_name,
                    "OVERSTAY",
                    min(stay / self.settings.max_stay_seconds, 9.999),
                    message=f"{name} melebihi durasi",
                )

            # Trigger Voice Alarm if person is without PPE for >= voice_alarm_trigger_seconds (default 30s)
            if (
                self.settings.voice_alarm_enabled
                and stay >= self.settings.voice_alarm_trigger_seconds
                and (
                    track.get("helmet") == "MISSING"
                    or track.get("vest") == "MISSING"
                    or self._status.get("ppe_status") == "VIOLATION"
                )
            ):
                person_name = track.get("name") or f"Track #{track['id']}"
                self._voice_alarm.trigger(f"{person_name} belum memakai APD setelah {int(stay)}s")

    def _update_ppe_states(self) -> None:
        if self._ppe_model is None:
            return
        for track in self._tracks.values():
            helmet, vest, matched = associate_ppe(
                track["box"],
                self._latest_ppe,
                keypoints=track.get("keypoints"),
                min_keypoint_conf=self.settings.pose_keypoint_confidence,
                head_radius_factor=self.settings.pose_head_radius_factor,
            )
            track["ppe_boxes"] = matched
            self._debounce_ppe(track, "helmet", helmet)
            self._debounce_ppe(track, "vest", vest)
        self._evaluate_global_ppe_status()

    def _debounce_ppe(self, track: dict[str, Any], field: str, observed: str) -> None:
        votes: deque[str] = track[f"{field}_votes"]
        votes.append(observed)
        if len(votes) == votes.maxlen and len(set(votes)) == 1:
            track[field] = votes[-1]

    def _evaluate_global_ppe_status(self) -> None:
        if not self._tracks:
            new_status = "NO_PERSON"
        elif any(
            track["helmet"] == "MISSING" or track["vest"] == "MISSING"
            for track in self._tracks.values()
        ):
            new_status = "VIOLATION"
        elif all(
            track["helmet"] == "OK" and track["vest"] == "OK"
            for track in self._tracks.values()
        ):
            new_status = "COMPLIANT"
        else:
            new_status = "CHECKING"

        current_status = self._status.get("ppe_status")
        self._set_status(ppe_status=new_status)
        if new_status not in {"VIOLATION", "COMPLIANT"} or new_status == current_status:
            return
        now = time.monotonic()
        # Apply one global cooldown. Without this, alternating model outputs
        # (COMPLIANT -> VIOLATION -> COMPLIANT) can flood the event history.
        if now - self._last_ppe_event_time < self.settings.ppe_event_cooldown_seconds:
            return
        violations = []
        for track in self._tracks.values():
            t_name = track.get("name") or f"ID {track.get('id', '?')}"
            h_stat = track.get("helmet", "UNKNOWN")
            v_stat = track.get("vest", "UNKNOWN")
            violations.append(f"{t_name}: helmet={h_stat}, vest={v_stat}")
        message = "; ".join(violations)
        event_name = "PPE_VIOLATION" if new_status == "VIOLATION" else "PPE_COMPLIANT"
        self._pending_ppe_event = (event_name, message, 1.0)
        self._last_ppe_event_status = new_status
        self._last_ppe_event_time = now

    def _flush_pending_event(self, annotated: np.ndarray) -> None:
        if self._pending_ppe_event is None:
            return
        event_name, message, score = self._pending_ppe_event
        self._pending_ppe_event = None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.settings.snapshots_dir / f"{event_name.lower()}_{timestamp}.jpg"
        cv2.imwrite(str(path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.store.add_event(
            self.settings.camera_name,
            event_name,
            score,
            snapshot_path=str(path),
            message=message,
        )

    def _publish_status(self, annotated: np.ndarray | None = None) -> None:
        now = time.monotonic()
        tracks = []
        has_fallen = any(track.get("posture") == "FALLEN" for track in self._tracks.values())
        has_smoking = any(track.get("is_smoking") for track in self._tracks.values())
        for track in self._tracks.values():
            lying_sec = int(now - track["lying_start_time"]) if track.get("lying_start_time") else 0
            tracks.append(
                {
                    "id": track["id"],
                    "name": track.get("name", f"Person #{track['id']}"),
                    "confidence": round(float(track["confidence"]), 3),
                    "stay_seconds": int(now - track["entered_at"]),
                    "overstay": track["overstay"],
                    "helmet": track["helmet"],
                    "vest": track["vest"],
                    "posture": track.get("posture", "STANDING"),
                    "lying_seconds": lying_sec,
                    "is_smoking": bool(track.get("is_smoking", False)),
                    "smoking_seconds": int(track.get("smoking_duration", 0)),
                }
            )
        longest = max((item["stay_seconds"] for item in tracks), default=0)
        cam_name = notifier.settings.get("camera_name") or self.settings.camera_name
        fire_cnt = len([d for d in self._latest_fire if d["label"] == "fire"])
        smoke_cnt = len([d for d in self._latest_fire if d["label"] == "smoke"])

        # Determine overall safety health status
        if self._fire_detected:
            h_stat = "🔥 BAHAYA KEBAKARAN (FIRE)"
        elif self._smoke_emergency_detected:
            h_stat = "🌫️ DARURAT ASAP TEBAL"
        elif has_fallen:
            h_stat = "⚠️ MAN DOWN / JATUH"
        else:
            h_stat = "NORMAL"

        self._set_status(
            camera_name=cam_name,
            connected=True,
            status=f"PEOPLE: {len(tracks)}",
            score=float(len(tracks)),
            people_count=len(tracks),
            longest_stay_seconds=longest,
            helmet_ok=sum(track["helmet"] == "OK" for track in self._tracks.values()),
            helmet_missing=sum(track["helmet"] == "MISSING" for track in self._tracks.values()),
            vest_ok=sum(track["vest"] == "OK" for track in self._tracks.values()),
            vest_missing=sum(track["vest"] == "MISSING" for track in self._tracks.values()),
            fall_detected=has_fallen,
            smoking_detected=has_smoking,
            fire_detected=self._fire_detected,
            smoke_emergency_detected=self._smoke_emergency_detected,
            fire_count=fire_cnt,
            smoke_count=smoke_cnt,
            fire_detections=self._latest_fire,
            health_status=h_stat,
            updated_at=datetime.now(timezone.utc).isoformat(),
            tracks=tracks,
        )

        # Sync voice alarm state dynamically from web settings
        if hasattr(self, "_voice_alarm") and self._voice_alarm is not None:
            self._voice_alarm.enabled = bool(notifier.settings.get("voice_alarm_enabled", True))

        # Check & dispatch WhatsApp snapshots
        latest_snap_path = None
        if annotated is not None:
            if notifier.settings.get("whatsapp_enabled") and notifier.settings.get("whatsapp_target"):
                has_any_person_alert = any(
                    (t["stay_seconds"] >= notifier.settings.get("alert_ppe_violation_seconds", 60) and (t["helmet"] == "MISSING" or t["vest"] == "MISSING"))
                    or (t["posture"] == "FALLEN" and t["lying_seconds"] >= 4)
                    or (t["stay_seconds"] >= notifier.settings.get("alert_er_activity_seconds", 300))
                    or t.get("is_smoking")
                    for t in tracks
                )
                has_env_emergency = self._fire_detected or self._smoke_emergency_detected
                if has_any_person_alert or has_env_emergency:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    snap_file = self.settings.snapshots_dir / f"wa_alert_{timestamp}.jpg"
                    cv2.imwrite(str(snap_file), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    latest_snap_path = snap_file

                    # Dispatch fire & smoke emergency alerts immediately
                    if self._fire_detected:
                        notifier.notify_fire_emergency(cam_name, image_path=latest_snap_path)
                    if self._smoke_emergency_detected:
                        notifier.notify_smoke_emergency(cam_name, image_path=latest_snap_path)

        notifier.process_tracks_and_alerts(tracks, latest_snapshot_path=latest_snap_path)

    def _annotate(self, frame: np.ndarray) -> np.ndarray:
        output = frame.copy()
        now = time.monotonic()
        has_fallen_global = any(track.get("posture") == "FALLEN" for track in self._tracks.values())
        has_smoking_global = any(track.get("is_smoking") for track in self._tracks.values())

        # Responsive scaling based on stream resolution
        img_w = output.shape[1]
        scale = max(0.85, min(2.5, img_w / 800.0))
        font_scale = 0.58 * scale
        font_thick = max(2, int(scale * 1.5))
        box_thickness = max(2, int(scale * 2.0))

        # 1. Annotate Fire and Smoke Detections
        for f_det in getattr(self, "_latest_fire", []):
            bx, by, bw, bh = f_det["box"]
            f_lbl = f_det["label"]
            f_conf = f_det["confidence"]
            if f_lbl == "fire":
                f_color = (0, 69, 255)  # Bright Orange-Red
                f_text = f"🔥 FIRE ({int(f_conf * 100)}%)"
            else:
                f_color = (180, 180, 100)  # Dense smoke teal-gray
                f_text = f"🌫️ DENSE SMOKE ({int(f_conf * 100)}%)"

            cv2.rectangle(output, (bx, by), (bx + bw, by + bh), f_color, box_thickness + 2)
            (tw, th), _ = cv2.getTextSize(f_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick)
            cv2.rectangle(output, (bx, max(0, by - th - int(10 * scale))), (min(output.shape[1], bx + tw + int(12 * scale)), by), f_color, -1)
            cv2.putText(output, f_text, (bx + int(6 * scale), by - int(5 * scale)), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 2. Annotate People & PPE
        for track in self._tracks.values():
            x, y, w, h = track["box"]
            is_fallen = track.get("posture") == "FALLEN"
            is_smoking = track.get("is_smoking", False)
            is_suspect = track.get("posture") == "SUSPECTED_FALL"
            violation = track["helmet"] == "MISSING" or track["vest"] == "MISSING"
            complete = track["helmet"] == "OK" and track["vest"] == "OK"

            if is_fallen or is_smoking:
                color = (0, 0, 255)
                box_thick = box_thickness + 2
            elif is_suspect:
                color = (0, 140, 255)
                box_thick = box_thickness + 1
            elif violation:
                color = (0, 0, 255)
                box_thick = box_thickness
            elif complete:
                color = (0, 190, 0)
                box_thick = box_thickness
            else:
                color = (0, 165, 255)
                box_thick = box_thickness

            cv2.rectangle(output, (x, y), (x + w, y + h), color, box_thick)

            # Draw face box if present
            fbox = track.get("face_box")
            if fbox is not None:
                fx, fy, fw, fh = fbox
                cv2.rectangle(output, (fx, fy), (fx + fw, fy + fh), (255, 255, 0), max(1, int(scale)))

            # Draw subtle skeleton connections if pose keypoints are present
            kps = track.get("keypoints")
            valid_pts = _extract_valid_keypoints(kps, self.settings.pose_keypoint_confidence)
            for p1_idx, p2_idx in SKELETON_PAIRS:
                if p1_idx in valid_pts and p2_idx in valid_pts:
                    pt1 = (int(valid_pts[p1_idx][0]), int(valid_pts[p1_idx][1]))
                    pt2 = (int(valid_pts[p2_idx][0]), int(valid_pts[p2_idx][1]))
                    cv2.line(output, pt1, pt2, (255, 200, 0), max(1, int(scale)), cv2.LINE_AA)
            for pt_coords in valid_pts.values():
                cv2.circle(output, (int(pt_coords[0]), int(pt_coords[1])), max(2, int(scale * 2)), (0, 255, 255), -1, cv2.LINE_AA)

            name = track.get("name", f"ID {track['id']}")
            if is_fallen:
                label = f"⚠️ JATUH/PINGSAN! {name} ({int(now - track['entered_at'])}s)"
            elif is_smoking:
                label = f"🔥 MEROKOK! {name} ({int(track.get('smoking_duration', 0))}s)"
            else:
                label = (
                    f"{name} ({int(now - track['entered_at'])}s) "
                    f"H:{track['helmet']} V:{track['vest']}"
                )

            # Draw solid contrast badge behind label text for high readability
            (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick)
            badge_y1 = max(0, y - text_h - int(10 * scale))
            badge_y2 = y
            badge_x2 = min(output.shape[1], x + text_w + int(12 * scale))
            cv2.rectangle(output, (x, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.putText(
                output,
                label,
                (x + int(6 * scale), y - int(5 * scale)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                font_thick,
                cv2.LINE_AA,
            )

        ppe_status = str(self._status.get("ppe_status", "CHECKING"))
        top_font_scale = 0.82 * scale
        top_font_thick = max(2, int(scale * 2.2))
        top_y = int(40 * scale)

        # 3. Prominent Top Header Banner
        if getattr(self, "_fire_detected", False):
            cv2.putText(
                output,
                "🚨🚨 BAHAYA KEBAKARAN: API TERDETEKSI DI RUANG ELEKTRIKAL! 🚨🚨",
                (int(20 * scale), top_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                top_font_scale,
                (0, 0, 255),
                top_font_thick + 1,
                cv2.LINE_AA,
            )
        elif getattr(self, "_smoke_emergency_detected", False):
            cv2.putText(
                output,
                "⚠️🚨 PERINGATAN K3: DETEKSI ASAP TEBAL DI RUANG ELEKTRIKAL!",
                (int(20 * scale), top_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                top_font_scale,
                (0, 140, 255),
                top_font_thick,
                cv2.LINE_AA,
            )
        elif has_fallen_global:
            cv2.putText(
                output,
                "⚠️ PERINGATAN DARURAT: PERSONEL JATUH / PINGSAN!",
                (int(20 * scale), top_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                top_font_scale,
                (0, 0, 255),
                top_font_thick,
                cv2.LINE_AA,
            )
        elif has_smoking_global:
            cv2.putText(
                output,
                "🔥 PERINGATAN K3: DETEKSI MEROKOK DI RUANG ELEKTRIKAL!",
                (int(20 * scale), top_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                top_font_scale,
                (0, 0, 255),
                top_font_thick,
                cv2.LINE_AA,
            )
        else:
            header_color = (0, 0, 255) if ppe_status == "VIOLATION" else (255, 255, 255)
            cv2.putText(
                output,
                f"People: {len(self._tracks)} | PPE: {ppe_status}",
                (int(20 * scale), top_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                top_font_scale,
                header_color,
                top_font_thick,
                cv2.LINE_AA,
            )
        return output

    @staticmethod
    def _encode_preview(frame: np.ndarray) -> bytes | None:
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        return encoded.tobytes() if ok else None
