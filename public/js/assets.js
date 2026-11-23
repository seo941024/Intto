// PNG 아틀라스 읽기와 그리기. 형식은 tools/art/ASSET_SPEC.md
import { CHARACTERS } from '/shared/characters.js';

export function loadImage(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => {
      console.warn('그림을 읽지 못함', url);
      resolve(null);
    };
    img.src = url;
  });
}

export class Atlas {
  constructor(def, img, url) {
    this.def = def;
    this.img = img;
    this.url = url;
    this.anims = def.animations || {};
    this.cols = img && def.frameWidth ? Math.max(1, Math.floor(img.width / def.frameWidth)) : 1;
    this.cache = new Map();
    // 그림이 어느 화면 크기 기준인지. res가 없는 그림은 640×360 기준 임시 그림이라 1.5배로 그린다
    this.k = def.res ? 960 / def.res : 1.5;
  }

  static async load(url) {
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error(res.status);
      const def = await res.json();
      const img = await loadImage(new URL(def.image, new URL(url, location.href)).href);
      if (!img) return Atlas.empty(url);
      return new Atlas(def, img, url);
    } catch (e) {
      console.warn('아틀라스를 읽지 못함', url, e);
      return Atlas.empty(url);
    }
  }

  static empty(url) {
    return new Atlas({ animations: {} }, null, url);
  }

  has(name) {
    return !!(this.img && this.anims[name]);
  }

  // name 애니메이션의 프레임 사각형. t는 초, index를 주면 그 프레임
  frame(name, t = 0, index = null) {
    const a = this.anims[name];
    if (!a || !this.img) return null;
    const frames = a.frames;
    let i;
    if (index != null) i = Math.min(frames.length - 1, Math.max(0, index));
    else {
      const k = Math.floor(t * (a.fps || 1));
      i = a.loop === false ? Math.min(frames.length - 1, k) : ((k % frames.length) + frames.length) % frames.length;
    }
    const key = name + ':' + i;
    let f = this.cache.get(key);
    if (f) return f;
    const fr = frames[i];
    let sx, sy, sw, sh;
    if (Array.isArray(fr)) [sx, sy, sw, sh] = fr;
    else {
      sw = this.def.frameWidth;
      sh = this.def.frameHeight;
      sx = (fr % this.cols) * sw;
      sy = Math.floor(fr / this.cols) * sh;
    }
    const anchor = a.anchor || [sw / 2, sh / 2];
    f = { sx, sy, sw, sh, ax: anchor[0], ay: anchor[1], hit: a.hit };
    this.cache.set(key, f);
    return f;
  }

  frameCount(name) {
    const a = this.anims[name];
    return a ? a.frames.length : 0;
  }

  // anchor가 (x, y)에 오도록 그린다
  draw(ctx, name, x, y, opt = {}) {
    const f = this.frame(name, opt.t || 0, opt.index ?? null);
    if (!f) return false;
    const s = (opt.scale || 1) * this.k;
    const dx = Math.round(x - f.ax * s);
    const dy = Math.round(y - f.ay * s);
    const w = Math.round(f.sw * s);
    const h = Math.round(f.sh * s);
    if (opt.alpha != null && opt.alpha < 1) {
      const prev = ctx.globalAlpha;
      ctx.globalAlpha = prev * opt.alpha;
      this.blit(ctx, f, dx, dy, w, h, opt.flipX);
      ctx.globalAlpha = prev;
    } else this.blit(ctx, f, dx, dy, w, h, opt.flipX);
    return true;
  }

  // 왼쪽 위가 (x, y)
  drawAt(ctx, name, x, y, opt = {}) {
    const f = this.frame(name, opt.t || 0, opt.index ?? null);
    if (!f) return false;
    const w = opt.w ?? Math.round(f.sw * this.k);
    const h = opt.h ?? Math.round(f.sh * this.k);
    this.blit(ctx, f, Math.round(x), Math.round(y), w, h, false);
    return true;
  }

  // 화면에 그려질 크기
  size(name) {
    const f = this.frame(name);
    return f ? { w: Math.round(f.sw * this.k), h: Math.round(f.sh * this.k) } : { w: 0, h: 0 };
  }

  // 프레임 아래 가운데가 (x, bottom)
  drawBottom(ctx, name, x, bottom, opt = {}) {
    const f = this.frame(name, opt.t || 0, opt.index ?? null);
    if (!f) return false;
    const w = Math.round(f.sw * this.k);
    const h = Math.round(f.sh * this.k);
    this.blit(ctx, f, Math.round(x - w / 2), Math.round(bottom - h), w, h, false);
    return true;
  }

  blit(ctx, f, dx, dy, w, h, flipX) {
    if (flipX) {
      ctx.save();
      ctx.translate(dx + w, dy);
      ctx.scale(-1, 1);
      ctx.drawImage(this.img, f.sx, f.sy, f.sw, f.sh, 0, 0, w, h);
      ctx.restore();
    } else ctx.drawImage(this.img, f.sx, f.sy, f.sw, f.sh, dx, dy, w, h);
  }

  // 한 프레임을 별도 canvas로 잘라 낸다. 패턴 채우기·띠 타일용.
  // native면 그림 원래 크기 그대로 두고, 아니면 화면 크기로 맞춘다
  toCanvas(name, native = false) {
    const f = this.frame(name);
    if (!f) return null;
    const c = document.createElement('canvas');
    const k = native ? 1 : this.k;
    c.width = Math.round(f.sw * k);
    c.height = Math.round(f.sh * k);
    const ctx = c.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this.img, f.sx, f.sy, f.sw, f.sh, 0, 0, c.width, c.height);
    return c;
  }
}

// 게임 내내 쓰는 공용 그림
export const ART = {
  chars: {}, // id → Atlas
  portraits: {}, // id → 얼굴 그림. 진행 막대에서 쓴다
  sprite: {}, // id → sprite.json 원본, hitRadius 등
  trail: {}, // id → 날갯짓 부스러기 Atlas
  items: null,
  fx: null,
  particles: null, // 모든 캐릭터가 같이 쓰는 가속 바람줄
  ui: null,
  hud: null, // 게임 화면 HUD, 구름섬 시안에서 오려 낸 그림
  worlds: {}, // theme → { sky, far, mid, tiles, obstacles }
  ready: false,
};

export async function loadCommonArt() {
  const jobs = [];
  for (const c of CHARACTERS) {
    jobs.push(
      Atlas.load(`/assets/characters/${c.id}/sprite.json`).then(async (a) => {
        ART.chars[c.id] = a;
        ART.sprite[c.id] = a.def;
        // 부스러기 그림이 있는 캐릭터만 sprite.json에 trail 파일 이름이 적혀 있다
        if (a.def.trail) ART.trail[c.id] = await Atlas.load(`/assets/characters/${c.id}/${a.def.trail}`);
      }),
    );
  }
  for (const c of CHARACTERS) jobs.push(loadImage(`/assets/characters/${c.id}/portrait.png`).then((img) => (ART.portraits[c.id] = img)));
  jobs.push(Atlas.load('/assets/items/items.json').then((a) => (ART.items = a)));
  jobs.push(Atlas.load('/assets/fx/fx.json').then((a) => (ART.fx = a)));
  jobs.push(Atlas.load('/assets/fx/particles.json').then((a) => (ART.particles = a)));
  jobs.push(Atlas.load('/assets/ui/ui.json').then((a) => (ART.ui = a)));
  jobs.push(Atlas.load('/assets/ui/hud.json').then((a) => (ART.hud = a)));
  await Promise.all(jobs);
  ART.ready = true;
}

export async function loadWorld(theme) {
  if (ART.worlds[theme]) return ART.worlds[theme];
  const base = `/assets/world/${theme}/`;
  const [sky, far, mid, tiles, obstacles] = await Promise.all([
    loadImage(base + 'sky.png'),
    loadImage(base + 'far.png'),
    loadImage(base + 'mid.png'),
    Atlas.load(base + 'tiles.json'),
    Atlas.load(base + 'obstacles.json'),
  ]);
  // 배경 그림이 960 폭이 아니면 640 기준 임시 그림이므로 키워 그린다. 층마다 따로 바뀌므로 따로 잰다
  // 960 기준 층은 높이가 540, 임시 그림은 360이다. 폭은 양 끝을 이은 띠라 그림마다 다르다
  const kOf = (img) => (img && img.height >= 540 ? 1 : 1.5);
  const w = { sky, far, mid, tiles, obstacles, k: { sky: kOf(sky), far: kOf(far), mid: kOf(mid) } };
  ART.worlds[theme] = w;
  return w;
}
