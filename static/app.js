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
    if (toggleVoiceAlarm) toggleVoiceAlarm.checked = data.voice_alarm_enabled !== false;
    if (toggleWaPpe) toggleWaPpe.checked = data.alert_ppe_violation_enabled !== false;
    if (toggleWaFall) toggleWaFall.checked = data.alert_fall_emergency_enabled !== false;
    if (toggleWaSmoking) toggleWaSmoking.checked = data.alert_smoking_enabled !== false;
    if (toggleWaOverstay) toggleWaOverstay.checked = data.alert_er_activity_enabled !== false;
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
if (toggleWaOverstay) {
  toggleWaOverstay.addEventListener("change", () => {
    saveSettings({ alert_er_activity_enabled: toggleWaOverstay.checked });
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
setInterval(loadWhatsAppStatus, 3000);
setInterval(loadWhatsAppGroups, 10000);



