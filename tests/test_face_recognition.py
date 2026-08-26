from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from faces import FaceManager


class TestFaceRecognition(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.yunet_path = Path("models/face_detection_yunet_2023mar.onnx")
        self.sface_path = Path("models/face_recognition_sface_2021dec.onnx")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        if not self.yunet_path.exists() or not self.sface_path.exists():
            self.skipTest("Face models not present")
        manager = FaceManager(
            yunet_model_path=self.yunet_path,
            sface_model_path=self.sface_path,
            known_faces_dir=self.temp_dir,
            enabled=True,
        )
        self.assertTrue(manager.enabled)
        self.assertEqual(manager.list_registered_faces(), [])

    def test_registration_and_matching(self):
        if not self.yunet_path.exists() or not self.sface_path.exists():
            self.skipTest("Face models not present")

        img_path = Path(".user_uploaded/media_1787728462117.jpg")
        if not img_path.exists():
            img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787728462117.jpg")
        if not img_path.exists():
            self.skipTest("Sample test image not present")

        img = cv2.imread(str(img_path))
        manager = FaceManager(
            yunet_model_path=self.yunet_path,
            sface_model_path=self.sface_path,
            known_faces_dir=self.temp_dir,
            enabled=True,
        )

        # 1. Register face as "Budi Santoso"
        success = manager.register_face("Budi Santoso", img)
        self.assertTrue(success)
        self.assertIn("Budi Santoso", manager.list_registered_faces())

        # 2. Identify person in full image
        h, w = img.shape[:2]
        person_box = (100, 100, w - 200, h - 200)
        name, conf, face_box = manager.identify_person(img, person_box)
        self.assertEqual(name, "Budi Santoso")
        self.assertGreaterEqual(conf, 0.363)
        self.assertIsNotNone(face_box)

    def test_anti_double_counting_session_locking(self):
        if not self.yunet_path.exists() or not self.sface_path.exists():
            self.skipTest("Face models not present")

        img_path = Path(".user_uploaded/media_1787728462117.jpg")
        if not img_path.exists():
            img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787728462117.jpg")
        if not img_path.exists():
            self.skipTest("Sample test image not present")

        img = cv2.imread(str(img_path))
        manager = FaceManager(
            yunet_model_path=self.yunet_path,
            sface_model_path=self.sface_path,
            known_faces_dir=self.temp_dir,
            enabled=True,
        )

        h, w = img.shape[:2]
        person_box = (100, 100, w - 200, h - 200)

        # First entry: locks as Person #1
        name1, conf1, _ = manager.identify_person(img, person_box)
        self.assertEqual(name1, "Person #1")

        # Second entry (e.g. after leaving and re-entering): must lock onto the exact same Person #1
        name2, conf2, _ = manager.identify_person(img, person_box)
        self.assertEqual(name2, "Person #1")
        self.assertGreaterEqual(conf2, 0.363)


if __name__ == "__main__":
    unittest.main()
