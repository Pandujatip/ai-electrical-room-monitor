from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any
import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

logger = logging.getLogger("imou-ptz")


class PTZController:
    """Controls PTZ rotation (Pan, Tilt, Zoom, Auto-Scan 360, Presets) for Imou & Dahua cameras."""

    def __init__(self, rtsp_url: str = "") -> None:
        self.ip, self.user, self.password, self.port = self._parse_rtsp(rtsp_url)

    def _parse_rtsp(self, rtsp_url: str) -> tuple[str, str, str, int]:
        """Extract IP, username, and password from RTSP URL."""
        if not rtsp_url or not str(rtsp_url).startswith(("rtsp://", "rtsps://")):
            return "", "admin", "", 80
        try:
            parsed = urllib.parse.urlparse(rtsp_url)
            user = parsed.username or "admin"
            password = parsed.password or ""
            ip = parsed.hostname or "192.168.1.108"
            return ip, user, password, 80
        except Exception as exc:
            logger.warning("Gagal parse RTSP URL: %s", exc)
            return "", "admin", "", 80

    def update_credentials(self, rtsp_url: str) -> None:
        self.ip, self.user, self.password, self.port = self._parse_rtsp(rtsp_url)

    def _send_cgi(self, params: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
        if not self.ip:
            return {"ok": False, "error": "IP Kamera PTZ belum diatur"}

        url = f"http://{self.ip}:{self.port}/cgi-bin/ptz.cgi"
        try:
            auth = HTTPDigestAuth(self.user, self.password)
            resp = requests.get(url, params=params, auth=auth, timeout=timeout)
            if resp.status_code == 401:
                # Fallback to basic auth if digest is rejected
                resp = requests.get(url, params=params, auth=HTTPBasicAuth(self.user, self.password), timeout=timeout)
            
            if resp.status_code == 200 and "OK" in resp.text.upper():
                return {"ok": True, "response": resp.text.strip()}
            return {"ok": resp.status_code == 200, "status_code": resp.status_code, "response": resp.text.strip()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def move(self, direction: str, speed: int = 5) -> dict[str, Any]:
        """Move camera: 'up', 'down', 'left', 'right', 'leftup', 'rightup', 'leftdown', 'rightdown', or 'stop'."""
        d = direction.strip().lower()
        speed = max(1, min(8, int(speed)))

        code_map = {
            "up": ("Up", 0, speed, 0),
            "down": ("Down", 0, speed, 0),
            "left": ("Left", speed, 0, 0),
            "right": ("Right", speed, 0, 0),
            "leftup": ("LeftUp", speed, speed, 0),
            "rightup": ("RightUp", speed, speed, 0),
            "leftdown": ("LeftDown", speed, speed, 0),
            "rightdown": ("RightDown", speed, speed, 0),
            "stop": ("Up", 0, 0, 0),
        }

        if d not in code_map:
            return {"ok": False, "error": f"Arah tidak valid: {direction}"}

        code, arg1, arg2, arg3 = code_map[d]
        action = "stop" if d == "stop" else "start"
        params = {
            "action": action,
            "channel": 1,
            "code": code,
            "arg1": arg1,
            "arg2": arg2,
            "arg3": arg3,
        }
        return self._send_cgi(params)

    def continuous_scan_360(self, action: str = "start") -> dict[str, Any]:
        """Start or stop 360-degree horizontal continuous tour scan."""
        act = "start" if action.lower() == "start" else "stop"
        params = {
            "action": act,
            "channel": 1,
            "code": "AutoScan",
            "arg1": 0,
            "arg2": 0,
            "arg3": 0,
        }
        return self._send_cgi(params)

    def goto_preset(self, preset_id: int = 1) -> dict[str, Any]:
        """Move camera to a saved preset position (e.g. Preset 1 = Door / Home)."""
        params = {
            "action": "start",
            "channel": 1,
            "code": "GotoPreset",
            "arg1": 0,
            "arg2": int(preset_id),
            "arg3": 0,
        }
        return self._send_cgi(params)

    def set_preset(self, preset_id: int = 1) -> dict[str, Any]:
        """Save current camera position as a preset."""
        params = {
            "action": "start",
            "channel": 1,
            "code": "SetPreset",
            "arg1": 0,
            "arg2": int(preset_id),
            "arg3": 0,
        }
        return self._send_cgi(params)
