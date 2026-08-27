const $ = (id) => document.getElementById(id);

function setIndicator(status) {
  const el = $("indicator");
  el.textContent = status;
    el.className = status.includes("PEOPLE") ? "green" : "unknown";
}

function stateClass(value) {
  if (["COMPLIANT", "OK", "NO_PERSON"].includes(value)) return "green";
  if (["VIOLATION", "MISSING", "MODEL_ERROR"].includes(value)) return "red";
  return "unknown";
}

const warningAudio = new Audio("/static/audio/warning_female.mp3");
let lastAudioTriggerTime = 0;

function checkAndPlayVoiceAlarm(status) {
  if (!status || !status.tracks) return;
  if (status.voice_alarm === "DISABLED") return;
  const toggle = document.getElementById("toggleVoiceAlarm");
  if (toggle && !toggle.checked) return;

  const tracks = status.tracks;
  const hasLongStayViolation = tracks.some(
    (t) => t.stay_seconds >= 30 && (t.helmet === "MISSING" || t.vest === "MISSING")
  );
  if (hasLongStayViolation) {
    const now = Date.now();
    if (now - lastAudioTriggerTime > 40000) {
      lastAudioTriggerTime = now;
      warningAudio.play().catch((e) => console.log("Audio play:", e));
    }
  }
}

const btnTestVoice = $("btnTestVoice");
if (btnTestVoice) {
  btnTestVoice.addEventListener("click", () => {
    warningAudio.currentTime = 0;
    warningAudio.play().catch((e) => alert("Klik di browser terlebih dahulu untuk mengizinkan audio."));
  });
}

function postureBadge(posture, lyingSec) {
  if (posture === "FALLEN") return `<span class="red" style="font-weight: 700;">⚠️ JATUH (${lyingSec}s)</span>`;
  if (posture === "SUSPECTED_FALL") return `<span class="unknown">POSISI MEREBAH</span>`;
  if (posture === "BENDING") return `<span class="unknown">MEMBUNGKUK</span>`;
  return `<span class="green">BERDIRI / NORMAL</span>`;
}

async function refresh() {
  try {
    const status = await fetch("/api/status", { cache: "no-store" }).then((r) => r.json());
    if ($("headerTitle") && status.camera_name) {
      $("headerTitle").textContent = status.camera_name + " Monitor";
    }
    $("connection").textContent = status.connected ? "TERHUBUNG" : "TERPUTUS";
    $("connection").className = status.connected ? "green" : "red";
    setIndicator(status.status || "NO PERSON DETECTOR");
    $("indicator").textContent = `${status.people_count || 0} orang`;
    $("score").textContent = `${status.longest_stay_seconds || 0} detik`;
    $("ppe").textContent = status.ppe_status || "NOT_CONFIGURED";
    $("ppe").className = stateClass(status.ppe_status);
    $("helmet").textContent = `${status.helmet_ok || 0} OK / ${status.helmet_missing || 0} TIDAK`;
    $("helmet").className = status.helmet_missing ? "red" : "green";
    $("vest").textContent = `${status.vest_ok || 0} OK / ${status.vest_missing || 0} TIDAK`;
    $("vest").className = status.vest_missing ? "red" : "green";
    $("healthStatus").textContent = status.health_status || "NORMAL";
    $("healthStatus").className = status.fall_detected ? "red" : "green";
    if ($("smokingStatus")) {
      $("smokingStatus").textContent = status.smoking_detected ? "⚠️ MEROKOK!" : "AMAN";
      $("smokingStatus").className = status.smoking_detected ? "red" : "green";
    }
    if ($("fireSmokeStatus")) {
      if (status.fire_detected) {
        $("fireSmokeStatus").textContent = "🔥 KOBARAN API!";
        $("fireSmokeStatus").className = "red";
      } else if (status.smoke_emergency_detected) {
        $("fireSmokeStatus").textContent = "🌫️ ASAP TEBAL!";
        $("fireSmokeStatus").className = "red";
      } else {
        $("fireSmokeStatus").textContent = "AMAN";
        $("fireSmokeStatus").className = "green";
      }
    }
    $("voiceAlarm").textContent = status.voice_alarm || "AKTIF";
    $("latency").textContent = `${status.inference_ms || 0} ms`;
    $("updated").textContent = status.updated_at ? new Date(status.updated_at).toLocaleString() : "-";
    const tracks = status.tracks || [];
    $("tracks").innerHTML = tracks.length
      ? tracks.map((track) => `<tr><td><strong>${track.name || ("Person #" + track.id)}</strong></td><td>${track.id}</td><td>${Math.round((track.confidence || 0) * 100)}%</td><td>${track.stay_seconds}s</td><td class="${stateClass(track.helmet)}">${track.helmet}</td><td class="${stateClass(track.vest)}">${track.vest}</td><td>${postureBadge(track.posture, track.lying_seconds || 0)}</td><td>${track.is_smoking ? `<span class="red" style="font-weight:700;">🔥 MEROKOK (${track.smoking_seconds || 0}s)</span>` : `<span class="green">TIDAK</span>`}</td></tr>`).join("")
      : '<tr><td colspan="8">Belum ada person</td></tr>';
    checkAndPlayVoiceAlarm(status);
    const events = await fetch("/api/events?limit=30", { cache: "no-store" }).then((r) => r.json());
    $("events").innerHTML = events.map((event) => `<tr><td>${new Date(event.created_at).toLocaleString()}</td><td>${event.status}</td><td>${Number(event.score).toFixed(3)}</td><td>${event.message || "-"}</td></tr>`).join("");
  } catch (error) {
    $("connection").textContent = "SERVER ERROR";
    $("connection").className = "red";
  }
}

async function deletePerson(name) {
  if (!confirm(`Hapus personel "${name}" dari database wajah?`)) return;
  try {
    const res = await fetch("/api/faces/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name }),
    });
    if (res.ok) {
      loadFaces();
    }
  } catch (e) {
    console.error("Gagal menghapus personel:", e);
  }
}

async function loadFaces() {
  try {
    const data = await fetch("/api/faces", { cache: "no-store" }).then((r) => r.json());
    const list = $("facesList");
    if (!list) return;
    if (!data.enabled) {
      list.innerHTML = '<span style="color: #64748b; font-size: 0.85rem;">Face Recognition dinonaktifkan</span>';
      return;
    }
    const faces = data.faces || [];
    list.innerHTML = faces.length
      ? faces.map((name) => `<span style="display: inline-flex; align-items: center; gap: 6px; background: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 6px; font-size: 0.84rem; font-weight: 500;">
          👤 ${name}
          <button onclick="deletePerson('${name.replace(/'/g, "\\'")}')" title="Hapus personel" style="background: none; border: none; color: #94a3b8; font-size: 0.85rem; cursor: pointer; padding: 0 2px; line-height: 1;">✕</button>
        </span>`).join("")
      : '<span style="color: #64748b; font-size: 0.85rem;">Belum ada personel terdaftar</span>';
  } catch (e) {
    console.error("Gagal memuat galeri wajah:", e);
  }
}

const btnCaptureCamera = $("btnCaptureCamera");
const facePhotoInput = $("facePhoto");
const personNameInput = $("personName");
const registerMsg = $("registerMsg");

if (btnCaptureCamera) {
  btnCaptureCamera.addEventListener("click", async () => {
    const name = (personNameInput.value || "").trim();
    if (!name) {
      registerMsg.style.color = "#c52222";
      registerMsg.textContent = "⚠️ Harap masukkan Nama Lengkap / NIK terlebih dahulu.";
      personNameInput.focus();
      return;
    }
    btnCaptureCamera.disabled = true;
    btnCaptureCamera.textContent = "📸 Mengambil Foto...";
    registerMsg.textContent = "";
    try {
      const res = await fetch("/api/faces/register-from-camera", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name }),
      });
      const result = await res.json();
      if (res.ok && result.ok) {
        registerMsg.style.color = "#16803c";
        registerMsg.textContent = "✅ " + result.message;
        personNameInput.value = "";
        loadFaces();
      } else {
        registerMsg.style.color = "#c52222";
        registerMsg.textContent = "❌ " + (result.detail || "Gagal mendaftarkan wajah.");
      }
    } catch (err) {
      registerMsg.style.color = "#c52222";
      registerMsg.textContent = "❌ Terjadi kesalahan jaringan.";
    } finally {
      btnCaptureCamera.disabled = false;
      btnCaptureCamera.textContent = "📸 Ambil Foto Langsung dari Kamera";
    }
  });
}

if (facePhotoInput) {
  facePhotoInput.addEventListener("change", async () => {
    const name = (personNameInput.value || "").trim();
    if (!name) {
      registerMsg.style.color = "#c52222";
      registerMsg.textContent = "⚠️ Harap masukkan Nama Lengkap / NIK sebelum memilih foto.";
      facePhotoInput.value = "";
      personNameInput.focus();
      return;
    }
    if (!facePhotoInput.files || !facePhotoInput.files[0]) return;
    registerMsg.style.color = "#0284c7";
    registerMsg.textContent = "Mengunggah foto...";
    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", facePhotoInput.files[0]);
      const res = await fetch("/api/faces/register", {
        method: "POST",
        body: formData,
      });
      const result = await res.json();
      if (res.ok && result.ok) {
        registerMsg.style.color = "#16803c";
        registerMsg.textContent = "✅ " + result.message;
        personNameInput.value = "";
        facePhotoInput.value = "";
        loadFaces();
      } else {
        registerMsg.style.color = "#c52222";
        registerMsg.textContent = "❌ " + (result.detail || "Gagal mendaftarkan wajah.");
      }
    } catch (err) {
      registerMsg.style.color = "#c52222";
      registerMsg.textContent = "❌ Terjadi kesalahan jaringan.";
    }
  });
}

// === WhatsApp Bot & System Settings Module ===
const waStatusBadge = document.getElementById("waStatusBadge");
const waQrContainer = document.getElementById("waQrContainer");
const waQrImg = document.getElementById("waQrImg");
const waConnectedContainer = document.getElementById("waConnectedContainer");
const waConnectedNumber = document.getElementById("waConnectedNumber");
const btnWaLogout = document.getElementById("btnWaLogout");
const waTargetInput = document.getElementById("waTargetInput");
const btnSaveTarget = document.getElementById("btnSaveTarget");
const btnTestWa = document.getElementById("btnTestWa");
const waTestResult = document.getElementById("waTestResult");

const toggleVoiceAlarm = document.getElementById("toggleVoiceAlarm");
const toggleWaPpe = document.getElementById("toggleWaPpe");
const toggleWaFall = document.getElementById("toggleWaFall");
const toggleWaOverstay = document.getElementById("toggleWaOverstay");
const settingsSaveStatus = document.getElementById("settingsSaveStatus");

async function loadWhatsAppStatus() {
  try {
    const res = await fetch("/api/whatsapp/status");
    const data = await res.json();
    if (data.status === "CONNECTED") {
      waStatusBadge.textContent = "TERHUBUNG";
      waStatusBadge.style.background = "#dcfce7";
      waStatusBadge.style.color = "#15803d";
      waQrContainer.style.display = "none";
      waConnectedContainer.style.display = "block";
      waConnectedNumber.textContent = "Nomor Bot: +" + (data.user || "");
    } else if (data.status === "QR_READY" && data.qr) {
      waStatusBadge.textContent = "SIAP SCAN QR";
      waStatusBadge.style.background = "#fef08a";
      waStatusBadge.style.color = "#854d0e";
      waQrContainer.style.display = "block";
      waConnectedContainer.style.display = "none";
      waQrImg.src = data.qr;
    } else {
      waStatusBadge.textContent = data.status || "OFFLINE";
      waStatusBadge.style.background = "#fee2e2";
      waStatusBadge.style.color = "#991b1b";
      waQrContainer.style.display = "block";
      waConnectedContainer.style.display = "none";
    }
  } catch (err) {
    waStatusBadge.textContent = "OFFLINE";
    waStatusBadge.style.background = "#fee2e2";
    waStatusBadge.style.color = "#991b1b";
  }
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (waTargetInput && !waTargetInput.matches(":focus")) {
      waTargetInput.value = data.whatsapp_target || "";
    }
    const cameraNameInput = document.getElementById("cameraNameInput");
    if (cameraNameInput && !cameraNameInput.matches(":focus")) {
      cameraNameInput.value = data.camera_name || "Electrical Room 1";
    }
    if (toggleVoiceAlarm) toggleVoiceAlarm.checked = data.voice_alarm_enabled !== false;
    if (toggleWaPpe) toggleWaPpe.checked = data.alert_ppe_violation_enabled !== false;
    if (toggleWaFall) toggleWaFall.checked = data.alert_fall_emergency_enabled !== false;
    if (toggleWaSmoking) toggleWaSmoking.checked = data.alert_smoking_enabled !== false;
    const toggleWaFire = document.getElementById("toggleWaFire");
    if (toggleWaFire) toggleWaFire.checked = data.alert_fire_emergency_enabled !== false;
    if (toggleWaOverstay) toggleWaOverstay.checked = data.alert_er_activity_enabled !== false;
    const toggleWaCameraOffline = document.getElementById("toggleWaCameraOffline");
    if (toggleWaCameraOffline) toggleWaCameraOffline.checked = data.alert_camera_offline_enabled !== false;
    const toggleAutoTracking = document.getElementById("toggleAutoTracking");
    if (toggleAutoTracking) toggleAutoTracking.checked = data.auto_tracking_enabled === true;
    const cooldownSelect = document.getElementById("cooldownSelect");
    if (cooldownSelect && data.alert_cooldown_seconds) {
      cooldownSelect.value = String(data.alert_cooldown_seconds);
    }
    const voiceTriggerSelect = document.getElementById("voiceTriggerSelect");
    if (voiceTriggerSelect && data.voice_alarm_trigger_seconds) {
      voiceTriggerSelect.value = String(data.voice_alarm_trigger_seconds);
    }
    const ppeViolationSelect = document.getElementById("ppeViolationSelect");
    if (ppeViolationSelect && data.alert_ppe_violation_seconds) {
      ppeViolationSelect.value = String(data.alert_ppe_violation_seconds);
    }
    const fallEmergencySelect = document.getElementById("fallEmergencySelect");
    if (fallEmergencySelect && data.alert_fall_emergency_seconds) {
      fallEmergencySelect.value = String(data.alert_fall_emergency_seconds);
    }
    const smokingAlertSelect = document.getElementById("smokingAlertSelect");
    if (smokingAlertSelect && data.alert_smoking_seconds) {
      smokingAlertSelect.value = String(data.alert_smoking_seconds);
    }
    const fireEmergencySelect = document.getElementById("fireEmergencySelect");
    if (fireEmergencySelect && data.alert_fire_emergency_seconds) {
      fireEmergencySelect.value = String(data.alert_fire_emergency_seconds);
    }
    const overstayAlertSelect = document.getElementById("overstayAlertSelect");
    if (overstayAlertSelect && data.alert_er_activity_seconds) {
      overstayAlertSelect.value = String(data.alert_er_activity_seconds);
    }
  } catch (err) {}
}

async function saveSettings(partial) {
  try {
    settingsSaveStatus.style.color = "#0284c7";
    settingsSaveStatus.textContent = "Menyimpan pengaturan...";
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(partial),
    });
    if (res.ok) {
      settingsSaveStatus.style.color = "#16803c";
      settingsSaveStatus.textContent = "✅ Pengaturan berhasil diperbarui!";
      setTimeout(() => { settingsSaveStatus.textContent = ""; }, 3000);
    }
  } catch (err) {
    settingsSaveStatus.style.color = "#c52222";
    settingsSaveStatus.textContent = "❌ Gagal menyimpan pengaturan.";
  }
}

const btnSaveRoomName = document.getElementById("btnSaveRoomName");
if (btnSaveRoomName) {
  btnSaveRoomName.addEventListener("click", () => {
    const input = document.getElementById("cameraNameInput");
    if (input && input.value.trim()) {
      saveSettings({ camera_name: input.value.trim() });
    }
  });
}

const cooldownSelectEl = document.getElementById("cooldownSelect");
if (cooldownSelectEl) {
  cooldownSelectEl.addEventListener("change", () => {
    saveSettings({ alert_cooldown_seconds: parseInt(cooldownSelectEl.value, 10) });
  });
}

const voiceTriggerSelect = document.getElementById("voiceTriggerSelect");
if (voiceTriggerSelect) {
  voiceTriggerSelect.addEventListener("change", () => {
    saveSettings({ voice_alarm_trigger_seconds: parseInt(voiceTriggerSelect.value, 10) });
  });
}

const ppeViolationSelect = document.getElementById("ppeViolationSelect");
if (ppeViolationSelect) {
  ppeViolationSelect.addEventListener("change", () => {
    saveSettings({ alert_ppe_violation_seconds: parseInt(ppeViolationSelect.value, 10) });
  });
}

const fallEmergencySelect = document.getElementById("fallEmergencySelect");
if (fallEmergencySelect) {
  fallEmergencySelect.addEventListener("change", () => {
    saveSettings({ alert_fall_emergency_seconds: parseFloat(fallEmergencySelect.value) });
  });
}

const smokingAlertSelect = document.getElementById("smokingAlertSelect");
if (smokingAlertSelect) {
  smokingAlertSelect.addEventListener("change", () => {
    saveSettings({ alert_smoking_seconds: parseFloat(smokingAlertSelect.value) });
  });
}

const fireEmergencySelect = document.getElementById("fireEmergencySelect");
if (fireEmergencySelect) {
  fireEmergencySelect.addEventListener("change", () => {
    const val = parseFloat(fireEmergencySelect.value);
    saveSettings({
      alert_fire_emergency_seconds: val,
      alert_smoke_emergency_seconds: val + 0.5,
    });
  });
}

const overstayAlertSelect = document.getElementById("overstayAlertSelect");
if (overstayAlertSelect) {
  overstayAlertSelect.addEventListener("change", () => {
    saveSettings({ alert_er_activity_seconds: parseInt(overstayAlertSelect.value, 10) });
  });
}

if (toggleVoiceAlarm) {
  toggleVoiceAlarm.addEventListener("change", () => {
    saveSettings({ voice_alarm_enabled: toggleVoiceAlarm.checked });
  });
}
if (toggleWaPpe) {
  toggleWaPpe.addEventListener("change", () => {
    saveSettings({ alert_ppe_violation_enabled: toggleWaPpe.checked });
  });
}
if (toggleWaFall) {
  toggleWaFall.addEventListener("change", () => {
    saveSettings({ alert_fall_emergency_enabled: toggleWaFall.checked });
  });
}
if (toggleWaSmoking) {
  toggleWaSmoking.addEventListener("change", () => {
    saveSettings({ alert_smoking_enabled: toggleWaSmoking.checked });
  });
}
const toggleWaFire = document.getElementById("toggleWaFire");
if (toggleWaFire) {
  toggleWaFire.addEventListener("change", () => {
    saveSettings({
      alert_fire_emergency_enabled: toggleWaFire.checked,
      alert_smoke_emergency_enabled: toggleWaFire.checked,
    });
  });
}
if (toggleWaOverstay) {
  toggleWaOverstay.addEventListener("change", () => {
    saveSettings({ alert_er_activity_enabled: toggleWaOverstay.checked });
  });
}
const toggleWaCameraOffline = document.getElementById("toggleWaCameraOffline");
if (toggleWaCameraOffline) {
  toggleWaCameraOffline.addEventListener("change", () => {
    saveSettings({ alert_camera_offline_enabled: toggleWaCameraOffline.checked });
  });
}
const toggleAutoTracking = document.getElementById("toggleAutoTracking");
if (toggleAutoTracking) {
  toggleAutoTracking.addEventListener("change", () => {
    saveSettings({ auto_tracking_enabled: toggleAutoTracking.checked });
  });
}

if (btnSaveTarget) {
  btnSaveTarget.addEventListener("click", () => {
    const val = (waTargetInput.value || "").trim();
    saveSettings({ whatsapp_target: val });
  });
}

if (btnTestWa) {
  btnTestWa.addEventListener("click", async () => {
    const target = (waTargetInput.value || "").trim();
    if (!target) {
      waTestResult.style.color = "#c52222";
      waTestResult.textContent = "⚠️ Harap masukkan Nomor/Grup WhatsApp tujuan terlebih dahulu.";
      waTargetInput.focus();
      return;
    }
    btnTestWa.disabled = true;
    waTestResult.style.color = "#0284c7";
    waTestResult.textContent = "Mengirim pesan & snapshot foto uji coba...";
    try {
      const res = await fetch("/api/whatsapp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        waTestResult.style.color = "#16803c";
        waTestResult.textContent = "✅ Pesan & foto snapshot berhasil terkirim ke WhatsApp!";
      } else {
        waTestResult.style.color = "#c52222";
        waTestResult.textContent = "❌ " + (data.detail || data.error || "Gagal mengirim.");
      }
    } catch (err) {
      waTestResult.style.color = "#c52222";
      waTestResult.textContent = "❌ Terjadi kesalahan jaringan.";
    } finally {
      btnTestWa.disabled = false;
    }
  });
}

if (btnWaLogout) {
  btnWaLogout.addEventListener("click", async () => {
    if (!confirm("Yakin ingin memutuskan koneksi WhatsApp dan berganti nomor?")) return;
    btnWaLogout.disabled = true;
    try {
      await fetch("/api/whatsapp/logout", { method: "POST" });
      loadWhatsAppStatus();
    } finally {
      btnWaLogout.disabled = false;
    }
  });
}

const waGroupSelect = document.getElementById("waGroupSelect");

async function loadWhatsAppGroups() {
  if (!waGroupSelect) return;
  try {
    const res = await fetch("/api/whatsapp/groups");
    const groups = await res.json();
    const currentVal = (waTargetInput.value || "").trim();
    let optionsHtml = '<option value="">-- Pilih Grup WhatsApp --</option>';
    if (Array.isArray(groups) && groups.length > 0) {
      groups.forEach((g) => {
        const selected = g.id === currentVal ? "selected" : "";
        optionsHtml += `<option value="${g.id}" ${selected}>👥 ${g.name} (${g.participants} anggota)</option>`;
      });
    }
    waGroupSelect.innerHTML = optionsHtml;
  } catch (e) {}
}

if (waGroupSelect) {
  waGroupSelect.addEventListener("change", () => {
    if (waGroupSelect.value) {
      waTargetInput.value = waGroupSelect.value;
      saveSettings({ whatsapp_target: waGroupSelect.value });
    }
  });
}

refresh();
loadFaces();
loadWhatsAppStatus();
loadSettings();
loadWhatsAppGroups();

setInterval(refresh, 1000);
setInterval(loadFaces, 5000);
// ==========================================
// PTZ CONTROLLER (TRACKPAD & D-PAD)
// ==========================================
const tabDpad = document.getElementById("tabDpad");
const tabTrackpad = document.getElementById("tabTrackpad");
const ptzDpadView = document.getElementById("ptzDpadView");
const ptzTrackpadView = document.getElementById("ptzTrackpadView");
const ptzSpeedInput = document.getElementById("ptzSpeed");
const ptzSpeedLabel = document.getElementById("ptzSpeedLabel");
const ptzStatusMsg = document.getElementById("ptzStatusMsg");

if (tabDpad && tabTrackpad) {
  tabDpad.addEventListener("click", () => {
    tabDpad.style.background = "#0284c7";
    tabDpad.style.color = "white";
    tabTrackpad.style.background = "#1e293b";
    tabTrackpad.style.color = "#94a3b8";
    if (ptzDpadView) ptzDpadView.style.display = "flex";
    if (ptzTrackpadView) ptzTrackpadView.style.display = "none";
  });
  tabTrackpad.addEventListener("click", () => {
    tabTrackpad.style.background = "#0284c7";
    tabTrackpad.style.color = "white";
    tabDpad.style.background = "#1e293b";
    tabDpad.style.color = "#94a3b8";
    if (ptzTrackpadView) ptzTrackpadView.style.display = "flex";
    if (ptzDpadView) ptzDpadView.style.display = "none";
  });
}

if (ptzSpeedInput) {
  ptzSpeedInput.addEventListener("input", () => {
    if (ptzSpeedLabel) ptzSpeedLabel.textContent = ptzSpeedInput.value;
  });
}

function getPtzSpeed() {
  return ptzSpeedInput ? parseInt(ptzSpeedInput.value, 10) : 5;
}

let activePtzDirection = "stop";

async function sendPtzMove(direction) {
  if (activePtzDirection === direction && direction !== "stop") return;
  activePtzDirection = direction;
  try {
    if (ptzStatusMsg) {
      ptzStatusMsg.textContent = direction === "stop" ? "Siap" : `Memutar: ${direction.toUpperCase()}...`;
    }
    await fetch("/api/ptz/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction, speed: getPtzSpeed() }),
    });
  } catch (e) {}
}

// Bind D-Pad Buttons
const ptzButtons = {
  btnPtzUp: "up",
  btnPtzDown: "down",
  btnPtzLeft: "left",
  btnPtzRight: "right",
  btnPtzLU: "leftup",
  btnPtzRU: "rightup",
  btnPtzLD: "leftdown",
  btnPtzRD: "rightdown",
};

Object.entries(ptzButtons).forEach(([btnId, dir]) => {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const startHandler = (e) => {
    e.preventDefault();
    btn.classList.add("active");
    sendPtzMove(dir);
  };
  const endHandler = (e) => {
    e.preventDefault();
    btn.classList.remove("active");
    sendPtzMove("stop");
  };
  btn.addEventListener("mousedown", startHandler);
  btn.addEventListener("mouseup", endHandler);
  btn.addEventListener("mouseleave", endHandler);
  btn.addEventListener("touchstart", startHandler, { passive: false });
  btn.addEventListener("touchend", endHandler, { passive: false });
});

const btnPtzStop = document.getElementById("btnPtzStop");
if (btnPtzStop) {
  btnPtzStop.addEventListener("click", () => sendPtzMove("stop"));
}

// 360 Scan & Presets
let isScanning360 = false;
const btnPtzScan = document.getElementById("btnPtzScan");
if (btnPtzScan) {
  btnPtzScan.addEventListener("click", async () => {
    isScanning360 = !isScanning360;
    btnPtzScan.style.background = isScanning360 ? "#ef4444" : "#6366f1";
    btnPtzScan.textContent = isScanning360 ? "⏹️ Stop 360°" : "🔄 Putar 360°";
    try {
      await fetch("/api/ptz/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: isScanning360 ? "start" : "stop" }),
      });
    } catch (e) {}
  });
}

const btnPtzHome = document.getElementById("btnPtzHome");
if (btnPtzHome) {
  btnPtzHome.addEventListener("click", async () => {
    if (ptzStatusMsg) ptzStatusMsg.textContent = "Kembali ke posisi Home...";
    try {
      await fetch("/api/ptz/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "goto", preset_id: 1 }),
      });
    } catch (e) {}
  });
}

const btnPtzSetHome = document.getElementById("btnPtzSetHome");
if (btnPtzSetHome) {
  btnPtzSetHome.addEventListener("click", async () => {
    if (!confirm("Simpan sudut kamera saat ini sebagai posisi Home / Standar?")) return;
    try {
      await fetch("/api/ptz/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set", preset_id: 1 }),
      });
      if (ptzStatusMsg) ptzStatusMsg.textContent = "✅ Posisi Home berhasil disimpan!";
    } catch (e) {}
  });
}

// Interactive Virtual Joystick Trackpad
const trackpad = document.getElementById("ptzTrackpad");
const knob = document.getElementById("ptzKnob");

if (trackpad && knob) {
  let isDragging = false;
  const maxRadius = 55;

  function handleTrackpadMove(clientX, clientY) {
    const rect = trackpad.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    let dx = clientX - centerX;
    let dy = clientY - centerY;
    const distance = Math.hypot(dx, dy);

    if (distance > maxRadius) {
      dx = (dx / distance) * maxRadius;
      dy = (dy / distance) * maxRadius;
    }

    knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;

    if (distance < 12) {
      sendPtzMove("stop");
      return;
    }

    // Determine direction from angle
    const angle = Math.atan2(dy, dx) * (180 / Math.PI); // -180 to 180
    if (angle >= -22.5 && angle <= 22.5) {
      sendPtzMove("right");
    } else if (angle > 22.5 && angle < 67.5) {
      sendPtzMove("rightdown");
    } else if (angle >= 67.5 && angle <= 112.5) {
      sendPtzMove("down");
    } else if (angle > 112.5 && angle < 157.5) {
      sendPtzMove("leftdown");
    } else if (angle >= 157.5 || angle <= -157.5) {
      sendPtzMove("left");
    } else if (angle >= -157.5 && angle < -112.5) {
      sendPtzMove("leftup");
    } else if (angle >= -112.5 && angle <= -67.5) {
      sendPtzMove("up");
    } else if (angle > -67.5 && angle < -22.5) {
      sendPtzMove("rightup");
    }
  }

  function stopTrackpad() {
    if (!isDragging) return;
    isDragging = false;
    knob.style.transform = "translate(-50%, -50%)";
    sendPtzMove("stop");
  }

  trackpad.addEventListener("mousedown", (e) => {
    isDragging = true;
    handleTrackpadMove(e.clientX, e.clientY);
  });
  window.addEventListener("mousemove", (e) => {
    if (isDragging) handleTrackpadMove(e.clientX, e.clientY);
  });
  window.addEventListener("mouseup", stopTrackpad);

  trackpad.addEventListener("touchstart", (e) => {
    if (e.touches.length > 0) {
      isDragging = true;
      handleTrackpadMove(e.touches[0].clientX, e.touches[0].clientY);
    }
  }, { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (isDragging && e.touches.length > 0) {
      handleTrackpadMove(e.touches[0].clientX, e.touches[0].clientY);
    }
  }, { passive: true });
  window.addEventListener("touchend", stopTrackpad);
}

// ==========================================
// FLOATING MODAL CONTROLLERS (SETTINGS & LOGS)
// ==========================================
const modalSettings = document.getElementById("modalSettings");
const modalLogs = document.getElementById("modalLogs");
const btnOpenSettings = document.getElementById("btnOpenSettings");
const btnCloseSettings = document.getElementById("btnCloseSettings");
const btnOpenLogs = document.getElementById("btnOpenLogs");
const btnCloseLogs = document.getElementById("btnCloseLogs");

function openModal(modal) {
  if (modal) modal.classList.add("open");
}

function closeModal(modal) {
  if (modal) modal.classList.remove("open");
}

if (btnOpenSettings) {
  btnOpenSettings.addEventListener("click", () => {
    loadSettings();
    loadWhatsAppStatus();
    loadWhatsAppGroups();
    loadFaces();
    openModal(modalSettings);
  });
}

if (btnCloseSettings) {
  btnCloseSettings.addEventListener("click", () => closeModal(modalSettings));
}

if (btnOpenLogs) {
  btnOpenLogs.addEventListener("click", () => {
    refresh();
    openModal(modalLogs);
  });
}

if (btnCloseLogs) {
  btnCloseLogs.addEventListener("click", () => closeModal(modalLogs));
}

// Close when clicking outside modal box
[modalSettings, modalLogs].forEach((m) => {
  if (m) {
    m.addEventListener("click", (e) => {
      if (e.target === m) closeModal(m);
    });
  }
});

// Close with Escape key
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal(modalSettings);
    closeModal(modalLogs);
  }
});

// Settings Modal Tabs
const tabSettingsWa = document.getElementById("tabSettingsWa");
const tabSettingsAlerts = document.getElementById("tabSettingsAlerts");
const tabSettingsFaces = document.getElementById("tabSettingsFaces");
const viewSettingsWa = document.getElementById("viewSettingsWa");
const viewSettingsAlerts = document.getElementById("viewSettingsAlerts");
const viewSettingsFaces = document.getElementById("viewSettingsFaces");

function selectSettingsTab(activeTab, activeView) {
  [tabSettingsWa, tabSettingsAlerts, tabSettingsFaces].forEach((t) => t && t.classList.remove("active"));
  [viewSettingsWa, viewSettingsAlerts, viewSettingsFaces].forEach((v) => v && (v.style.display = "none"));
  if (activeTab) activeTab.classList.add("active");
  if (activeView) activeView.style.display = "flex";
}

if (tabSettingsWa) {
  tabSettingsWa.addEventListener("click", () => selectSettingsTab(tabSettingsWa, viewSettingsWa));
}
if (tabSettingsAlerts) {
  tabSettingsAlerts.addEventListener("click", () => selectSettingsTab(tabSettingsAlerts, viewSettingsAlerts));
}
if (tabSettingsFaces) {
  tabSettingsFaces.addEventListener("click", () => selectSettingsTab(tabSettingsFaces, viewSettingsFaces));
}



