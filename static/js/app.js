// NEXUS 3D Biometric Web Client
let knownLastRecordId = null;

// Audio Chime using Web Audio API
function playChime(success = true) {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    if (success) {
      // High-tech affirmative dual beep
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, ctx.currentTime); // A5
      osc.frequency.setValueAtTime(1320, ctx.currentTime + 0.08); // E6
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    }
  } catch (e) {
    console.warn("Audio chime prevented:", e);
  }
}

// Update live clock
function updateClock() {
  const clockEl = document.getElementById("live-clock");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString() + " // " + now.toLocaleDateString();
  }
}
setInterval(updateClock, 1000);
updateClock();

// Toggle HUD settings on server
async function toggleHudElement(elementKey) {
  const btn = document.getElementById(`btn-toggle-${elementKey}`);
  const isCurrentlyActive = btn ? btn.classList.contains("active") : false;
  const newState = !isCurrentlyActive;

  if (btn) {
    btn.classList.toggle("active", newState);
  }

  const payload = {};
  payload[elementKey] = newState;

  try {
    await fetch("/api/toggle_hud", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    console.error("Failed to toggle HUD:", e);
  }
}

// Fetch telemetry & attendance stats
async function refreshStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();

    const totalEl = document.getElementById("total-users");
    if (totalEl) totalEl.textContent = data.total_users;

    const officeEl = document.getElementById("present-office");
    if (officeEl) officeEl.textContent = `${data.present_employees || 0} / ${data.total_employees || 0}`;

    const studentEl = document.getElementById("present-students");
    if (studentEl) studentEl.textContent = `${data.present_students || 0} / ${data.total_students || 0}`;

    const lateEl = document.getElementById("late-count");
    if (lateEl) lateEl.textContent = data.late_count_today || 0;

    if (data.last_scan && data.last_scan.id !== knownLastRecordId) {
      if (knownLastRecordId !== null) {
        // New record detected!
        playChime(true);
        if (window.pulseHologramVerified) {
          window.pulseHologramVerified(data.last_scan.user_name);
        }
      }
      knownLastRecordId = data.last_scan.id;
      refreshFeed();
      refreshAnalytics();
    }
  } catch (e) {
    console.warn("Telemetry fetch error:", e);
  }
}

// Refresh table feed
async function refreshFeed() {
  try {
    const res = await fetch("/api/today");
    const records = await res.json();
    const tbody = document.getElementById("attendance-tbody");
    if (!tbody) return;

    if (records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="no-records">Waiting for face detection check-ins...</td></tr>`;
      return;
    }

    let rowsHtml = "";
    records.slice(0, 6).forEach(rec => {
      const confPct = Math.round(rec.confidence * 100);
      const isStu = (rec.user_type === 'Student');
      const punchType = rec.punch_type || 'CHECK_IN';
      const isLate = rec.is_late ? `<span class="badge late">LATE</span>` : `<span class="badge ontimed">ON TIME</span>`;
      const recJson = JSON.stringify(rec).replace(/"/g, '&quot;');
      const avatarHtml = rec.snapshot_url
        ? `<img src="${rec.snapshot_url}" class="punch-thumb" alt="Proof" onclick="openForensicModal(${recJson})" title="Click to inspect Forensic Telemetry">`
        : `👤`;

      rowsHtml += `
        <tr>
          <td class="user-cell" style="cursor:pointer;" onclick="openForensicModal(${recJson})">
            <div class="avatar-ring">${avatarHtml}</div>
            <div>
              <strong>${rec.user_name}</strong>
              <div style="font-size:0.75rem; color:#94a3b8;">${rec.user_type || 'Employee'}</div>
            </div>
          </td>
          <td>
            <span class="badge ${isStu ? 'student' : 'office'}">${isStu ? '🎓 Student' : '🏢 Staff'}</span>
          </td>
          <td>
            <span class="punch-pill ${punchType === 'CHECK_IN' ? 'in' : 'out'}">${punchType}</span>
          </td>
          <td>${isLate}</td>
          <td>${rec.time}</td>
          <td>
            <div class="conf-bar-wrapper">
              <div class="conf-bar" style="width: ${confPct}%"></div>
              <span>${confPct}%</span>
            </div>
          </td>
          <td><span class="badge present">${rec.status}</span></td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;
  } catch (e) {
    console.warn("Feed fetch error:", e);
  }
}

// HUD Theme Switching
async function switchTheme(themeName) {
  document.querySelectorAll(".theme-dot").forEach(d => d.classList.remove("active"));
  const activeDot = document.querySelector(`.theme-dot.${themeName}`);
  if (activeDot) activeDot.classList.add("active");

  try {
    await fetch("/api/set_theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: themeName })
    });
  } catch (e) {
    console.error("Theme switch error:", e);
  }
}

// Camera Source Switching
function onSourceChange(val) {
  const ipWrap = document.getElementById("ipcam-input-wrap");
  if (val === "ipcam") {
    if (ipWrap) ipWrap.style.display = "flex";
  } else {
    if (ipWrap) ipWrap.style.display = "none";
    switchCameraSource(val);
  }
}

function connectIpCam() {
  const url = document.getElementById("ipcam-url").value.trim();
  if (url) {
    switchCameraSource(url);
  }
}

async function switchCameraSource(src) {
  try {
    const res = await fetch("/api/set_camera", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: src })
    });
    const data = await res.json();
    const badge = document.getElementById("cam-active-badge");
    if (badge) badge.textContent = `SOURCE: ${data.active_mode.toUpperCase()}`;
  } catch (e) {
    console.error("Camera switch error:", e);
  }
}

// Chart.js Futuristic Visualizations
let hourlyChart = null;
let deptChart = null;

function initCharts() {
  const hourlyCtx = document.getElementById("hourly-chart");
  const deptCtx = document.getElementById("dept-chart");

  if (hourlyCtx && window.Chart) {
    hourlyChart = new Chart(hourlyCtx, {
      type: "bar",
      data: {
        labels: ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
        datasets: [{
          label: "Arrivals",
          data: [0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 1, 0],
          backgroundColor: "rgba(0, 243, 255, 0.4)",
          borderColor: "#00f3ff",
          borderWidth: 1.5,
          borderRadius: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { color: "rgba(0, 243, 255, 0.08)" },
            ticks: { color: "#94a3b8", font: { family: "Orbitron", size: 10 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(0, 243, 255, 0.08)" },
            ticks: { color: "#94a3b8", stepSize: 1, font: { family: "Orbitron", size: 10 } }
          }
        }
      }
    });
  }

  if (deptCtx && window.Chart) {
    deptChart = new Chart(deptCtx, {
      type: "doughnut",
      data: {
        labels: ["Engineering", "Operations", "AI Research"],
        datasets: [{
          data: [1, 1, 1],
          backgroundColor: [
            "rgba(0, 243, 255, 0.7)",
            "rgba(0, 255, 136, 0.7)",
            "rgba(157, 78, 221, 0.7)"
          ],
          borderColor: "#0a0f1a",
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "right",
            labels: { color: "#e2e8f0", font: { family: "Rajdhani", size: 13 } }
          }
        }
      }
    });
  }
}

async function refreshAnalytics() {
  try {
    const res = await fetch("/api/analytics");
    const data = await res.json();

    if (hourlyChart && data.hourly) {
      hourlyChart.data.labels = data.hourly.labels;
      hourlyChart.data.datasets[0].data = data.hourly.data;
      hourlyChart.update();
    }

    if (deptChart && data.departments && data.departments.labels.length > 0) {
      deptChart.data.labels = data.departments.labels;
      deptChart.data.datasets[0].data = data.departments.data;
      deptChart.update();
    }
  } catch (e) {
    console.warn("Analytics fetch error:", e);
  }
}

// Voice Activated HUD Commands
let recognition = null;
let isVoiceListening = false;

function initVoiceControl() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    console.warn("Speech recognition not supported in this browser.");
    return;
  }

  recognition = new SpeechRec();
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = function() {
    isVoiceListening = true;
    updateVoiceUI(true, "LISTENING...");
  };

  recognition.onend = function() {
    isVoiceListening = false;
    updateVoiceUI(false, "VOICE: READY");
  };

  recognition.onerror = function(e) {
    console.warn("Speech recognition error:", e);
    isVoiceListening = false;
    updateVoiceUI(false, "VOICE: ERROR");
  };

  recognition.onresult = function(event) {
    const transcript = event.results[event.results.length - 1][0].transcript.trim().toLowerCase();
    console.log("Voice Command Received:", transcript);
    handleVoiceCommand(transcript);
  };
}

function toggleVoiceControl() {
  if (!recognition) initVoiceControl();
  if (!recognition) {
    alert("Speech recognition is not supported in this browser. Please use Chrome/Edge.");
    return;
  }

  if (isVoiceListening) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch(e) {
      console.warn("Could not start recognition:", e);
    }
  }
}

function updateVoiceUI(active, text) {
  const pill = document.getElementById("voice-status-pill");
  const txt = document.getElementById("voice-status-text");
  if (pill) pill.classList.toggle("listening", active);
  if (txt) txt.textContent = text;
}

function handleVoiceCommand(cmd) {
  playChime(true);
  if (cmd.includes("matrix") || cmd.includes("green")) {
    switchTheme("matrix");
  } else if (cmd.includes("cyan") || cmd.includes("blue")) {
    switchTheme("cyan");
  } else if (cmd.includes("synthwave") || cmd.includes("magenta") || cmd.includes("purple")) {
    switchTheme("synthwave");
  } else if (cmd.includes("amber") || cmd.includes("gold") || cmd.includes("yellow")) {
    switchTheme("amber");
  } else if (cmd.includes("cube")) {
    toggleHudElement("cube");
  } else if (cmd.includes("mesh")) {
    toggleHudElement("mesh");
  } else if (cmd.includes("laser")) {
    toggleHudElement("laser");
  } else if (cmd.includes("reticle")) {
    toggleHudElement("reticle");
  } else if (cmd.includes("report")) {
    window.location.href = "/report";
  } else if (cmd.includes("badge") || cmd.includes("id card") || cmd.includes("card")) {
    window.location.href = "/idcard";
  } else if (cmd.includes("alert")) {
    window.location.href = "/alerts";
  } else if (cmd.includes("log") || cmd.includes("record")) {
    window.location.href = "/records";
  }
}

// Biometric Forensic Lightbox Modal
function openForensicModal(data) {
  let modal = document.getElementById("forensic-modal");
  if (!modal) {
    const modalHtml = `
      <div id="forensic-modal" class="cyber-modal-overlay" onclick="closeForensicModal(event)">
        <div class="cyber-modal" onclick="event.stopPropagation()">
          <div class="modal-header">
            <div class="modal-title"><span class="bracket">[</span> BIOMETRIC FORENSIC AUDIT EVIDENCE <span class="bracket">]</span></div>
            <button class="modal-close-btn" onclick="closeForensicModal()">✕</button>
          </div>
          <div class="modal-body">
            <div class="modal-img-col">
              <img id="modal-img" src="" alt="Forensic Snapshot" class="forensic-large-img">
            </div>
            <div class="modal-info-col">
              <h3 id="modal-name">Subject Name</h3>
              <div class="modal-role" id="modal-role">Role / Department</div>
              <div class="telemetry-grid">
                <div class="t-row"><span class="t-label">COHORT / TYPE:</span><span class="t-val" id="modal-type">Employee</span></div>
                <div class="t-row"><span class="t-label">PUNCH DIRECTION:</span><span class="t-val" id="modal-punch">CHECK_IN</span></div>
                <div class="t-row"><span class="t-label">TIMESTAMP:</span><span class="t-val" id="modal-time">09:15:22</span></div>
                <div class="t-row"><span class="t-label">DATE:</span><span class="t-val" id="modal-date">2026-11-20</span></div>
                <div class="t-row"><span class="t-label">PUNCTUALITY:</span><span class="t-val" id="modal-punctuality">ON TIME</span></div>
                <div class="t-row"><span class="t-label">MATCH CONFIDENCE:</span><span class="t-val text-cyan" id="modal-conf">98.4%</span></div>
                <div class="t-row"><span class="t-label">LIVENESS STATUS:</span><span class="t-val text-green" id="modal-liveness">PASSED (Micro-Motion Verified)</span></div>
                <div class="t-row"><span class="t-label">EMOTION TELEMETRY:</span><span class="t-val text-green" id="modal-emotion">FOCUSED / ENGAGED</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    modal = document.getElementById("forensic-modal");
  }

  document.getElementById("modal-img").src = data.snapshot_url || "/static/img/placeholder.png";
  document.getElementById("modal-name").textContent = data.user_name || "Unknown Profile";
  document.getElementById("modal-role").textContent = `${data.user_type || 'Member'} // Forensic Log #${data.id || '-'}`;
  document.getElementById("modal-type").textContent = data.user_type || "Employee";
  document.getElementById("modal-punch").textContent = data.punch_type || "CHECK_IN";
  document.getElementById("modal-time").textContent = data.time || "-";
  document.getElementById("modal-date").textContent = data.date || "-";
  
  const puncEl = document.getElementById("modal-punctuality");
  if (data.is_late) {
    puncEl.textContent = "LATE ARRIVAL";
    puncEl.className = "t-val text-red";
  } else {
    puncEl.textContent = "ON TIME";
    puncEl.className = "t-val text-green";
  }

  const confVal = typeof data.confidence === 'number' ? Math.round(data.confidence * 100) : (data.confidence || 98);
  document.getElementById("modal-conf").textContent = `${confVal}% Match`;

  modal.style.display = "flex";
}

function closeForensicModal(e) {
  const modal = document.getElementById("forensic-modal");
  if (modal) modal.style.display = "none";
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeForensicModal();
});

// Server-Sent Events (SSE) Push Stream
function initSSEClient() {
  if (!window.EventSource) return;
  const es = new EventSource('/api/events');

  es.onmessage = function(e) {
    try {
      const payload = JSON.parse(e.data);
      if (payload.type === "attendance") {
        playChime(true);
        if (window.pulseHologramVerified) {
          window.pulseHologramVerified(payload.data.user_name);
        }
        refreshStats();
        refreshFeed();
        refreshAnalytics();
      } else if (payload.type === "security_alert") {
        const badge = document.getElementById("alert-badge-count");
        if (badge) {
          badge.textContent = parseInt(badge.textContent || 0) + 1;
        }
      }
    } catch(err) {}
  };

  es.onerror = function() {
    es.close();
    setTimeout(initSSEClient, 4000);
  };
}
initSSEClient();

async function triggerWalkUpTest() {
  const sel = document.getElementById("sim-subject-select");
  const subject = sel ? sel.value : "Chiru";
  try {
    const res = await fetch("/api/simulate_subject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject: subject })
    });
    const data = await res.json();
    playChime(true);
    const camSelect = document.getElementById("cam-source-select");
    if (camSelect) camSelect.value = "simulated";
    const badge = document.getElementById("cam-active-badge");
    if (badge) badge.textContent = `SOURCE: SIMULATOR [${subject.toUpperCase()}]`;
  } catch (e) {
    console.error("Walk-up test error:", e);
  }
}

// NEXUS AI Natural Language Query Assistant
async function submitAssistantQuery() {
  const inp = document.getElementById("assistant-query-input");
  if (!inp) return;
  const query = inp.value.trim();
  if (!query) return;

  const replyBox = document.getElementById("assistant-reply-box");
  const replyText = document.getElementById("assistant-reply-text");
  if (replyBox) replyBox.style.display = "block";
  if (replyText) replyText.textContent = "Processing natural language biometric query...";

  try {
    const res = await fetch("/api/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query })
    });
    const data = await res.json();
    if (replyText) replyText.textContent = data.speech;

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(data.speech);
      utter.rate = 1.05;
      utter.pitch = 1.0;
      window.speechSynthesis.speak(utter);
    }
  } catch(e) {
    if (replyText) replyText.textContent = "Query error: " + e.message;
  }
}

function startAssistantVoiceInput() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert("Speech recognition not supported in this browser. Please type your query in the input box.");
    return;
  }
  const micBtn = document.getElementById("btn-assistant-mic");
  if (micBtn) micBtn.textContent = "🔴 Listening...";
  const rec = new SpeechRec();
  rec.lang = "en-US";
  rec.onresult = function(e) {
    const transcript = e.results[0][0].transcript;
    const inp = document.getElementById("assistant-query-input");
    if (inp) inp.value = transcript;
    submitAssistantQuery();
  };
  rec.onend = function() {
    if (micBtn) micBtn.textContent = "🎙️ Speak";
  };
  rec.start();
}

// DEFCON Threat Level Controller
let currentDefcon = 4;

async function cycleDefconLevel() {
  currentDefcon = currentDefcon === 1 ? 4 : currentDefcon - 1;
  try {
    const res = await fetch("/api/set_defcon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: currentDefcon })
    });
    const data = await res.json();
    updateDefconUI(data.defcon);
  } catch(e) {}
}

function updateDefconUI(lvl) {
  currentDefcon = lvl;
  const txt = document.getElementById("defcon-text");
  if (!txt) return;
  const map = {
    4: "LEVEL 4 [NORMAL]",
    3: "LEVEL 3 [GUARDED]",
    2: "LEVEL 2 [ELEVATED]",
    1: "LEVEL 1 [LOCKDOWN]"
  };
  txt.textContent = map[lvl] || "NORMAL";
  txt.className = `defcon-${lvl}`;
  if (lvl === 1) {
    playChime(false);
  }
}

// Polling interval (Graceful fallback)
setInterval(refreshStats, 3000);
setInterval(refreshAnalytics, 10000);
refreshStats();
refreshFeed();
setTimeout(initCharts, 500);
setTimeout(refreshAnalytics, 1000);

// Mega-Menu Apps Matrix Drawer Toggle
function toggleAppsMatrix() {
  const drawer = document.getElementById("apps-matrix-drawer");
  if (drawer) {
    drawer.classList.toggle("open");
  }
}

document.addEventListener("click", function(e) {
  const drawer = document.getElementById("apps-matrix-drawer");
  const launcher = e.target.closest(".apps-launcher-btn");
  if (drawer && drawer.classList.contains("open") && !drawer.contains(e.target) && !launcher) {
    drawer.classList.remove("open");
  }
});

