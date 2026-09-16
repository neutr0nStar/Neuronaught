// brain.js — live 3D point cloud of ~140k neurons that light up when they spike.
//
// Rendering is a single custom ShaderMaterial point cloud so we can keep
// 140,024 points at 60fps: inactive neurons render as tiny, low-alpha,
// dark-tinted "ghost" dots, and only the (typically ~20%) neurons that are
// currently spiking get a bigger, brighter, additive-blended sprite. Per
// frame we only touch the neurons in a typed-array "active list" — never a
// full pass over all 140k points, and never a Set.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const NEUTRAL_TINT = new THREE.Color(0x3a4672);
const INPUT_TINT = new THREE.Color(0x234b52);
const READOUT_TINT = new THREE.Color(0x4a3720);
const DIM_FACTOR = 0.08;

const X_MARK_COLOR = new THREE.Color(0x7dd3fc);
const O_MARK_COLOR = new THREE.Color(0xf9a8d4);

const VERTEX_SHADER = `
  attribute vec3 aTint;
  attribute float aDim;
  attribute float aActivity;
  uniform float uDpr;
  uniform float uBrightness;
  varying vec3 vColor;
  varying float vActivity;
  varying float vDim;
  varying float vViewZ;
  void main() {
    vColor = aTint;
    vActivity = aActivity;
    vDim = aDim;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewZ = -mvPosition.z;
    float size = mix(1.5 * sqrt(uBrightness), 4.5, aActivity);
    gl_PointSize = size * uDpr;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = `
  varying vec3 vColor;
  varying float vActivity;
  varying float vDim;
  varying float vViewZ;
  uniform float uNear;
  uniform float uFar;
  uniform float uBrightness;
  void main() {
    vec2 c = gl_PointCoord - vec2(0.5);
    float d = length(c) * 2.0;
    if (d > 1.0) discard;
    float edge = 1.0 - smoothstep(0.55, 1.0, d);
    vec3 hot = vec3(1.0, 1.0, 1.0);
    vec3 baseTint = clamp(vColor * uBrightness, 0.0, 1.0);
    vec3 col = mix(baseTint, hot, clamp(vActivity, 0.0, 1.0));
    float depthFactor = clamp((vViewZ - uNear) / max(uFar - uNear, 0.0001), 0.0, 1.0);
    float distDim = mix(1.0, 0.35, depthFactor);
    float alpha = clamp(mix(0.34 * uBrightness, 1.0, vActivity), 0.0, 1.0) * edge * distDim * vDim;
    gl_FragColor = vec4(col, alpha);
  }
`;

let renderer, scene, camera, controls, points, geometry, material;
let tintAttr, dimAttr, activityAttr;
let container;
let n = 0;
let activity = null;
let activeList = null;
let activeFlags = null;
let activeCount = 0;
let view = 'all';
let decay = 0.85;
let brightness = 1.0;
let currentBoard = null;
let inputSetX = [];
let inputSetO = [];
let inputAll = new Set();
let readoutSet = new Set();
let fpsEl = null;
let spikingEl = null;
let framesEl = null;
let frameCount = 0;
let totalFrames = 0;
let lastStatTime = 0;
let idleTimer = null;
let defaultCameraPos = new THREE.Vector3(0, 0, 2.4);
let defaultTarget = new THREE.Vector3(0, 0, 0);

export const Brain = {
  init(el, m, xyz) {
    container = el;
    n = m.n;
    activity = new Float32Array(n);
    activeList = new Uint32Array(n);
    activeFlags = new Uint8Array(n);
    activeCount = 0;

    inputSetX = (m.input_groups && (m.input_groups.X || m.input_groups.cell_X)) || [];
    inputSetO = (m.input_groups && (m.input_groups.O || m.input_groups.cell_O)) || [];
    inputAll = new Set();
    inputSetX.forEach((arr) => arr.forEach((i) => inputAll.add(i)));
    inputSetO.forEach((arr) => arr.forEach((i) => inputAll.add(i)));
    readoutSet = new Set(m.readout || []);

    const positions = orientCloud(xyz);
    const fitInfo = fitCamera(positions);

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0d12);

    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 100);
    camera.position.copy(fitInfo.cameraPos);
    defaultCameraPos = fitInfo.cameraPos.clone();
    defaultTarget = new THREE.Vector3(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.4;
    controls.target.copy(defaultTarget);
    controls.addEventListener('start', () => {
      controls.autoRotate = false;
      if (idleTimer) clearTimeout(idleTimer);
    });
    controls.addEventListener('end', () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        controls.autoRotate = true;
      }, 3000);
    });

    geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    tintAttr = new THREE.BufferAttribute(new Float32Array(n * 3), 3);
    dimAttr = new THREE.BufferAttribute(new Float32Array(n).fill(1), 1);
    activityAttr = new THREE.BufferAttribute(new Float32Array(n), 1);
    geometry.setAttribute('aTint', tintAttr);
    geometry.setAttribute('aDim', dimAttr);
    geometry.setAttribute('aActivity', activityAttr);

    material = new THREE.ShaderMaterial({
      uniforms: {
        uDpr: { value: dpr },
        uNear: { value: fitInfo.near },
        uFar: { value: fitInfo.far },
        uBrightness: { value: brightness },
      },
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.AdditiveBlending,
    });

    points = new THREE.Points(geometry, material);
    scene.add(points);

    computeTints();

    fpsEl = document.getElementById('fps-counter');
    spikingEl = document.getElementById('stat-spiking');
    framesEl = document.getElementById('stat-frames');

    const resetBtn = document.getElementById('brain-reset-btn');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        camera.position.copy(defaultCameraPos);
        controls.target.copy(defaultTarget);
        controls.update();
        controls.autoRotate = true;
      });
    }

    window.addEventListener('resize', onResize);
    renderer.setAnimationLoop(animate);
  },

  spikes(idxArray) {
    if (!activity) return;
    for (let i = 0; i < idxArray.length; i++) {
      const idx = idxArray[i];
      activity[idx] = 1;
      if (!activeFlags[idx]) {
        activeFlags[idx] = 1;
        activeList[activeCount++] = idx;
      }
    }
  },

  setBoard(board) {
    currentBoard = board;
    computeTints();
  },

  setView(mode) {
    view = mode;
    computeTints();
  },

  setDecay(v) {
    decay = v;
  },

  setBrightness(v) {
    brightness = v;
    if (material) material.uniforms.uBrightness.value = v;
  },
};

// Rotate + recenter the raw xyz so the cloud's longest axis reads as
// horizontal on screen (camera looks down -Z with Y up), and the cloud is
// centered on the origin regardless of where the connectome coordinates put
// the soma positions.
function orientCloud(xyz) {
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < xyz.length; i += 3) {
    const x = xyz[i], y = xyz[i + 1], z = xyz[i + 2];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const cz = (minZ + maxZ) / 2;
  const ex = maxX - minX;
  const ey = maxY - minY;
  const ez = maxZ - minZ;

  const longest = ex >= ey && ex >= ez ? 'x' : ey >= ez ? 'y' : 'z';

  const out = new Float32Array(xyz.length);
  for (let i = 0; i < xyz.length; i += 3) {
    const x = xyz[i] - cx;
    const y = xyz[i + 1] - cy;
    const z = xyz[i + 2] - cz;
    if (longest === 'y') {
      out[i] = -y; out[i + 1] = x; out[i + 2] = z;
    } else if (longest === 'z') {
      out[i] = z; out[i + 1] = y; out[i + 2] = -x;
    } else {
      out[i] = x; out[i + 1] = y; out[i + 2] = z;
    }
  }
  out._extents = [ex, ey, ez];
  return out;
}

function fitCamera(positions) {
  let maxR2 = 0;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i], y = positions[i + 1], z = positions[i + 2];
    const r2 = x * x + y * y + z * z;
    if (r2 > maxR2) maxR2 = r2;
  }
  const radius = Math.max(Math.sqrt(maxR2), 0.05);
  const fovRad = (50 * Math.PI) / 180;
  const dist = (radius / Math.sin(fovRad / 2)) * 1.2;
  return {
    cameraPos: new THREE.Vector3(0, 0, dist),
    near: dist - radius,
    far: dist + radius,
  };
}

function computeTints() {
  if (!tintAttr) return;
  const tint = tintAttr.array;
  const dim = dimAttr.array;

  for (let i = 0; i < n; i++) {
    let c = NEUTRAL_TINT;
    if (inputAll.has(i)) c = INPUT_TINT;
    if (readoutSet.has(i)) c = READOUT_TINT;
    tint[i * 3] = c.r;
    tint[i * 3 + 1] = c.g;
    tint[i * 3 + 2] = c.b;

    let d = 1;
    if (view === 'inputs' && !inputAll.has(i)) d = DIM_FACTOR;
    if (view === 'readout' && !readoutSet.has(i)) d = DIM_FACTOR;
    dim[i] = d;
  }

  if (currentBoard) {
    for (let cell = 0; cell < 9; cell++) {
      const v = currentBoard[cell];
      if (v === 1 && inputSetX[cell]) paintGroup(tint, inputSetX[cell], X_MARK_COLOR);
      else if (v === 2 && inputSetO[cell]) paintGroup(tint, inputSetO[cell], O_MARK_COLOR);
    }
  }

  tintAttr.needsUpdate = true;
  dimAttr.needsUpdate = true;
}

function paintGroup(tint, arr, color) {
  for (let j = 0; j < arr.length; j++) {
    const idx = arr[j];
    tint[idx * 3] = color.r;
    tint[idx * 3 + 1] = color.g;
    tint[idx * 3 + 2] = color.b;
  }
}

function animate() {
  if (activityAttr && activity) {
    const arr = activityAttr.array;
    let write = 0;
    for (let read = 0; read < activeCount; read++) {
      const idx = activeList[read];
      activity[idx] *= decay;
      if (activity[idx] > 0.01) {
        arr[idx] = activity[idx];
        activeList[write++] = idx;
      } else {
        activity[idx] = 0;
        arr[idx] = 0;
        activeFlags[idx] = 0;
      }
    }
    activeCount = write;
    activityAttr.needsUpdate = true;
  }

  controls.update();
  renderer.render(scene, camera);
  tickStats();
}

function tickStats() {
  frameCount++;
  totalFrames++;
  const now = performance.now();
  if (now - lastStatTime >= 500) {
    const fps = Math.round((frameCount * 1000) / (now - lastStatTime));
    if (fpsEl) fpsEl.textContent = `${fps} fps`;
    if (spikingEl) spikingEl.textContent = activeCount.toLocaleString();
    if (framesEl) framesEl.textContent = totalFrames.toLocaleString();
    frameCount = 0;
    lastStatTime = now;
  }
}

function onResize() {
  if (!container || !camera || !renderer) return;
  const w = container.clientWidth || 1;
  const h = container.clientHeight || 1;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}
