from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from detector import PersonMonitor
from notifier import notifier
from ptz import PTZController
from storage import EventStore


store = EventStore(settings.db_path)
detector = PersonMonitor(settings, store)
ptz = PTZController(settings.rtsp_url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    detector.start()
    yield
    detector.stop()


app = FastAPI(title="Imou Electrical Room Monitor", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "templates" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/health")
def health() -> dict[str, object]:
    status = detector.status()
    return {"ok": True, "camera_connected": status["connected"], "status": status["status"]}


@app.get("/api/status")
def api_status() -> dict[str, object]:
    return detector.status()


@app.get("/api/events")
def api_events(limit: int = 50) -> list[dict[str, object]]:
    return store.recent(limit)


@app.get("/api/faces")
def api_faces() -> dict[str, object]:
    if getattr(detector, "_face_manager", None) is None:
        return {"enabled": False, "faces": []}
    return {
        "enabled": detector._face_manager.enabled,
        "faces": detector._face_manager.list_registered_faces(),
    }


@app.post("/api/faces/register")
async def api_register_face(name: str = Form(...), file: UploadFile = File(...)) -> JSONResponse:
    if getattr(detector, "_face_manager", None) is None or not detector._face_manager.enabled:
        raise HTTPException(status_code=503, detail="Modul Face Recognition tidak aktif")
    contents = await file.read()
    ok = detector._face_manager.register_face(name, contents)
    if not ok:
        raise HTTPException(status_code=400, detail="Wajah tidak terdeteksi pada foto yang diunggah")
    return JSONResponse(content={"ok": True, "message": f"Wajah untuk {name} berhasil didaftarkan"})


@app.post("/api/faces/register-from-camera")
def api_register_face_from_camera(data: dict[str, str] = Body(...)) -> JSONResponse:
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nama personel tidak boleh kosong")
    if getattr(detector, "_face_manager", None) is None or not detector._face_manager.enabled:
        raise HTTPException(status_code=503, detail="Modul Face Recognition tidak aktif")
    raw_frame = detector.latest_raw_frame()
    if raw_frame is None:
        raise HTTPException(status_code=503, detail="Belum ada frame dari kamera")
    ok = detector._face_manager.register_face(name, raw_frame)
    if not ok:
        raise HTTPException(status_code=400, detail="Wajah tidak terdeteksi pada posisi kamera saat ini. Pastikan wajah menghadap jelas ke kamera.")
    return JSONResponse(content={"ok": True, "message": f"Wajah untuk {name} berhasil didaftarkan langsung dari kamera!"})


@app.post("/api/faces/delete")
def api_delete_face(data: dict[str, str] = Body(...)) -> JSONResponse:
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nama personel tidak boleh kosong")
    if getattr(detector, "_face_manager", None) is None or not detector._face_manager.enabled:
        raise HTTPException(status_code=503, detail="Modul Face Recognition tidak aktif")
    ok = detector._face_manager.delete_face(name)
    return JSONResponse(content={"ok": True, "message": f"Personel {name} berhasil dihapus."})


@app.get("/api/whatsapp/status")
def api_whatsapp_status() -> dict[str, Any]:
    return notifier.get_whatsapp_status()


@app.get("/api/whatsapp/groups")
def api_whatsapp_groups() -> list[dict[str, Any]]:
    return notifier.get_whatsapp_groups()


@app.post("/api/whatsapp/logout")
def api_whatsapp_logout() -> dict[str, Any]:
    return notifier.logout_whatsapp()


@app.post("/api/whatsapp/test")
def api_whatsapp_test(data: dict[str, Any] = Body(...)) -> JSONResponse:
    target = data.get("target") or notifier.settings.get("whatsapp_target", "")
    if not target:
        raise HTTPException(status_code=400, detail="Nomor/Grup WhatsApp tujuan belum diisi.")
    snap_path = None
    jpeg = detector.latest_jpeg()
    if jpeg:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_file = settings.snapshots_dir / f"test_{timestamp}.jpg"
        with open(snap_file, "wb") as f:
            f.write(jpeg)
        snap_path = snap_file

    msg = "🧪 *Uji Coba Notifikasi WhatsApp K3*\n\nSistem monitoring Ruang Elektrikal berhasil terhubung dengan WhatsApp Anda!"
    res = notifier.send_whatsapp_message(target, msg, snap_path)
    if not res.get("ok"):
        raise HTTPException(status_code=500, detail=res.get("error", "Gagal mengirim pesan WhatsApp"))
    return JSONResponse(content={"ok": True, "message": f"Pesan uji coba berhasil dikirim ke {target}!"})


@app.get("/api/settings")
def api_get_settings() -> dict[str, Any]:
    return notifier.settings


@app.post("/api/settings")
def api_save_settings(data: dict[str, Any] = Body(...)) -> JSONResponse:
    saved = notifier.save_settings(data)
    return JSONResponse(content={"ok": True, "settings": saved})


@app.post("/api/ptz/move")
def api_ptz_move(data: dict[str, Any] = Body(...)) -> JSONResponse:
    direction = str(data.get("direction", "stop"))
    speed = int(data.get("speed", 5))
    if direction == "stop":
        detector._is_patrolling = False
    res = ptz.move(direction, speed)
    return JSONResponse(content=res)


@app.post("/api/ptz/scan")
def api_ptz_scan(data: dict[str, Any] = Body(...)) -> JSONResponse:
    import time
    action = str(data.get("action", "start"))
    if action == "start":
        detector._is_patrolling = True
        detector._patrol_start_time = time.time()
        res = ptz.continuous_scan_360("start")
    else:
        detector._is_patrolling = False
        res = ptz.move("stop")
    return JSONResponse(content=res)


@app.post("/api/ptz/preset")
def api_ptz_preset(data: dict[str, Any] = Body(...)) -> JSONResponse:
    action = str(data.get("action", "goto"))
    preset_id = int(data.get("preset_id", 1))
    if action == "set":
        res = ptz.set_preset(preset_id)
    else:
        res = ptz.goto_preset(preset_id)
    return JSONResponse(content=res)


@app.get("/snapshot.jpg")
def snapshot() -> Response:
    image = detector.latest_jpeg()
    if image is None:
        raise HTTPException(status_code=503, detail="Belum ada frame dari kamera")
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def mjpeg_frames():
    """Yield the newest JPEG repeatedly; stale frames are never queued."""
    last = None
    while True:
        image = detector.latest_jpeg()
        if image and image != last:
            last = image
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Cache-Control: no-cache\r\n\r\n" + image + b"\r\n")
        else:
            import time
            time.sleep(0.03)


@app.get("/stream.mjpg")
def stream_mjpg() -> StreamingResponse:
    return StreamingResponse(
        mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
