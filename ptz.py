from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any
import requests

logger = logging.getLogger("imou-ptz")


class PTZController:
    """High-performance ONVIF SOAP PTZ Controller for Imou Cruiser and Dahua cameras."""

    def __init__(self, rtsp_url: str = "") -> None:
        self.ip, self.user, self.password, self.port = self._parse_rtsp(rtsp_url)
        self.profile_token = "Profile000"
        self._session = requests.Session()

    def _parse_rtsp(self, rtsp_url: str) -> tuple[str, str, str, int]:
        """Extract IP, username, and password from RTSP URL."""
        if not rtsp_url or not str(rtsp_url).startswith(("rtsp://", "rtsps://")):
            return "", "admin", "", 80
        try:
            parsed = urllib.parse.urlparse(rtsp_url)
            user = parsed.username or "admin"
            password = parsed.password or ""
            ip = parsed.hostname or "192.168.1.2"
            return ip, user, password, 80
        except Exception as exc:
            logger.warning("Gagal parse RTSP URL: %s", exc)
            return "", "admin", "", 80

    def update_credentials(self, rtsp_url: str) -> None:
        self.ip, self.user, self.password, self.port = self._parse_rtsp(rtsp_url)

    def _create_wsse_header(self) -> str:
        """Create ONVIF WS-Security UsernameToken Digest."""
        nonce_raw = os.urandom(16)
        nonce_b64 = base64.b64encode(nonce_raw).decode("ascii")
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        raw_digest = hashlib.sha1(nonce_raw + created.encode("utf-8") + self.password.encode("utf-8")).digest()
        digest_b64 = base64.b64encode(raw_digest).decode("ascii")
        return (
            f'<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" '
            f'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
            f'<wsse:UsernameToken>'
            f'<wsse:Username>{self.user}</wsse:Username>'
            f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest_b64}</wsse:Password>'
            f'<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>'
            f'<wsu:Created>{created}</wsu:Created>'
            f'</wsse:UsernameToken>'
            f'</wsse:Security>'
        )

    def _send_soap(self, service_path: str, body_xml: str, timeout: float = 3.0) -> dict[str, Any]:
        if not self.ip:
            return {"ok": False, "error": "IP Kamera PTZ belum terpasang"}

        wsse = self._create_wsse_header()
        soap = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            f'<soap:Header>{wsse}</soap:Header>'
            f'<soap:Body>{body_xml}</soap:Body>'
            '</soap:Envelope>'
        )
        url = f"http://{self.ip}:{self.port}/onvif/{service_path.lstrip('/')}"
        headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
        try:
            resp = self._session.post(url, data=soap, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return {"ok": True, "status_code": resp.status_code}
            return {"ok": False, "status_code": resp.status_code, "error": resp.text[:200]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def move(self, direction: str, speed: int = 5) -> dict[str, Any]:
        """Move camera: 'up', 'down', 'left', 'right', diagonals, or 'stop'."""
        d = direction.strip().lower()
        if d == "stop":
            body = (
                f'<tptz:Stop>'
                f'<tptz:ProfileToken>{self.profile_token}</tptz:ProfileToken>'
                f'<tptz:PanTilt>true</tptz:PanTilt>'
                f'<tptz:Zoom>true</tptz:Zoom>'
                f'</tptz:Stop>'
            )
            return self._send_soap("ptz_service", body)

        # Scale speed 1..8 to float 0.15 .. 1.0
        val = max(0.15, min(1.0, float(speed) / 8.0))

        vec_map = {
            "up": (0.0, val),
            "down": (0.0, -val),
            "left": (-val, 0.0),
            "right": (val, 0.0),
            "leftup": (-val, val),
            "rightup": (val, val),
            "leftdown": (-val, -val),
            "rightdown": (val, -val),
        }

        if d not in vec_map:
            return {"ok": False, "error": f"Arah tidak valid: {direction}"}

        vx, vy = vec_map[d]
        body = (
            f'<tptz:ContinuousMove>'
            f'<tptz:ProfileToken>{self.profile_token}</tptz:ProfileToken>'
            f'<tptz:Velocity>'
            f'<tt:PanTilt x="{vx:.2f}" y="{vy:.2f}"/>'
            f'</tptz:Velocity>'
            f'</tptz:ContinuousMove>'
        )
        return self._send_soap("ptz_service", body)

    def continuous_scan_360(self, action: str = "start") -> dict[str, Any]:
        """Start or stop 360-degree horizontal continuous tour scan."""
        if action.lower() == "stop":
            return self.move("stop")
        # Continuous pan right at steady speed
        body = (
            f'<tptz:ContinuousMove>'
            f'<tptz:ProfileToken>{self.profile_token}</tptz:ProfileToken>'
            f'<tptz:Velocity>'
            f'<tt:PanTilt x="0.40" y="0.00"/>'
            f'</tptz:Velocity>'
            f'</tptz:ContinuousMove>'
        )
        return self._send_soap("ptz_service", body)

    def goto_preset(self, preset_id: int = 1) -> dict[str, Any]:
        """Move camera to a saved preset position (e.g. Preset 1 = Door / Home)."""
        body = (
            f'<tptz:GotoPreset>'
            f'<tptz:ProfileToken>{self.profile_token}</tptz:ProfileToken>'
            f'<tptz:PresetToken>{preset_id}</tptz:PresetToken>'
            f'</tptz:GotoPreset>'
        )
        return self._send_soap("ptz_service", body)

    def set_preset(self, preset_id: int = 1) -> dict[str, Any]:
        """Save current camera position as a preset."""
        body = (
            f'<tptz:SetPreset>'
            f'<tptz:ProfileToken>{self.profile_token}</tptz:ProfileToken>'
            f'<tptz:PresetToken>{preset_id}</tptz:PresetToken>'
            f'<tptz:PresetName>Home_{preset_id}</tptz:PresetName>'
            f'</tptz:SetPreset>'
        )
        return self._send_soap("ptz_service", body)
