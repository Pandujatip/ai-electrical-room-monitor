from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    rtsp_url: str = os.getenv("IMOU_RTSP_URL", "")
    server_host: str = os.getenv("SERVER_HOST", "127.0.0.1")
    server_port: int = _int("SERVER_PORT", 8000)
    camera_name: str = os.getenv("CAMERA_NAME", "Imou Electrical Room")
    roi_x: int = _int("ROI_X", 0)
    roi_y: int = _int("ROI_Y", 0)
    roi_width: int = _int("ROI_WIDTH", 0)
    roi_height: int = _int("ROI_HEIGHT", 0)
    debounce_frames: int = max(1, _int("DEBOUNCE_FRAMES", 5))
    event_cooldown_seconds: float = max(0, _float("EVENT_COOLDOWN_SECONDS", 30))
    frame_interval_seconds: float = max(0.02, _float("FRAME_INTERVAL_SECONDS", 0.15))
    detector_mode: str = os.getenv("DETECTOR_MODE", "ultralytics")
    yolo_model: str = os.getenv("YOLO_MODEL", str(BASE_DIR / "yolo11n.pt" if (BASE_DIR / "yolo11n.pt").exists() else BASE_DIR / "yolo11s.pt"))
    yolo_confidence: float = max(0.05, _float("YOLO_CONFIDENCE", 0.25))
    yolo_iou: float = min(0.95, max(0.05, _float("YOLO_IOU", 0.50)))
    yolo_imgsz: int = max(320, _int("YOLO_IMGSZ", 640))
    yolo_device: str = os.getenv("YOLO_DEVICE", "cpu")
    tracker_config: str = os.getenv("TRACKER_CONFIG", "bytetrack.yaml")
    pose_keypoint_confidence: float = max(0.1, _float("POSE_KEYPOINT_CONFIDENCE", 0.25))
    pose_head_radius_factor: float = max(0.5, _float("POSE_HEAD_RADIUS_FACTOR", 1.4))
    max_stay_seconds: int = max(1, _int("MAX_STAY_SECONDS", 1800))
    person_process_interval: int = max(1, _int("PERSON_PROCESS_INTERVAL", 2))
    person_min_score: float = max(0.1, _float("PERSON_MIN_SCORE", 0.35))
    person_min_height: int = max(25, _int("PERSON_MIN_HEIGHT", 35))
    person_min_area_ratio: float = min(0.5, max(0.0, _float("PERSON_MIN_AREA_RATIO", 0.003)))
    person_duplicate_overlap: float = min(0.95, max(0.1, _float("PERSON_DUPLICATE_OVERLAP", 0.60)))
    ppe_model: str = os.getenv("PPE_MODEL", str(BASE_DIR / "models" / "ppe_full.pt"))
    ppe_confidence: float = min(0.95, max(0.05, _float("PPE_CONFIDENCE", 0.30)))
    ppe_helmet_ok_confidence: float = min(
        0.99, max(0.05, _float("PPE_HELMET_OK_CONFIDENCE", 0.35))
    )
    ppe_helmet_missing_confidence: float = min(
        0.99, max(0.05, _float("PPE_HELMET_MISSING_CONFIDENCE", 0.30))
    )
    ppe_vest_ok_confidence: float = min(
        0.99, max(0.05, _float("PPE_VEST_OK_CONFIDENCE", 0.40))
    )
    ppe_vest_missing_confidence: float = min(
        0.99, max(0.05, _float("PPE_VEST_MISSING_CONFIDENCE", 0.28))
    )
    ppe_iou: float = min(0.95, max(0.05, _float("PPE_IOU", 0.45)))
    ppe_imgsz: int = max(320, _int("PPE_IMGSZ", 640))
    ppe_process_interval: int = max(1, _int("PPE_PROCESS_INTERVAL", 2))
    ppe_debounce_cycles: int = max(1, _int("PPE_DEBOUNCE_CYCLES", 5))
    ppe_event_cooldown_seconds: float = max(0, _float("PPE_EVENT_COOLDOWN_SECONDS", 60))
    rotate_180: bool = os.getenv("VIDEO_ROTATE_180", "0").strip().lower() in {"1", "true", "yes"}
    face_recognition_enabled: bool = os.getenv("FACE_RECOGNITION_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    face_similarity_threshold: float = min(0.99, max(0.1, _float("FACE_SIMILARITY_THRESHOLD", 0.363)))
    face_yunet_model: str = os.getenv("FACE_YUNET_MODEL", str(BASE_DIR / "models" / "face_detection_yunet_2023mar.onnx"))
    face_sface_model: str = os.getenv("FACE_SFACE_MODEL", str(BASE_DIR / "models" / "face_recognition_sface_2021dec.onnx"))
    voice_alarm_enabled: bool = os.getenv("VOICE_ALARM_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    voice_alarm_trigger_seconds: int = max(1, _int("VOICE_ALARM_TRIGGER_SECONDS", 30))
    voice_alarm_cooldown_seconds: float = max(5, _float("VOICE_ALARM_COOLDOWN_SECONDS", 40))
    voice_alarm_audio_file: Path = BASE_DIR / "static" / "audio" / "warning_female.mp3"
    fall_detection_enabled: bool = os.getenv("FALL_DETECTION_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    fall_debounce_seconds: float = max(1.0, _float("FALL_DEBOUNCE_SECONDS", 4.0))
    fall_angle_threshold: float = max(10.0, _float("FALL_ANGLE_THRESHOLD", 38.0))
    fall_aspect_ratio_threshold: float = max(0.5, _float("FALL_ASPECT_RATIO_THRESHOLD", 1.05))
    smoking_detection_enabled: bool = os.getenv("SMOKING_DETECTION_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    smoking_debounce_seconds: float = max(1.0, _float("SMOKING_DEBOUNCE_SECONDS", 2.5))
    smoking_audio_file: Path = BASE_DIR / "static" / "audio" / "smoking_warning.mp3"
    fire_detection_enabled: bool = os.getenv("FIRE_DETECTION_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    fire_model: str = os.getenv("FIRE_MODEL", str(BASE_DIR / "models" / "fire_smoke_yolov8n.pt"))
    fire_confidence: float = min(0.95, max(0.05, _float("FIRE_CONFIDENCE", 0.35)))
    smoke_confidence: float = min(0.95, max(0.05, _float("SMOKE_CONFIDENCE", 0.35)))
    fire_process_interval: int = max(1, _int("FIRE_PROCESS_INTERVAL", 2))
    fire_debounce_seconds: float = max(0.5, _float("FIRE_DEBOUNCE_SECONDS", 1.0))
    smoke_emergency_debounce_seconds: float = max(0.5, _float("SMOKE_EMERGENCY_DEBOUNCE_SECONDS", 1.5))
    fire_audio_file: Path = BASE_DIR / "static" / "audio" / "fire_warning.mp3"
    known_faces_dir: Path = BASE_DIR / "known_faces"
    db_path: Path = BASE_DIR / "events.db"
    snapshots_dir: Path = BASE_DIR / "snapshots"
    logs_dir: Path = BASE_DIR / "logs"


settings = Settings()
settings.snapshots_dir.mkdir(exist_ok=True)
settings.logs_dir.mkdir(exist_ok=True)
settings.known_faces_dir.mkdir(exist_ok=True)
