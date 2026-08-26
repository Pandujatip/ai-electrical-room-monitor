from __future__ import annotations

import unittest
from unittest.mock import patch
from detector import analyze_smoking_gesture
from notifier import NotificationManager


class SmokingDetectionTests(unittest.TestCase):
    def test_smoking_gesture_detected(self):
        # Head box: w=200, h=400
        box = (100, 80, 200, 400)
        # Left wrist right near mouth
        kps = {
            0: (200.0, 150.0),  # Nose
            1: (215.0, 135.0),  # L Eye
            2: (185.0, 135.0),  # R Eye
            9: (205.0, 160.0),  # L Wrist at mouth!
            10: (120.0, 300.0), # R Wrist down
        }
        is_near, dist = analyze_smoking_gesture(box, kps)
        self.assertTrue(is_near)
        self.assertLess(dist, 0.70)

    def test_normal_standing_no_smoking(self):
        box = (100, 80, 200, 400)
        kps = {
            0: (200.0, 150.0),
            1: (215.0, 135.0),
            2: (185.0, 135.0),
            9: (280.0, 320.0),  # L Wrist at side
            10: (120.0, 320.0), # R Wrist at side
        }
        is_near, dist = analyze_smoking_gesture(box, kps)
        self.assertFalse(is_near)
        self.assertTrue(dist is None or dist > 1.0)

    def test_hand_scratching_forehead_rejected(self):
        box = (100, 80, 200, 400)
        # Hand way up at top of forehead/hair (y=90, while nose is at y=150)
        kps = {
            0: (200.0, 150.0),
            1: (215.0, 135.0),
            2: (185.0, 135.0),
            9: (200.0, 90.0),   # Wrist above eyes
            10: (120.0, 320.0),
        }
        is_near, dist = analyze_smoking_gesture(box, kps)
        self.assertFalse(is_near)

    @patch.object(NotificationManager, "dispatch_alert")
    def test_notifier_smoking_alert_dispatched(self, mock_dispatch):
        mgr = NotificationManager(bridge_url="http://127.0.0.1:3001")
        mgr.settings = {
            "whatsapp_enabled": True,
            "whatsapp_target": "6281234567890",
            "alert_smoking_enabled": True,
            "alert_cooldown_seconds": 3600,
        }
        tracks = [
            {
                "id": 1,
                "name": "Pandu",
                "stay_seconds": 15,
                "helmet": "OK",
                "vest": "OK",
                "posture": "STANDING",
                "lying_seconds": 0,
                "is_smoking": True,
                "smoking_seconds": 3,
            }
        ]
        self.mgr = mgr
        mgr.process_tracks_and_alerts(tracks)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "smoking_pandu")

    def test_real_user_cigarette_image_triggers_smoking(self):
        import cv2
        from pathlib import Path
        from ultralytics import YOLO
        img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787748463284.png")
        if not img_path.exists():
            self.skipTest("Cigarette image not found")
        pose = YOLO("models/yolo11n-pose.pt")
        img = cv2.imread(str(img_path))
        res = pose.predict(img, verbose=False)[0]
        kps = {int(i): (float(x), float(y)) for i, (x, y) in enumerate(res.keypoints.xy.cpu().numpy()[0]) if res.keypoints.conf.cpu().numpy()[0][i] > 0.2}
        box = (76, 16, 823, 570)
        is_smoking, dist = analyze_smoking_gesture(box, kps)
        self.assertTrue(is_smoking)

    def test_real_user_hand_on_chest_does_not_trigger_smoking(self):
        import cv2
        from pathlib import Path
        from ultralytics import YOLO
        img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787747384610.png")
        if not img_path.exists():
            self.skipTest("Chest image not found")
        pose = YOLO("models/yolo11n-pose.pt")
        img = cv2.imread(str(img_path))
        res = pose.predict(img, verbose=False)[0]
        kps = {int(i): (float(x), float(y)) for i, (x, y) in enumerate(res.keypoints.xy.cpu().numpy()[0]) if res.keypoints.conf.cpu().numpy()[0][i] > 0.2}
        box = (100, 50, 400, 600)
        is_smoking, dist = analyze_smoking_gesture(box, kps)
        self.assertFalse(is_smoking)


    def test_real_user_cigarette_image_2_triggers_smoking(self):
        import cv2
        from pathlib import Path
        from ultralytics import YOLO
        img_path = Path("C:/Users/tigal/.gemini/antigravity/brain/db3941c9-719c-4654-907f-1bce61498615/.user_uploaded/media_1787748746228.png")
        if not img_path.exists():
            self.skipTest("Cigarette image 2 not found")
        pose = YOLO("models/yolo11n-pose.pt")
        img = cv2.imread(str(img_path))
        res = pose.predict(img, verbose=False)[0]
        kps = {int(i): (float(x), float(y)) for i, (x, y) in enumerate(res.keypoints.xy.cpu().numpy()[0]) if res.keypoints.conf.cpu().numpy()[0][i] > 0.2}
        box = (223, 72, 480, 470)
        is_smoking, dist = analyze_smoking_gesture(box, kps, frame=img)
        self.assertTrue(is_smoking)


if __name__ == "__main__":
    unittest.main()
