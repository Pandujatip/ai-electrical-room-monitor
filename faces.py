from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FaceManager:
    """Lightweight Face Recognition and Appearance Identity Locking using OpenCV YuNet and SFace."""

    def __init__(
        self,
        yunet_model_path: str | Path,
        sface_model_path: str | Path,
        known_faces_dir: str | Path,
        similarity_threshold: float = 0.363,
        enabled: bool = True,
    ) -> None:
        self.yunet_path = Path(yunet_model_path)
        self.sface_path = Path(sface_model_path)
        self.known_faces_dir = Path(known_faces_dir)
        self.similarity_threshold = similarity_threshold
        self.enabled = enabled

        self._detector: cv2.FaceDetectorYN | None = None
        self._recognizer: cv2.FaceRecognizerSF | None = None
        self._current_input_size = (320, 320)

        self._known_faces: dict[str, np.ndarray] = {}
        self._session_faces: dict[int, dict[str, Any]] = {}
        self._next_session_id = 1

        if self.enabled:
            self._load_models()
            self._load_known_faces()

    def _load_models(self) -> None:
        if not self.yunet_path.exists() or not self.sface_path.exists():
            logger.warning(
                "Model wajah tidak ditemukan pada %s atau %s. Face recognition dinonaktifkan.",
                self.yunet_path,
                self.sface_path,
            )
            self.enabled = False
            return

        try:
            self._detector = cv2.FaceDetectorYN.create(
                str(self.yunet_path),
                "",
                self._current_input_size,
                score_threshold=0.6,
                nms_threshold=0.3,
                top_k=5,
            )
            self._recognizer = cv2.FaceRecognizerSF.create(str(self.sface_path), "")
            logger.info("Modul Face Recognition (YuNet & SFace) berhasil diinisialisasi.")
        except Exception as exc:
            logger.error("Gagal menginisialisasi modul Face Recognition: %s", exc)
            self.enabled = False

    def _load_known_faces(self) -> None:
        if not self.enabled or self._recognizer is None:
            return

        self.known_faces_dir.mkdir(parents=True, exist_ok=True)
        self._known_faces.clear()

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        for img_file in self.known_faces_dir.iterdir():
            if img_file.suffix.lower() not in valid_exts:
                continue
            name = img_file.stem.replace("_", " ").title()
            try:
                img = cv2.imread(str(img_file))
                if img is None:
                    continue
                embedding = self.extract_embedding_from_image(img)
                if embedding is not None:
                    self._known_faces[name] = embedding
                    logger.info("Personel terdaftar dimuat: %s (%s)", name, img_file.name)
            except Exception as exc:
                logger.warning("Gagal memuat wajah dari %s: %s", img_file, exc)

    def extract_embedding_from_image(self, image: np.ndarray) -> np.ndarray | None:
        """Detect the largest face in an image and return its 128-d embedding."""
        if not self.enabled or self._detector is None or self._recognizer is None:
            return None
        if image is None or image.size == 0:
            return None

        h, w = image.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(image)

        if faces is None or len(faces) == 0:
            return None

        # Choose largest face by bounding box area
        best_face = max(faces, key=lambda f: float(f[2] * f[3]))
        aligned = self._recognizer.alignCrop(image, best_face)
        feature = self._recognizer.feature(aligned)
        return feature.copy()

    def identify_person(
        self,
        frame: np.ndarray,
        person_box: tuple[int, int, int, int],
        keypoints: dict[int, tuple[float, float]] | None = None,
    ) -> tuple[str, float, tuple[int, int, int, int] | None]:
        """Identify a person within their bounding box / head keypoints.

        Returns:
            (name_or_id, confidence, face_box_xywh_in_frame)
        """
        if not self.enabled or self._detector is None or self._recognizer is None:
            return "Person", 0.0, None
        if frame is None or frame.size == 0:
            return "Person", 0.0, None

        fh, fw = frame.shape[:2]
        px, py, pw, ph = person_box

        # Extract head/upper region crop
        cx1 = max(0, px - int(pw * 0.1))
        cy1 = max(0, py - int(ph * 0.05))
        cx2 = min(fw, px + pw + int(pw * 0.1))
        cy2 = min(fh, py + int(ph * 0.55))

        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0 or crop.shape[0] < 30 or crop.shape[1] < 30:
            return "Person", 0.0, None

        ch, cw = crop.shape[:2]
        self._detector.setInputSize((cw, ch))
        _, faces = self._detector.detect(crop)

        if faces is None or len(faces) == 0:
            return "Person", 0.0, None

        # Target head center based on keypoints or person geometry
        if keypoints and any(k in keypoints for k in (0, 1, 2, 3, 4)):
            head_pts = [keypoints[k] for k in (0, 1, 2, 3, 4) if k in keypoints]
            target_hx = sum(p[0] for p in head_pts) / len(head_pts)
            target_hy = sum(p[1] for p in head_pts) / len(head_pts)
        else:
            target_hx = px + pw * 0.5
            target_hy = py + ph * 0.25

        valid_faces = [f for f in faces if float(f[-1]) >= 0.50]
        if not valid_faces:
            return "Person", 0.0, None

        def face_score(f: Any) -> float:
            fx, fy, f_w, f_h = f[0:4]
            fcx = cx1 + fx + f_w / 2
            fcy = cy1 + fy + f_h / 2
            dist = float(np.hypot(fcx - target_hx, fcy - target_hy))
            return dist - float(f[-1]) * 40.0

        best_face = min(valid_faces, key=face_score)
        fx, fy, f_w, f_h = best_face[0:4].astype(int)
        global_face_box = (cx1 + fx, cy1 + fy, f_w, f_h)

        aligned = self._recognizer.alignCrop(crop, best_face)
        feature = self._recognizer.feature(aligned)

        # 1. Match against Known Gallery (Registered Personnel)
        best_known_name = None
        best_known_score = -1.0
        for name, known_feat in self._known_faces.items():
            score = float(self._recognizer.match(feature, known_feat, cv2.FaceRecognizerSF_FR_COSINE))
            if score > best_known_score:
                best_known_score = score
                best_known_name = name

        if best_known_name is not None and best_known_score >= self.similarity_threshold:
            return best_known_name, best_known_score, global_face_box

        # 2. Match against Active Session Gallery (Anti-Double-Counting for Unregistered Persons)
        best_session_id = None
        best_session_score = -1.0
        for sid, sdata in self._session_faces.items():
            score = float(self._recognizer.match(feature, sdata["feature"], cv2.FaceRecognizerSF_FR_COSINE))
            if score > best_session_score:
                best_session_score = score
                best_session_id = sid

        if best_session_id is not None and best_session_score >= self.similarity_threshold:
            return f"Person #{best_session_id}", best_session_score, global_face_box

        # 3. New Session Person Registration
        new_sid = self._next_session_id
        self._next_session_id += 1
        self._session_faces[new_sid] = {
            "feature": feature.copy(),
            "id": new_sid,
        }
        return f"Person #{new_sid}", 1.0, global_face_box

    def register_face(self, name: str, image_data: bytes | np.ndarray) -> bool:
        """Register a new person in the known faces gallery."""
        if isinstance(image_data, bytes):
            arr = np.asarray(bytearray(image_data), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            img = image_data

        if img is None:
            return False

        embedding = self.extract_embedding_from_image(img)
        if embedding is None:
            return False

        clean_name = name.strip()
        filename = f"{clean_name.replace(' ', '_')}.jpg"
        save_path = self.known_faces_dir / filename
        cv2.imwrite(str(save_path), img)

        formatted_name = clean_name.replace("_", " ").title()
        self._known_faces[formatted_name] = embedding
        logger.info("Personel baru berhasil didaftarkan: %s", formatted_name)
        return True

    def list_registered_faces(self) -> list[str]:
        """Return a list of all registered personnel names."""
        return sorted(list(self._known_faces.keys()))

    def delete_face(self, name: str) -> bool:
        """Delete a registered person from database and disk."""
        clean_name = name.strip()
        formatted_name = clean_name.replace("_", " ").title()
        if formatted_name in self._known_faces:
            del self._known_faces[formatted_name]
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        deleted = False
        for img_file in self.known_faces_dir.iterdir():
            if img_file.suffix.lower() in valid_exts:
                if img_file.stem.replace("_", " ").title() == formatted_name:
                    try:
                        img_file.unlink()
                        deleted = True
                    except Exception:
                        pass
        return deleted or (formatted_name in self._known_faces)
