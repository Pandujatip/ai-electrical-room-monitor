from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger("imou-audio")


class VoiceAlarm:
    """Manages audio voice warnings with cooldown."""

    def __init__(
        self,
        audio_file: str | Path = "static/audio/warning_female.mp3",
        cooldown_seconds: float = 40.0,
        enabled: bool = True,
    ) -> None:
        self.audio_file = Path(audio_file)
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled
        self._last_played_time = 0.0
        self._lock = threading.Lock()

    def trigger(self, reason: str = "") -> bool:
        """Trigger playback if cooldown has elapsed. Non-blocking."""
        if not self.enabled:
            return False
        now = time.monotonic()
        with self._lock:
            if now - self._last_played_time < self.cooldown_seconds:
                return False
            self._last_played_time = now

        def _play_worker() -> None:
            try:
                resolved_path = str(self.audio_file.resolve()).replace("/", "\\")
                ps_script = (
                    "Add-Type -AssemblyName presentationCore; "
                    "$p = New-Object System.Windows.Media.MediaPlayer; "
                    f"$p.Open([System.Uri]'{resolved_path}'); "
                    "$p.Play(); "
                    "Start-Sleep -Seconds 5; "
                    "$p.Close()"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as exc:
                logger.warning("Voice alarm playback failed: %s", exc)

        t = threading.Thread(target=_play_worker, name="voice-alarm-worker", daemon=True)
        t.start()
        logger.info("Voice alarm triggered: %s", reason)
        return True

    def trigger_custom(
        self,
        audio_file: str | Path,
        reason: str = "",
        cooldown: float = 30.0,
    ) -> bool:
        """Trigger playback of custom audio with independent cooldown."""
        if not self.enabled:
            return False
        now = time.monotonic()
        key = str(audio_file)
        with self._lock:
            if not hasattr(self, "_custom_last_times"):
                self._custom_last_times: dict[str, float] = {}
            if now - self._custom_last_times.get(key, 0.0) < cooldown:
                return False
            self._custom_last_times[key] = now

        def _play_worker() -> None:
            try:
                resolved_path = str(Path(audio_file).resolve()).replace("/", "\\")
                ps_script = (
                    "Add-Type -AssemblyName presentationCore; "
                    "$p = New-Object System.Windows.Media.MediaPlayer; "
                    f"$p.Open([System.Uri]'{resolved_path}'); "
                    "$p.Play(); "
                    "Start-Sleep -Seconds 5; "
                    "$p.Close()"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as exc:
                logger.warning("Custom voice alarm playback failed: %s", exc)

        t = threading.Thread(target=_play_worker, name=f"voice-alarm-{reason}", daemon=True)
        t.start()
        logger.info("Custom voice alarm triggered: %s (%s)", reason, audio_file)
        return True

