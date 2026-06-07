/* 灯 Tomoshibi — 見守りパネル
 * 2秒ごとに /api/guardian/tick をポーリングして state を描画（S1→S2→S3 を自動進行）。
 * 操作ボタンで fall/event/reset を叩く。見守り発話(speech)は seq 変化時に再生＋吹き出し。
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const TICK_MS = 2000;
  let lastSpeechSeq = 0;
  let activeDemo = 0; // 再生中のデモ番号（0=なし/実カメラ）
  let camRunning = false;

  const els = {
    status: $("status"),
    stLabel: $("st-label"),
    stDesc: $("st-desc"),
    timeline: $("timeline"),
    emergency: $("emergency"),
    eScript: $("e-script"),
    eFacts: $("e-facts"),
    profile: $("profile-card"),
    backends: $("backends"),
  };

  function api(path, opts) {
    // main.js の共有ヘルパがあれば使う
    if (window.Tomoshibi && window.Tomoshibi.api) return window.Tomoshibi.api(path, opts);
    return fetch(path, opts).then((r) => r.json());
  }

  function renderStatus(s) {
    els.status.className = "status tone-" + (s.tone || "ok");
    els.stLabel.textContent = s.phase_icon + " " + s.phase_label;
    els.stDesc.textContent = s.phase_desc;
  }

  function renderTimeline(items) {
    els.timeline.innerHTML = "";
    (items || []).forEach((e) => {
      const div = document.createElement("div");
      div.className = "tl kind-" + e.kind;
      div.innerHTML =
        '<span class="t-time">' + e.time + "</span><span>" + e.icon + "</span><span>" +
        escapeHtml(e.text) + "</span>";
      els.timeline.appendChild(div);
    });
  }

  function renderEmergency(em) {
    if (!em || !em.active || !em.script) {
      els.emergency.hidden = true;
      return;
    }
    els.emergency.hidden = false;
    els.eScript.textContent = em.script;
    els.eFacts.innerHTML = "";
    (em.facts || []).forEach((f) => {
      const span = document.createElement("span");
      span.textContent = "・" + f;
      els.eFacts.appendChild(span);
    });
  }

  function renderProfile(p) {
    if (!p) return;
    const age = p.age != null ? p.age + "歳" : "—";
    els.profile.innerHTML =
      "<b>" + escapeHtml(p.name) + "</b> さん（" + age + "・" + escapeHtml(p.sex || "—") + "）<br>" +
      "📍 " + escapeHtml(p.address || "—") + "<br>" +
      "🩺 持病: " + escapeHtml((p.conditions || []).join("、") || "—") + "<br>" +
      "💊 服薬: " + escapeHtml((p.medications || []).join("、") || "—") + "<br>" +
      '<span class="pc-warn">⚠️ アレルギー: ' + escapeHtml((p.allergies || []).join("、") || "—") + "</span><br>" +
      '<span class="pc-note">※ 端末内に保存され、外部送信されません。</span>';
  }

  function renderBackends(b) {
    if (!b) return;
    els.backends.innerHTML = "";
    Object.keys(b).forEach((k) => {
      const span = document.createElement("span");
      span.textContent = k + ":" + b[k];
      els.backends.appendChild(span);
    });
  }

  // 見守りが発話したら、ブラウザでも声＋吹き出しを出す
  function handleSpeech(sp) {
    if (!sp || sp.seq <= lastSpeechSeq) return;
    lastSpeechSeq = sp.seq;
    if (window.Tomoshibi) {
      if (sp.text) window.Tomoshibi.showBubble(sp.text);
      if (sp.audio) window.Tomoshibi.playSpeech(sp.audio).catch(() => {});
    }
  }

  function renderCamera(cam) {
    const status = $("cam-status");
    const btn = $("btn-cam");
    const img = $("guardian-cam");
    const live = $("cam-live");
    const ph = $("cam-placeholder");
    if (!cam) return;
    camRunning = cam.running;
    if (!cam.running) activeDemo = 0;
    // デモボタンのハイライト（再生中のデモのみ）
    document.querySelectorAll(".cam-demo").forEach((b) => {
      b.classList.toggle("on", cam.running && parseInt(b.dataset.demo, 10) === activeDemo);
    });
    if (cam.running) {
      // 実カメラ時のみ btn を OFF表示。デモ再生中は live 切替用に「📷 ON」のまま。
      btn.textContent = activeDemo ? "📷 ON" : "OFF";
      btn.classList.toggle("on", activeDemo === 0);
      live.hidden = false;
      ph.hidden = true;
      img.classList.add("on");
      if (!img.src || img.dataset.on !== "1") {
        img.src = "/api/guardian/camera.mjpg?ts=" + Date.now();
        img.dataset.on = "1";
      }
      status.textContent =
        (activeDemo ? "デモ" + activeDemo + " 再生中" : "見守り中") + " — 姿勢を解析しています";
    } else {
      btn.textContent = "📷 ON";
      btn.classList.remove("on");
      live.hidden = true;
      img.classList.remove("on");
      img.removeAttribute("src");
      img.dataset.on = "0";
      ph.hidden = false;
      const phText = ph.querySelector("span:last-child");
      if (cam.error) {
        status.textContent = "エラー: " + cam.error;
        if (phText) phText.textContent = "カメラエラー: " + cam.error;
      } else {
        status.textContent = "停止中";
        if (phText) phText.textContent = "カメラOFF — 「📷 ON」かデモを選択";
      }
    }
  }

  function render(s) {
    if (!s) return;
    renderStatus(s);
    renderTimeline(s.timeline);
    renderEmergency(s.emergency);
    renderProfile(s.profile);
    renderBackends(s.backends);
    renderCamera(s.camera);
    handleSpeech(s.speech);
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  async function post(path) {
    try {
      render(await api(path, { method: "POST" }));
    } catch (e) {
      console.error(e);
    }
  }

  async function postEvent(event) {
    try {
      render(
        await api("/api/guardian/event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event }),
        })
      );
    } catch (e) {
      console.error(e);
    }
  }

  // ---- 配線 ----
  $("btn-fall").addEventListener("click", () => {
    if (window.Tomoshibi) window.Tomoshibi.ensureAudio(); // 発話再生の許可をユーザー操作で取得
    post("/api/guardian/fall");
  });
  $("btn-ok").addEventListener("click", () => postEvent("resident_ok"));
  $("btn-help").addEventListener("click", () => postEvent("resident_help"));
  $("btn-ack").addEventListener("click", () => postEvent("family_ack"));
  $("btn-reset").addEventListener("click", () => post("/api/guardian/reset"));
  async function startCamera(source, demo) {
    activeDemo = source === "demo" ? demo : 0;
    try {
      render(
        await api("/api/guardian/camera/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source, demo: demo || 1 }),
        })
      );
    } catch (e) {
      console.error(e);
    }
  }
  $("btn-cam").addEventListener("click", async () => {
    if (window.Tomoshibi) window.Tomoshibi.ensureAudio(); // 発話再生の許可を取得
    if (camRunning && activeDemo === 0) {
      post("/api/guardian/camera/stop"); // 実カメラ稼働中 → 停止
    } else {
      await post("/api/guardian/camera/stop"); // デモ中なら止めてから実カメラへ
      startCamera("camera");
    }
  });
  document.querySelectorAll(".cam-demo").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (window.Tomoshibi) window.Tomoshibi.ensureAudio();
      const n = parseInt(btn.dataset.demo, 10);
      if (camRunning && activeDemo === n) {
        post("/api/guardian/camera/stop"); // 同じデモを再クリック → 停止
        return;
      }
      await post("/api/guardian/camera/stop"); // 動作中なら止めてから
      await post("/api/guardian/reset"); // 毎デモ前に見守りをクリーンに
      startCamera("demo", n);
    });
  });

  // ---- ポーリング（タイムアウト自動進行） ----
  async function loop() {
    await post("/api/guardian/tick");
  }

  // 起動時: 見守りをクリーンにリセットし、過去の発話(seq)はベースライン化して再生しない。
  // （サーバ状態は永続するため、前回の緊急が残って読み上げられるのを防ぐ）
  api("/api/guardian/reset", { method: "POST" })
    .then((s) => {
      lastSpeechSeq = s && s.speech ? s.speech.seq : 0; // ベースライン（再生せず）
      render(s);
      setInterval(loop, TICK_MS); // 初期化後にポーリング開始
    })
    .catch((e) => {
      console.error(e);
      setInterval(loop, TICK_MS);
    });
})();
