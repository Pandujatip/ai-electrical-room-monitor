from __future__ import annotations

import unittest

from config import Settings
from detector import associate_ppe, ppe_confidence_threshold, suppress_duplicate_people


class DuplicateSuppressionTests(unittest.TestCase):
    def test_nested_partial_person_is_suppressed(self) -> None:
        detections = [
            {"id": 1, "box": (100, 50, 300, 500), "confidence": 0.91},
            {"id": 2, "box": (180, 100, 130, 260), "confidence": 0.82},
        ]
        result = suppress_duplicate_people(detections, 0.55)
        self.assertEqual([item["id"] for item in result], [1])

    def test_separate_people_are_retained(self) -> None:
        detections = [
            {"id": 1, "box": (10, 10, 100, 300), "confidence": 0.90},
            {"id": 2, "box": (180, 10, 100, 300), "confidence": 0.88},
        ]
        result = suppress_duplicate_people(detections, 0.55)
        self.assertEqual({item["id"] for item in result}, {1, 2})


class PPEAssociationTests(unittest.TestCase):
    def test_helmet_and_vest_are_associated_by_region(self) -> None:
        detections = [
            {"box": (125, 60, 45, 35), "label": "Helmet", "normalized_label": "helmet", "confidence": 0.87},
            {"box": (115, 180, 80, 100), "label": "Safety Vest", "normalized_label": "safety_vest", "confidence": 0.84},
        ]
        helmet, vest, matched = associate_ppe((100, 50, 120, 400), detections)
        self.assertEqual(helmet, "OK")
        self.assertEqual(vest, "OK")
        self.assertEqual(len(matched), 2)

    def test_explicit_missing_labels_produce_violation(self) -> None:
        detections = [
            {"box": (125, 60, 45, 35), "label": "No Helmet", "normalized_label": "no_helmet", "confidence": 0.91},
            {"box": (115, 180, 80, 100), "label": "NO-Safety Vest", "normalized_label": "no_safety_vest", "confidence": 0.89},
        ]
        helmet, vest, _ = associate_ppe((100, 50, 120, 400), detections)
        self.assertEqual(helmet, "MISSING")
        self.assertEqual(vest, "MISSING")

    def test_side_profile_pose_associates_helmet_and_vest(self) -> None:
        # Person facing sideways (profile view)
        import numpy as np
        kps = np.zeros((17, 3))
        kps[0] = [230, 95, 0.90]   # Nose
        kps[2] = [220, 90, 0.92]   # Right Eye
        kps[4] = [205, 90, 0.88]   # Right Ear
        kps[6] = [200, 160, 0.95]  # Right Shoulder
        kps[12] = [195, 290, 0.90] # Right Hip

        person_box = (150, 50, 110, 400)
        detections = [
            {"box": (200, 65, 45, 40), "label": "Helmet", "normalized_label": "helmet", "confidence": 0.88},
            {"box": (170, 140, 70, 140), "label": "Safety Vest", "normalized_label": "safety_vest", "confidence": 0.85},
        ]
        helmet, vest, matched = associate_ppe(person_box, detections, keypoints=kps)
        self.assertEqual(helmet, "OK")
        self.assertEqual(vest, "OK")
        self.assertEqual(len(matched), 2)

    def test_bent_over_posture_associates_helmet_and_vest(self) -> None:
        # Person bending forward inspecting a panel (wide box, head at front-left)
        import numpy as np
        kps = np.zeros((17, 3))
        kps[0] = [80, 120, 0.90]   # Nose
        kps[1] = [90, 110, 0.90]   # L Eye
        kps[5] = [130, 130, 0.92]  # L Shoulder
        kps[6] = [140, 160, 0.85]  # R Shoulder
        kps[11] = [230, 170, 0.88] # L Hip
        kps[12] = [240, 200, 0.86] # R Hip

        person_box = (60, 80, 220, 180) # Aspect ratio = 220/180 = 1.22 (Bending)
        detections = [
            {"box": (70, 95, 40, 35), "label": "Helmet", "normalized_label": "helmet", "confidence": 0.89},
            {"box": (115, 120, 80, 70), "label": "Safety Vest", "normalized_label": "safety_vest", "confidence": 0.86},
        ]
        helmet, vest, matched = associate_ppe(person_box, detections, keypoints=kps)
        self.assertEqual(helmet, "OK")
        self.assertEqual(vest, "OK")
        self.assertEqual(len(matched), 2)

    def test_back_view_with_shoulder_guidance(self) -> None:
        # Person facing away from camera (head keypoints hidden, shoulders visible)
        import numpy as np
        kps = np.zeros((17, 3))
        kps[5] = [120, 130, 0.90] # L Shoulder
        kps[6] = [180, 130, 0.90] # R Shoulder
        kps[11] = [130, 250, 0.88] # L Hip
        kps[12] = [170, 250, 0.88] # R Hip

        person_box = (100, 60, 100, 350)
        detections = [
            {"box": (130, 70, 45, 40), "label": "Helmet", "normalized_label": "helmet", "confidence": 0.88},
            {"box": (115, 125, 75, 110), "label": "Safety Vest", "normalized_label": "safety_vest", "confidence": 0.87},
        ]
        helmet, vest, matched = associate_ppe(person_box, detections, keypoints=kps)
        self.assertEqual(helmet, "OK")
        self.assertEqual(vest, "OK")
        self.assertEqual(len(matched), 2)

    def test_unmatched_ppe_is_unknown_not_violation(self) -> None:
        helmet, vest, _ = associate_ppe((100, 50, 120, 400), [])
        self.assertEqual(helmet, "UNKNOWN")
        self.assertEqual(vest, "UNKNOWN")


class PPEThresholdTests(unittest.TestCase):
    def test_positive_and_negative_classes_have_independent_thresholds(self) -> None:
        settings = Settings()
        self.assertEqual(
            ppe_confidence_threshold(settings, "helmet"),
            settings.ppe_helmet_ok_confidence,
        )
        self.assertEqual(
            ppe_confidence_threshold(settings, "no_safety_vest"),
            settings.ppe_vest_missing_confidence,
        )

    def test_green_safety_wearpack_from_real_image(self) -> None:
        from pathlib import Path
        import cv2
        img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787746613113.jpg")
        if not img_path.exists():
            self.skipTest("Green wearpack test image not found")
        from storage import EventStore
        from detector import PersonMonitor
        monitor = PersonMonitor(Settings(), EventStore(Path("events.db")))
        img = cv2.imread(str(img_path))
        people = monitor._detect_and_track_people(img)
        ppe_items = monitor._detect_ppe(img)
        self.assertGreaterEqual(len(people), 1)
        h_stat, v_stat, matched = associate_ppe(people[0]["box"], ppe_items, keypoints=people[0].get("keypoints"))
        self.assertEqual(h_stat, "OK")
        self.assertEqual(v_stat, "OK")

    def test_hand_over_chest_casual_shirt_does_not_trigger_vest_ok(self) -> None:
        from pathlib import Path
        import cv2
        img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787747384610.png")
        if not img_path.exists():
            self.skipTest("Hand over chest test image not found")
        from storage import EventStore
        from detector import PersonMonitor
        monitor = PersonMonitor(Settings(), EventStore(Path("events.db")))
        img = cv2.imread(str(img_path))
        people = monitor._detect_and_track_people(img)
        ppe_items = monitor._detect_ppe(img)
        self.assertGreaterEqual(len(people), 1)
        h_stat, v_stat, matched = associate_ppe(people[0]["box"], ppe_items, keypoints=people[0].get("keypoints"))
        self.assertIn(h_stat, {"MISSING", "UNKNOWN"})
        self.assertEqual(v_stat, "MISSING")


if __name__ == "__main__":
    unittest.main()
