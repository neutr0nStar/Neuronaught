// board.js — renders the 3x3 tic-tac-toe grid and the fly's move-logit bars.

const SVG_NS = 'http://www.w3.org/2000/svg';

const LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];

let cells = [];
let onMoveCb = null;
let gridEl = null;
let winOverlay = null;
let lastWinKey = null;
let flashTimers = new Map();

export const Board = {
  init(container, onMove) {
    onMoveCb = onMove;
    container.innerHTML = '';
    lastWinKey = null;
    flashTimers = new Map();

    const grid = document.createElement('div');
    grid.className = 'board-grid';
    gridEl = grid;
    cells = [];
    for (let i = 0; i < 9; i++) {
      const cell = document.createElement('button');
      cell.className = 'board-cell';
      cell.type = 'button';
      cell.dataset.idx = String(i);

      const bar = document.createElement('div');
      bar.className = 'cell-logit-bar';

      cell.appendChild(bar);
      cell.addEventListener('click', () => {
        if (cell.disabled) {
          triggerShake(cell);
          return;
        }
        onMoveCb && onMoveCb(i);
      });

      grid.appendChild(cell);
      cells.push({ el: cell, mark: null, bar, value: 0 });
    }

    winOverlay = document.createElementNS(SVG_NS, 'svg');
    winOverlay.setAttribute('class', 'win-line-overlay');
    winOverlay.setAttribute('viewBox', '0 0 100 100');
    winOverlay.setAttribute('preserveAspectRatio', 'none');
    grid.appendChild(winOverlay);

    container.appendChild(grid);
  },

  render(state) {
    if (!state || !cells.length) return;
    const { board, status, human, thinking } = state;
    const terminal = status === 'x_wins' || status === 'o_wins' || status === 'draw';
    const humanIsX = human === 1;
    const humanTurn = (status === 'x_to_move' && humanIsX) || (status === 'o_to_move' && !humanIsX);
    const winLine = terminal ? findWinningLine(board) : null;

    board.forEach((v, i) => {
      const slot = cells[i];
      const { el } = slot;
      if (slot.value !== v) {
        slot.value = v;
        if (v === 0) {
          if (slot.mark) {
            slot.mark.remove();
            slot.mark = null;
          }
        } else {
          const svg = createMarkSvg(v === 1 ? 'x' : 'o');
          if (slot.mark) slot.mark.remove();
          el.insertBefore(svg, el.firstChild);
          slot.mark = svg;
        }
      }
      el.disabled = v !== 0 || !humanTurn || terminal || !!thinking;
      el.classList.toggle('win-cell', !!(winLine && winLine.includes(i)));
    });

    updateWinLine(winLine);
  },

  // Softmax the fly's raw logits and show a proportional bar under each
  // still-empty cell so the user can see what the fly "wanted".
  showLogits(logits, board) {
    if (!logits || !cells.length) return;
    const max = Math.max(...logits);
    const exps = logits.map((v) => Math.exp(v - max));
    const sum = exps.reduce((a, b) => a + b, 0);
    const probs = exps.map((v) => v / sum);
    cells.forEach(({ bar }, i) => {
      if (board[i] !== 0) {
        bar.style.opacity = '0';
        bar.style.transform = 'scaleX(0)';
        return;
      }
      bar.style.opacity = String(0.25 + 0.75 * probs[i]);
      bar.style.transform = `scaleX(${probs[i]})`;
    });
  },

  clearLogits() {
    cells.forEach(({ bar }) => {
      bar.style.opacity = '0';
      bar.style.transform = 'scaleX(0)';
    });
  },

  // Briefly highlight the cell the fly just played, as a "sweep" landing cue.
  flashCell(idx) {
    const slot = cells[idx];
    if (!slot) return;
    const { el } = slot;
    el.classList.remove('flash-cell');
    // Force reflow so the animation restarts if it's already running.
    void el.offsetWidth;
    el.classList.add('flash-cell');
    const prevTimer = flashTimers.get(idx);
    if (prevTimer) clearTimeout(prevTimer);
    flashTimers.set(idx, setTimeout(() => el.classList.remove('flash-cell'), 720));
  },
};

function triggerShake(el) {
  el.classList.remove('shake');
  void el.offsetWidth;
  el.classList.add('shake');
  setTimeout(() => el.classList.remove('shake'), 340);
}

// Fixed geometry (see coordinates below) means we can hardcode the path
// lengths instead of calling getTotalLength() on elements that may not be
// attached to the document yet (unreliable across browsers).
const X_LINE_LEN = Math.hypot(78 - 22, 78 - 22); // ~79.2
const O_CIRCLE_LEN = 2 * Math.PI * 30; // ~188.5

function createMarkSvg(type) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `cell-mark-svg mark-${type}`);
  svg.setAttribute('viewBox', '0 0 100 100');

  if (type === 'x') {
    const l1 = document.createElementNS(SVG_NS, 'line');
    l1.setAttribute('class', 'mark-line');
    l1.setAttribute('x1', '22'); l1.setAttribute('y1', '22');
    l1.setAttribute('x2', '78'); l1.setAttribute('y2', '78');
    const l2 = document.createElementNS(SVG_NS, 'line');
    l2.setAttribute('class', 'mark-line');
    l2.setAttribute('x1', '78'); l2.setAttribute('y1', '22');
    l2.setAttribute('x2', '22'); l2.setAttribute('y2', '78');
    svg.appendChild(l1);
    svg.appendChild(l2);
    setDashLength(l1, X_LINE_LEN, 0.05);
    setDashLength(l2, X_LINE_LEN, 0.15);
  } else {
    const c = document.createElementNS(SVG_NS, 'circle');
    c.setAttribute('class', 'mark-circle');
    c.setAttribute('cx', '50'); c.setAttribute('cy', '50'); c.setAttribute('r', '30');
    svg.appendChild(c);
    setDashLength(c, O_CIRCLE_LEN, 0);
  }
  return svg;
}

function setDashLength(el, len, delay) {
  el.style.strokeDasharray = String(len);
  el.style.setProperty('--mark-len', String(len));
  el.style.animationDelay = `${delay}s`;
}

function updateWinLine(winLine) {
  if (!winOverlay) return;
  const key = winLine ? winLine.join(',') : null;
  if (key === lastWinKey) return;
  lastWinKey = key;

  while (winOverlay.firstChild) winOverlay.removeChild(winOverlay.firstChild);
  if (!winLine) return;

  const [a, , c] = winLine;
  const pa = cellCenter(a);
  const pc = cellCenter(c);
  const dx = pc.x - pa.x;
  const dy = pc.y - pa.y;
  const ext = 0.28;
  const x1 = pa.x - dx * ext;
  const y1 = pa.y - dy * ext;
  const x2 = pc.x + dx * ext;
  const y2 = pc.y + dy * ext;

  const line = document.createElementNS(SVG_NS, 'line');
  line.setAttribute('x1', String(x1));
  line.setAttribute('y1', String(y1));
  line.setAttribute('x2', String(x2));
  line.setAttribute('y2', String(y2));
  winOverlay.appendChild(line);

  const len = Math.hypot(x2 - x1, y2 - y1);
  line.style.strokeDasharray = String(len);
  line.style.setProperty('--line-len', String(len));
}

function cellCenter(i) {
  const row = Math.floor(i / 3);
  const col = i % 3;
  return { x: ((col * 2 + 1) / 6) * 100, y: ((row * 2 + 1) / 6) * 100 };
}

function findWinningLine(board) {
  for (const line of LINES) {
    const [a, b, c] = line;
    if (board[a] !== 0 && board[a] === board[b] && board[b] === board[c]) return line;
  }
  return null;
}
