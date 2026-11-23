// 첫 화면 장면: 구름섬 배경이 흐르고 캐릭터들이 날아가며, 가운데 위에서 로고 글자가 통통 튄다
import { RULES } from '/shared/rules.js';
import { CHARACTERS } from '/shared/characters.js';
import { ART, Atlas, loadWorld } from './assets.js';

const W = RULES.view.w;
const H = RULES.view.h;

export class TitleScene {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;
    this.running = false;
    this.world = null;
    this.logo = null;
    this.t0 = performance.now();
    // 캐릭터마다 높이·속도·시작 위치를 다르게
    this.flyers = CHARACTERS.map((c, i) => ({
      id: c.id,
      y: 300 + i * 52,
      speed: 70 + i * 14,
      x: -120 - i * 260,
      phase: i * 1.7,
    }));
    // CSS가 캔버스를 화면에 꽉 채우고, 그림 해상도는 창 비율에 맞춰 바꾼다
    this.cw = W;
    this.ch = H;
    new ResizeObserver(() => this.fit()).observe(canvas);
  }

  async start() {
    if (this.running) return;
    this.running = true;
    if (!this.world) this.world = await loadWorld('cloud');
    if (!this.logo) this.logo = await Atlas.load('/assets/ui/logo_parts.json');
    this.fit();
    this.last = performance.now();
    requestAnimationFrame((ts) => this.frame(ts));
  }

  stop() {
    this.running = false;
  }

  // 960×540이 통째로 들어가는 배율을 고르고, 창이 더 넓거나 높으면 그만큼 그림을 넓게 또는 높게 그린다.
  // 그래서 창 비율이 어떻든 로고와 캐릭터가 잘리지 않는다
  fit() {
    const vw = this.canvas.clientWidth;
    const vh = this.canvas.clientHeight;
    if (!vw || !vh) return;
    const k = Math.min(vw / W, vh / H);
    const cw = Math.max(W, Math.round(vw / k));
    const ch = Math.max(H, Math.round(vh / k));
    if (this.canvas.width !== cw || this.canvas.height !== ch) {
      this.canvas.width = cw;
      this.canvas.height = ch;
      this.ctx.imageSmoothingEnabled = false;
    }
    this.cw = cw;
    this.ch = ch;
  }

  frame(ts) {
    if (!this.running) return;
    const dt = Math.min(0.05, (ts - this.last) / 1000);
    this.last = ts;
    const t = (ts - this.t0) / 1000;
    const ctx = this.ctx;
    const w = this.world;
    const camX = t * 60;
    const cw = this.cw;
    const ch = this.ch;
    // 960×540 기준 장면을 아래에 붙이고, 창이 더 높으면 위로 하늘이 늘어난다
    const oy = ch - H;

    ctx.clearRect(0, 0, cw, ch);
    if (w.sky) {
      const s = Math.max(cw / w.sky.width, ch / w.sky.height);
      const sw = Math.ceil(w.sky.width * s);
      const sh = Math.ceil(w.sky.height * s);
      ctx.drawImage(w.sky, Math.round((cw - sw) / 2), ch - sh, sw, sh);
    }
    for (const [img, f, k] of [[w.far, 0.25, w.k.far], [w.mid, 0.6, w.k.mid]]) {
      if (!img) continue;
      const iw = Math.round(img.width * k);
      const ih = Math.round(img.height * k);
      const off = -(((Math.round(camX * f) % iw) + iw) % iw);
      for (let x = off; x < cw; x += iw) ctx.drawImage(img, x, ch - ih, iw, ih);
    }

    // 날아가는 캐릭터
    for (const f of this.flyers) {
      f.x += f.speed * dt;
      if (f.x > cw + 120) f.x = -120 - Math.random() * 300;
      const y = oy + f.y + Math.sin(t * 1.8 + f.phase) * 14;
      ART.chars[f.id]?.draw(ctx, 'fly', f.x, y, { t: t + f.phase });
    }

    if (this.logo && this.logo.img) this.drawLogo(t, cw / 2, oy * 0.4 + 262);
    requestAnimationFrame((x) => this.frame(x));
  }

  // 로고 부품을 하나씩 움직여 그린다. (cx, base)가 글자 바닥선 가운데
  drawLogo(t, cx, base) {
    const L = this.logo;
    const def = L.def;
    const ctx = this.ctx;
    const S = LOGO_SCALE;
    // 글자 폭 전체의 가운데를 cx에 맞춘다
    const left = def.layout.in[0] - L.frame('in').ax;
    const right = def.layout.tto[0] - L.frame('tto').ax + L.frame('tto').sw;
    const ox = cx - ((left + right) / 2) * S;
    // 글자는 번갈아 통통 뛰고, 땅에 닿을 때 살짝 납작해진다
    const hop = {};
    ['in', 'tto'].forEach((n, i) => {
      const h = Math.abs(Math.sin(t * Math.PI / HOP_SEC + i * Math.PI / 2));
      const land = Math.pow(1 - h, 6);
      hop[n] = { dy: -h * HOP_PX, sx: 1 + 0.07 * land, sy: 1 - 0.07 * land + 0.03 * h };
    });
    // 날개는 파닥이고, 별은 반짝이고, 구름은 천천히 흔들린다
    const flap = Math.sin(t * Math.PI * 2 * 1.3) * 0.26;
    const moves = {
      wingL: { rot: flap },
      wingR: { rot: -flap },
      cloud: { dx: Math.sin(t * 0.9) * 5, dy: Math.sin(t * 1.3) * 2 },
      cloudS: { dx: Math.sin(t * 0.9 + 2) * 5, dy: Math.sin(t * 1.3 + 1) * 2 },
    };
    [['sparkle', 0], ['star', 1.3], ['sparkleS', 2.6]].forEach(([n, ph]) => {
      const tw = (Math.sin(t * 3.1 + ph) + 1) / 2;
      moves[n] = { sx: 0.7 + 0.4 * tw, sy: 0.7 + 0.4 * tw, rot: n === 'star' ? Math.sin(t * 1.7) * 0.18 : 0, alpha: 0.6 + 0.4 * tw };
    });
    ctx.save();
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    for (const n of def.order) {
      const f = L.frame(n);
      if (!f) continue;
      const m = moves[n] || {};
      const h = hop[n] || hop[def.follow[n]] || { dy: 0, sx: 1, sy: 1 };
      const own = hop[n];
      const [lx, ly] = def.layout[n];
      ctx.save();
      ctx.translate(ox + (lx + (m.dx || 0)) * S, base + (ly + h.dy + (m.dy || 0)) * S);
      if (m.rot) ctx.rotate(m.rot);
      ctx.scale(S * (own ? own.sx : m.sx || 1), S * (own ? own.sy : m.sy || 1));
      if (m.alpha != null) ctx.globalAlpha = m.alpha;
      ctx.drawImage(L.img, f.sx, f.sy, f.sw, f.sh, -f.ax, -f.ay, f.sw, f.sh);
      ctx.restore();
    }
    ctx.restore();
  }
}

const LOGO_SCALE = 0.85; // 부품 그림을 이만큼 줄여 그린다
const HOP_SEC = 0.75; // 한 번 뛰는 데 걸리는 초
const HOP_PX = 12; // 뛰는 높이, 부품 그림 픽셀
