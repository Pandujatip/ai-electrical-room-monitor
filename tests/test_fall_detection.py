from __future__ import annotations

import unittest
from detector import analyze_posture


class TestFallDetection(unittest.TestCase):
    def test_sitting_upright_in_front_of_webcam(self):
        # User sitting case: upper body crop w=410, h=297 (w > h)
        # Head is on top (y=150), shoulders lower (y=280)
        box = (389, 61, 410, 297)
        kps = {
            0: (592.5, 157.6),
            1: (614.6, 136.7),
            2: (565.9, 139.2),
            5: (711.2, 273.3),
            6: (460.2, 289.5),
        }
        posture, angle, is_lying = analyze_posture(box, kps)
        self.assertIn(posture, {"SITTING", "STANDING"})
        self.assertFalse(is_lying)
        self.assertGreater(angle, 70.0)

    def test_standing_pose_full_body(self):
        box = (100, 100, 150, 400)
        kps = {
            0: (170.0, 110.0),
            5: (140.0, 150.0),
            6: (200.0, 150.0),
            11: (150.0, 260.0),
            12: (190.0, 260.0),
        }
        posture, angle, is_lying = analyze_posture(box, kps)
        self.assertEqual(posture, "STANDING")
        self.assertFalse(is_lying)

    def test_fallen_horizontal_pose(self):
        # Real fall: horizontal on floor
        box = (100, 300, 420, 160)
        kps = {
            0: (120.0, 360.0),
            5: (200.0, 365.0),
            6: (200.0, 380.0),
            11: (380.0, 370.0),
            12: (380.0, 385.0),
        }
        posture, angle, is_lying = analyze_posture(box, kps)
        self.assertEqual(posture, "FALLEN")
        self.assertTrue(is_lying)
        self.assertLess(angle, 35.0)

    def test_bending_pose(self):
        box = (100, 100, 200, 300)
        kps = {
            0: (160.0, 120.0),
            5: (140.0, 150.0),
            6: (180.0, 150.0),
            11: (200.0, 200.0),
            12: (220.0, 200.0),
        }
        posture, angle, is_lying = analyze_posture(box, kps)
        self.assertEqual(posture, "BENDING")
        self.assertFalse(is_lying)


if __name__ == "__main__":
    unittest.main()
