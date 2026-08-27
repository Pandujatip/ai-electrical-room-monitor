from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from notifier import NotificationManager


class NotifierTests(unittest.TestCase):
    def setUp(self):
        self.mgr = NotificationManager(bridge_url="http://127.0.0.1:3001")
        self.mgr.settings = {
            "whatsapp_enabled": True,
            "whatsapp_target": "6281234567890",
            "alert_ppe_violation_enabled": True,
            "alert_ppe_violation_seconds": 60,
            "alert_fall_emergency_enabled": True,
            "alert_er_activity_enabled": True,
            "alert_er_activity_seconds": 300,
            "alert_cooldown_seconds": 60,
        }

    def test_save_and_load_settings(self):
        saved = self.mgr.save_settings({"voice_alarm_enabled": False, "whatsapp_target": "628999999"})
        self.assertFalse(saved["voice_alarm_enabled"])
        self.assertEqual(saved["whatsapp_target"], "628999999")

    @patch.object(NotificationManager, "dispatch_alert")
    def test_ppe_violation_at_60s_triggers_alert(self, mock_dispatch):
        tracks = [
            {
                "id": 1,
                "name": "Pandu",
                "stay_seconds": 65,
                "helmet": "MISSING",
                "vest": "OK",
                "posture": "STANDING",
                "lying_seconds": 0,
            }
        ]
        self.mgr.process_tracks_and_alerts(tracks)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "ppe_violation_pandu")

    @patch.object(NotificationManager, "dispatch_alert")
    def test_fall_emergency_triggers_alert(self, mock_dispatch):
        tracks = [
            {
                "id": 2,
                "name": "Teknisi",
                "stay_seconds": 20,
                "helmet": "OK",
                "vest": "OK",
                "posture": "FALLEN",
                "lying_seconds": 5,
            }
        ]
        self.mgr.process_tracks_and_alerts(tracks)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "fall_emergency_teknisi")

    @patch.object(NotificationManager, "dispatch_alert")
    def test_overstay_at_300s_triggers_alert(self, mock_dispatch):
        tracks = [
            {
                "id": 3,
                "name": "Worker",
                "stay_seconds": 310,
                "helmet": "OK",
                "vest": "OK",
                "posture": "STANDING",
                "lying_seconds": 0,
            }
        ]
        self.mgr.process_tracks_and_alerts(tracks)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "er_overstay_worker")


    @patch.object(NotificationManager, "dispatch_alert")
    def test_camera_offline_and_recovery_alert(self, mock_dispatch):
        # 1. Trigger camera offline alert
        self.mgr.notify_camera_status(connected=False, room_name="Electrical Room 17", error_msg="RTSP disconnect")
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "cam_offline_electricalroom17")

        # 2. Trigger camera online recovery
        mock_dispatch.reset_mock()
        self.mgr.notify_camera_status(connected=True, room_name="Electrical Room 17")
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key") or args[0], "cam_online_electricalroom17")


if __name__ == "__main__":
    unittest.main()
