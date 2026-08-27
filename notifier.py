from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import re

logger = logging.getLogger("imou-notifier")

CONFIG_FILE = Path(__file__).resolve().parent / "notification_settings.json"
COOLDOWN_FILE = Path(__file__).resolve().parent / ".alert_cooldowns.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "camera_name": "Electrical Room 1",
    "whatsapp_enabled": True,
    "whatsapp_target": "",  # e.g. "6281234567890" or "120363xxx@g.us"
    "voice_alarm_enabled": True,
    "alert_ppe_violation_enabled": True,
    "alert_ppe_violation_seconds": 60,  # 1 menit
    "alert_fall_emergency_enabled": True,
    "alert_er_activity_enabled": True,
    "alert_er_activity_seconds": 300,  # 5 menit
    "alert_smoking_enabled": True,
    "alert_fire_emergency_enabled": True,
    "alert_smoke_emergency_enabled": True,
    "alert_camera_offline_enabled": True,
    "alert_cooldown_seconds": 3600,  # 1 jam (3600s) per orang agar tidak spam
    "auto_tracking_enabled": False,
    "auto_tracking_speed": 4,
    "auto_tracking_return_home": True,
}


def _canonical_person_key(name: str) -> str:
    """Normalize names like 'Pandu 7130', 'pandu_7130', 'pandu' -> 'pandu'."""
    raw = (name or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9]", "", raw)
    match = re.match(r"^([a-z]+)", cleaned)
    if match and not cleaned.startswith("person") and not cleaned.startswith("track") and not cleaned.startswith("id"):
        return match.group(1)
    if cleaned and not cleaned.startswith("person") and not cleaned.startswith("track"):
        return cleaned
    return "unnamed_violator"


class NotificationManager:
    """Manages WhatsApp alerting with dynamic settings, snapshot attachments, and persistent cooldowns."""

    def __init__(self, bridge_url: str = "http://127.0.0.1:3001") -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self._lock = threading.Lock()
        self._last_alert_times: dict[str, float] = self._load_cooldowns()
        self._offline_rooms: set[str] = set()
        self.settings: dict[str, Any] = self._load_settings()

    def _load_cooldowns(self) -> dict[str, float]:
        if COOLDOWN_FILE.exists():
            try:
                with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cooldowns(self) -> None:
        try:
            with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
                json.dump(self._last_alert_times, f)
        except Exception:
            pass

    def _load_settings(self) -> dict[str, Any]:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    res = dict(DEFAULT_SETTINGS)
                    res.update(loaded)
                    return res
            except Exception as exc:
                logger.warning("Gagal memuat notification_settings.json: %s", exc)
        return dict(DEFAULT_SETTINGS)

    def save_settings(self, new_settings: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.settings.update(new_settings)
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=2)
            except Exception as exc:
                logger.error("Gagal menyimpan notification_settings.json: %s", exc)
        return dict(self.settings)

    def get_whatsapp_status(self) -> dict[str, Any]:
        try:
            req = urllib.request.Request(f"{self.bridge_url}/status", headers={"User-Agent": "ImouMonitor"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "ok": True,
                    "bridge_connected": True,
                    "status": data.get("status", "UNKNOWN"),
                    "qr": data.get("qr"),
                    "user": data.get("user"),
                }
        except Exception as exc:
            return {
                "ok": False,
                "bridge_connected": False,
                "status": "SERVICE_OFFLINE",
                "error": str(exc),
            }

    def get_whatsapp_groups(self) -> list[dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{self.bridge_url}/groups", headers={"User-Agent": "ImouMonitor"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("groups", [])
        except Exception as exc:
            logger.warning("Gagal mengambil daftar grup WhatsApp: %s", exc)
            return []

    def logout_whatsapp(self) -> dict[str, Any]:
        try:
            req = urllib.request.Request(
                f"{self.bridge_url}/logout",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def send_whatsapp_message(
        self,
        to: str,
        message: str,
        image_path: str | Path | None = None,
    ) -> dict[str, Any]:
        try:
            payload = {"to": str(to).strip(), "message": message}
            if image_path:
                p = Path(image_path)
                if p.exists():
                    payload["image_path"] = str(p.resolve())

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.bridge_url}/send",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8")
            return {"ok": False, "error": f"HTTP {he.code}: {err_body}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dispatch_alert(
        self,
        alert_key: str,
        title: str,
        message: str,
        image_path: str | Path | None = None,
        force: bool = False,
    ) -> bool:
        """Dispatch alert if WhatsApp is enabled and cooldown has passed. Non-blocking."""
        if not self.settings.get("whatsapp_enabled") and not force:
            return False

        target = self.settings.get("whatsapp_target", "").strip()
        if not target and not force:
            return False

        now = time.time()
        cooldown = float(self.settings.get("alert_cooldown_seconds", 3600))

        with self._lock:
            last_sent = self._last_alert_times.get(alert_key, 0.0)
            if not force and (now - last_sent < cooldown):
                return False
            self._last_alert_times[alert_key] = now
            self._save_cooldowns()

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        full_text = f"*{title}*\n\n{message}\n\n🕒 _Waktu: {now_str}_"

        def _worker() -> None:
            res = self.send_whatsapp_message(target, full_text, image_path)
            if res.get("ok"):
                logger.info("WhatsApp Alert successfully sent: %s -> %s", alert_key, target)
            else:
                logger.warning("WhatsApp Alert failed: %s -> %s", alert_key, res.get("error"))

        t = threading.Thread(target=_worker, name=f"wa-alert-{alert_key}", daemon=True)
        t.start()
        return True

    def process_tracks_and_alerts(
        self,
        tracks: list[dict[str, Any]],
        latest_snapshot_path: str | Path | None = None,
    ) -> None:
        """Evaluate tracks against safety alert rules."""
        if not self.settings.get("whatsapp_enabled"):
            return
        if not self.settings.get("whatsapp_target"):
            return

        room_name = self.settings.get("camera_name", "Electrical Room")

        for track in tracks:
            track_id = track["id"]
            name = track.get("name") or f"Person #{track_id}"
            stay_sec = int(track.get("stay_seconds", 0))
            helmet = track.get("helmet", "UNKNOWN")
            vest = track.get("vest", "UNKNOWN")
            posture = track.get("posture", "STANDING")
            lying_sec = int(track.get("lying_seconds", 0))
            person_key = _canonical_person_key(name)

            # Rule 1: APD Non-Compliance for >= 1 Minute (60 seconds)
            if self.settings.get("alert_ppe_violation_enabled", True):
                ppe_threshold = int(self.settings.get("alert_ppe_violation_seconds", 60))
                if (helmet == "MISSING" or vest == "MISSING") and stay_sec >= ppe_threshold:
                    violations = []
                    if helmet == "MISSING":
                        violations.append("Helm Keselamatan")
                    if vest == "MISSING":
                        violations.append("Rompi / Baju Kerja K3")
                    v_str = " & ".join(violations)
                    self.dispatch_alert(
                        alert_key=f"ppe_violation_{person_key}",
                        title="⚠️ PERINGATAN K3: PELANGGARAN APD",
                        message=(
                            f"📍 *Lokasi:* {room_name}\n"
                            f"👤 *Personel:* {name}\n"
                            f"⏱️ *Durasi:* {stay_sec} detik\n"
                            f"❌ *Pelanggaran APD:* Tidak memakai *{v_str}*!\n\n"
                            f"Harap segera gunakan APD lengkap sebelum melanjutkan pekerjaan."
                        ),
                        image_path=latest_snapshot_path,
                    )

            # Rule 2: Unconscious / Fall Emergency
            if self.settings.get("alert_fall_emergency_enabled", True):
                if posture == "FALLEN" and lying_sec >= 4:
                    self.dispatch_alert(
                        alert_key=f"fall_emergency_{person_key}",
                        title="🚨 DARURAT K3: PERSONEL JATUH / PINGSAN!",
                        message=(
                            f"⚠️ *PERINGATAN DARURAT TINGGI!*\n"
                            f"📍 *Lokasi:* {room_name}\n"
                            f"👤 *Personel:* {name}\n"
                            f"⏱️ *Tergeletak di Lantai:* {lying_sec} detik\n\n"
                            f"🚨 *TIM RESCUE / K3 HARAP SEGERA CEK LOKASI!*"
                        ),
                        image_path=latest_snapshot_path,
                    )

            # Rule 3: Electrical Room Activity > 5 Minutes (300 seconds)
            if self.settings.get("alert_er_activity_enabled", True):
                overstay_threshold = int(self.settings.get("alert_er_activity_seconds", 300))
                if stay_sec >= overstay_threshold:
                    mins = stay_sec // 60
                    self.dispatch_alert(
                        alert_key=f"er_overstay_{person_key}",
                        title="⏱️ LAPORAN K3: DURASI AKTIVITAS MELEBIHI BATAS",
                        message=(
                            f"📍 *Lokasi:* {room_name}\n"
                            f"👤 *Personel:* {name}\n"
                            f"⏱️ *Total Durasi:* *{mins} menit* ({stay_sec}s)\n"
                            f"Batas izin durasi kerja standar: {overstay_threshold // 60} menit."
                        ),
                        image_path=latest_snapshot_path,
                    )

            # Rule 4: Smoking Detection Alert
            if self.settings.get("alert_smoking_enabled", True):
                if track.get("is_smoking"):
                    self.dispatch_alert(
                        alert_key=f"smoking_{person_key}",
                        title="🔥 PERINGATAN K3: DETEKSI AKTIVITAS MEROKOK!",
                        message=(
                            f"⚠️ *PELANGGARAN K3 TINGKAT TINGGI!*\n"
                            f"📍 *Lokasi:* {room_name}\n"
                            f"👤 *Personel:* {name}\n"
                            f"Terdeteksi melakukan aktivitas *MEROKOK* ({track.get('smoking_seconds', 0)}s)!\n\n"
                            f"🚨 *DILARANG MEROKOK DI AREA INI KARENA BAHAYA KEBAKARAN & ARC FLASH!*"
                        ),
                        image_path=latest_snapshot_path,
                    )

    def notify_fire_emergency(
        self,
        room_name: str = "Electrical Room",
        confidence: float = 1.0,
        image_path: str | Path | None = None,
    ) -> bool:
        """Dispatch immediate high-priority alert for fire detection."""
        if not self.settings.get("alert_fire_emergency_enabled", True):
            return False
        room_key = re.sub(r"[^a-z0-9]", "", room_name.lower()) or "default_room"
        return self.dispatch_alert(
            alert_key=f"fire_emergency_{room_key}",
            title="🚨🚨 DARURAT TINGGI: DETEKSI KOBARAN API / KEBAKARAN! 🚨🚨",
            message=(
                f"🔥 *BAHAYA TINGKAT TINGGI (FIRE HAZARD)!*\n"
                f"📍 *Lokasi:* {room_name}\n"
                f"📊 *Tingkat Keyakinan:* {int(confidence * 100)}%\n\n"
                f"⚠️ *Terdeteksi kobaran api / percikan api di Ruang Elektrikal!*\n"
                f"🚨 *SEGERA AKTIFKAN SISTEM PEMADAM (APAR/FM200) DAN LAKUKAN EVAKUASI DARURAT!*"
            ),
            image_path=image_path,
            force=True,  # Bypass normal cooldown for critical life safety
        )

    def notify_smoke_emergency(
        self,
        room_name: str = "Electrical Room",
        confidence: float = 1.0,
        image_path: str | Path | None = None,
    ) -> bool:
        """Dispatch high-priority alert for thick smoke detection."""
        if not self.settings.get("alert_smoke_emergency_enabled", True):
            return False
        room_key = re.sub(r"[^a-z0-9]", "", room_name.lower()) or "default_room"
        return self.dispatch_alert(
            alert_key=f"smoke_emergency_{room_key}",
            title="⚠️🚨 DARURAT K3: DETEKSI GUMPALAN ASAP TEBAL!",
            message=(
                f"🌫️ *PERINGATAN DINI BAHAYA ASAP (THICK SMOKE HAZARD)!*\n"
                f"📍 *Lokasi:* {room_name}\n"
                f"📊 *Tingkat Keyakinan:* {int(confidence * 100)}%\n\n"
                f"⚠️ *Terdeteksi gumpalan asap tebal di Ruang Elektrikal!*\n"
                f"Kemungkinan terjadi korsleting atau awal kebakaran panel listrik.\n"
                f"🚨 *TIM TEKNISI & K3 HARAP SEGERA CEK LOKASI!*"
            ),
            image_path=image_path,
            force=True,
        )

    def notify_camera_status(
        self,
        connected: bool,
        room_name: str = "Electrical Room",
        error_msg: str = "",
    ) -> None:
        """Alert when camera stream goes offline or recovers online."""
        if not self.settings.get("alert_camera_offline_enabled", True):
            return

        room_key = re.sub(r"[^a-z0-9]", "", room_name.lower()) or "default_room"
        if not connected:
            self._offline_rooms.add(room_key)
            self.dispatch_alert(
                alert_key=f"cam_offline_{room_key}",
                title="🚨 PERINGATAN SISTEM: KAMERA CCTV TERPUTUS / OFFLINE!",
                message=(
                    f"📍 *Lokasi:* {room_name}\n"
                    f"⚠️ *Status:* Aliran video RTSP terputus atau daya CCTV mati!\n"
                    f"Keterangan: {error_msg or 'Koneksi kamera gagal'}\n\n"
                    f"🚨 *Harap segera periksa kabel LAN / sumber daya PoE kamera!*"
                ),
            )
        else:
            # If camera was offline, send online recovery message
            if room_key in self._offline_rooms:
                self._offline_rooms.remove(room_key)
                self.dispatch_alert(
                    alert_key=f"cam_online_{room_key}",
                    title="✅ INFORMASI SISTEM: KAMERA CCTV KEMBALI ONLINE",
                    message=(
                        f"📍 *Lokasi:* {room_name}\n"
                        f"Status: Aliran video RTSP berhasil terhubung normal.\n"
                        f"Pemantauan keselamatan K3 kembali aktif."
                    ),
                    force=True,
                )
                self._last_alert_times.pop(f"cam_offline_{room_key}", None)
                self._save_cooldowns()


notifier = NotificationManager()
