// app.js — wires the game board and the brain visualization to the backend
// (or, with ?mock=1, to a fully local simulation so the page works standalone).

import { Board } from './board.js';
import { Brain } from './brain.js';

const params = new URLSearchParams(location.search);
const MOCK = params.get('mock') === '1';

const statusEl = document.getElementById('status-line');
const newGameBtn = document.getElementById('new-game-btn');
const flyFirstCheckbox = document.getElementById('fly-first-checkbox');
const viewSelect = document.getElementById('view-select');
const decaySlider = document.getElementById('decay-slider');
const brightnessSlider = document.getElementById('brightness-slider');
const brainHeader = document.getElementById('brain-header');
const brainPanel = document.getElementById('brain-panel');
const connDot = document.getElementById('conn-dot');
const muteBtn = document.getElementById('mute-btn');
const flyAvatar = document.getElementById('fly-avatar');
const scoreYouEl = document.getElementById('score-you');
const scoreDrawsEl = document.getElementById('score-draws');
const scoreFlyEl = document.getElementById('score-fly');

let ws = null;
let reconnectDelay = 500;
let currentState = { board: Array(9).fill(0), status: 'x_to_move', human: 1, fly: 2, thinking: false };

function setStatus(text) {
  statusEl.textContent = text;
}

function statusText(state) {
  if (state.status === 'x_wins' || state.status === 'o_wins') {
    const winner = state.status === 'x_wins' ? 1 : 2;
    return winner === state.human ? 'You win!' : 'Fly wins!';
  }
  if (state.status === 'draw') return 'Draw.';
  if (state.thinking) return 'Fly is thinking…';
  const toMove = state.status === 'x_to_move' ? 1 : 2;
  return toMove === state.human ? `Your move (${state.human === 1 ? 'X' : 'O'})` : 'Fly is thinking…';
}

// ---------- Scoreboard (persisted in localStorage) ----------

const SCORE_KEY = 'fable_scoreboard_v1';
let scores = loadScores();
let scoredThisGame = false;

function loadScores() {
  try {
    const raw = localStorage.getItem(SCORE_KEY);
    if (raw) return Object.assign({ you: 0, draws: 0, fly: 0 }, JSON.parse(raw));
  } catch (_) {
    // localStorage unavailable or corrupt; fall back to zeros
  }
  return { you: 0, draws: 0, fly: 0 };
}

function saveScores() {
  try {
    localStorage.setItem(SCORE_KEY, JSON.stringify(scores));
  } catch (_) {
    // ignore persistence failures (private browsing, quota, etc.)
  }
}

function renderScores() {
  if (scoreYouEl) scoreYouEl.textContent = String(scores.you);
  if (scoreDrawsEl) scoreDrawsEl.textContent = String(scores.draws);
  if (scoreFlyEl) scoreFlyEl.textContent = String(scores.fly);
}

// ---------- Brain brightness (persisted in localStorage) ----------

const BRIGHTNESS_KEY = 'fable_brightness_v1';
const DEFAULT_BRIGHTNESS = 1.4;

function loadBrightness() {
  try {
    const raw = localStorage.getItem(BRIGHTNESS_KEY);
    if (raw !== null) {
      const v = parseFloat(raw);
      if (!Number.isNaN(v)) return v;
    }
  } catch (_) {
    // localStorage unavailable; fall back to default
  }
  return DEFAULT_BRIGHTNESS;
}

function saveBrightness(v) {
  try {
    localStorage.setItem(BRIGHTNESS_KEY, String(v));
  } catch (_) {
    // ignore persistence failures (private browsing, quota, etc.)
  }
}

function setFlyAvatarState(cls) {
  if (!flyAvatar) return;
  flyAvatar.classList.remove('state-idle', 'state-thinking', 'state-happy', 'state-sad');
  flyAvatar.classList.add(cls);
}

function isEmptyBoard(board) {
  return board.every((v) => v === 0);
}

function applyState(state) {
  currentState = state;
  Board.render(state);
  Brain.setBoard(state.board);
  setStatus(statusText(state));
  brainHeader.classList.toggle('thinking', !!state.thinking);
  if (brainPanel) brainPanel.classList.toggle('thinking', !!state.thinking);

  if (isEmptyBoard(state.board)) {
    scoredThisGame = false;
  }

  const terminal = state.status === 'x_wins' || state.status === 'o_wins' || state.status === 'draw';
  if (terminal && !scoredThisGame) {
    scoredThisGame = true;
    if (state.status === 'draw') {
      scores.draws++;
      setFlyAvatarState('state-idle');
      playDraw();
    } else {
      const winner = state.status === 'x_wins' ? 1 : 2;
      if (winner === state.human) {
        scores.you++;
        setFlyAvatarState('state-sad');
        playWinGood();
      } else {
        scores.fly++;
        setFlyAvatarState('state-happy');
        playWinBad();
      }
    }
    saveScores();
    renderScores();
  } else if (!terminal) {
    setFlyAvatarState(state.thinking ? 'state-thinking' : 'state-idle');
  }
}

async function boot() {
  let meta, xyz;
  if (MOCK) {
    ({ meta, xyz } = makeMockMeta());
  } else {
    const metaRes = await fetch('/api/meta');
    const metaJson = await metaRes.json();
    const superclass = base64ToUint8(metaJson.superclass);
    meta = { ...metaJson, superclass };
    const xyzRes = await fetch(metaJson.xyz_url || '/api/xyz');
    const xyzBuf = await xyzRes.arrayBuffer();
    xyz = new Float32Array(xyzBuf);
  }

  Board.init(document.getElementById('board-container'), onHumanMove);
  Brain.init(document.getElementById('brain-container'), meta, xyz);
  renderScores();
  applyState(currentState);

  const initialBrightness = loadBrightness();
  if (brightnessSlider) brightnessSlider.value = String(initialBrightness);
  Brain.setBrightness(initialBrightness);

  newGameBtn.addEventListener('click', () => {
    Board.clearLogits();
    scoredThisGame = false;
    setFlyAvatarState('state-idle');
    if (MOCK) mockNewGame(flyFirstCheckbox.checked);
    else sendWS({ type: 'new_game', fly_first: flyFirstCheckbox.checked });
  });

  viewSelect.addEventListener('change', () => Brain.setView(viewSelect.value));
  decaySlider.addEventListener('input', () => Brain.setDecay(parseFloat(decaySlider.value)));
  if (brightnessSlider) {
    brightnessSlider.addEventListener('input', () => {
      const v = parseFloat(brightnessSlider.value);
      Brain.setBrightness(v);
      saveBrightness(v);
    });
  }

  if (muteBtn) {
    muteBtn.addEventListener('click', () => {
      muted = !muted;
      muteBtn.classList.toggle('muted', muted);
      muteBtn.textContent = muted ? '🔇' : '🔊';
      muteBtn.title = muted ? 'Sound effects (muted)' : 'Sound effects (on)';
      if (!muted) tone(440, 0.06, 'sine', 0.04);
    });
  }

  if (MOCK) startMock();
  else connectWS();
}

function onHumanMove(cell) {
  Board.clearLogits();
  playClick();
  if (MOCK) mockHumanMove(cell);
  else sendWS({ type: 'human_move', cell });
}

// ---------- Sound effects (WebAudio oscillators, muted by default) ----------

let audioCtx = null;
let muted = true;

function ensureAudioCtx() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audioCtx = new Ctx();
  }
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

function tone(freq, dur = 0.12, type = 'sine', gainVal = 0.06) {
  if (muted) return;
  const ctx = ensureAudioCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  osc.connect(gain).connect(ctx.destination);
  const t = ctx.currentTime;
  gain.gain.setValueAtTime(gainVal, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
  osc.start(t);
  osc.stop(t + dur + 0.02);
}

function playClick() {
  tone(520, 0.08, 'square', 0.05);
}

function playFlyMove() {
  tone(300, 0.1, 'triangle', 0.06);
}

function playWinGood() {
  tone(660, 0.12, 'sine', 0.06);
  setTimeout(() => tone(880, 0.16, 'sine', 0.06), 120);
}

function playWinBad() {
  tone(220, 0.18, 'sawtooth', 0.05);
  setTimeout(() => tone(160, 0.22, 'sawtooth', 0.05), 140);
}

function playDraw() {
  tone(440, 0.15, 'sine', 0.05);
}

function base64ToUint8(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// ---------- WebSocket wiring ----------

function sendWS(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    reconnectDelay = 500;
    setConnDot(true);
  };
  ws.onclose = () => {
    setConnDot(false);
    setStatus('Connection lost. Reconnecting…');
    setTimeout(connectWS, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 8000);
  };
  ws.onerror = () => {
    try { ws.close(); } catch (_) { /* already closing */ }
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      handleMessage(JSON.parse(ev.data));
    } else {
      Brain.spikes(new Uint32Array(ev.data));
    }
  };
}

function handleMessage(msg) {
  if (msg.type === 'state') {
    applyState(msg);
  } else if (msg.type === 'fly_move') {
    Board.showLogits(msg.logits, currentState.board);
    Board.flashCell(msg.cell);
    playFlyMove();
    setStatus(`Fly played ${msg.cell}`);
  } else if (msg.type === 'error') {
    setStatus('Error: ' + msg.message);
  }
}

function setConnDot(ok) {
  if (connDot) connDot.classList.toggle('conn-ok', ok);
}


// ---------- MOCK MODE ----------
// Generates a fly-brain-ish point cloud and simulates a random opponent so
// the page can be exercised with `python3 -m http.server` and no backend.

function makeMockMeta() {
  const n = 20000;
  const xyz = new Float32Array(n * 3);
  const superclass_names = ['unknown', 'optic', 'central', 'input', 'readout'];
  const superclass = new Uint8Array(n);

  for (let i = 0; i < n; i++) {
    const lobe = Math.random() < 0.5 ? -1 : 1;
    let x, y, z;
    if (Math.random() < 0.7) {
      // two lobes
      const r = Math.pow(Math.random(), 0.5) * 0.55;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      x = lobe * 0.4 + r * Math.sin(phi) * Math.cos(theta) * 0.8;
      y = r * Math.sin(phi) * Math.sin(theta);
      z = r * Math.cos(phi);
    } else {
      // central mass
      const r = Math.pow(Math.random(), 0.5) * 0.3;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      x = r * Math.sin(phi) * Math.cos(theta) * 0.5;
      y = r * Math.sin(phi) * Math.sin(theta) * 0.6 - 0.1;
      z = r * Math.cos(phi) * 0.5;
    }
    xyz[i * 3] = clamp(x, -1, 1);
    xyz[i * 3 + 1] = clamp(y, -1, 1);
    xyz[i * 3 + 2] = clamp(z, -1, 1);
    superclass[i] = Math.floor(Math.random() * superclass_names.length);
  }

  const input_groups = { X: [], O: [] };
  for (let cell = 0; cell < 9; cell++) {
    input_groups.X.push(randIndices(n, 40));
    input_groups.O.push(randIndices(n, 40));
  }
  const readout = randIndices(n, 120);

  return { meta: { n, superclass, superclass_names, input_groups, readout }, xyz };
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function randIndices(n, count) {
  const out = new Array(count);
  for (let i = 0; i < count; i++) out[i] = Math.floor(Math.random() * n);
  return out;
}

// `var` on purpose: boot() runs before this point in module evaluation, and
// `let` bindings would still be in their temporal dead zone (ReferenceError).
var mockSpikeTimer = null;
var mockBoard = Array(9).fill(0);
var mockHuman = 1;
var mockFly = 2;
var mockToMove = 1;

function startMock() {
  mockNewGame(false);
  if (mockSpikeTimer) clearInterval(mockSpikeTimer);
  mockSpikeTimer = setInterval(() => {
    Brain.spikes(randIndices(20000, 30 + Math.floor(Math.random() * 60)));
  }, 120);
}

function mockNewGame(flyFirst) {
  mockBoard = Array(9).fill(0);
  mockHuman = flyFirst ? 2 : 1;
  mockFly = flyFirst ? 1 : 2;
  mockToMove = 1;
  pushMockState(flyFirst);
  if (flyFirst) setTimeout(mockFlyTurn, 500);
}

function pushMockState(thinking) {
  const status = checkTerminal(mockBoard) || (mockToMove === 1 ? 'x_to_move' : 'o_to_move');
  applyState({ board: mockBoard.slice(), status, human: mockHuman, fly: mockFly, thinking });
}

function mockHumanMove(cell) {
  if (mockBoard[cell] !== 0 || mockToMove !== mockHuman) return;
  mockBoard[cell] = mockHuman;
  mockToMove = mockToMove === 1 ? 2 : 1;
  if (checkTerminal(mockBoard)) {
    pushMockState(false);
    return;
  }
  pushMockState(true);
  setTimeout(mockFlyTurn, 400 + Math.random() * 500);
}

function mockFlyTurn() {
  if (checkTerminal(mockBoard)) return;
  const empties = mockBoard.map((v, i) => (v === 0 ? i : -1)).filter((i) => i >= 0);
  const cell = empties[Math.floor(Math.random() * empties.length)];
  mockBoard[cell] = mockFly;
  mockToMove = mockToMove === 1 ? 2 : 1;
  const logits = Array.from({ length: 9 }, () => Math.random() * 2 - 1);
  Board.showLogits(logits, mockBoard);
  Board.flashCell(cell);
  playFlyMove();
  pushMockState(false);
}

const LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];

function checkTerminal(board) {
  for (const [a, b, c] of LINES) {
    if (board[a] !== 0 && board[a] === board[b] && board[b] === board[c]) {
      return board[a] === 1 ? 'x_wins' : 'o_wins';
    }
  }
  if (board.every((v) => v !== 0)) return 'draw';
  return null;
}

// Start after the whole module has been evaluated so every top-level binding exists.
boot();
