/* 灯 Tomoshibi — ハンズフリー音声会話モード（音声のみ）
 * 🎤を1回押すと会話開始（マイク許可＋音声解禁＋挨拶発話）、以降は VAD で自動ターン制御。
 * もう一度押すと終了。sobani web/call.js の VAD を音声のみに簡略化して流用。
 * 既存資産 window.Tomoshibi（ensureAudio/playSpeech/showBubble/handleSpeak/api）を再利用。
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const T = () => window.Tomoshibi;

  // VAD チューニング（sobani 実績値）
  const VAD = {
    arm: 0.03, // この音量で即録音開始（語頭を取りこぼさない）
    on: 0.045, // 明確な発話とみなすRMS
    off: 0.02, // 発話継続とみなすRMS（小声/語尾でも切らない＝ヒステリシス）
    minSpeechMs: 200, // 明確な声がこれだけ続けば本物の発話と確定
    softConfirmMs: 600, // 小声でもこれだけ続けば発話と確定
    silenceMs: 1400, // この長さ黙ったらターン終了
    maxUnconfirmedMs: 1500, // 確定しないまま続いたらノイズとして破棄
    maxTurnMs: 30000, // 1ターンの最大長（保険）
  };
  const MIN_TURN_BYTES = 1200; // 短すぎる録音は捨てる

  let stream = null;
  let convCtx = null;
  let analyser = null;
  let timeData = null;
  let rafId = 0;

  let active = false;
  let listening = false;
  let speaking = false; // 灯の発話/処理中（VAD一時停止＋マイクOFF）
  let turnRec = null;
  let recording = false;
  let confirmed = false;
  let discardTurn = false;
  let turnChunks = [];
  let loudMs = 0;
  let voicedMs = 0;
  let lastLoud = 0;
  let turnStart = 0;
  let prevNow = 0;
  let turnExt = "webm";

  const micBtn = $("mic");
  const statusEl = $("conv-status");

  function setStatus(msg) {
    if (statusEl) {
      statusEl.textContent = msg;
      statusEl.hidden = !msg;
    }
  }

  // 灯の発話中はマイクtrackを無効化し、TTSがマイクに回り込む自己誤検知を防ぐ
  function setSpeaking(v) {
    speaking = v;
    if (stream) stream.getAudioTracks().forEach((t) => (t.enabled = !v));
  }

  function pickAudioMime() {
    for (const m of ["audio/webm", "audio/mp4", "audio/ogg"]) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) {
        turnExt = m.split("/")[1];
        return m;
      }
    }
    turnExt = "webm";
    return "";
  }

  function setActiveUI(on) {
    if (micBtn) {
      micBtn.classList.toggle("recording", on);
      micBtn.textContent = on ? "⏹" : "🎤";
      micBtn.title = on ? "会話をおわる" : "会話をはじめる";
    }
    // 会話中はテキスト入力を無効化（操作の競合を避ける）
    const input = $("chat-input");
    const send = $("send");
    if (input) input.disabled = on;
    if (send) send.disabled = on;
  }

  // ---- 開始 / 終了（ボタン2回の唯一の操作） ----
  async function startConversation() {
    if (active) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      T().showBubble("マイクを使えませんでした。ブラウザのマイク許可を確認してくださいね。");
      console.error(e);
      return;
    }
    active = true;
    T().ensureAudio(); // ユーザー操作（クリック）の文脈で音声を解禁

    const AC = window.AudioContext || window.webkitAudioContext;
    convCtx = new AC();
    const src = convCtx.createMediaStreamSource(stream);
    analyser = convCtx.createAnalyser();
    analyser.fftSize = 1024;
    timeData = new Uint8Array(analyser.fftSize);
    src.connect(analyser); // destination には繋がない（ハウリング防止）

    setActiveUI(true);
    pickAudioMime();

    // 挨拶を発話（ここで初めて音声が鳴る＝自動再生ブロックの解消）
    setSpeaking(true);
    setStatus("つないでいます…");
    try {
      const data = await T().api("/api/greet", { method: "POST" });
      await T().handleSpeak(data);
    } catch (e) {
      console.warn(e);
    }
    if (!active) return; // 挨拶中に終了された場合
    setSpeaking(false);

    listening = true;
    lastLoud = performance.now();
    prevNow = 0;
    rafId = requestAnimationFrame(vad);
    setStatus("聞いています。話しかけてください🎤");
  }

  function endConversation() {
    active = false;
    listening = false;
    cancelAnimationFrame(rafId);
    if (turnRec && recording) {
      try {
        turnRec.stop();
      } catch (e) {
        /* noop */
      }
    }
    recording = false;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    if (convCtx) {
      try {
        convCtx.close();
      } catch (e) {
        /* noop */
      }
      convCtx = null;
    }
    setActiveUI(false);
    setStatus("");
  }

  // ---- VAD ループ ----
  function rms() {
    analyser.getByteTimeDomainData(timeData);
    let sum = 0;
    for (let i = 0; i < timeData.length; i++) {
      const v = (timeData[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / timeData.length);
  }

  function vad() {
    rafId = requestAnimationFrame(vad);
    if (!listening || speaking) {
      prevNow = 0;
      return;
    }
    const now = performance.now();
    const dt = prevNow ? now - prevNow : 16;
    prevNow = now;
    const level = rms();

    if (!recording) {
      if (level > VAD.arm) startTurn(now);
      return;
    }

    if (level > VAD.off) {
      lastLoud = now;
      voicedMs += dt;
    }
    if (level > VAD.on) loudMs += dt;
    if (!confirmed && (loudMs >= VAD.minSpeechMs || voicedMs >= VAD.softConfirmMs)) {
      confirmed = true;
      setStatus("聞いています…🎤");
    }

    if (!confirmed) {
      if (now - lastLoud >= VAD.silenceMs || now - turnStart >= VAD.maxUnconfirmedMs) abortTurn();
      return;
    }
    if (now - lastLoud >= VAD.silenceMs || now - turnStart >= VAD.maxTurnMs) stopTurn();
  }

  function startTurn(now) {
    const mime = pickAudioMime();
    const audioStream = new MediaStream(stream.getAudioTracks());
    turnRec = mime
      ? new MediaRecorder(audioStream, { mimeType: mime })
      : new MediaRecorder(audioStream);
    turnChunks = [];
    discardTurn = false;
    turnRec.ondataavailable = (e) => e.data && e.data.size && turnChunks.push(e.data);
    turnRec.onstop = () => {
      const blob = new Blob(turnChunks, { type: turnRec.mimeType || "audio/webm" });
      if (discardTurn) {
        discardTurn = false;
        return;
      }
      processTurn(blob);
    };
    turnRec.start();
    recording = true;
    confirmed = false;
    loudMs = 0;
    voicedMs = 0;
    turnStart = now;
    lastLoud = now;
  }

  function stopTurn() {
    recording = false;
    discardTurn = false;
    try {
      turnRec.stop();
    } catch (e) {
      /* noop */
    }
  }

  function abortTurn() {
    recording = false;
    discardTurn = true;
    try {
      turnRec.stop();
    } catch (e) {
      /* noop */
    }
    setStatus("聞いています。話しかけてください🎤");
  }

  // ---- 1ターン処理: 文字起こし → 応答 → 発話 ----
  function blobToB64(blob) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        const s = String(r.result);
        resolve(s.slice(s.lastIndexOf(",") + 1));
      };
      r.onerror = reject;
      r.readAsDataURL(blob);
    });
  }

  async function processTurn(blob) {
    if (!active) return;
    if (!blob || blob.size < MIN_TURN_BYTES) {
      setStatus("もう一度お話しください🎤");
      return;
    }
    setSpeaking(true); // 処理＋返答中はマイクOFF＋VAD停止
    setStatus("聞き取っています…");
    try {
      const audio = await blobToB64(blob);
      const t = await T().api("/api/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audio, ext: turnExt }),
      });
      const text = (t.text || "").trim();
      if (!text) {
        setStatus("うまく聞き取れませんでした。もう一度お願いします🎤");
        return;
      }
      setStatus("「" + text + "」…考えています");
      const reply = await T().api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      await T().handleSpeak(reply); // 吹き出し＋音声＋口パク（再生終了で解決）
    } catch (e) {
      console.error(e);
      setStatus("通信に失敗しました。もう一度お試しください");
    } finally {
      setSpeaking(false);
      if (active) {
        lastLoud = performance.now();
        setStatus("聞いています。話しかけてください🎤");
      }
    }
  }

  // ---- 配線: 🎤 を開始/終了トグルに ----
  if (micBtn) {
    micBtn.addEventListener("click", () => (active ? endConversation() : startConversation()));
  }
})();
