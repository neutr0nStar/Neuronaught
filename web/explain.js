// explain.js — mode toggle (Simple/Detailed) with persistence + fade,
// scroll-spy for the table of contents, "back to game" handling, and the
// three inline SVG diagrams for this page. No external libraries.

(function () {
  'use strict';

  var MODE_KEY = 'fly-explain-mode';
  var body = document.body;
  var toggleBtn = document.getElementById('mode-toggle');
  var content = document.getElementById('content');

  function getStoredMode() {
    try {
      var m = localStorage.getItem(MODE_KEY);
      return m === 'simple' || m === 'detailed' ? m : null;
    } catch (_) {
      return null;
    }
  }

  function storeMode(mode) {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch (_) {
      /* localStorage unavailable (private mode, etc.) — persistence is best-effort */
    }
  }

  function applyMode(mode, animate) {
    var run = function () {
      body.setAttribute('data-mode', mode);
      toggleBtn.setAttribute('aria-checked', mode === 'detailed' ? 'true' : 'false');
      if (animate) {
        requestAnimationFrame(function () {
          content.classList.remove('fading');
        });
      }
    };
    if (animate) {
      content.classList.add('fading');
      window.setTimeout(run, 160);
    } else {
      run();
    }
  }

  function setMode(mode) {
    storeMode(mode);
    applyMode(mode, true);
  }

  function currentMode() {
    return body.getAttribute('data-mode') === 'detailed' ? 'detailed' : 'simple';
  }

  // Initial mode: stored choice, else the "simple" default already set in HTML.
  var stored = getStoredMode();
  if (stored) applyMode(stored, false);

  toggleBtn.addEventListener('click', function () {
    setMode(currentMode() === 'simple' ? 'detailed' : 'simple');
  });

  document.querySelectorAll('.mode-label').forEach(function (label) {
    label.addEventListener('click', function () {
      setMode(label.getAttribute('data-for'));
    });
  });

  // ---------------- Back to the game ----------------
  function wireBack(el) {
    if (!el) return;
    el.addEventListener('click', function (e) {
      e.preventDefault();
      window.close();
      // window.close() is a no-op in most browsers unless this tab was
      // opened by script; if we're still here shortly after, just navigate.
      window.setTimeout(function () {
        location.href = '/';
      }, 60);
    });
  }
  wireBack(document.getElementById('back-link'));
  wireBack(document.getElementById('back-link-bottom'));

  // ---------------- Table-of-contents scroll spy ----------------
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('#toc a'));
  var sections = tocLinks
    .map(function (a) { return document.querySelector(a.getAttribute('href')); })
    .filter(Boolean);

  if ('IntersectionObserver' in window && sections.length) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          var link = byId[entry.target.id];
          if (!link) return;
          if (entry.isIntersecting) {
            tocLinks.forEach(function (l) { l.classList.remove('active'); });
            link.classList.add('active');
          }
        });
      },
      { rootMargin: '-15% 0px -70% 0px', threshold: 0 }
    );
    sections.forEach(function (s) { observer.observe(s); });
  }

  // ---------------- Inline SVG diagrams ----------------

  var COL = {
    bg: '#0b0d12',
    panel: '#12151d',
    text: '#e6e8ee',
    muted: '#8a90a2',
    accent: '#ffb347',
    teal: '#5eead4',
    border: '#2a3044',
    x: '#7dd3fc',
    o: '#f9a8d4',
  };

  function mount(id, svg) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = svg;
  }

  // 1) Pipeline: board -> eye -> brain -> readout -> move
  mount('svg-pipeline-anchor', buildPipelineSvg());
  // 2) LIF neuron voltage trace
  mount('svg-lif-anchor', buildLifSvg());
  // 3) Board-to-eye retinotopic mapping
  mount('svg-mapping-anchor', buildMappingSvg());

  // ---------------- Pitch deck diagrams (reuse + new) ----------------
  mount('svg-deck-pipeline-anchor', buildPipelineSvg('Deck'));
  mount('svg-deck-lif-anchor', buildLifSvg());
  mount('svg-deck-mapping-anchor', buildMappingSvg('Deck'));
  mount('svg-deck-scale-anchor', buildDeckScaleSvg());
  mount('svg-deck-connectome-anchor', buildDeckConnectomeSvg());
  mount('svg-deck-network-anchor', buildDeckNetworkSvg());
  mount('svg-deck-storyboard-anchor', buildDeckStoryboardSvg());
  mount('svg-deck-training-anchor', buildDeckTrainingSvg());
  mount('svg-deck-flow-anchor', buildDeckFlowSvg());
  mount('svg-deck-chart-anchor', buildDeckChartSvg());
  mount('svg-deck-closing-anchor', buildDeckClosingSvg());

  function buildDeckScaleSvg() {
    var w = 700, h = 300;
    var flyX = 150, flyY = 160, flyR = 5;
    var humX = 500, humY = 160, humR = 85;
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Size comparison: a fruit fly brain with about 140,000 neurons versus a human brain with about 86 billion neurons, not to scale">' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      '<text x="' + (w / 2) + '" y="24" text-anchor="middle" fill="' + COL.muted + '" font-size="11.5" font-family="system-ui, sans-serif" font-style="italic">illustrative — not shown to true scale</text>' +
      '<circle cx="' + humX + '" cy="' + humY + '" r="' + humR + '" fill="' + COL.teal + '" fill-opacity="0.16" stroke="' + COL.teal + '" stroke-width="1.5"/>' +
      '<circle cx="' + flyX + '" cy="' + flyY + '" r="' + (flyR + 8) + '" fill="none" stroke="' + COL.accent + '" stroke-width="1" stroke-dasharray="2 3" opacity="0.6"/>' +
      '<circle cx="' + flyX + '" cy="' + flyY + '" r="' + flyR + '" fill="' + COL.accent + '"/>' +
      '<text x="' + flyX + '" y="' + (flyY - 46) + '" text-anchor="middle" fill="' + COL.text + '" font-size="14" font-family="system-ui, sans-serif" font-weight="600">Fruit fly</text>' +
      '<text x="' + flyX + '" y="' + (flyY - 30) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11.5" font-family="system-ui, sans-serif">~140,000 neurons</text>' +
      '<text x="' + flyX + '" y="' + (flyY + 34) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11" font-family="system-ui, sans-serif">(poppy-seed sized)</text>' +
      '<text x="' + humX + '" y="' + (humY + humR + 26) + '" text-anchor="middle" fill="' + COL.text + '" font-size="14" font-family="system-ui, sans-serif" font-weight="600">You</text>' +
      '<text x="' + humX + '" y="' + (humY + humR + 42) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11.5" font-family="system-ui, sans-serif">~86 billion neurons</text>' +
      '</svg>';
  }

  function buildDeckConnectomeSvg() {
    var w = 700, h = 300;
    var n = 6;
    var slices = '';
    var dots = [];
    for (var i = 0; i < n; i++) {
      var cx = 150 + i * 6;
      var cy = 55 + i * 34;
      var rx = 90, ry = 16;
      slices += '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + rx + '" ry="' + ry + '" fill="' + COL.panel + '" fill-opacity="0.7" stroke="' + COL.border + '" stroke-width="1.2"/>';
      var dotx = cx - 30 + i * 10;
      var doty = cy;
      dots.push([dotx, doty]);
    }
    dots.forEach(function (p) {
      slices += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3.2" fill="' + COL.teal + '"/>';
    });
    var tracePath = 'M ' + dots.map(function (p) { return p[0] + ' ' + p[1]; }).join(' L ');
    slices += '<path d="' + tracePath + '" fill="none" stroke="' + COL.teal + '" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.7"/>';

    var arrow = '<line x1="330" y1="150" x2="410" y2="150" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#dcArrow)"/>';

    var neuronCx = 560, neuronCy = 150;
    var neuron = '<circle cx="' + neuronCx + '" cy="' + neuronCy + '" r="14" fill="' + COL.teal + '" fill-opacity="0.25" stroke="' + COL.teal + '" stroke-width="2"/>';
    var branches = [[-70, -70], [-40, -90], [60, -80], [80, 20], [-60, 70], [50, 85]];
    branches.forEach(function (b) {
      neuron += '<path d="M ' + neuronCx + ' ' + neuronCy + ' Q ' + (neuronCx + b[0] * 0.5) + ' ' + (neuronCy + b[1] * 0.5) + ' ' + (neuronCx + b[0]) + ' ' + (neuronCy + b[1]) + '" fill="none" stroke="' + COL.teal + '" stroke-width="1.5" opacity="0.85"/>';
    });

    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Thousands of thin brain slices imaged and traced into a single connected neuron">' +
      '<defs><marker id="dcArrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      slices + arrow + neuron +
      '<text x="150" y="270" text-anchor="middle" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">thousands of EM slices</text>' +
      '<text x="560" y="270" text-anchor="middle" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">one traced neuron</text>' +
      '</svg>';
  }

  function buildDeckNetworkSvg() {
    var w = 700, h = 300;
    var nodes = [[110, 150], [280, 70], [280, 230], [450, 70], [450, 230], [610, 150]];
    var edges = [
      { a: 0, b: 1, w: 6, exc: true },
      { a: 0, b: 2, w: 3, exc: false },
      { a: 1, b: 3, w: 8, exc: true },
      { a: 2, b: 4, w: 5, exc: false },
      { a: 1, b: 4, w: 2, exc: true },
      { a: 2, b: 3, w: 2, exc: false },
      { a: 3, b: 5, w: 7, exc: true },
      { a: 4, b: 5, w: 5, exc: false },
    ];
    var edgeSvg = '';
    edges.forEach(function (e) {
      var p0 = nodes[e.a], p1 = nodes[e.b];
      var color = e.exc ? COL.teal : COL.o;
      var dx = p1[0] - p0[0], dy = p1[1] - p0[1];
      var len = Math.sqrt(dx * dx + dy * dy);
      var ux = dx / len, uy = dy / len;
      var x0 = p0[0] + ux * 18, y0 = p0[1] + uy * 18;
      var x1 = p1[0] - ux * 18, y1 = p1[1] - uy * 18;
      edgeSvg += '<line x1="' + x0 + '" y1="' + y0 + '" x2="' + x1 + '" y2="' + y1 + '" stroke="' + color + '" stroke-width="' + e.w + '" stroke-linecap="round" opacity="0.85" marker-end="url(' + (e.exc ? '#netArrow' : '#netBar') + ')"/>';
    });
    var nodeSvg = '';
    nodes.forEach(function (p) {
      nodeSvg += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="16" fill="' + COL.panel + '" stroke="' + COL.border + '" stroke-width="2"/>';
    });
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A small network of neurons connected by excitatory and inhibitory pipes of varying width">' +
      '<defs>' +
      '<marker id="netArrow" markerUnits="userSpaceOnUse" markerWidth="14" markerHeight="14" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="' + COL.teal + '"/></marker>' +
      '<marker id="netBar" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="14" refX="6" refY="7" orient="auto"><rect x="5" y="0" width="2.5" height="14" fill="' + COL.o + '"/></marker>' +
      '</defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      edgeSvg + nodeSvg +
      '<circle cx="90" cy="278" r="6" fill="' + COL.teal + '"/><text x="102" y="282" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">excitatory</text>' +
      '<circle cx="230" cy="278" r="6" fill="' + COL.o + '"/><text x="242" y="282" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">inhibitory</text>' +
      '<text x="610" y="282" text-anchor="end" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">5.5M pipes total</text>' +
      '</svg>';
  }

  function storyboardPoints(n, w2, h2) {
    var pts = [];
    for (var i = 0; i < n; i++) {
      var a = i * 2.399963;
      var r = Math.sqrt(i / n) * Math.min(w2, h2) / 2 * 0.92;
      var x = w2 / 2 + r * Math.cos(a);
      var y = h2 / 2 + r * Math.sin(a) * 0.75;
      pts.push([x, y]);
    }
    return pts;
  }

  function buildDeckStoryboardSvg() {
    var w = 900, h = 260;
    var panelW = 260, panelH = 200, gap = 25;
    var startX = 15;
    var y0 = (h - panelH) / 2 - 10;
    var pts = storyboardPoints(140, panelW, panelH);
    var minDim = Math.min(panelW, panelH);
    var eyeAnchor = [panelW * 0.24, panelH * 0.5];
    var radii = [minDim * 0.18, minDim * 0.42, minDim * 0.78];
    var labels = ['eye lights up', 'activity spreads', 'whole brain active'];
    var frames = '';
    for (var f = 0; f < 3; f++) {
      var px = startX + f * (panelW + gap);
      var dotsSvg = '';
      pts.forEach(function (p) {
        var dx = p[0] - eyeAnchor[0], dy = p[1] - eyeAnchor[1];
        var dist = Math.sqrt(dx * dx + dy * dy);
        var active = dist < radii[f];
        var cx = px + p[0], cy = y0 + p[1];
        if (active) {
          dotsSvg += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="2.4" fill="' + COL.accent + '"/>';
        } else {
          dotsSvg += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="1.6" fill="' + COL.border + '"/>';
        }
      });
      frames += '<rect x="' + px + '" y="' + y0 + '" width="' + panelW + '" height="' + panelH + '" rx="10" fill="' + COL.panel + '" stroke="' + COL.border + '" stroke-width="1"/>';
      frames += dotsSvg;
      frames += '<text x="' + (px + panelW / 2) + '" y="' + (y0 + panelH + 22) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">' + labels[f] + '</text>';
      if (f < 2) {
        var ax = px + panelW + 4, ax2 = px + panelW + gap - 4;
        frames += '<line x1="' + ax + '" y1="' + (y0 + panelH / 2) + '" x2="' + ax2 + '" y2="' + (y0 + panelH / 2) + '" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#sbArrow)"/>';
      }
    }
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Three frames showing activity spreading from the eye across the whole simulated brain">' +
      '<defs><marker id="sbArrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      frames +
      '</svg>';
  }

  function buildDeckTrainingSvg() {
    var w = 900, h = 260;
    var gx = 40, gy = 60, cols = 16, rows = 8, cs = 10;
    var heat = '';
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var v = Math.sin(r * 12.9898 + c * 78.233) * 43758.5453;
        v = v - Math.floor(v);
        var op = 0.08 + v * 0.55;
        heat += '<rect x="' + (gx + c * cs) + '" y="' + (gy + r * cs) + '" width="' + (cs - 1.5) + '" height="' + (cs - 1.5) + '" fill="' + COL.teal + '" fill-opacity="' + op.toFixed(2) + '"/>';
      }
    }
    var heatLabel = '<text x="' + (gx + cols * cs / 2) + '" y="' + (gy + rows * cs + 22) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">4,000 neuron spike counts</text>';

    var arrowX1 = gx + cols * cs + 20, arrowX2 = arrowX1 + 90;
    var midY = gy + rows * cs / 2;
    var arrow = '<line x1="' + arrowX1 + '" y1="' + midY + '" x2="' + (arrowX2 - 6) + '" y2="' + midY + '" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#trArrow)"/>';
    var formulaBox = '<rect x="' + arrowX2 + '" y="' + (midY - 24) + '" width="120" height="48" rx="8" fill="' + COL.panel + '" stroke="' + COL.accent + '" stroke-width="1.5"/>' +
      '<text x="' + (arrowX2 + 60) + '" y="' + (midY - 2) + '" text-anchor="middle" fill="' + COL.text + '" font-size="12" font-family="system-ui, sans-serif" font-weight="600">one trained</text>' +
      '<text x="' + (arrowX2 + 60) + '" y="' + (midY + 14) + '" text-anchor="middle" fill="' + COL.text + '" font-size="12" font-family="system-ui, sans-serif" font-weight="600">formula</text>';

    var arrow2X1 = arrowX2 + 120 + 16, arrow2X2 = arrow2X1 + 70;
    var arrow2 = '<line x1="' + arrow2X1 + '" y1="' + midY + '" x2="' + (arrow2X2 - 6) + '" y2="' + midY + '" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#trArrow)"/>';

    var sgx = arrow2X2 + 10, sgy = gy - 6, ss = 44;
    var scores = [0.1, -1, 0.3, 0.2, 0.9, -0.2, 0.0, -1, 0.4];
    var maxIdx = 4;
    var scoreGrid = '';
    for (var i = 0; i < 9; i++) {
      var rr = Math.floor(i / 3), cc = i % 3;
      var sx = sgx + cc * ss, sy = sgy + rr * ss;
      var isMax = i === maxIdx;
      scoreGrid += '<rect x="' + sx + '" y="' + sy + '" width="' + (ss - 6) + '" height="' + (ss - 6) + '" rx="6" fill="' + (isMax ? 'rgba(255,179,71,0.18)' : COL.panel) + '" stroke="' + (isMax ? COL.accent : COL.border) + '" stroke-width="' + (isMax ? 2 : 1) + '"/>';
      scoreGrid += '<text x="' + (sx + (ss - 6) / 2) + '" y="' + (sy + (ss - 6) / 2 + 4) + '" text-anchor="middle" fill="' + (isMax ? COL.accent : COL.muted) + '" font-size="12" font-family="ui-monospace, monospace">' + scores[i].toFixed(1) + '</text>';
    }
    var scoreLabel = '<text x="' + (sgx + (3 * ss - 6) / 2) + '" y="' + (sgy + 3 * ss + 18) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="12" font-family="system-ui, sans-serif">9 move scores</text>';

    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A pattern of neuron spike counts mapped through one trained formula into nine move scores">' +
      '<defs><marker id="trArrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      heat + heatLabel + arrow + formulaBox + arrow2 + scoreGrid + scoreLabel +
      '</svg>';
  }

  function flowIcon(type, cx, cy) {
    if (type === 'board') return svgStageIcon(0, cx, cy);
    if (type === 'brain') return svgStageIcon(2, cx, cy);
    if (type === 'readout') return svgStageIcon(3, cx, cy);
    if (type === 'check') return svgStageIcon(4, cx, cy);
    if (type === 'click') {
      return '<circle cx="' + cx + '" cy="' + cy + '" r="10" fill="none" stroke="' + COL.accent + '" stroke-width="1.5" opacity="0.6"/>' +
        '<path d="M ' + (cx - 6) + ' ' + (cy - 8) + ' L ' + (cx - 6) + ' ' + (cy + 9) + ' L ' + (cx - 1) + ' ' + (cy + 4) + ' L ' + (cx + 3) + ' ' + (cy + 11) + ' L ' + (cx + 6) + ' ' + (cy + 9) + ' L ' + (cx + 2) + ' ' + (cy + 2) + ' L ' + (cx + 8) + ' ' + (cy + 1) + ' Z" fill="' + COL.text + '"/>';
    }
    // frames: three small vertical bars, like film frames / a waveform
    var bars = [-14, -2, 10], heights = [10, 18, 7];
    var g = '';
    bars.forEach(function (bx, i) {
      g += '<rect x="' + (cx + bx - 3) + '" y="' + (cy - heights[i] / 2) + '" width="6" height="' + heights[i] + '" rx="1.5" fill="' + COL.teal + '"/>';
    });
    return g;
  }

  function buildDeckFlowSvg() {
    var stages = [
      { label: 'Click a cell', icon: 'click' },
      { label: 'Board → eye', icon: 'board' },
      { label: '0.4s brain time', icon: 'brain' },
      { label: '30 activity frames', icon: 'frames' },
      { label: '4,000 → 9 scores', icon: 'readout' },
      { label: 'Best move wins', icon: 'check' },
    ];
    var w = 900, h = 200;
    var stageW = 130, stageH = 92;
    var gap = (w - stages.length * stageW) / (stages.length + 1);
    var y = (h - stageH) / 2;
    var boxes = '', arrows = '';
    stages.forEach(function (s, i) {
      var x = gap + i * (stageW + gap);
      var stroke = i === 5 ? COL.accent : (i === 2 ? COL.teal : COL.border);
      var icon = flowIcon(s.icon, x + stageW / 2, y + 30);
      boxes += '<g><rect x="' + x + '" y="' + y + '" width="' + stageW + '" height="' + stageH + '" rx="10" fill="' + (i === 2 ? COL.panel : '#171b26') + '" stroke="' + stroke + '" stroke-width="1.5"/>' +
        icon +
        '<text x="' + (x + stageW / 2) + '" y="' + (y + 64) + '" text-anchor="middle" fill="' + COL.text + '" font-size="11" font-family="system-ui, sans-serif" font-weight="600">' + s.label + '</text>' +
        '</g>';
      if (i < stages.length - 1) {
        var x1 = x + stageW, x2 = x + stageW + gap;
        arrows += '<line x1="' + x1 + '" y1="' + (y + stageH / 2) + '" x2="' + (x2 - 10) + '" y2="' + (y + stageH / 2) + '" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#flowArrowhead)"/>';
      }
    });
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Six steps from clicking a cell to the fly choosing its move">' +
      '<defs><marker id="flowArrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      arrows + boxes +
      '</svg>';
  }

  function buildDeckChartSvg() {
    var w = 700, h = 320;
    var data = [
      { label: 'Right move, with brain', value: 84, color: COL.teal },
      { label: 'Right move, no brain', value: 71, color: COL.muted },
      { label: 'Win or draw vs random', value: 93, color: COL.accent },
    ];
    var padB = 70, padT = 30;
    var plotH = h - padB - padT;
    var barW = 110, gap = 60;
    var totalW = data.length * barW + (data.length - 1) * gap;
    var startX = (w - totalW) / 2;
    var bars = '';
    data.forEach(function (d, i) {
      var x = startX + i * (barW + gap);
      var bh = plotH * (d.value / 100);
      var y = padT + plotH - bh;
      bars += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + bh + '" rx="6" fill="' + d.color + '" fill-opacity="0.85"/>';
      bars += '<text x="' + (x + barW / 2) + '" y="' + (y - 10) + '" text-anchor="middle" fill="' + COL.text + '" font-size="16" font-family="system-ui, sans-serif" font-weight="700">' + d.value + '%</text>';
      var words = d.label.split(' ');
      var mid = Math.ceil(words.length / 2);
      var line1 = words.slice(0, mid).join(' '), line2 = words.slice(mid).join(' ');
      bars += '<text x="' + (x + barW / 2) + '" y="' + (padT + plotH + 22) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11.5" font-family="system-ui, sans-serif">' + line1 + '</text>';
      bars += '<text x="' + (x + barW / 2) + '" y="' + (padT + plotH + 38) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11.5" font-family="system-ui, sans-serif">' + line2 + '</text>';
    });
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Bar chart: 84 percent optimal moves with the brain, 71 percent without it, 93 percent win or draw rate against a random opponent">' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      '<line x1="' + (startX - 20) + '" y1="' + (padT + plotH) + '" x2="' + (startX + totalW + 20) + '" y2="' + (padT + plotH) + '" stroke="' + COL.border + '" stroke-width="1"/>' +
      bars +
      '</svg>';
  }

  function buildDeckClosingSvg() {
    var w = 520, h = 240;
    var cy = 120;
    var xC = 110, oC = 230, arrowX1 = 300, arrowX2 = 380, playCx = 440;
    var xSize = 34;
    var g = '';
    g += '<line x1="' + (xC - xSize) + '" y1="' + (cy - xSize) + '" x2="' + (xC + xSize) + '" y2="' + (cy + xSize) + '" stroke="' + COL.x + '" stroke-width="7" stroke-linecap="round"/>';
    g += '<line x1="' + (xC + xSize) + '" y1="' + (cy - xSize) + '" x2="' + (xC - xSize) + '" y2="' + (cy + xSize) + '" stroke="' + COL.x + '" stroke-width="7" stroke-linecap="round"/>';
    g += '<circle cx="' + oC + '" cy="' + cy + '" r="' + xSize + '" fill="none" stroke="' + COL.o + '" stroke-width="7"/>';
    g += '<line x1="' + arrowX1 + '" y1="' + cy + '" x2="' + (arrowX2 - 8) + '" y2="' + cy + '" stroke="' + COL.muted + '" stroke-width="3" marker-end="url(#closeArrow)"/>';
    g += '<polygon points="' + (playCx - 16) + ',' + (cy - 22) + ' ' + (playCx - 16) + ',' + (cy + 22) + ' ' + (playCx + 18) + ',' + cy + '" fill="' + COL.accent + '"/>';
    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="An X and an O pointing toward a play button">' +
      '<defs><marker id="closeArrow" markerWidth="9" markerHeight="9" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      g +
      '</svg>';
  }

  // ---------------- Pitch deck controller ----------------
  (function initDeck() {
    var deckSection = document.getElementById('deck');
    var card = document.getElementById('deck-card');
    var track = document.getElementById('deck-track');
    if (!deckSection || !card || !track) return;
    var slides = Array.prototype.slice.call(track.querySelectorAll('.slide'));
    var total = slides.length;
    var prevBtn = document.getElementById('deck-prev');
    var nextBtn = document.getElementById('deck-next');
    var fsBtn = document.getElementById('deck-fullscreen');
    var counter = document.getElementById('deck-counter');
    var dotsWrap = document.getElementById('deck-dots');
    var index = 0;

    var dots = [];
    for (var i = 0; i < total; i++) {
      var d = document.createElement('button');
      d.type = 'button';
      d.className = 'deck-dot';
      d.setAttribute('aria-label', 'Go to slide ' + (i + 1));
      (function (idx) {
        d.addEventListener('click', function () { goTo(idx); });
      })(i);
      dotsWrap.appendChild(d);
      dots.push(d);
    }

    function render() {
      track.style.transform = 'translateX(-' + (index * 100) + '%)';
      counter.textContent = (index + 1) + ' / ' + total;
      dots.forEach(function (dot, i2) { dot.classList.toggle('active', i2 === index); });
      prevBtn.disabled = index === 0;
      nextBtn.disabled = index === total - 1;
    }

    function goTo(i2) {
      index = Math.max(0, Math.min(total - 1, i2));
      render();
    }

    prevBtn.addEventListener('click', function () { goTo(index - 1); });
    nextBtn.addEventListener('click', function () { goTo(index + 1); });

    // Arrow keys move the deck only while it's the part of the page in view,
    // and only when the user isn't typing into a form field.
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      var tag = (document.activeElement && document.activeElement.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      var rect = deckSection.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      e.preventDefault();
      goTo(index + (e.key === 'ArrowRight' ? 1 : -1));
    });

    // Touch swipe.
    var touchStartX = null;
    card.addEventListener('touchstart', function (e) {
      touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    card.addEventListener('touchend', function (e) {
      if (touchStartX === null) return;
      var dx = e.changedTouches[0].clientX - touchStartX;
      touchStartX = null;
      if (Math.abs(dx) < 40) return;
      goTo(index + (dx < 0 ? 1 : -1));
    }, { passive: true });

    // Fullscreen toggle on the card itself.
    if (fsBtn) {
      fsBtn.addEventListener('click', function () {
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else if (card.requestFullscreen) {
          card.requestFullscreen();
        }
      });
    }

    // Support ?slide=N (1-based) for direct linking / headless testing.
    var slideParam = null;
    try {
      slideParam = parseInt(new URLSearchParams(window.location.search).get('slide'), 10);
    } catch (_) {
      slideParam = null;
    }
    if (slideParam && !isNaN(slideParam)) {
      index = Math.max(0, Math.min(total - 1, slideParam - 1));
    }
    render();
  })();

  function buildPipelineSvg(idSuffix) {
    idSuffix = idSuffix || '';
    var markerId = 'arrowhead' + idSuffix;
    var stages = [
      { label: 'Board', sub: '3×3 grid' },
      { label: "Fly's eye", sub: 'retinotopic drive' },
      { label: 'Whole brain', sub: '140k neurons, 300 ms' },
      { label: 'Readout', sub: '4,000-neuron ridge fit' },
      { label: 'Move', sub: 'argmax score' },
    ];
    var w = 900, h = 220;
    var stageW = 140, stageH = 92;
    var gap = (w - stages.length * stageW) / (stages.length + 1);
    var y = (h - stageH) / 2;

    var boxes = '';
    var arrows = '';
    stages.forEach(function (s, i) {
      var x = gap + i * (stageW + gap);
      var fill = i === 2 ? COL.panel : '#171b26';
      var stroke = i === 4 ? COL.accent : (i === 1 ? COL.teal : COL.border);
      boxes += svgStageBox(x, y, stageW, stageH, s.label, s.sub, fill, stroke, i);
      if (i < stages.length - 1) {
        var x1 = x + stageW;
        var x2 = x + stageW + gap;
        arrows += '<line x1="' + x1 + '" y1="' + (y + stageH / 2) + '" x2="' + (x2 - 10) + '" y2="' + (y + stageH / 2) + '" stroke="' + COL.muted + '" stroke-width="2" marker-end="url(#' + markerId + ')"/>';
      }
    });

    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Pipeline: board to eye to brain to readout to move">' +
      '<defs><marker id="' + markerId + '" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      arrows + boxes +
      '</svg>';
  }

  function svgStageBox(x, y, w, h, label, sub, fill, stroke, i) {
    var icon = svgStageIcon(i, x + w / 2, y + 30);
    return '' +
      '<g>' +
      '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="10" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1.5"/>' +
      icon +
      '<text x="' + (x + w / 2) + '" y="' + (y + 62) + '" text-anchor="middle" fill="' + COL.text + '" font-size="14" font-family="system-ui, sans-serif" font-weight="600">' + label + '</text>' +
      '<text x="' + (x + w / 2) + '" y="' + (y + 79) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="10.5" font-family="system-ui, sans-serif">' + sub + '</text>' +
      '</g>';
  }

  function svgStageIcon(i, cx, cy) {
    if (i === 0) {
      // board: 3x3 grid with one X one O
      var s = 8, x0 = cx - 1.5 * s, y0 = cy - 1.5 * s, g = '';
      for (var r = 0; r < 3; r++) {
        for (var c = 0; c < 3; c++) {
          g += '<rect x="' + (x0 + c * s) + '" y="' + (y0 + r * s) + '" width="' + (s - 1.5) + '" height="' + (s - 1.5) + '" fill="none" stroke="' + COL.muted + '" stroke-width="0.8"/>';
        }
      }
      g += '<line x1="' + (x0 + 1) + '" y1="' + (y0 + 1) + '" x2="' + (x0 + s - 2) + '" y2="' + (y0 + s - 2) + '" stroke="' + COL.x + '" stroke-width="1.2"/>';
      g += '<line x1="' + (x0 + s - 2) + '" y1="' + (y0 + 1) + '" x2="' + (x0 + 1) + '" y2="' + (y0 + s - 2) + '" stroke="' + COL.x + '" stroke-width="1.2"/>';
      g += '<circle cx="' + (x0 + s * 1.5) + '" cy="' + (y0 + s * 1.5) + '" r="' + (s / 2 - 1) + '" fill="none" stroke="' + COL.o + '" stroke-width="1.2"/>';
      return g;
    }
    if (i === 1) {
      // eye: almond shape with pupil
      return '' +
        '<path d="M ' + (cx - 20) + ' ' + cy + ' Q ' + cx + ' ' + (cy - 14) + ' ' + (cx + 20) + ' ' + cy + ' Q ' + cx + ' ' + (cy + 14) + ' ' + (cx - 20) + ' ' + cy + ' Z" fill="none" stroke="' + COL.teal + '" stroke-width="1.5"/>' +
        '<circle cx="' + cx + '" cy="' + cy + '" r="5" fill="' + COL.teal + '"/>';
    }
    if (i === 2) {
      // brain: cluster of dots with connecting lines
      var pts = [[-16, -6], [0, -12], [16, -6], [-10, 8], [10, 8], [0, 0]];
      var d = '';
      for (var p = 0; p < pts.length; p++) {
        for (var q = p + 1; q < pts.length; q++) {
          if (Math.random() > 0.55) continue;
          d += '<line x1="' + (cx + pts[p][0]) + '" y1="' + (cy + pts[p][1]) + '" x2="' + (cx + pts[q][0]) + '" y2="' + (cy + pts[q][1]) + '" stroke="' + COL.border + '" stroke-width="0.8"/>';
        }
      }
      var dots = '';
      pts.forEach(function (pt, idx) {
        dots += '<circle cx="' + (cx + pt[0]) + '" cy="' + (cy + pt[1]) + '" r="2.6" fill="' + (idx === 5 ? COL.accent : COL.muted) + '"/>';
      });
      return d + dots;
    }
    if (i === 3) {
      // readout: funnel of lines converging
      var lines = '';
      var starts = [-18, -9, 0, 9, 18];
      starts.forEach(function (sx) {
        lines += '<line x1="' + (cx + sx) + '" y1="' + (cy - 10) + '" x2="' + cx + '" y2="' + (cy + 10) + '" stroke="' + COL.teal + '" stroke-width="1"/>';
      });
      lines += '<circle cx="' + cx + '" cy="' + (cy + 10) + '" r="2.8" fill="' + COL.accent + '"/>';
      return lines;
    }
    // move: checkmark
    return '<path d="M ' + (cx - 12) + ' ' + cy + ' L ' + (cx - 3) + ' ' + (cy + 9) + ' L ' + (cx + 14) + ' ' + (cy - 10) + '" fill="none" stroke="' + COL.accent + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
  }

  function buildLifSvg() {
    var w = 760, h = 260;
    var padL = 56, padR = 20, padT = 20, padB = 36;
    var plotW = w - padL - padR, plotH = h - padT - padB;
    var vRest = -52, vThresh = -45, vSpikeTop = -30;
    var yMinV = -55, yMaxV = -28;
    function yOf(v) { return padT + (yMaxV - v) / (yMaxV - yMinV) * plotH; }
    function xOf(t) { return padL + t / 100 * plotW; }

    // Trace: charge from reset toward threshold, spike, reset, refractory flat, charge again, spike, decay a bit
    var path = 'M ' + xOf(0) + ' ' + yOf(vRest);
    function chargeTo(t0, t1, vStart, vTarget, steps) {
      steps = steps || 12;
      var seg = '';
      for (var k = 1; k <= steps; k++) {
        var t = t0 + (t1 - t0) * (k / steps);
        var frac = 1 - Math.exp(-3 * (k / steps));
        var v = vStart + (vTarget - vStart) * frac;
        seg += ' L ' + xOf(t) + ' ' + yOf(v);
      }
      return seg;
    }
    path += chargeTo(0, 28, vRest, vThresh + 1, 14);
    path += ' L ' + xOf(28) + ' ' + yOf(vSpikeTop);
    path += ' L ' + xOf(29.5) + ' ' + yOf(vRest);
    path += ' L ' + xOf(38) + ' ' + yOf(vRest); // refractory flat (2.2ms ~ drawn wider for legibility)
    path += chargeTo(38, 78, vRest, vThresh + 1, 16);
    path += ' L ' + xOf(78) + ' ' + yOf(vSpikeTop);
    path += ' L ' + xOf(79.5) + ' ' + yOf(vRest);
    path += chargeTo(79.5, 100, vRest, -49, 10);

    var threshY = yOf(vThresh);
    var restY = yOf(vRest);

    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Membrane voltage trace of a leaky integrate-and-fire neuron, spiking and resetting">' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      '<line x1="' + padL + '" y1="' + padT + '" x2="' + padL + '" y2="' + (h - padB) + '" stroke="' + COL.border + '" stroke-width="1"/>' +
      '<line x1="' + padL + '" y1="' + (h - padB) + '" x2="' + (w - padR) + '" y2="' + (h - padB) + '" stroke="' + COL.border + '" stroke-width="1"/>' +
      '<line x1="' + padL + '" y1="' + threshY + '" x2="' + (w - padR) + '" y2="' + threshY + '" stroke="' + COL.accent + '" stroke-width="1" stroke-dasharray="4 4"/>' +
      '<text x="' + (w - padR) + '" y="' + (threshY - 6) + '" text-anchor="end" fill="' + COL.accent + '" font-size="12" font-family="ui-monospace, monospace">v_thresh = −45 mV</text>' +
      '<line x1="' + padL + '" y1="' + restY + '" x2="' + (w - padR) + '" y2="' + restY + '" stroke="' + COL.muted + '" stroke-width="1" stroke-dasharray="2 5"/>' +
      '<text x="' + (w - padR) + '" y="' + (restY + 16) + '" text-anchor="end" fill="' + COL.muted + '" font-size="12" font-family="ui-monospace, monospace">v_reset = −52 mV</text>' +
      '<path d="' + path + '" fill="none" stroke="' + COL.teal + '" stroke-width="2.2" stroke-linejoin="round"/>' +
      '<text x="' + xOf(28) + '" y="' + (padT + 10) + '" text-anchor="middle" fill="' + COL.text + '" font-size="11" font-family="system-ui, sans-serif">spike</text>' +
      '<text x="' + xOf(78) + '" y="' + (padT + 10) + '" text-anchor="middle" fill="' + COL.text + '" font-size="11" font-family="system-ui, sans-serif">spike</text>' +
      '<text x="' + xOf(33) + '" y="' + (h - padB + 18) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="10.5" font-family="system-ui, sans-serif">refractory (2.2 ms)</text>' +
      '<text x="' + (padL - 10) + '" y="' + (padT + plotH / 2) + '" text-anchor="end" fill="' + COL.muted + '" font-size="11" font-family="system-ui, sans-serif" transform="rotate(-90 ' + (padL - 40) + ' ' + (padT + plotH / 2) + ')">membrane potential</text>' +
      '<text x="' + (padL + plotW / 2) + '" y="' + (h - 6) + '" text-anchor="middle" fill="' + COL.muted + '" font-size="11" font-family="system-ui, sans-serif">time</text>' +
      '</svg>';
  }

  function buildMappingSvg(idSuffix) {
    idSuffix = idSuffix || '';
    var markerId = 'arrowhead2' + idSuffix;
    var w = 820, h = 300;
    var cellColors = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9', '#e34948', '#5eead4', '#8a90a2'];

    // Left: 3x3 board grid
    var gx = 60, gy = 40, gs = 66;
    var boardBoxes = '';
    var boardMarks = ['X', '', 'O', '', 'X', 'O', '', 'O', 'X'];
    for (var r = 0; r < 3; r++) {
      for (var c = 0; c < 3; c++) {
        var idx = r * 3 + c;
        var x = gx + c * gs, y = gy + r * gs;
        boardBoxes += '<rect x="' + x + '" y="' + y + '" width="' + (gs - 6) + '" height="' + (gs - 6) + '" rx="6" fill="' + cellColors[idx] + '" fill-opacity="0.22" stroke="' + cellColors[idx] + '" stroke-width="1.5"/>';
        var mark = boardMarks[idx];
        var cx = x + (gs - 6) / 2, cy = y + (gs - 6) / 2;
        if (mark === 'X') {
          boardBoxes += '<line x1="' + (cx - 12) + '" y1="' + (cy - 12) + '" x2="' + (cx + 12) + '" y2="' + (cy + 12) + '" stroke="' + COL.x + '" stroke-width="3" stroke-linecap="round"/>';
          boardBoxes += '<line x1="' + (cx + 12) + '" y1="' + (cy - 12) + '" x2="' + (cx - 12) + '" y2="' + (cy + 12) + '" stroke="' + COL.x + '" stroke-width="3" stroke-linecap="round"/>';
        } else if (mark === 'O') {
          boardBoxes += '<circle cx="' + cx + '" cy="' + cy + '" r="13" fill="none" stroke="' + COL.o + '" stroke-width="3"/>';
        }
      }
    }

    // Right: hex-column patch (pointy-top hexagons in offset rows, 3x3-ish)
    var hexR = 34;
    var hexW = Math.sqrt(3) * hexR;
    var hexH = 2 * hexR;
    var originX = 560, originY = 150;
    var hexes = '';
    var order = [
      [-1, -1], [0, -1], [1, -1],
      [-1, 0], [0, 0], [1, 0],
      [-1, 1], [0, 1], [1, 1],
    ];
    order.forEach(function (pos, idx) {
      var col = pos[0], row = pos[1];
      var cx = originX + col * hexW + (row % 2 !== 0 ? hexW / 2 : 0);
      var cy = originY + row * (hexH * 0.75);
      hexes += hexPath(cx, cy, hexR, cellColors[idx]);
    });

    var arrowsMid = '';
    var midX1 = gx + 3 * gs - 6 + 14;
    var midX2 = originX - 3 * hexR - 10;
    arrowsMid += '<line x1="' + midX1 + '" y1="' + (gy + 1.5 * gs - 3) + '" x2="' + midX2 + '" y2="' + originY + '" stroke="' + COL.muted + '" stroke-width="1.5" stroke-dasharray="5 4" marker-end="url(#' + markerId + ')"/>';

    return '' +
      '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mapping of the 3 by 3 tic-tac-toe board onto a 3 by 3 patch of hexagonal eye columns">' +
      '<defs><marker id="' + markerId + '" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="' + COL.muted + '"/></marker></defs>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="' + COL.bg + '"/>' +
      '<text x="' + (gx + (3 * gs - 6) / 2) + '" y="24" text-anchor="middle" fill="' + COL.muted + '" font-size="12.5" font-family="system-ui, sans-serif">the board</text>' +
      boardBoxes +
      arrowsMid +
      '<text x="' + originX + '" y="24" text-anchor="middle" fill="' + COL.muted + '" font-size="12.5" font-family="system-ui, sans-serif">right eye, hex columns</text>' +
      hexes +
      '</svg>';
  }

  function hexPath(cx, cy, r, fill) {
    var pts = [];
    for (var i = 0; i < 6; i++) {
      var ang = Math.PI / 180 * (60 * i - 90);
      pts.push((cx + r * Math.cos(ang)).toFixed(1) + ',' + (cy + r * Math.sin(ang)).toFixed(1));
    }
    return '<polygon points="' + pts.join(' ') + '" fill="' + fill + '" fill-opacity="0.28" stroke="' + fill + '" stroke-width="1.5"/>';
  }
})();
