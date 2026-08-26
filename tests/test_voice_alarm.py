from __future__ import annotations

import unittest
from pathlib import Path

from audio import VoiceAlarm


class TestVoiceAlarm(unittest.TestCase):
    def test_voice_alarm_initialization(self):
        audio_file = Path("static/audio/warning_female.mp3")
        alarm = VoiceAlarm(audio_file=audio_file, cooldown_seconds=10.0, enabled=True)
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.cooldown_seconds, 10.0)

    def test_voice_alarm_cooldown(self):
        audio_file = Path("static/audio/warning_female.mp3")
        alarm = VoiceAlarm(audio_file=audio_file, cooldown_seconds=5.0, enabled=True)
        # First trigger should return True
        res1 = alarm.trigger("Test 1")
        self.assertTrue(res1)
        # Immediate second trigger should be throttled (return False)
        res2 = alarm.trigger("Test 2")
        self.assertFalse(res2)

    def test_voice_alarm_disabled(self):
        audio_file = Path("static/audio/warning_female.mp3")
        alarm = VoiceAlarm(audio_file=audio_file, cooldown_seconds=5.0, enabled=False)
        self.assertFalse(alarm.trigger("Disabled test"))


if __name__ == "__main__":
    unittest.main()
