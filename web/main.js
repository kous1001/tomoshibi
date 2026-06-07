/* 灯 Tomoshibi — 会話オーケストレーション
 * Live2D起動 → 挨拶 → 対話。応答を吹き出しに出し、TTS音声を再生しながら口パク(RMS)。
 * sobani main.js の handleSpeak/playSpeech を移植・簡約（オンボーディング/設定/通話は除去）。
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  // リップシンク調整定数: floor=無音下限 / gain=開き倍率 / max=最大開き / attack,release=開閉速度
  const LIP = { floor: 0.06, gain: 15.0, max: 0.9, attack: 0.6, release: 0.25 };

  let audioCtx = null;
  let rafId = 0;
  let speakToken = 0;
  let currentSource = null; // 現在再生中の音声。次の再生前に必ず停止して重複を防ぐ

  const els = {
    bubble: $("bubble"),
    charLabel: $("char-label"),
    loading: $("loading"),
    listening: $("listening"),
    chatForm: $("chat-form"),
    chatInput: $("chat-input"),
    send: $("send"),
  };

  // ---- 音声 + 口パク ----
  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AC();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
  }

  function b64ToArrayBuffer(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  function setMouth(v) {
    if (window.Popo) window.Popo.setMouth(v);
  }

  // 現在の音声を止める（重複再生の防止）。会話・見守りの両経路が共有する。
  function stopSpeech() {
    speakToken++; // 旧口パクループを無効化
    cancelAnimationFrame(rafId);
    if (currentSource) {
      try {
        currentSource.onended = null; // 停止由来の onended で口を閉じない
        currentSource.stop();
        currentSource.disconnect();
      } catch (e) {
        /* 既に停止済み等は無視 */
      }
      currentSource = null;
    }
    setMouth(0);
  }

  // 再生終了で解決する Promise。RMSで口パク。常に「1音声だけ」を保証する。
  async function playSpeech(b64Wav) {
    if (!b64Wav) return;
    ensureAudio();
    const buffer = await audioCtx.decodeAudioData(b64ToArrayBuffer(b64Wav));

    stopSpeech(); // ← 前の音声を確実に止めてから次を鳴らす（最新発話が優先）
    const myToken = speakToken;

    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    const data = new Uint8Array(analyser.fftSize);
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    currentSource = source;

    let mouth = 0;
    function tick() {
      if (myToken !== speakToken) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      let target = ((rms - LIP.floor) * LIP.gain) / (1 - LIP.floor);
      target = Math.max(0, Math.min(LIP.max, target));
      const k = target > mouth ? LIP.attack : LIP.release;
      mouth += (target - mouth) * k;
      setMouth(mouth);
      rafId = requestAnimationFrame(tick);
    }

    return new Promise((resolve) => {
      source.onended = () => {
        if (myToken === speakToken) {
          cancelAnimationFrame(rafId);
          setMouth(0);
          currentSource = null;
        }
        resolve();
      };
      tick();
      source.start();
    });
  }

  // ---- 表示 ----
  function showBubble(text) {
    els.bubble.textContent = text;
    els.bubble.style.animation = "none";
    void els.bubble.offsetWidth; // reflow でアニメ再生
    els.bubble.style.animation = "";
  }

  function setBusy(busy) {
    els.send.disabled = busy;
    els.chatInput.disabled = busy;
    els.listening.hidden = !busy;
  }

  async function handleSpeak(data) {
    if (!data) return;
    if (data.character_name) els.charLabel.textContent = data.character_name;
    if (data.text) showBubble(data.text);
    if (data.audio) {
      try {
        await playSpeech(data.audio);
      } catch (e) {
        console.warn("音声再生に失敗:", e);
      }
    }
  }

  // ---- API ----
  async function api(path, opts) {
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(path + " -> " + res.status);
    return res.json();
  }

  // 起動時はテキストのみ表示（音声はブラウザ仕様で操作前に鳴らせない）。
  // 実際の挨拶発話は会話開始（🎤）時に conversation.js が行う。
  async function showGreeting() {
    try {
      const data = await api("/api/greet", { method: "POST" });
      if (data && data.text) showBubble(data.text);
    } catch (e) {
      console.error(e);
    } finally {
      els.chatInput.focus();
    }
  }

  async function sendChat(text) {
    setBusy(true);
    try {
      const data = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      await handleSpeak(data);
    } catch (e) {
      console.error(e);
      showBubble("ごめんなさい、うまく聞き取れませんでした。");
    } finally {
      setBusy(false);
      els.chatInput.focus();
    }
  }

  // ---- 起動 ----
  async function bootLive2D() {
    try {
      await window.Popo.init($("live2d"));
      els.loading.hidden = true;
    } catch (e) {
      els.loading.textContent = "キャラの読み込みに失敗しました: " + e.message;
      console.error(e);
    }
  }

  els.chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    ensureAudio();
    const text = els.chatInput.value.trim();
    if (!text || els.send.disabled) return;
    els.chatInput.value = "";
    sendChat(text);
  });

  // 音声入力（🎤ハンズフリー会話）は conversation.js が担当する。
  // ここでは共有ヘルパだけ公開する。
  window.Tomoshibi = { ensureAudio, playSpeech, stopSpeech, showBubble, handleSpeak, api };

  // 時計（毎秒更新）
  function updateClock() {
    const t = new Date();
    const hh = String(t.getHours()).padStart(2, "0");
    const mm = String(t.getMinutes()).padStart(2, "0");
    const icon = t.getHours() >= 18 || t.getHours() < 6 ? "🌙" : "☀️";
    $("clock").textContent = `${icon} ${hh}:${mm}`;
  }
  updateClock();
  setInterval(updateClock, 1000);

  // 初期化
  (async function start() {
    await bootLive2D();
    await showGreeting(); // テキストのみ。音声は🎤会話開始時に。
  })();
})();
