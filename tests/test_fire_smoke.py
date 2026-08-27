from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import numpy as np

from config import Settings
from detector import PersonMonitor
from notifier import NotificationManager
from storage import EventStore


class FireSmokeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "test_events.db"
        self.settings = Settings(
            rtsp_url="0",
            fire_detection_enabled=True,
            fire_confidence=0.35,
            smoke_confidence=0.35,
            fire_debounce_seconds=0.1,
            smoke_emergency_debounce_seconds=0.1,
            db_path=self.db_path,
        )
        self.store = EventStore(self.db_path)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_fire_model_loaded_and_detects_structure(self):
        monitor = PersonMonitor(self.settings, self.store)
        self.assertIsNotNone(monitor._fire_model)
        self.assertIn("fire", monitor._fire_model.names.values())
        self.assertIn("smoke", monitor._fire_model.names.values())

    def test_fire_state_update_triggers_emergency_event(self):
        monitor = PersonMonitor(self.settings, self.store)
        mock_fire_detections = [
            {"box": (100, 100, 80, 80), "label": "fire", "confidence": 0.88}
        ]
        monitor._update_fire_states(mock_fire_detections)
        self.assertIsNotNone(monitor._fire_first_seen)
        
        import time
        time.sleep(0.15)
        monitor._update_fire_states(mock_fire_detections)
        self.assertTrue(monitor._fire_detected)
        self.assertTrue(monitor._fire_alert_triggered)

        events = self.store.recent(10)
        self.assertTrue(any(e["status"] == "FIRE_EMERGENCY" for e in events))

    def test_smoke_state_update_triggers_emergency_event(self):
        monitor = PersonMonitor(self.settings, self.store)
        mock_smoke_detections = [
            {"box": (50, 50, 200, 150), "label": "smoke", "confidence": 0.75}
        ]
        monitor._update_fire_states(mock_smoke_detections)
        import time
        time.sleep(0.15)
        monitor._update_fire_states(mock_smoke_detections)
        self.assertTrue(monitor._smoke_emergency_detected)
        self.assertTrue(monitor._smoke_alert_triggered)

        events = self.store.recent(10)
        self.assertTrue(any(e["status"] == "THICK_SMOKE_EMERGENCY" for e in events))

    @patch.object(NotificationManager, "dispatch_alert")
    def test_notifier_fire_emergency_alert_dispatched(self, mock_dispatch):
        mgr = NotificationManager(bridge_url="http://127.0.0.1:3001")
        mgr.settings = {
            "whatsapp_enabled": True,
            "whatsapp_target": "6281234567890",
            "alert_fire_emergency_enabled": True,
        }
        mgr.notify_fire_emergency("Electrical Room 17", confidence=0.92)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key"), "fire_emergency_electricalroom17")
        self.assertTrue(kwargs.get("force"))

    @patch.object(NotificationManager, "dispatch_alert")
    def test_notifier_smoke_emergency_alert_dispatched(self, mock_dispatch):
        mgr = NotificationManager(bridge_url="http://127.0.0.1:3001")
        mgr.settings = {
            "whatsapp_enabled": True,
            "whatsapp_target": "6281234567890",
            "alert_smoke_emergency_enabled": True,
        }
        mgr.notify_smoke_emergency("Electrical Room 17", confidence=0.85)
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(kwargs.get("alert_key"), "smoke_emergency_electricalroom17")
        self.assertTrue(kwargs.get("force"))


if __name__ == "__main__":
    unittest.main()
