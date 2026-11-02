// Pixel-art top-down tech-company office used by the Launch "Office" view.
// Base 960x540 map units; one unit equals one sprite art pixel (sprites are 30x38 art px).
// Regenerate the image and the seat/obstacle map with:
//   node scripts/office/draw-office.cjs public/office/office.png src/utils/officeMap.json
/* global require, process, Buffer */
const fs = require('fs')
const zlib = require('zlib')

const W = 960, H = 540
const buf = new Float32Array(W * H * 3)

let seed = 20261102
const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 }
const hash = (x, y, z = 0) => { let h = (x * 374761393 + y * 668265263 + z * 2147483647) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296 }

const hex = (c) => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]
const col = (c) => (typeof c === 'string' ? hex(c) : c)
function px(x, y, c, a = 1) {
  x = Math.round(x); y = Math.round(y)
  if (x < 0 || y < 0 || x >= W || y >= H || a <= 0) return
  const [r, g, b] = col(c), i = (y * W + x) * 3
  buf[i] += (r - buf[i]) * a; buf[i + 1] += (g - buf[i + 1]) * a; buf[i + 2] += (b - buf[i + 2]) * a
}
function rect(x, y, w, h, c, a = 1) { const k = col(c); for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) px(x + i, y + j, k, a) }
function rrect(x, y, w, h, r, c, a = 1) {
  const k = col(c)
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const cx = i < r ? r - i - 0.5 : i >= w - r ? i - (w - r) + 0.5 : 0
    const cy = j < r ? r - j - 0.5 : j >= h - r ? j - (h - r) + 0.5 : 0
    if (cx * cx + cy * cy <= r * r) px(x + i, y + j, k, a)
  }
}
const orrect = (x, y, w, h, r, fill, line = OL) => { rrect(x, y, w, h, r, line); rrect(x + 1, y + 1, w - 2, h - 2, Math.max(0, r - 1), fill) }
function ellipse(cx, cy, rx, ry, c, a = 1) {
  const k = col(c)
  for (let dy = -ry; dy <= ry; dy++) for (let dx = -rx; dx <= rx; dx++) if ((dx * dx) / ((rx + 0.5) * (rx + 0.5)) + (dy * dy) / ((ry + 0.5) * (ry + 0.5)) <= 1) px(cx + dx, cy + dy, k, a)
}
const disc = (cx, cy, r, c, a) => ellipse(cx, cy, r, r, c, a)
function vgrad(x, y, w, h, c1, c2) { const a = col(c1), b = col(c2); for (let j = 0; j < h; j++) { const t = h > 1 ? j / (h - 1) : 0; rect(x, y + j, w, 1, [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]) } }
function softShadow(x, y, w, h, { dx = 3, dy = 5, blur = 6, a = 0.32, r = 2 } = {}) {
  const X = x + dx, Y = y + dy
  for (let j = Y - blur; j < Y + h + blur; j++) for (let i = X - blur; i < X + w + blur; i++) {
    const ox = Math.max(X + r - i, 0, i - (X + w - 1 - r)), oy = Math.max(Y + r - j, 0, j - (Y + h - 1 - r))
    const d = Math.sqrt(ox * ox + oy * oy) - r
    if (d < blur) px(i, j, '#0b0d12', a * Math.pow(1 - Math.max(0, d) / blur, 2))
  }
}
function ovalShadow(cx, cy, rx, ry, a = 0.3) {
  for (let dy = -ry - 3; dy <= ry + 3; dy++) for (let dx = -rx - 3; dx <= rx + 3; dx++) {
    const d = Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry))
    if (d < 1.4) px(cx + dx, cy + dy, '#0b0d12', a * Math.min(1, (1.4 - d) / 0.5))
  }
}
function glow(cx, cy, rx, ry, c, a) {
  for (let dy = -ry; dy <= ry; dy++) for (let dx = -rx; dx <= rx; dx++) {
    const d = (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry)
    if (d < 1) px(cx + dx, cy + dy, c, a * Math.pow(1 - d, 1.6))
  }
}

// ---------- pixel font ----------
const GLYPH = {
  A: ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
  G: ['01110', '10001', '10000', '10111', '10001', '10001', '01110'],
  E: ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
  N: ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
  T: ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
  D: ['11110', '10001', '10001', '10001', '10001', '10001', '11110'],
  V: ['10001', '10001', '10001', '10001', '10001', '01010', '00100'],
}
function text(str, x, y, c, shadowC) {
  for (const ch of str) {
    const g = GLYPH[ch]
    if (g) g.forEach((row, j) => [...row].forEach((b, i) => { if (b === '1') { if (shadowC) px(x + i + 1, y + j + 1, shadowC); px(x + i, y + j, c) } }))
    x += 6
  }
}

// ---------- palette ----------
const OL = '#1c1f27'
const CAP = '#2d313b', CAP_HI = '#474d5c', CAP_LO = '#23262e'
const FACE = '#eceae6', FACE_SH = '#d6d3cd', BASE = '#3a3f4a'

// ---------- floors ----------
function oakWeave(x, y, w, h) {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y
    const cx = Math.floor(gx / 24), cy = Math.floor(gy / 24), u = gx % 24, v = gy % 24
    const horiz = (cx + cy) % 2 === 0
    const p = Math.floor((horiz ? v : u) / 8), along = horiz ? u : v, across = (horiz ? v : u) % 8
    const tone = (hash(cx, cy, p) - 0.5) * 18
    const grain = (hash(cx * 7 + p, Math.floor(along / 3), 9) - 0.5) * 6 + (across === 3 && hash(cx, cy, p + 5) > 0.5 ? -5 : 0)
    let r = 214 + tone + grain, g = 181 + tone * 0.9 + grain, b = 140 + tone * 0.7 + grain
    if (across === 7) { r -= 26; g -= 26; b -= 22 }
    if (across === 0) { r += 6; g += 6; b += 5 }
    if (u === 0 || v === 0) { r -= 14; g -= 14; b -= 12 }
    px(gx, gy, [r, g, b])
  }
}
function marble(x, y, w, h) {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y
    const n = Math.sin(gx * 0.035 + gy * 0.052 + 3.2 * Math.sin(gx * 0.012 + gy * 0.008) + 2.1 * Math.sin(gy * 0.021 - gx * 0.006))
    const m = Math.sin(gx * 0.06 - gy * 0.03 + 2 * Math.sin(gy * 0.017))
    let v = 238 + (hash(gx, gy, 3) - 0.5) * 4
    let c = [v, v, v + 2]
    if (Math.abs(n) < 0.035) c = [196, 198, 204]
    else if (Math.abs(n) < 0.08) c = [222, 223, 227]
    if (Math.abs(m) < 0.02) c = [208, 210, 216]
    if (gx % 48 === 0 || gy % 48 === 0) c = [210, 212, 217]
    px(gx, gy, c)
  }
}
function carpetTex(x, y, w, h, base, tile = 40) {
  const [r0, g0, b0] = col(base)
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y
    const tx = Math.floor(gx / tile), ty = Math.floor(gy / tile)
    const stripe = (tx + ty) % 2 ? gx % 3 === 0 : gy % 3 === 0
    const n = (hash(gx, gy, 1) - 0.5) * 8 + (stripe ? -4 : 0) + ((tx + ty) % 2 ? 2 : -2)
    px(gx, gy, [r0 + n, g0 + n, b0 + n])
  }
}
function terrazzo(x, y, w, h) {
  const chips = ['#c9b8a2', '#9aa3ad', '#d7a98c', '#7d8a80', '#b6bcc4']
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y, n = (hash(gx, gy, 2) - 0.5) * 4
    let c = [234 + n, 230 + n, 222 + n]
    const hh = hash(Math.floor(gx / 2), Math.floor(gy / 2), 4)
    if (hh < 0.05) c = col(chips[Math.floor(hh * 100) % chips.length])
    if (gx % 56 === 0 || gy % 56 === 0) c = [214, 209, 199]
    px(gx, gy, c)
  }
}
function rug(x, y, w, h, base, border, accent) {
  softShadow(x, y, w, h, { dx: 0, dy: 1, blur: 3, a: 0.18, r: 1 })
  rect(x, y, w, h, border)
  carpetTex(x + 3, y + 3, w - 6, h - 6, base, 1000)
  if (accent) {
    rect(x + 6, y + 6, w - 12, 1, accent); rect(x + 6, y + h - 7, w - 12, 1, accent)
    rect(x + 6, y + 6, 1, h - 12, accent); rect(x + w - 7, y + 6, 1, h - 12, accent)
    for (let i = x + 10; i < x + w - 10; i += 6) { px(i, y + 1, accent); px(i, y + h - 2, accent) }
  }
}

// ---------- walls ----------
function capH(x, y, len, t = 8) { rect(x, y, len, t, CAP); rect(x, y, len, 1, CAP_HI); rect(x, y + t - 1, len, 1, CAP_LO) }
function capV(x, y, len, t = 8) { rect(x, y, t, len, CAP); rect(x, y, 1, len, CAP_HI); rect(x + t - 1, y, 1, len, CAP_LO) }
function faceH(x, y, len, h = 16) {
  vgrad(x, y, len, h, FACE_SH, FACE)
  rect(x, y + h - 3, len, 3, BASE); rect(x, y + h - 3, len, 1, '#555b68')
}
function wallH(x, y, len) { capH(x, y, len); faceH(x, y + 8, len) }
function glassWallH(x, y, len) {
  rect(x, y, len, 4, '#8f98a6'); rect(x, y, len, 1, '#c4cbd6')
  rect(x, y + 4, len, 16, '#b9e0f0', 0.55)
  rect(x, y + 9, len, 4, '#f2f7fa', 0.55) // frosted band
  for (let i = 0; i < len; i += 40) rect(x + i, y + 4, 2, 16, '#8f98a6')
  for (let i = 6; i < len; i += 40) for (let k = 0; k < 10; k++) px(x + i + k, y + 18 - k, '#ffffff', 0.45)
  rect(x, y + 19, len, 1, '#8f98a6')
}
function ao(x, y, w, h, dir, a = 0.28) {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const t = dir === 'down' ? j / h : dir === 'up' ? 1 - j / h : dir === 'right' ? i / w : 1 - i / w
    px(x + i, y + j, '#141720', a * Math.pow(1 - t, 2))
  }
}
function windows(x, y, len, h) {
  rect(x, y, len, h, '#2f333d')
  const pane = 30
  for (let i = 0; i + 4 < len; i += pane + 3) {
    const ww = Math.min(pane, len - 3 - i), gx = x + 3 + i, gy = y + 3, gh = h - 6
    vgrad(gx, gy, ww, gh, '#d6f1fd', '#86c4e4')
    // distant skyline
    for (let k = 0; k < ww; k++) { const bh = 3 + Math.floor(hash(gx + k >> 2, 7) * 8); rect(gx + k, gy + gh - bh, 1, bh, '#9cc3d9', 0.7) }
    for (let k = 0; k < 12; k++) { px(gx + 4 + k, gy + gh - 1 - k, '#ffffff', 0.5); px(gx + 5 + k, gy + gh - 1 - k, '#ffffff', 0.3) }
    rect(gx, gy, ww, 1, '#ffffff', 0.6)
  }
  rect(x - 2, y + h, len + 4, 2, '#f7f6f3'); rect(x - 2, y + h + 2, len + 4, 1, '#bdb9b2')
}
function sunShaft(x, y, w, h) {
  for (let j = 0; j < h; j++) rect(x + j * 0.55, y + j, w, 1, '#fff4d2', 0.2 * Math.pow(1 - j / h, 1.3))
}
function threshold(x, y, w, h) { rect(x, y, w, h, '#a7acb6'); rect(x, y, w, 1, '#d4d8de') }

// ---------- furniture ----------
function desk(x, y, w, h, top = '#efece6', edge = '#c39a68') {
  softShadow(x, y, w, h, { blur: 5, a: 0.3 })
  rrect(x, y, w, h, 2, OL); rrect(x + 1, y + 1, w - 2, h - 2, 1, top)
  rect(x + 2, y + 1, w - 4, 1, '#ffffff', 0.6)
  rect(x + 1, y + h - 4, w - 2, 3, edge); rect(x + 1, y + h - 4, w - 2, 1, '#ffffff', 0.25)
}
function monitorBack(x, y, w = 28, h = 5) { rect(x + w / 2 - 3, y - 2, 6, 3, '#8a919e'); orrect(x, y, w, h, 2, '#3e4350'); rect(x + 2, y + 1, w - 4, 1, '#5b6170'); px(x + w / 2, y + 2, '#9aa1ae') }
function keyboard(x, y) { orrect(x, y, 20, 6, 1, '#e7e9ed', '#8a919e'); for (let r = 0; r < 2; r++) for (let k = 0; k < 8; k++) px(x + 2 + k * 2, y + 2 + r * 2, '#b5bac4') }
function mouseP(x, y) { rrect(x, y, 4, 6, 2, '#8a919e'); rect(x + 1, y + 1, 2, 2, '#e7e9ed') }
function coffee(x, y) { disc(x + 2, y + 2, 3, '#f4f2ee'); disc(x + 2, y + 2, 1, '#6b4127'); px(x + 1, y + 1, '#8b5a3a'); px(x + 6, y + 2, '#d6d3cd') }
function notebook(x, y, c = '#2b4c7e') { rect(x, y, 10, 12, c); rect(x + 1, y, 1, 12, '#ffffff', 0.4); rect(x + 9, y + 1, 1, 11, '#000000', 0.2) }
function paperStack(x, y) { rect(x + 1, y + 1, 10, 12, '#cfd3da'); rect(x, y, 10, 12, '#fafafa'); for (let k = 0; k < 4; k++) rect(x + 2, y + 2 + k * 2, 5 + (k % 2) * 2, 1, '#c3c8d0') }
function succulent(cx, cy) { disc(cx, cy + 2, 3, '#e9e5de'); disc(cx, cy, 3, '#5f9e6e'); px(cx - 1, cy - 1, '#9ad1a4'); px(cx + 1, cy + 1, '#3f7a51') }
function laptop(x, y) { orrect(x, y, 22, 14, 1, '#c9cdd4', '#7b818e'); rect(x + 2, y + 2, 18, 8, '#1f2d4a'); rect(x + 4, y + 4, 8, 1, '#7cc7ff'); rect(x + 4, y + 6, 12, 1, '#7ee0a3'); rect(x + 1, y + 11, 20, 2, '#e1e4e9') }
function deskLamp(x, y) { glow(x + 2, y + 2, 16, 11, '#ffe7a8', 0.22); disc(x + 1, y + 1, 5, '#000000', 0.25); disc(x, y, 5, '#8c6a3c'); disc(x, y, 4, '#f5ead2'); disc(x - 1, y - 1, 2, '#fffaf0') }

function chair(cx, cy, dir, theme = 'mesh') {
  const T = {
    mesh: ['#2b2f38', '#3e4451', '#1c1f26', '#4c5361'],
    leather: ['#7a4528', '#9a5b35', '#4e2b18', '#b87448'],
    white: ['#d9dce2', '#eef0f3', '#9ca2ad', '#ffffff'],
    sage: ['#5f7d6a', '#7a9a85', '#3f5648', '#93b39e'],
  }[theme]
  const [seat, seatHi, back, hi] = T
  ovalShadow(cx + 2, cy + 3, 10, 8, 0.3)
  // star base peeking out
  for (const [dx, dy] of [[-8, 0], [8, 0], [0, 8], [0, -8], [-6, 6], [6, 6], [-6, -6], [6, -6]]) px(cx + dx, cy + dy, '#3a3f4a')
  orrect(cx - 8, cy - 7, 16, 15, 4, seat, OL)
  rrect(cx - 6, cy - 5, 12, 4, 2, seatHi, 0.6)
  px(cx - 4, cy - 4, hi, 0.7)
  if (dir === 'up') { orrect(cx - 10, cy + 4, 20, 7, 3, back, OL); rect(cx - 7, cy + 5, 14, 1, hi, 0.35) }
  if (dir === 'down') { orrect(cx - 10, cy - 10, 20, 7, 3, back, OL); rect(cx - 7, cy - 9, 14, 1, hi, 0.45) }
  if (dir === 'right') { orrect(cx - 11, cy - 9, 7, 19, 3, back, OL); rect(cx - 10, cy - 7, 1, 14, hi, 0.4) }
  if (dir === 'left') { orrect(cx + 4, cy - 9, 7, 19, 3, back, OL); rect(cx + 5, cy - 7, 1, 14, hi, 0.3) }
  if (dir === 'up' || dir === 'down') { rect(cx - 10, cy - 3, 2, 8, back); rect(cx + 8, cy - 3, 2, 8, back) }
  else { rect(cx - 5, cy - 9, 9, 2, back); rect(cx - 5, cy + 8, 9, 2, back) }
}
function stool(cx, cy) { ovalShadow(cx + 1, cy + 3, 6, 4, 0.28); disc(cx, cy, 6, OL); disc(cx, cy, 5, '#b07a48'); disc(cx - 1, cy - 1, 3, '#c99460'); px(cx - 2, cy - 2, '#e2b583') }

function pot(cx, by, w, h, kind = 'white') {
  const P = { white: ['#f1efeb', '#d2cec6', '#ffffff'], concrete: ['#a7abb2', '#868b93', '#c4c8ce'], black: ['#30343d', '#1f2229', '#4b505b'], terracotta: ['#c4774a', '#9c5a34', '#de9467'] }[kind]
  ovalShadow(cx + 2, by, w / 2 + 2, 4, 0.32)
  orrect(cx - w / 2, by - h, w, h, 3, P[0])
  rect(cx - w / 2 + 1, by - h + 1, w - 2, 2, P[2], 0.8)
  rect(cx + w / 2 - 4, by - h + 3, 3, h - 5, P[1], 0.8)
  rect(cx - w / 2 + 2, by - h + 2, w - 4, 2, '#4a3324')
}
function bushyPlant(cx, by, s = 1, potKind = 'white') {
  const pw = Math.round(14 * s), ph = Math.round(11 * s)
  pot(cx, by, pw, ph, potKind)
  const R = Math.round(13 * s), top = by - ph - R + 3
  const greens = ['#1f5130', '#2b6b3c', '#358248', '#46a05a', '#62bd70']
  for (let layer = 0; layer < 5; layer++) {
    const n = 10 + layer * 3
    for (let k = 0; k < n; k++) {
      const ang = rnd() * Math.PI * 2, d = rnd() * R * (1 - layer * 0.16)
      const lx = cx + Math.cos(ang) * d, ly = top + Math.sin(ang) * d * 0.85 - layer * 1.2
      ellipse(Math.round(lx), Math.round(ly), Math.max(1, Math.round((4 - layer * 0.5) * s)), Math.max(1, Math.round((3 - layer * 0.4) * s)), greens[layer])
    }
  }
  for (let k = 0; k < 8 * s; k++) px(cx - R / 2 + rnd() * R * 0.8, top - R / 2 + rnd() * R * 0.6, '#9fe0a6')
}
function monstera(cx, by, s = 1) {
  pot(cx, by, Math.round(16 * s), Math.round(12 * s), 'concrete')
  const ccx = cx, ccy = by - Math.round(12 * s) - Math.round(9 * s)
  const leaves = [[200, 0.9], [250, 1], [290, 1.05], [330, 1], [20, 0.9], [160, 0.85], [110, 0.8], [65, 0.8]]
  leaves.sort((a, b) => Math.sin(a[0] * Math.PI / 180) - Math.sin(b[0] * Math.PI / 180))
  for (const [deg, k] of leaves) {
    const a = deg * Math.PI / 180, d = 9 * s * k
    const lx = Math.round(ccx + Math.cos(a) * d), ly = Math.round(ccy + Math.sin(a) * d * 0.8)
    const rx = Math.round(7 * s * k), ry = Math.round(5.5 * s * k)
    ellipse(lx, ly, rx + 1, ry + 1, '#173d24')
    ellipse(lx, ly, rx, ry, '#2f7a45')
    ellipse(lx - 1, ly - 1, Math.max(1, rx - 3), Math.max(1, ry - 2), '#3f9558')
    for (let t = 0; t <= 1; t += 0.08) px(ccx + (lx - ccx) * (0.4 + t * 0.9), ccy + (ly - ccy) * (0.4 + t * 0.9), '#6cc07f')
    for (const sgn of [-1, 1]) px(lx + Math.round(Math.sin(a) * sgn * rx * 0.6), ly - Math.round(Math.cos(a) * sgn * ry * 0.6), '#173d24')
  }
  disc(ccx, ccy, Math.round(3 * s), '#2f7a45'); px(ccx - 1, ccy - 1, '#6cc07f')
}
function snakePlant(cx, by) {
  pot(cx, by, 12, 10, 'black')
  for (let k = -4; k <= 4; k += 2) {
    const hgt = 16 + Math.abs((k * 7) % 6) + (k === 0 ? 6 : 0)
    for (let j = 0; j < hgt; j++) { const wdt = j > hgt - 4 ? 1 : 2; rect(cx + k + Math.round(k * j / 40), by - 10 - j, wdt, 1, j % 5 === 0 ? '#7a9e4a' : '#2f6b3c') }
    rect(cx + k, by - 10 - hgt + 3, 1, hgt - 3, '#c9c25a', 0.5)
  }
}
function bookshelf(x, y, w, h, wood = '#5b3a24', woodHi = '#7a5134') {
  softShadow(x, y, w, h, { blur: 5, a: 0.3 })
  orrect(x, y, w, h, 1, wood); rect(x + 1, y + 1, w - 2, 1, woodHi)
  const books = ['#a8433d', '#2f5d8a', '#c99a3e', '#4f7a5a', '#6b4f8a', '#e8e2d0', '#2d7f7f', '#8a8f99', '#d27a4a']
  for (let sy = y + 3; sy + 9 <= y + h - 2; sy += 10) {
    rect(x + 2, sy, w - 4, 8, '#2b1c12')
    rect(x + 1, sy + 8, w - 2, 2, woodHi)
    let bx = x + 3
    while (bx < x + w - 5) {
      const r = rnd()
      if (r < 0.08) { disc(bx + 2, sy + 5, 2, '#e8e2d0'); px(bx + 2, sy + 2, '#5fb574'); bx += 6; continue }
      if (r < 0.14) { bx += 3; continue }
      const bw = r < 0.5 ? 2 : 3, bh = 5 + Math.floor(rnd() * 3), c = books[Math.floor(rnd() * books.length)]
      rect(bx, sy + 8 - bh, bw, bh, c); rect(bx, sy + 8 - bh, 1, bh, '#ffffff', 0.18)
      bx += bw
    }
  }
}
function sofa(x, y, w, h, dir, c = ['#a8643a', '#c27c4c', '#7c4526', '#e0a074']) {
  const [base, cush, dark, hi] = c
  softShadow(x, y, w, h, { blur: 6, a: 0.34, r: 3 })
  orrect(x, y, w, h, 4, dark)
  const seats = dir === 'up' || dir === 'down' ? Math.max(1, Math.round((w - 12) / 26)) : Math.max(1, Math.round((h - 12) / 26))
  if (dir === 'up' || dir === 'down') {
    const sy = dir === 'up' ? y + 2 : y + 8, sh = h - 10, sw = (w - 12) / seats
    for (let k = 0; k < seats; k++) { orrect(Math.round(x + 6 + k * sw), sy, Math.round(sw), sh, 3, cush, dark); rect(Math.round(x + 8 + k * sw), sy + 2, Math.round(sw) - 4, 1, hi, 0.7) }
    rrect(x + 3, dir === 'up' ? y + h - 7 : y + 2, w - 6, 5, 2, base); rect(x + 5, dir === 'up' ? y + h - 6 : y + 3, w - 10, 1, hi, 0.4)
  } else {
    const sx = dir === 'right' ? x + 8 : x + 2, sw = w - 10, sh = (h - 12) / seats
    for (let k = 0; k < seats; k++) { orrect(sx, Math.round(y + 6 + k * sh), sw, Math.round(sh), 3, cush, dark); rect(sx + 2, Math.round(y + 8 + k * sh), sw - 4, 1, hi, 0.7) }
    rrect(dir === 'right' ? x + 2 : x + w - 7, y + 3, 5, h - 6, 2, base)
  }
  rrect(x + 1, y + 1, w - 2, 5, 2, base, dir === 'down' || dir === 'up' ? 0 : 1)
  if (dir === 'right' || dir === 'left') { rrect(x + 2, y + 1, w - 4, 5, 2, base); rrect(x + 2, y + h - 6, w - 4, 5, 2, base) }
  else { rrect(x + 1, y + 2, 5, h - 4, 2, base); rrect(x + w - 6, y + 2, 5, h - 4, 2, base) }
}
function roundTable(cx, cy, r, top = '#f2f0ec', edge = '#b9b5ad', veins = true) {
  ovalShadow(cx + 3, cy + 5, r, Math.round(r * 0.8), 0.32)
  disc(cx, cy + 1, r, OL); disc(cx, cy + 1, r - 1, edge); disc(cx, cy, r - 1, top)
  if (veins) for (let k = -r + 3; k < r - 3; k++) px(cx + k, cy + Math.round(Math.sin(k * 0.35) * 2.5), '#cfd1d6')
  glow(cx - r / 3, cy - r / 3, Math.round(r / 2), Math.round(r / 3), '#ffffff', 0.5)
}
function whiteboard(x, y, w, h) {
  rect(x + 3, y + h, 2, 6, '#7b818e'); rect(x + w - 5, y + h, 2, 6, '#7b818e')
  softShadow(x, y, w, h, { blur: 4, a: 0.25 })
  orrect(x, y, w, h, 1, '#fbfbfc', '#8a919e')
  rect(x + 4, y + 4, 18, 1, '#2f5d8a'); rect(x + 4, y + 7, 26, 1, '#2f5d8a'); rect(x + 4, y + 10, 14, 1, '#a8433d')
  orrect(x + w - 24, y + 3, 10, 9, 0, '#fff3a8', '#e2c85a'); orrect(x + w - 13, y + 5, 10, 9, 0, '#bde6c8', '#7cbf8f')
  rect(x + 38, y + 4, 1, 12, '#4f7a5a'); rect(x + 38, y + 15, 14, 1, '#4f7a5a'); rect(x + 40, y + 12, 3, 3, '#4f7a5a'); rect(x + 45, y + 9, 3, 6, '#4f7a5a')
}
function printer(x, y) { softShadow(x, y, 30, 22, { blur: 4 }); orrect(x, y, 30, 22, 2, '#d9dce2', '#7b818e'); rect(x + 2, y + 2, 26, 6, '#f1f3f6'); rect(x + 5, y + 11, 20, 4, '#2d313b'); rect(x + 7, y + 8, 16, 4, '#ffffff'); px(x + 25, y + 17, '#5fd17a'); px(x + 22, y + 17, '#7b818e') }
function waterCooler(x, y) { softShadow(x, y, 16, 26, { blur: 4 }); orrect(x, y + 10, 16, 16, 2, '#eef0f3', '#7b818e'); disc(x + 8, y + 7, 7, '#5d8fb0'); disc(x + 8, y + 6, 6, '#9fd8f2'); px(x + 5, y + 4, '#ffffff'); px(x + 6, y + 3, '#ffffff'); rect(x + 4, y + 18, 2, 2, '#3b82c4'); rect(x + 10, y + 18, 2, 2, '#d9534f') }
function counter(x, y, w, h, top = 'marble', front = '#5b3a24') {
  softShadow(x, y, w, h, { blur: 5, a: 0.32 })
  orrect(x, y, w, h, 1, front)
  for (let i = x + 3; i < x + w - 2; i += 4) rect(i, y + h - 7, 1, 6, '#000000', 0.18)
  if (top === 'marble') {
    rect(x + 1, y + 1, w - 2, h - 8, '#f3f2ef')
    for (let i = 0; i < w - 4; i++) px(x + 2 + i, y + 3 + Math.round((Math.sin(i * 0.11) + 1) * (h - 13) / 2), '#cfd1d6')
  } else rect(x + 1, y + 1, w - 2, h - 8, top)
  rect(x + 1, y + h - 8, w - 2, 1, '#c9a24f') // brass trim
  rect(x + 1, y + 1, w - 2, 1, '#ffffff', 0.7)
}
function fridge(x, y, w, h) { softShadow(x, y, w, h, { blur: 4 }); orrect(x, y, w, h, 2, '#d6dade', '#6b717d'); vgrad(x + 2, y + 2, w - 4, h - 4, '#eef0f3', '#c4c9d0'); rect(x + 1, y + Math.round(h * 0.35), w - 2, 1, '#8a919e'); rect(x + w - 5, y + 5, 1, 8, '#6b717d'); rect(x + w - 5, y + Math.round(h * 0.35) + 4, 1, 14, '#6b717d') }
function tv(x, y, w, h) { orrect(x, y, w, h, 1, '#101217', '#000000'); vgrad(x + 2, y + 2, w - 4, h - 4, '#24395e', '#16213a'); rect(x + 5, y + 4, Math.round(w * 0.3), 2, '#7cc7ff'); for (let k = 0; k < 4; k++) rect(x + w - 30 + k * 6, y + h - 4 - (k + 1) * 2, 4, (k + 1) * 2, ['#7ee0a3', '#7cc7ff', '#f5d67a', '#ff9bd0'][k]); glow(x + w / 2, y + h + 8, w / 2 + 10, 10, '#8fc8ff', 0.12) }
function cabinetsWall(x, y, w, h) { rect(x, y, w, h, '#f4f2ee'); for (let i = x; i < x + w; i += 24) { rect(i, y, 1, h, '#c9c5bd'); rect(i + 18, y + h - 9, 1, 6, '#8a919e') } rect(x, y + h - 1, w, 1, '#c9c5bd'); rect(x, y, w, 1, '#ffffff') }

// ================= LAYOUT (tech company, v3) =================
// One sprite pixel (240x304 sprite = 30x38 art px) equals one map unit, so characters
// are drawn at 38 map units tall and line up with the furniture pixel grid.

const DEPT = {
  eng: '#4f8cff', design: '#e06fb4', mgmt: '#c9a24f', pantry: '#84cc16',
  qa: '#ef6b5b', rnd: '#8b6cf0', ops: '#2fbf9b', lobby: '#94a3b8', meeting: '#f59e0b',
}
const rooms = []
const seats = []
const solids = []
const doors = []
const solid = (x, y, w, h) => solids.push([Math.round(x), Math.round(y), Math.round(w), Math.round(h)])
const room = (id, x, y, w, h, label) => rooms.push({ id, x, y, w, h, label, color: DEPT[id] })
const addSeat = (id, dept, x, y, facing, purpose = 'work', kind = 'chair') => seats.push({ id, dept, x, y, facing, purpose, kind })

// ---------- extra materials & props ----------
function concrete(x, y, w, h) {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y, n = (hash(gx, gy, 5) - 0.5) * 5 + Math.sin(gx * 0.02 + gy * 0.013) * 2
    let c = [206 + n, 208 + n, 212 + n]
    if (gx % 64 === 0 || gy % 64 === 0) c = [190, 193, 199]
    px(gx, gy, c)
  }
}
function vinyl(x, y, w, h, a, b) {
  const A = col(a), B = col(b)
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y, t = (Math.floor(gx / 16) + Math.floor(gy / 16)) % 2
    const n = (hash(gx, gy, 6) - 0.5) * 4, c = t ? A : B
    px(gx, gy, gx % 16 === 0 || gy % 16 === 0 ? [c[0] - 10, c[1] - 10, c[2] - 10] : [c[0] + n, c[1] + n, c[2] + n])
  }
}
function raisedFloor(x, y, w, h) {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const gx = i + x, gy = j + y, u = gx % 20, v = gy % 20
    let c = [70, 76, 88]
    if (u === 0 || v === 0) c = [48, 52, 61]
    else if (u === 1 || v === 1) c = [92, 99, 112]
    else if (u % 4 === 2 && v % 4 === 2) c = [56, 61, 71]
    px(gx, gy, c)
  }
}
function monitorStyled(x, y, w, h, style) {
  rect(x + w / 2 - 3, y + h - 1, 6, 3, '#8a919e'); rect(x + w / 2 - 5, y + h + 2, 10, 1, '#5d6472')
  orrect(x, y, w, h, 1, '#14171d', OL)
  const ix = x + 2, iy = y + 2, iw = w - 4, ih = h - 4
  if (style === 'design') {
    vgrad(ix, iy, iw, ih, '#f6f0ff', '#e9dcff')
    disc(ix + 6, iy + 4, 3, '#e06fb4'); rect(ix + 11, iy + 2, 8, 5, '#4f8cff'); rect(ix + 3, iy + ih - 2, iw - 6, 1, '#8b6cf0')
  } else if (style === 'data') {
    vgrad(ix, iy, iw, ih, '#1b2240', '#141a30')
    for (let k = 0; k < 6; k++) { const bh = 2 + Math.floor(hash(x, k) * (ih - 3)); rect(ix + 2 + k * 3, iy + ih - bh, 2, bh, ['#8b6cf0', '#4f8cff', '#2fbf9b'][k % 3]) }
    for (let k = 0; k < iw - 6; k++) px(ix + 3 + k, iy + 2 + Math.round(Math.sin(k * 0.6 + x) * 1.5 + 1.5), '#f5d67a')
  } else if (style === 'term') {
    rect(ix, iy, iw, ih, '#0c1210')
    for (let k = 0; k < Math.floor(ih / 2); k++) rect(ix + 1, iy + 1 + k * 2, 3 + Math.floor(hash(k, x) * (iw - 5)), 1, '#3ee08f', 0.9)
  } else if (style === 'qa') {
    vgrad(ix, iy, iw, ih, '#1f2d4a', '#162036')
    for (let k = 0; k < Math.floor((ih - 1) / 2); k++) {
      const ok = hash(x, k, 3) > 0.25
      px(ix + 2, iy + 1 + k * 2, ok ? '#4ade80' : '#ef6b5b'); rect(ix + 4, iy + 1 + k * 2, 5 + Math.floor(hash(k, x, 1) * (iw - 10)), 1, '#c3cbe0', 0.8)
    }
  } else {
    vgrad(ix, iy, iw, ih, '#1f2d4a', '#162036')
    const lines = ['#7ee0a3', '#7cc7ff', '#ff9bd0', '#f5d67a', '#c3cbe0']
    for (let k = 0; k < Math.floor((ih - 1) / 2); k++) {
      const ind = Math.floor(hash(x, y, k) * 3) * 2, len = 4 + Math.floor(hash(x, k, y) * (iw - 8))
      rect(ix + 1 + ind, iy + 1 + k * 2, Math.min(len, iw - 2 - ind), 1, lines[Math.floor(hash(k, x) * lines.length)], 0.9)
    }
  }
  glow(x + w / 2, y + h + 4, w / 2 + 4, 6, style === 'term' ? '#7dffb6' : '#9fd8ff', 0.12)
}
function tablet(x, y) { orrect(x, y, 16, 11, 2, '#2d313b'); rect(x + 2, y + 2, 12, 7, '#3a3f4b'); rect(x + 14, y + 3, 1, 6, '#c9a24f'); px(x + 5, y + 5, '#e06fb4') }
function phone(x, y) { orrect(x, y, 5, 8, 1, '#2d313b'); rect(x + 1, y + 1, 3, 5, '#7cc7ff') }
function corkBoard(x, y, w, h, notes) {
  orrect(x, y, w, h, 1, '#b9895a', '#6e4426'); for (let k = 0; k < w * h / 25; k++) px(x + 2 + rnd() * (w - 4), y + 2 + rnd() * (h - 4), '#9c6f44')
  const cols = notes || ['#fff3a8', '#ffb3b3', '#bde6c8', '#b9d7ff']
  for (let i = x + 3; i < x + w - 7; i += 9) for (let j = y + 2; j < y + h - 6; j += 7) if (hash(i, j) > 0.25) { rect(i, j, 6, 5, cols[Math.floor(hash(j, i) * cols.length)]); px(i + 2, j, '#d9534f') }
}
function kanban(x, y, w, h) {
  orrect(x, y, w, h, 1, '#fbfbfc', '#8a919e')
  const colW = Math.floor((w - 2) / 3), heads = ['#4f8cff', '#f59e0b', '#2fbf9b']
  for (let c = 0; c < 3; c++) {
    rect(x + 1 + c * colW, y + 1, colW, 2, heads[c]); if (c) rect(x + 1 + c * colW, y + 1, 1, h - 2, '#d6d9df')
    for (let r = 0; r < 3; r++) if (hash(c, r, x) > 0.2) rect(x + 3 + c * colW, y + 5 + r * 7, colW - 5, 5, ['#fff3a8', '#bde6c8', '#b9d7ff', '#ffb3b3'][(c + r) % 4])
  }
}
function wallScreen(x, y, w, h) {
  orrect(x, y, w, h, 1, '#101217', '#000000'); vgrad(x + 1, y + 1, w - 2, h - 2, '#17203a', '#101830')
  for (let k = 0; k < w - 30; k++) px(x + 3 + k, y + h - 4 - Math.round((Math.sin(k * 0.15) + 1) * (h - 8) / 3 + k * (h - 8) / (w * 1.4)), '#8b6cf0')
  for (let k = 0; k < 4; k++) rect(x + w - 24 + k * 5, y + h - 3 - (k + 2) * 2, 3, (k + 2) * 2, ['#4f8cff', '#2fbf9b', '#f5d67a', '#e06fb4'][k])
  glow(x + w / 2, y + h + 8, w / 2 + 6, 10, '#a99bff', 0.12)
}
function serverRack(x, y, w, h) {
  softShadow(x, y, w, h, { blur: 4, a: 0.35 })
  orrect(x, y, w, h, 1, '#23262e', '#0f1115'); rect(x + 1, y + 1, w - 2, 1, '#3a3f4b')
  for (let j = y + 4; j < y + h - 3; j += 5) {
    rect(x + 2, j, w - 4, 3, '#2d313b'); rect(x + 2, j, w - 4, 1, '#3e4350')
    px(x + 3, j + 1, hash(x, j) > 0.3 ? '#3ee08f' : '#f5b84a'); px(x + 5, j + 1, hash(j, x) > 0.5 ? '#4f8cff' : '#3ee08f')
    for (let i = x + 8; i < x + w - 3; i += 2) px(i, j + 1, '#1a1d23')
  }
}
function beanBag(cx, cy, c, d, l) { ovalShadow(cx + 2, cy + 4, 11, 7, 0.32); ellipse(cx, cy, 11, 9, d); ellipse(cx, cy - 1, 10, 8, c); ellipse(cx - 3, cy - 3, 5, 3, l) }
function vending(x, y, w, h) {
  softShadow(x, y, w, h, { blur: 4 }); orrect(x, y, w, h, 2, '#c43d3d', '#7a1f1f')
  rect(x + 2, y + 3, w - 8, h - 10, '#bfe3f0', 0.9)
  const cs = ['#f5d67a', '#4f8cff', '#2fbf9b', '#e06fb4', '#ff9b55']
  for (let j = y + 5; j < y + h - 9; j += 5) for (let i = x + 3; i < x + w - 7; i += 3) rect(i, j, 2, 3, cs[Math.floor(hash(i, j) * cs.length)])
  rect(x + w - 5, y + 6, 2, 6, '#2d313b'); rect(x + 2, y + h - 6, w - 8, 3, '#2d313b')
}
function bench(x, y, w) { softShadow(x, y, w, 10, { blur: 3, a: 0.28 }); orrect(x, y, w, 10, 2, '#b07a48', '#5b3a24'); for (let i = x + 4; i < x + w - 2; i += 6) rect(i, y + 2, 1, 6, '#8a5a34') }
function deviceShelf(x, y, w, h) {
  softShadow(x, y, w, h, { blur: 4 }); orrect(x, y, w, h, 1, '#d9dce2', '#7b818e')
  for (let i = x + 3; i < x + w - 6; i += 8) { phone(i, y + 3); if (hash(i, y) > 0.4) tablet(i, y + h - 13) }
}
function doorFrame(x, y, w, horizontal) {
  if (horizontal) { rect(x - 1, y, 2, 6, '#1c1f27'); rect(x + w - 1, y, 2, 6, '#1c1f27') } else { rect(x, y - 1, 6, 2, '#1c1f27'); rect(x, y + w - 1, 6, 2, '#1c1f27') }
}

// ---------- workstation pods ----------
const STYLE = { eng: 'code', design: 'design', qa: 'qa', rnd: 'data', ops: 'term' }
const FELT = { eng: ['#4d6fa8', '#2f4a78', '#7896cc'], design: ['#b8608f', '#7f3b61', '#d98bb3'], qa: ['#b8584d', '#7c342c', '#d98479'], rnd: ['#6d5bb8', '#45387d', '#9585d6'], ops: ['#2f8f76', '#1c5c4b', '#58b89d'] }
function pod(dept, x0, y0, perSide, seatW = 52) {
  const w = perSide * seatW
  for (let k = 0; k < perSide; k++) {
    const cx = x0 + k * seatW + seatW / 2
    chair(cx, y0 - 12, 'down'); addSeat(`${dept}-${seats.filter((s) => s.dept === dept).length}`, dept, cx, y0 - 12, 'D')
    chair(cx, y0 + 66, 'up'); addSeat(`${dept}-${seats.filter((s) => s.dept === dept).length}`, dept, cx, y0 + 66, 'U')
  }
  desk(x0, y0, w, 26); desk(x0, y0 + 28, w, 26)
  for (let k = 1; k < perSide; k++) rect(x0 + k * seatW, y0 + 1, 1, 52, '#000000', 0.15)
  for (let k = 0; k < perSide; k++) {
    const dx = x0 + k * seatW, mw = 26, mx = dx + (seatW - mw) / 2
    monitorBack(mx, y0 + 17, mw)
    monitorStyled(mx, y0 + 32, mw, 13, STYLE[dept])
    if (dept === 'design') { tablet(dx + 8, y0 + 4); tablet(dx + 8, y0 + 42) } else { keyboard(dx + 15, y0 + 5); keyboard(dx + 15, y0 + 45) }
    mouseP(dx + seatW - 12, y0 + 5); mouseP(dx + seatW - 12, y0 + 45)
    if (dept === 'qa') { phone(dx + 4, y0 + 4); phone(dx + 4, y0 + 40) }
    if (hash(dx, y0) > 0.5) coffee(dx + 4, y0 + 44); else succulent(dx + seatW - 6, y0 + 40)
  }
  const [f, fd, fl] = FELT[dept]
  softShadow(x0 - 1, y0 + 24, w + 2, 6, { dx: 1, dy: 2, blur: 3, a: 0.3 })
  orrect(x0 - 1, y0 + 24, w + 2, 6, 2, f, fd); rect(x0 + 1, y0 + 25, w - 2, 1, fl)
  solid(x0 - 1, y0, w + 2, 54)
}

// ---------- coordinates ----------
const TOP_Y = 60, CAP_TOP = 216, CORR_Y = 220, CAP_BOT = 284, BOT_Y = 292, END_Y = 516

// backdrop
vgrad(0, 0, W, H, '#262a33', '#1c1f26')
for (let j = 0; j < H; j += 8) for (let i = (j / 8) % 2 ? 4 : 0; i < W; i += 8) px(i, j, '#2f343f')
softShadow(16, 16, 928, 508, { dx: 6, dy: 10, blur: 14, a: 0.6, r: 4 })

// floors
oakWeave(24, TOP_Y, 368, 160)
terrazzo(398, TOP_Y, 198, 160)
carpetTex(602, TOP_Y, 174, 160, '#2f3a52')
vinyl(782, TOP_Y, 154, 160, '#ece8df', '#e2dccf')
concrete(24, CORR_Y, 912, 72)
vinyl(24, BOT_Y, 190, 224, '#e4e8ee', '#d9dee6')
carpetTex(220, BOT_Y, 200, 224, '#33405e')
raisedFloor(426, BOT_Y, 160, 224)
marble(592, BOT_Y - 8, 150, 232)
carpetTex(748, BOT_Y, 188, 224, '#3b3f48')

room('eng', 24, TOP_Y, 368, 156); room('design', 398, TOP_Y, 198, 156); room('mgmt', 602, TOP_Y, 174, 156); room('pantry', 782, TOP_Y, 154, 156)
room('qa', 24, BOT_Y, 190, 224); room('rnd', 220, BOT_Y, 200, 224); room('ops', 426, BOT_Y, 160, 224); room('lobby', 592, BOT_Y, 150, 224); room('meeting', 748, BOT_Y, 188, 224)
rooms.push({ id: 'corridor', x: 24, y: CORR_Y, w: 912, h: 64 })

for (const sx of [44, 250]) sunShaft(sx, TOP_Y, 100, 60)
sunShaft(486, TOP_Y, 90, 50); sunShaft(612, TOP_Y, 80, 44)

// ---------- outer walls ----------
capH(16, 16, 928)
faceH(24, 24, 912, 36)
windows(36, 28, 114, 26); kanban(162, 27, 74, 30); windows(246, 28, 140, 26)
corkBoard(406, 27, 62, 30, ['#ffb3d9', '#e9dcff', '#bfe3ff', '#fff3a8']); windows(478, 28, 112, 26)
windows(610, 28, 92, 26)
cabinetsWall(790, 26, 110, 30)
const ENTRY = [646, 690]
vgrad(16, END_Y, ENTRY[0] - 16, 8, CAP, CAP_LO); vgrad(ENTRY[1], END_Y, 944 - ENTRY[1], 8, CAP, CAP_LO)
rect(16, END_Y, ENTRY[0] - 16, 1, CAP_HI); rect(ENTRY[1], END_Y, 944 - ENTRY[1], 1, CAP_HI)
capV(16, 16, 508); capV(936, 16, 508)
ao(24, TOP_Y, 912, 10, 'down', 0.3); ao(24, TOP_Y, 8, 456, 'right', 0.22); ao(928, TOP_Y, 8, 456, 'left', 0.22)
solid(0, 0, 960, TOP_Y + 2); solid(0, 0, 24, 540); solid(936, 0, 24, 540)
solid(0, END_Y, ENTRY[0], 24); solid(ENTRY[1], END_Y, 960 - ENTRY[1], 24)

// ---------- top row: vertical walls + glass front with doors ----------
for (const x of [392, 596, 776]) { capV(x, TOP_Y, CAP_TOP - TOP_Y + 4, 6); ao(x + 6, TOP_Y, 6, 156, 'right', 0.18); solid(x, TOP_Y, 6, CAP_TOP - TOP_Y + 20) }
const topDoors = [[108, 144], [292, 328], [478, 514], [616, 652], [846, 882]]
let cursor = 24
for (const [a, b] of [...topDoors, [936, 936]]) {
  if (a > cursor) { glassWallH(cursor, CAP_TOP, a - cursor); solid(cursor, CAP_TOP, a - cursor, 20) }
  if (a < 936) { doorFrame(a, CAP_TOP, b - a, true); threshold(a, CAP_TOP, b - a, 4); doors.push({ x: (a + b) / 2, y: CAP_TOP + 10 }) }
  cursor = b
}
ao(24, CAP_TOP + 20, 912, 8, 'down', 0.18)

// ---------- bottom row: north walls (lobby open to corridor) + vertical walls ----------
const botDoors = [[132, 168], [300, 336], [452, 488], [592, 742], [782, 818]]
cursor = 24
for (const [a, b] of [...botDoors, [936, 936]]) {
  if (a > cursor) { wallH(cursor, CAP_BOT, a - cursor); solid(cursor, CAP_BOT, a - cursor, 24) }
  if (a < 936 && b - a < 100) { doorFrame(a, CAP_BOT, b - a, true); threshold(a, CAP_BOT, b - a, 8); doors.push({ x: (a + b) / 2, y: CAP_BOT + 12 }) }
  cursor = b
}
for (const x of [214, 420, 586, 742]) { capV(x, CAP_BOT, END_Y - CAP_BOT, 6); ao(x + 6, BOT_Y, 6, 224, 'right', 0.16); solid(x, CAP_BOT, 6, END_Y - CAP_BOT) }
ao(24, BOT_Y + 16, 562, 8, 'down', 0.2); ao(748, BOT_Y + 16, 188, 8, 'down', 0.2)
// decorations on the visible faces of the bottom north walls
corkBoard(36, 293, 84, 13, ['#ffb3b3', '#fff3a8', '#bde6c8'])
wallScreen(236, 293, 168, 13)
orrect(500, 293, 70, 13, 1, '#0c1210', '#000000'); for (let k = 0; k < 5; k++) rect(503, 295 + k * 2, 10 + Math.floor(hash(k, 9) * 50), 1, '#3ee08f', 0.85)
tv(838, 293, 80, 13)

// ceiling light pools
for (const [cx, cy, rx, ry] of [[196, 140, 170, 60], [497, 140, 90, 54], [689, 132, 80, 50], [858, 140, 70, 50], [119, 390, 90, 60], [320, 390, 95, 60], [506, 400, 74, 60], [842, 400, 90, 70]]) glow(cx, cy, rx, ry, '#fff1c9', 0.1)
glow(480, 252, 440, 26, '#ffffff', 0.08)

// ---------- ENGINEERING (12 desks) ----------
for (const x0 of [44, 160, 276]) pod('eng', x0, 104, 2, 48)
snakePlant(34, 202); bushyPlant(384, 210, 0.8, 'concrete')

// ---------- DESIGN STUDIO (4 desks + bean bag) ----------
pod('design', 446, 104, 2)
roundTable(418, 196, 9, '#f4f2ee', '#b9b5ad'); solid(409, 187, 18, 18)
monstera(586, 100, 0.8); solid(574, 78, 24, 26)
beanBag(568, 196, '#e06fb4', '#9c3f74', '#f3a3cf'); addSeat('design-bean', 'design', 568, 194, 'D', 'rest', 'sofa')

// ---------- MANAGEMENT ----------
bookshelf(712, 38, 58, 32, '#3e2a1b', '#5b3e28'); solid(712, 38, 58, 32)
rug(616, 90, 146, 110, '#c8b08a', '#7a5f3e', '#e8d8b6')
desk(640, 112, 98, 28, '#6b4429', '#3e2717'); rect(642, 114, 94, 1, '#8a5d3c'); solid(640, 112, 98, 28)
orrect(670, 116, 38, 13, 2, '#2d313b', '#1c1f26'); monitorBack(675, 132, 28, 5); keyboard(679, 118); paperStack(646, 116); deskLamp(726, 120); coffee(714, 118)
chair(689, 100, 'down', 'leather'); addSeat('mgmt-0', 'mgmt', 689, 100, 'D')
chair(665, 166, 'up', 'white'); addSeat('mgmt-1', 'mgmt', 665, 166, 'U')
chair(713, 166, 'up', 'white'); addSeat('mgmt-2', 'mgmt', 713, 166, 'U')
bushyPlant(614, 206, 0.8, 'black'); solid(604, 186, 20, 22)
snakePlant(764, 206); solid(756, 186, 16, 22)

// ---------- PANTRY & LOUNGE ----------
counter(786, 56, 116, 30)
rect(800, 60, 24, 14, '#9aa1ae'); rect(802, 62, 20, 10, '#c4cad3'); rect(811, 58, 2, 5, '#6b717d')
orrect(834, 52, 18, 22, 2, '#2d313b'); rect(837, 56, 12, 5, '#a8433d'); rect(839, 64, 8, 6, '#f4f2ee'); coffee(840, 66)
orrect(862, 56, 30, 18, 2, '#3e4350'); rect(865, 59, 18, 12, '#161a21'); px(887, 62, '#5fd17a')
fridge(906, 40, 26, 52)
solid(786, 56, 116, 30); solid(906, 40, 26, 52)
vending(788, 112, 22, 40); solid(788, 112, 22, 40)
roundTable(858, 140, 15, '#f4f2ee', '#b9b5ad'); coffee(852, 134); coffee(862, 140); solid(843, 125, 30, 30)
stool(832, 140); stool(884, 140); stool(858, 168)
addSeat('pantry-1', 'pantry', 832, 140, 'R', 'rest', 'coffee'); addSeat('pantry-2', 'pantry', 884, 140, 'L', 'rest', 'coffee'); addSeat('pantry-3', 'pantry', 858, 168, 'U', 'rest', 'coffee')
beanBag(916, 190, '#4f8cff', '#2c5290', '#8fb6ff'); addSeat('pantry-bean', 'pantry', 916, 188, 'D', 'rest', 'sofa')
beanBag(806, 194, '#84cc16', '#4d7c0f', '#bef264'); addSeat('pantry-bean-2', 'pantry', 806, 192, 'D', 'rest', 'sofa')
addSeat('pantry-coffee', 'pantry', 843, 100, 'U', 'rest', 'stand')

// ---------- CORRIDOR ----------
bench(186, 240, 64); solid(186, 240, 64, 10); addSeat('corr-1', 'corridor', 204, 246, 'D', 'rest', 'sofa'); addSeat('corr-2', 'corridor', 232, 246, 'D', 'rest', 'sofa')
bench(538, 240, 64); solid(538, 240, 64, 10); addSeat('corr-3', 'corridor', 556, 246, 'D', 'rest', 'sofa'); addSeat('corr-4', 'corridor', 584, 246, 'D', 'rest', 'sofa')
waterCooler(756, 238); solid(756, 238, 16, 26); addSeat('corr-cooler', 'corridor', 764, 274, 'U', 'rest', 'stand')
bushyPlant(40, 266, 0.75, 'white'); solid(30, 248, 20, 20); bushyPlant(920, 266, 0.75, 'white'); solid(910, 248, 20, 20)
snakePlant(400, 262); solid(392, 244, 16, 20)

// ---------- QA LAB (6 desks) ----------
pod('qa', 44, 352, 3, 50)
deviceShelf(36, 470, 96, 34); solid(36, 470, 96, 34)
bushyPlant(196, 506, 0.8, 'black'); solid(186, 486, 20, 22)
printer(150, 478); solid(150, 478, 30, 22)

// ---------- R&D / AI LAB (6 desks + brainstorm table) ----------
pod('rnd', 242, 352, 3)
whiteboard(236, 466, 64, 20); solid(236, 466, 64, 24)
roundTable(368, 478, 12); solid(356, 466, 24, 24)
chair(342, 478, 'right', 'sage'); addSeat('rnd-6', 'rnd', 342, 478, 'R')
chair(394, 478, 'left', 'sage'); addSeat('rnd-7', 'rnd', 394, 478, 'L')
laptop(358, 472)

// ---------- OPS & INFRASTRUCTURE (server room) ----------
pod('ops', 454, 352, 2)
for (const x of [436, 466, 496]) { serverRack(x, 448, 24, 60); solid(x, 448, 24, 60) }
desk(556, 444, 24, 62, '#3e4350', '#23262e'); solid(556, 444, 24, 62)
monitorStyled(560, 450, 16, 11, 'term'); monitorStyled(560, 478, 16, 11, 'term')
chair(540, 458, 'right'); addSeat('ops-4', 'ops', 540, 458, 'R')
chair(540, 490, 'right'); addSeat('ops-5', 'ops', 540, 490, 'R')

// ---------- LOBBY / RECEPTION ----------
counter(612, 334, 112, 24); solid(612, 334, 112, 24)
monitorBack(630, 344, 24, 5); monitorBack(678, 344, 24, 5); paperStack(706, 338); bushyPlant(716, 344, 0.45, 'white')
chair(642, 320, 'down'); addSeat('lobby-0', 'lobby', 642, 320, 'D', 'human')
chair(690, 320, 'down'); addSeat('lobby-1', 'lobby', 690, 320, 'D', 'human')
sofa(600, 398, 30, 70, 'right', ['#2f3a52', '#41506e', '#1f2738', '#6a7da3']); solid(600, 398, 30, 70)
addSeat('lobby-2', 'lobby', 615, 416, 'R', 'human', 'sofa'); addSeat('lobby-3', 'lobby', 615, 450, 'R', 'human', 'sofa')
roundTable(648, 432, 9); solid(639, 423, 18, 18)
chair(730, 414, 'left', 'white'); addSeat('lobby-4', 'lobby', 730, 414, 'L', 'human')
chair(730, 450, 'left', 'white'); addSeat('lobby-5', 'lobby', 730, 450, 'L', 'human')
rug(634, 478, 68, 32, '#2f3a52', '#1f2738', '#c9a24f')
text('AGENTDEV', 644, 491, '#d9b46a', '#000000')
bushyPlant(604, 506, 0.85, 'black'); solid(594, 486, 20, 22)
rect(ENTRY[0], END_Y, ENTRY[1] - ENTRY[0], 8, '#b9e0f0', 0.75); rect((ENTRY[0] + ENTRY[1]) / 2 - 1, END_Y, 2, 8, '#8f98a6')
rect((ENTRY[0] + ENTRY[1]) / 2 - 5, END_Y + 2, 1, 4, '#c9a24f'); rect((ENTRY[0] + ENTRY[1]) / 2 + 4, END_Y + 2, 1, 4, '#c9a24f')

// ---------- MEETING ROOM (8 seats) ----------
rug(764, 330, 156, 160, '#545b68', '#2d313b', '#8a919e')
const mx = [808, 842, 876]
for (const x of mx) { chair(x, 378, 'down', 'white'); addSeat(`meeting-${seats.filter((s) => s.dept === 'meeting').length}`, 'meeting', x, 378, 'D') }
for (const x of mx) { chair(x, 444, 'up', 'white'); addSeat(`meeting-${seats.filter((s) => s.dept === 'meeting').length}`, 'meeting', x, 444, 'U') }
chair(778, 411, 'right', 'white'); addSeat('meeting-6', 'meeting', 778, 411, 'R')
chair(906, 411, 'left', 'white'); addSeat('meeting-7', 'meeting', 906, 411, 'L')
desk(792, 390, 100, 42, '#6b4429', '#3e2717'); rect(794, 392, 96, 1, '#8a5d3c'); solid(792, 390, 100, 42)
for (let j = 394; j < 428; j += 8) rect(794, j, 96, 1, '#5e3b23', 0.5)
for (const x of mx) { notebook(x - 5, 393, '#2d313b'); notebook(x - 5, 416, '#2d313b') }
laptop(830, 404); orrect(864, 406, 12, 8, 2, '#2d313b'); px(870, 409, '#7cc7ff')
bushyPlant(762, 506, 0.85, 'black'); solid(752, 486, 20, 22); bushyPlant(924, 506, 0.85, 'black'); solid(914, 486, 20, 22)
snakePlant(924, 320); solid(916, 300, 16, 22)

// ---------- finishing ----------
for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) {
  const dx = (i - W / 2) / (W / 2), dy = (j - H / 2) / (H / 2), d = dx * dx * 0.6 + dy * dy * 0.8
  if (d > 0.45) px(i, j, '#000000', Math.min(0.2, (d - 0.45) * 0.32))
}
rect(15, 15, 930, 1, OL); rect(15, 524, 930, 1, OL); rect(15, 15, 1, 510, OL); rect(944, 15, 1, 510, OL)

// ---------- encode PNG ----------
const SC = Number(process.env.OFFICE_SCALE || 4)
const OW = W * SC, OH = H * SC, stride = OW * 3 + 1
const raw = Buffer.alloc(stride * OH)
for (let y = 0; y < OH; y++) for (let x = 0; x < OW; x++) {
  const i = ((y / SC | 0) * W + (x / SC | 0)) * 3, o = y * stride + 1 + x * 3
  raw[o] = Math.max(0, Math.min(255, buf[i])); raw[o + 1] = Math.max(0, Math.min(255, buf[i + 1])); raw[o + 2] = Math.max(0, Math.min(255, buf[i + 2]))
}
const crcT = new Int32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c })
const crc = (b) => { let c = -1; for (const v of b) c = crcT[(c ^ v) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0 }
const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]) }
const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(OW, 0); ihdr.writeUInt32BE(OH, 4); ihdr[8] = 8; ihdr[9] = 2
const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))])
const out = process.argv[2] || 'office.png'
fs.writeFileSync(out, png)
if (process.argv[3]) {
  const map = { width: W, height: H, entrance: { x: (ENTRY[0] + ENTRY[1]) / 2, y: END_Y - 8 }, rooms, seats, obstacles: solids, doors }
  fs.writeFileSync(process.argv[3], JSON.stringify(map) + '\n')
}
console.log('wrote', out, OW + 'x' + OH, 'seats:', seats.length, 'work:', seats.filter((s) => s.purpose === 'work').length, 'rest:', seats.filter((s) => s.purpose === 'rest').length)
