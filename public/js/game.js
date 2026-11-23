// 레이스 화면: 내 비행 계산, 서버 신호 반영, 그리기
import { RULES, deriveStats, PLAYER_COLORS } from '/shared/rules.js';
import {
  buildMap, terrainAt, circleHitsTerrain, circleHitsObstacle, obstacleY, boltState, MAP_BY_ID,
} from '/shared/mapgen.js';
import { CHARACTER_BY_ID, SKILLS } from '/shared/characters.js';
import { mulberry32 } from '/shared/rng.js';
import { steerFlyer, moveFlyer } from '/shared/flight.js';
import { ART, loadWorld } from './assets.js';
import { socket, serverNow } from './net.js';
import { sfx } from './sfx.js';

const W = RULES.view.w;
const H = RULES.view.h;
// 맵을 당겨 보는 배율과, 그때 화면에 보이는 맵 크기
const Z = RULES.cameraZoom || 1;
const VW = W / Z;
const VH = H / Z;
const WH = RULES.worldH; // 맵 세로 크기
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
// 글씨는 모두 갈무리 굵은 글꼴. 맵 위 글씨는 1.5배로 당겨 보이므로 13px, 화면 위 HUD 글씨는 18px
const FONT = '18px Galmuri11B';
const FONT_BIG = '24px Galmuri11B';
const FONT_SMALL = '13px Galmuri11B';
const FONT_HUD = '18px Galmuri11B';
const INK = '#181425';
const OUTLINE = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1]]; // 글씨 테두리
const DIGIT_OVERLAP = { S: 1, M: 2, L: 2 }; // 이웃 숫자의 외곽선을 이만큼 겹쳐 붙인다
const BUBBLE_W = 130; // 말풍선 글줄 최대 폭, 월드 픽셀
const BUBBLE_LINES = 3;

// 글자 단위로 줄을 나눈다. 줄 수를 넘기면 마지막 줄 끝을 …로 줄인다
function wrapText(ctx, text, maxW, maxLines) {
  const lines = [];
  let cur = '';
  for (const ch of text) {
    if (cur && ctx.measureText(cur + ch).width > maxW) {
      lines.push(cur);
      cur = ch === ' ' ? '' : ch;
    } else cur += ch;
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines.length = maxLines;
    let last = lines[maxLines - 1];
    while (last && ctx.measureText(last + '…').width > maxW) last = last.slice(0, -1);
    lines[maxLines - 1] = last + '…';
  }
  return lines;
}

function lowerBound(arr, x) {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (arr[m].x < x) lo = m + 1;
    else hi = m;
  }
  return lo;
}

export class Game {
  constructor(canvas, init, myId, hooks) {
    this.canvas = canvas;
    // 그림 해상도는 규칙의 화면 크기를 따른다. HTML에 적힌 크기와 어긋나면 화면 일부가 잘린다
    canvas.width = W;
    canvas.height = H;
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;
    this.init = init;
    this.myId = myId;
    this.hooks = hooks;
    this.map = buildMap(init.seed, init.mapId);
    this.theme = init.mapId;
    this.world = null;
    this.players = new Map();
    for (const p of init.players) this.players.set(p.id, { ...p, snaps: [], cur: null, slot: 0 });
    this.me = this.players.get(myId);
    this.ch = CHARACTER_BY_ID[this.me.charId];
    const st = deriveStats(this.ch.stats, 0);
    // 출발 통로 가운데 둘레에 네 명을 나란히. 통로는 위 30, 아래 46을 뺀 자리
    const startY = (30 + WH - 46) / 2 - 30 + this.me.color * 20;
    this.L = {
      x: 0, y: startY, vx: st.baseSpeed, vy: 0,
      hp: st.maxHp, maxHp: st.maxHp, lives: RULES.lives,
      ghost: false, dead: false, ghostDist: 0, feathers: 0,
      invUntil: 0, dashUntil: 0, obsCd: 0, hurtUntil: 0, shield: false,
      eff: { blind: 0, heavy: 0, shake: 0, slow: 0, glide: 0, small: 0 },
      shakeNext: 0, lastHit: null, niceIdx: 0, wasDashing: false, startY,
    };
    this.slot = 0;
    this.input = { up: false, boost: false };
    this.gemTaken = new Set();
    this.grabbed = new Set(); // 내가 먹은 기술 아이콘
    this.gemPending = new Map(); // id → 보낸 시각
    this.foodEaten = new Set();
    this.featherTaken = new Set();
    this.projectiles = new Map();
    this.puddles = new Map();
    this.fx = []; // { name, x, y, t0, dur, atlas, follow }
    this.popups = [];
    this.feed = [];
    this.squash = new Map();
    this.boltWarn = new Map();
    this.bubbles = new Map(); // id → { text, lines, t0, ms } 채팅 말풍선
    this.shakeUntil = 0;
    this.ended = false;
    this.alive = true;
    this.lastSend = 0;
    this.lastCount = 99;
    this.lastTs = performance.now();
    this.camX = -RULES.cameraLead;
    this.particles = [];
    this.crumbs = []; // 날갯짓 부스러기 { charId, x, y, vx, vy, s, t0, life }
    this.flapIdx = new Map(); // 플레이어 id → 지난번 날갯짓 프레임
    this.handlers = [];
    this.bindSocket();
    this.bindInput();
    loadWorld(this.theme).then((w) => {
      this.world = w;
      this.prepareWorld();
    });
    requestAnimationFrame((ts) => this.frame(ts));
  }

  destroy() {
    this.alive = false;
    for (const [ev, fn] of this.handlers) socket.off(ev, fn);
    for (const [el, ev, fn, o] of this.domHandlers) el.removeEventListener(ev, fn, o);
  }

  // ── 준비 ──
  prepareWorld() {
    const t = this.world.tiles;
    const ctx = this.ctx;
    // 지형 그림은 원래 크기로 두고 그릴 때 줄인다. 카메라가 당겨 보면 화면에서 1:1로 선명하게 그려진다
    const ek = t.k;
    this.edgeK = ek;
    const pattern = (c) => {
      const p = ctx.createPattern(c, 'repeat');
      p.setTransform(new DOMMatrix().scaleSelf(ek, ek));
      return p;
    };
    const cb = t.toCanvas('ceilBody', true);
    const fb = t.toCanvas('floorBody', true);
    this.ceilPattern = cb ? pattern(cb) : '#262b44';
    this.floorPattern = fb ? pattern(fb) : '#262b44';
    // 띠 타일은 4 맵 단위 폭 세로줄로 잘라 지형 경계선을 따라 붙인다
    this.ceilEdge = t.toCanvas('ceilEdge', true);
    this.floorEdge = t.toCanvas('floorEdge', true);
    this.ceilEdgeAy = (t.frame('ceilEdge')?.ay || 0) * ek;
    this.floorEdgeAy = (t.frame('floorEdge')?.ay || 0) * ek;
    this.decor = t.def.decor || { floor: [], ceil: [] };
    const rng = mulberry32(this.init.seed);
    for (let i = 0; i < 60; i++) {
      this.particles.push({ x: rng.range(0, W), y: rng.range(0, H), p: rng.range(0, 10), s: rng.range(0.6, 1.4) });
    }
  }

  on(ev, fn) {
    socket.on(ev, fn);
    this.handlers.push([ev, fn]);
  }

  bindSocket() {
    this.on('race:snap', (d) => {
      for (const s of d.p) {
        const p = this.players.get(s.id);
        if (!p) continue;
        p.cur = s;
        p.slot = s.slot;
        if (s.id === this.myId) {
          this.slot = s.slot;
          continue;
        }
        p.snaps.push({ ...s, t: d.t });
        if (p.snaps.length > 40) p.snaps.shift();
      }
    });
    this.on('race:gem', (d) => {
      this.gemTaken.add(d.id);
      this.gemPending.delete(d.id);
      const p = this.players.get(d.by);
      if (p) p.slot = d.slot;
      if (d.by === this.myId) {
        this.slot = d.slot;
        this.map.gems[d.id]?.red ? sfx.gemRed() : sfx.gem();
      }
    });
    this.on('race:grab', (d) => {
      const p = this.players.get(d.by);
      if (p) p.slot = d.slot;
      if (d.by === this.myId) this.slot = d.slot;
    });
    this.on('race:skill', (d) => {
      const p = this.players.get(d.by);
      if (p) p.slot = 0;
      if (d.by === this.myId) this.slot = 0;
      const pos = this.posOf(d.by);
      if (pos) this.popups.push({ text: SKILLS[d.skill].name, x: pos.x, y: pos.y - 40, t0: performance.now(), dur: 900, color: PLAYER_COLORS[p.color] });
      if (d.by === this.myId) sfx.skill();
    });
    this.on('race:self', (d) => this.applySelf(d.skill));
    this.on('race:proj', (d) => {
      this.projectiles.set(d.id, { ...d, start: performance.now() - Math.max(0, serverNow() - d.t) });
      if (d.by === this.myId) sfx.shoot();
    });
    this.on('race:projGone', (d) => {
      this.projectiles.delete(d.id);
      if (d.hit) this.addFx('hit', d.x, d.y, 280);
    });
    this.on('race:puddle', (d) => this.puddles.set(d.id, { ...d, until: performance.now() + d.lifeMs, t0: performance.now() }));
    this.on('race:hit', (d) => this.damage(d.dmg, d.by, d.kind));
    this.on('race:debuff', (d) => this.debuff(d.effect, d.ms, d.by));
    this.on('race:fx', (d) => this.remoteFx(d));
    this.on('race:drain', (d) => {
      const L = this.L;
      if (L.ghost || L.dead) return;
      L.hp -= d.amount;
      L.lastHit = { by: d.by, at: performance.now() };
      L.hurtUntil = performance.now() + 400;
      this.addFx('hit', L.x, L.y, 280);
      sfx.hit();
      if (L.hp <= 0) this.loseLife('drain');
    });
    this.on('race:revive', (d) => {
      const L = this.L;
      if (!L.ghost || L.dead) return;
      L.ghost = false;
      L.lives = 1;
      L.hp = Math.min(L.maxHp, d.hp);
      L.invUntil = performance.now() + 1500;
      this.addFx('revive', L.x, L.y, 500);
      sfx.revive();
    });
    this.on('race:event', (d) => this.onEvent(d));
    this.on('race:end', (d) => {
      if (this.ended) return;
      this.ended = true;
      this.input.up = false;
      this.input.boost = false;
      sfx.end();
      setTimeout(() => this.hooks.onEnd && this.hooks.onEnd(d), RULES.resultHoldMs);
    });
  }

  bindInput() {
    this.domHandlers = [];
    const add = (el, ev, fn, o) => {
      el.addEventListener(ev, fn, o);
      this.domHandlers.push([el, ev, fn, o]);
    };
    const typing = () => this.hooks.isTyping && this.hooks.isTyping();
    add(this.canvas, 'mousedown', (e) => {
      e.preventDefault();
      if (e.button === 0) this.input.up = true;
      if (e.button === 2) this.action();
    });
    add(window, 'mouseup', (e) => {
      if (e.button === 0) this.input.up = false;
    });
    add(this.canvas, 'contextmenu', (e) => e.preventDefault());
    add(this.canvas, 'touchstart', (e) => {
      e.preventDefault();
      if (e.touches.length >= 2) this.action();
      else this.input.up = true;
    }, { passive: false });
    add(this.canvas, 'touchend', (e) => {
      if (e.touches.length === 0) this.input.up = false;
    });
    add(window, 'keydown', (e) => {
      if (typing()) return;
      const k = e.code;
      if (k === 'ArrowUp' || k === 'KeyW') this.input.up = true;
      else if (k === 'Space') this.input.boost = true;
      else if (this.L.dead && ['ArrowLeft', 'KeyA', 'ArrowRight', 'KeyD'].includes(k)) {
        if (!e.repeat) this.cycleSpec(k === 'ArrowLeft' || k === 'KeyA' ? -1 : 1);
      } else if ((k === 'ArrowRight' || k === 'KeyD') && !e.repeat) this.action();
      else return;
      e.preventDefault();
    });
    add(window, 'keyup', (e) => {
      const k = e.code;
      if (k === 'ArrowUp' || k === 'KeyW') this.input.up = false;
      if (k === 'Space') this.input.boost = false;
    });
    add(window, 'blur', () => {
      this.input.up = false;
      this.input.boost = false;
    });
  }

  // 탈락한 뒤 볼 수 있는 사람. 순위 순서
  specList() {
    return this.standings().filter((s) => !s.dead && s.p.id !== this.myId && s.p._view);
  }

  // 탈락한 뒤 ←→로 볼 사람을 바꾼다
  cycleSpec(dir) {
    const list = this.specList();
    if (!list.length) return;
    const i = list.findIndex((s) => s.p.id === this.specId);
    const n = list.length;
    this.specId = list[(((i < 0 ? 0 : i + dir) % n) + n) % n].p.id;
  }

  // HUD에 보일 사람. 관전 중이면 보고 있는 사람, 아니면 나
  hudView() {
    const sp = this.spectating;
    if (sp && sp.cur) {
      const c = sp.cur;
      return { lives: c.lv, hp: c.hp, maxHp: c.mhp || 1, ghost: c.ghost, dead: c.dead, dist: c.dist || 0, feathers: 0, slot: sp.slot || 0, ch: CHARACTER_BY_ID[sp.charId] || this.ch };
    }
    const L = this.L;
    return { lives: L.lives, hp: L.hp, maxHp: L.maxHp, ghost: L.ghost, dead: L.dead, dist: Math.max(0, (L.x - L.ghostDist) / RULES.pxPerMeter), feathers: L.feathers, slot: this.slot, ch: this.ch };
  }

  // 오른쪽 버튼: 살아 있으면 기술, 유령이면 붙기
  action() {
    if (this.ended || this.raceT() < 0) return;
    const L = this.L;
    if (L.dead) return;
    if (L.ghost) socket.emit('race:latch');
    else if (this.slot > 0) socket.emit('race:skill');
  }

  raceT() {
    return (serverNow() - this.init.startAt) / 1000;
  }

  // ── 루프 ──
  frame(ts) {
    if (!this.alive) return;
    const dt = Math.min(0.05, Math.max(0, (ts - this.lastTs) / 1000));
    this.lastTs = ts;
    const t = this.raceT();
    if (t < 0) {
      const n = Math.ceil(-t);
      if (n < this.lastCount && n <= 3) {
        this.lastCount = n;
        sfx.count();
      }
      this.L.y = this.L.startY + Math.sin(ts / 300) * 3;
    } else {
      if (this.lastCount > 0) {
        this.lastCount = 0;
        sfx.go();
      }
      if (!this.ended) {
        const n = Math.max(1, Math.ceil(dt / (1 / 120)));
        for (let i = 0; i < n; i++) this.step(dt / n, t);
      }
    }
    this.sendState(ts);
    this.cleanup();
    if (this.world) this.render(t, dt);
    requestAnimationFrame((x) => this.frame(x));
  }

  step(dt, t) {
    const L = this.L;
    if (L.dead) return;
    const now = performance.now();
    const st = deriveStats(this.ch.stats, L.feathers);
    L.maxHp = st.maxHp;
    const dashing = now < L.dashUntil;
    const eff = (k) => now < L.eff[k];

    // 앞으로, 위아래. 서버 봇과 같은 계산
    steerFlyer(L, st, this.input, { dashing, slow: eff('slow'), heavy: eff('heavy'), glide: eff('glide') }, dt);
    if (eff('shake') && now > L.shakeNext) {
      L.vy += (Math.random() * 2 - 1) * 260;
      L.shakeNext = now + 160;
    }
    moveFlyer(L, dt);

    const r = eff('small') ? 6 : 12;
    if (L.wasDashing && !dashing && circleHitsTerrain(this.map, L.x, L.y, r)) this.recenter();
    L.wasDashing = dashing;

    // 지형
    if (!dashing && circleHitsTerrain(this.map, L.x, L.y, r)) {
      if (L.ghost) return this.finalOut();
      if (now < L.invUntil) this.pushInside(r);
      else if (L.shield) {
        L.shield = false;
        L.invUntil = now + 600;
        this.pushInside(r);
        this.addFx('hit', L.x, L.y, 280);
        sfx.shield();
      } else if (RULES.terrainCostsLife) {
        this.loseLife('terrain');
      } else {
        this.damage(RULES.obstacleDamage, null, 'terrain', true);
        this.pushInside(r);
      }
    }
    if (L.dead) return;

    // 장애물
    if (!L.ghost && !dashing) {
      const obs = this.map.obstacles;
      for (let i = Math.max(0, lowerBound(obs, L.x - 72)); i < obs.length && obs[i].x < L.x + 72; i++) {
        const o = obs[i];
        const res = circleHitsObstacle(this.map, o, t, L.x, L.y, r);
        if (!res) continue;
        if (res === 'bounce') {
          if (L.vy > -200) {
            L.vy = -330;
            this.squash.set(o.id, now + 260);
            sfx.bounce();
          }
          continue;
        }
        if (now < L.invUntil || now < L.obsCd) continue;
        if (L.shield) {
          L.shield = false;
          L.obsCd = now + RULES.hitInvulnMs;
          this.addFx('hit', L.x, L.y, 280);
          sfx.shield();
        } else if (RULES.obstacleCostsLife) {
          this.loseLife('obstacle');
        } else {
          L.obsCd = now + RULES.hitInvulnMs;
          this.damage(RULES.obstacleDamage, null, 'obstacle', true);
        }
        break;
      }
    }
    if (L.dead) return;

    // 보석·회복·깃털
    if (!L.ghost) {
      const reach = (r + 15) ** 2;
      const gems = this.map.gems;
      for (let i = lowerBound(gems, L.x - 30); i < gems.length && gems[i].x < L.x + 30; i++) {
        const g = gems[i];
        if (this.gemTaken.has(g.id) || this.gemPending.has(g.id)) continue;
        if ((g.x - L.x) ** 2 + (g.y - L.y) ** 2 < reach) {
          this.gemPending.set(g.id, now);
          socket.emit('race:pickup', g.id);
          this.addFx('pickup', g.x, g.y, 260, 'fx');
        }
      }
      for (const f of this.map.foods) {
        if (f.x > L.x + 30) break;
        if (this.foodEaten.has(f.id) || f.x < L.x - 30) continue;
        if ((f.x - L.x) ** 2 + (f.y - L.y) ** 2 < reach) {
          this.foodEaten.add(f.id);
          L.hp = Math.min(L.maxHp, L.hp + RULES.foodHeal);
          this.addFx('pickup', f.x, f.y, 260);
          sfx.food();
        }
      }
      for (const f of this.map.feathers) {
        if (f.x > L.x + 30) break;
        if (this.featherTaken.has(f.id) || f.x < L.x - 30) continue;
        if ((f.x - L.x) ** 2 + (f.y - L.y) ** 2 < reach) {
          this.featherTaken.add(f.id);
          L.feathers++;
          this.addFx('pickup', f.x, f.y, 260);
          sfx.feather();
        }
      }
      // 기술 아이콘: 먹으면 그 칸 기술을 하나 든다
      const sk = this.map.skills;
      for (let i = lowerBound(sk, L.x - 30); i < sk.length && sk[i].x < L.x + 30; i++) {
        const it = sk[i];
        if (this.grabbed.has(it.id)) continue;
        if ((it.x - L.x) ** 2 + (it.y - L.y) ** 2 < (r + 19) ** 2) {
          this.grabbed.add(it.id);
          socket.emit('race:grab', it.id);
          this.addFx('pickup', it.x, it.y, 260, 'fx');
          sfx.gem();
        }
      }
      // 시간이 지나며 HP 감소
      L.hp -= RULES.hpDrainPerSec * dt;
      if (L.hp <= 0) this.loseLife('hp');
    }

    // 좁은 목 통과
    const nice = this.map.nice;
    while (L.niceIdx < nice.length && nice[L.niceIdx].x < L.x) {
      if (!L.ghost && !L.dead && !dashing) {
        socket.emit('race:nice', L.niceIdx);
        this.popups.push({ img: 'nice', x: L.x, y: L.y - 45, t0: now, dur: 900 });
        sfx.nice();
      }
      L.niceIdx++;
    }
  }

  recenter() {
    const tb = terrainAt(this.map, this.L.x);
    this.L.y = (tb.top + tb.bottom) / 2;
    this.L.vy = 0;
  }

  pushInside(r) {
    const tb = terrainAt(this.map, this.L.x);
    this.L.y = clamp(this.L.y, tb.top + r + 2, tb.bottom - r - 2);
    this.L.vy = 0;
  }

  damage(dmg, by, kind, local = false) {
    const L = this.L;
    const now = performance.now();
    if (L.dead || L.ghost || now < L.invUntil || now < L.dashUntil) return;
    if (L.shield && !local) {
      L.shield = false;
      this.addFx('hit', L.x, L.y, 280);
      sfx.shield();
      return;
    }
    L.hp -= dmg;
    L.hurtUntil = now + 380;
    if (by) L.lastHit = { by, at: now };
    this.shakeUntil = now + 180;
    this.addFx('hit', L.x, L.y, 280);
    sfx.hit();
    if (L.hp <= 0) this.loseLife(kind || 'hit');
  }

  debuff(effect, ms, by) {
    const L = this.L;
    const now = performance.now();
    if (L.dead || L.ghost || now < L.invUntil || now < L.dashUntil) return;
    if (!(effect in L.eff)) return;
    L.eff[effect] = now + ms;
    L.lastHit = { by, at: now };
    sfx.hit();
  }

  applySelf(skill) {
    const L = this.L;
    const now = performance.now();
    if (L.dead || L.ghost) return;
    if (skill === 'dash') {
      L.dashUntil = now + SKILLS.dash.ms;
      sfx.dash();
    } else if (skill === 'shield') {
      L.shield = true;
      sfx.shield();
    } else if (skill === 'repair') {
      L.hp = Math.min(L.maxHp, L.hp + SKILLS.repair.heal);
      sfx.heal();
    } else if (skill === 'glide') {
      L.eff.glide = now + SKILLS.glide.ms;
      sfx.feather();
    } else if (skill === 'fold') {
      L.eff.small = now + SKILLS.fold.ms;
      sfx.feather();
    }
  }

  loseLife(cause) {
    const L = this.L;
    const now = performance.now();
    if (L.dead || L.ghost) return;
    const by = L.lastHit && now - L.lastHit.at < RULES.killCreditMs ? L.lastHit.by : null;
    L.lives -= 1;
    L.lastHit = null;
    socket.emit('race:lifeLost', { by, cause, lv: L.lives });
    this.addFx('hit', L.x, L.y, 320);
    this.shakeUntil = now + 300;
    for (const k of Object.keys(L.eff)) L.eff[k] = 0;
    if (L.lives <= 0) {
      L.ghost = true;
      L.hp = 0;
      L.shield = false;
      sfx.ghost();
    } else {
      L.hp = L.maxHp;
      L.invUntil = now + RULES.lifeLostInvulnMs;
      sfx.lifeLost();
    }
    this.recenter();
  }

  finalOut() {
    const L = this.L;
    if (L.dead) return;
    L.dead = true;
    L.ghost = false;
    socket.emit('race:final');
    this.addFx('hit', L.x, L.y, 320);
    sfx.lifeLost();
  }

  sendState(ts) {
    if (ts - this.lastSend < 1000 / RULES.sendHz) return;
    this.lastSend = ts;
    const L = this.L;
    const now = performance.now();
    socket.volatile.emit('race:state', {
      x: Math.round(L.x * 10) / 10,
      y: Math.round(L.y * 10) / 10,
      vx: Math.round(L.vx),
      vy: Math.round(L.vy),
      hp: Math.max(0, Math.ceil(L.hp)),
      mhp: L.maxHp,
      lv: L.lives,
      ghost: L.ghost,
      dead: L.dead,
      dist: Math.max(0, (L.x - L.ghostDist) / RULES.pxPerMeter),
      inv: now < L.invUntil || now < L.dashUntil,
      shield: L.shield,
      small: now < L.eff.small,
      a: this.animOf(),
      e: this.effFlags(),
    });
  }

  animOf() {
    const L = this.L;
    const now = performance.now();
    if (L.ghost) return 'ghost';
    if (now < L.hurtUntil) return 'hurt';
    if (now < L.dashUntil || (this.input.boost && L.vx > deriveStats(this.ch.stats, L.feathers).baseSpeed + 8)) return 'boost';
    return 'fly';
  }

  effFlags() {
    const L = this.L;
    const now = performance.now();
    let s = '';
    if (now < L.dashUntil) s += 'd';
    if (now < L.invUntil) s += 'i';
    for (const [k, c] of [['blind', 'b'], ['heavy', 'h'], ['shake', 's'], ['slow', 'w'], ['glide', 'g'], ['small', 'm']]) {
      if (now < L.eff[k]) s += c;
    }
    return s;
  }

  cleanup() {
    const now = performance.now();
    for (const [id, at] of this.gemPending) if (now - at > 1200) this.gemPending.delete(id);
    this.fx = this.fx.filter((f) => now - f.t0 < f.dur);
    this.crumbs = this.crumbs.filter((c) => now - c.t0 < c.life);
    this.popups = this.popups.filter((p) => now - p.t0 < p.dur);
    this.feed = this.feed.filter((f) => now - f.t0 < 5000);
    for (const [id, p] of this.puddles) if (now > p.until) this.puddles.delete(id);
    for (const [id, pr] of this.projectiles) if (now - pr.start > pr.lifeMs + 200) this.projectiles.delete(id);
  }

  addFx(name, x, y, dur, atlas = 'fx', follow = null) {
    this.fx.push({ name, x, y, t0: performance.now(), dur, atlas, follow });
  }

  remoteFx(d) {
    const now = performance.now();
    if (d.type === 'boltWarn') {
      this.boltWarn.set(d.target, now + d.ms);
      if (d.target === this.myId) sfx.warn();
    } else if (d.type === 'bolt') {
      this.boltWarn.delete(d.target);
      this.addFx('boltHit', 0, 0, 360, 'fx', d.target);
      this.addFx('boltSeg', 0, 0, 260, 'fx', d.target);
      sfx.bolt();
    } else if (d.type === 'shake') {
      for (const id of d.targets || []) this.addFx('whirl', 0, 0, 2500, 'fx', id);
    }
  }

  onEvent(d) {
    const name = (id) => this.players.get(id)?.name ?? '?';
    const color = (id) => PLAYER_COLORS[this.players.get(id)?.color ?? 0];
    const now = performance.now();
    let text = null;
    if (d.type === 'kill') {
      text = `${name(d.by)} ▶ ${name(d.target)} KILL`;
      const pos = this.posOf(d.by);
      if (pos) this.popups.push({ img: 'kill', x: pos.x, y: pos.y - 45, t0: now, dur: 1000 });
      if (d.by === this.myId) sfx.kill();
    } else if (d.type === 'crash') text = `${name(d.target)} 충돌, 남은 생명 ${Math.max(0, d.lv)}`;
    else if (d.type === 'revive') text = `${name(d.by)} 부활`;
    else if (d.type === 'out') text = `${name(d.target)} 탈락`;
    else if (d.type === 'left') text = `${name(d.target)} 나감`;
    else if (d.type === 'nice' && d.target !== this.myId) text = `${name(d.target)} NICE`;
    if (text) this.feed.push({ text, t0: now, color: color(d.by || d.target) });
  }

  // ── 위치 ──
  remoteState(p, renderT) {
    const s = p.snaps;
    if (!s.length) return null;
    if (renderT <= s[0].t) return s[0];
    for (let i = s.length - 1; i >= 0; i--) {
      if (s[i].t <= renderT) {
        const a = s[i];
        const b = s[i + 1];
        if (!b) {
          const k = Math.min(0.2, (renderT - a.t) / 1000);
          return { ...a, x: a.x + a.vx * k, y: a.y };
        }
        const k = (renderT - a.t) / (b.t - a.t || 1);
        return { ...b, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
      }
    }
    return s[s.length - 1];
  }

  posOf(id) {
    if (id === this.myId) return { x: this.L.x, y: this.L.y };
    const p = this.players.get(id);
    return p ? p._view || null : null;
  }

  standings() {
    const list = [];
    for (const p of this.players.values()) {
      if (p.id === this.myId) {
        const L = this.L;
        list.push({ p, dist: Math.max(0, (L.x - L.ghostDist) / RULES.pxPerMeter), ghost: L.ghost, dead: L.dead, x: L.x });
      } else if (p.cur) {
        list.push({ p, dist: p.cur.dist, ghost: p.cur.ghost, dead: p.cur.dead, x: p._view ? p._view.x : p.cur.x });
      } else list.push({ p, dist: 0, ghost: false, dead: false, x: 0 });
    }
    return list.sort((a, b) => b.dist - a.dist);
  }

  // ── 그리기 ──
  render(t, dt = 0.016) {
    const ctx = this.ctx;
    const now = performance.now();
    const L = this.L;
    const renderT = serverNow() - RULES.interpDelayMs;
    for (const p of this.players.values()) if (p.id !== this.myId) p._view = this.remoteState(p, renderT);

    // 카메라: 탈락하면 고른 사람을, 고른 적 없거나 그 사람도 탈락했으면 1위를 따라간다
    let focus = L;
    this.spectating = null;
    if (L.dead) {
      const list = this.specList();
      const pick = list.find((s) => s.p.id === this.specId) || list[0];
      if (pick) {
        this.specId = pick.p.id;
        focus = pick.p._view;
        this.spectating = pick.p;
      }
    }
    // 가로는 캐릭터를 화면 왼쪽 cameraLead 자리에 두고, 세로는 캐릭터를 부드럽게 따라가되 맵 위아래 끝에서 멈춘다
    const camX = Math.round((t < 0 ? 0 : focus.x) - RULES.cameraLead / Z);
    const wantY = clamp(focus.y - VH / 2, 0, Math.max(0, WH - VH));
    this.camY = this.camY == null || t < 0 ? wantY : this.camY + (wantY - this.camY) * Math.min(1, dt * 5);
    let shakeX = 0;
    let shakeY = 0;
    if (now < this.shakeUntil) {
      shakeX = Math.round(Math.random() * 6 - 3);
      shakeY = Math.round(Math.random() * 6 - 3);
    }
    const prevCam = this.camX;
    this.camX = camX;
    const tw = Math.max(0, t);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    this.drawBackground(camX * Z);

    ctx.setTransform(Z, 0, 0, Z, Math.round(-camX * Z) + shakeX, Math.round(-this.camY * Z) + shakeY);
    this.drawTerrain(camX);
    this.drawObstacles(camX, tw, now);
    this.drawItems(camX, tw);
    this.drawPuddles(now);
    this.drawProjectiles(now);
    this.drawCrumbs(now);
    this.drawPlayers(tw, now);
    this.drawFx(now);
    this.drawPopups(now);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.drawParticles((camX - prevCam) * Z, now);
    if (!L.dead && !L.ghost && now < L.eff.blind) this.drawFog(now);
    this.drawHud(t, now);
  }

  drawBackground(camX) {
    const ctx = this.ctx;
    const w = this.world;
    if (w.sky) ctx.drawImage(w.sky, 0, 0, Math.round(w.sky.width * w.k.sky), Math.round(w.sky.height * w.k.sky));
    for (const [img, f, k] of [[w.far, 0.15, w.k.far], [w.mid, 0.4, w.k.mid]]) {
      if (!img) continue;
      const iw = Math.round(img.width * k);
      const ih = Math.round(img.height * k);
      const off = -(((Math.round(camX * f) % iw) + iw) % iw);
      ctx.drawImage(img, off, 0, iw, ih);
      ctx.drawImage(img, off + iw, 0, iw, ih);
    }
  }

  drawTerrain(camX) {
    const ctx = this.ctx;
    const tiles = this.world.tiles;
    const x0 = Math.floor(camX / 4) * 4 - 4;
    const x1 = camX + VW + 8;
    const cols = [];
    for (let x = x0; x < x1; x += 4) {
      const tb = terrainAt(this.map, x + 2);
      cols.push([x, Math.round(tb.top), Math.round(tb.bottom)]);
    }
    // 속 무늬는 띠가 꽉 찬 깊이부터 깐다. 경계선 바로 밑부터 깔면 띠의 울퉁불퉁한 틈으로 비쳐 보인다
    const gap = tiles.def.bodyGap || { floor: 0, ceil: 0 };
    const gf = Math.round(gap.floor * this.edgeK);
    const gc = Math.round(gap.ceil * this.edgeK);
    ctx.fillStyle = this.ceilPattern;
    for (const [x, t] of cols) ctx.fillRect(x, -8, 4, t - gc + 8);
    ctx.fillStyle = this.floorPattern;
    for (const [x, , b] of cols) ctx.fillRect(x, b + gf, 4, WH - b - gf + 8);
    const ce = this.ceilEdge;
    const fe = this.floorEdge;
    const ek = this.edgeK;
    const sw = 4 / ek;
    const src = (img, x) => Math.min(img.width - sw, (((x / ek) % img.width) + img.width) % img.width);
    // 띠에서 떼어 낸 키 큰 장식은 조각내지 않고 그 가운데 땅 높이에 통째로 세운다.
    // 장식 밑의 띠도 같은 높이로 맞춰, 기울어진 땅에서 장식과 띠에 남은 밑동이 어긋나지 않게 한다
    const RAMP = 16; // 장식 양옆 이 폭에서 띠가 다시 땅 높이로 돌아간다, 맵 단위
    const pins = { floor: [], ceil: [] };
    for (const [list, img, kind] of [[this.decor.floor, fe, 'floor'], [this.decor.ceil, ce, 'ceil']]) {
      if (!list || !list.length || !img) continue;
      const tw = img.width * ek;
      for (let k = Math.floor((x0 - 200) / tw); k * tw < x1 + 200; k++) {
        for (const d of list) {
          const x = k * tw + d.x * ek;
          const hw = ((tiles.frame(d.name)?.sw || 0) * ek) / 2;
          if (x + hw + RAMP < x0 || x - hw - RAMP > x1) continue;
          const tb = terrainAt(this.map, x);
          pins[kind].push({ d, x, hw, h: kind === 'floor' ? tb.bottom : tb.top });
        }
      }
    }
    const pinned = (list, x, h) => {
      let ws = 0;
      let hs = 0;
      let wmax = 0;
      for (const p of list) {
        const out = Math.abs(x - p.x) - p.hw;
        if (out >= RAMP) continue;
        let w = out <= 0 ? 1 : 1 - out / RAMP;
        w = w * w * (3 - 2 * w);
        ws += w;
        hs += w * p.h;
        wmax = Math.max(wmax, w);
      }
      return ws ? Math.round(h + (hs / ws - h) * wmax) : h;
    };
    for (const [x, t, b] of cols) {
      if (ce) ctx.drawImage(ce, src(ce, x), 0, sw, ce.height, x, pinned(pins.ceil, x + 2, t) - this.ceilEdgeAy, 4, ce.height * ek);
      if (fe) ctx.drawImage(fe, src(fe, x), 0, sw, fe.height, x, pinned(pins.floor, x + 2, b) - this.floorEdgeAy, 4, fe.height * ek);
    }
    for (const p of pins.floor) tiles.draw(ctx, p.d.name, Math.round(p.x), Math.round(p.h - p.d.dy * ek));
    for (const p of pins.ceil) tiles.draw(ctx, p.d.name, Math.round(p.x), Math.round(p.h + p.d.dy * ek));
  }

  drawObstacles(camX, t, now) {
    const ctx = this.ctx;
    const atlas = this.world.obstacles;
    const obs = this.map.obstacles;
    for (let i = lowerBound(obs, camX - 60); i < obs.length && obs[i].x < camX + VW + 60; i++) {
      const o = obs[i];
      if (o.type === 'bolt') {
        const tb = terrainAt(this.map, o.x);
        const top = Math.round(tb.top);
        const bot = Math.round(tb.bottom);
        const state = boltState(o, t);
        if (state !== 'idle') {
          const name = state === 'active' ? 'beam' : 'beamWarn';
          const bs = atlas.size(name);
          ctx.save();
          ctx.beginPath();
          ctx.rect(o.x - bs.w / 2, top, bs.w, bot - top);
          ctx.clip();
          // 줄기 그림 한 장을 위아래 땅 사이 가운데에 놓는다. 가장 먼 간격도 덮는 길이라 양 끝은 기둥 머리와 땅에 가려진다
          atlas.draw(ctx, name, o.x, (top + bot) / 2, { t });
          ctx.restore();
        }
        atlas.draw(ctx, 'pylonTop', o.x, top);
        atlas.draw(ctx, 'pylonBottom', o.x, bot);
      } else if (o.type === 'mushroom') {
        atlas.drawBottom(ctx, 'mushroom', o.x, o.floorY, { index: now < (this.squash.get(o.id) || 0) ? 1 : 0 });
      } else {
        atlas.draw(ctx, o.variant || o.type, o.x, obstacleY(o, t), { t: t + o.id * 0.37 });
      }
    }
  }

  drawItems(camX, t) {
    const ctx = this.ctx;
    const items = ART.items;
    const gems = this.map.gems;
    for (let i = lowerBound(gems, camX - 16); i < gems.length && gems[i].x < camX + VW + 16; i++) {
      const g = gems[i];
      if (this.gemTaken.has(g.id) || this.gemPending.has(g.id)) continue;
      items.draw(ctx, g.red ? 'gemRed' : 'gemBlue', g.x, g.y + Math.round(Math.sin(t * 3 + g.id) * 1.5), { t: t + g.id * 0.11 });
    }
    for (const f of this.map.foods) {
      if (f.x < camX - 16 || f.x > camX + VW + 16 || this.foodEaten.has(f.id)) continue;
      items.draw(ctx, 'food', f.x, f.y, { t });
    }
    // 기술 아이콘: 빛 방울 안에 내 캐릭터의 그 칸 기술
    const sk = this.map.skills;
    for (let i = lowerBound(sk, camX - 20); i < sk.length && sk[i].x < camX + VW + 20; i++) {
      const it = sk[i];
      if (this.grabbed.has(it.id)) continue;
      const y = it.y + Math.round(Math.sin(t * 2.4 + it.id) * 2);
      ctx.beginPath();
      ctx.arc(it.x, y, 18, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.stroke();
      ART.hud.draw(ctx, 'icon_' + this.ch.skills[it.slot - 1], it.x, y, { scale: 0.75 });
    }
    for (const f of this.map.feathers) {
      if (f.x < camX - 16 || f.x > camX + VW + 16 || this.featherTaken.has(f.id)) continue;
      items.draw(ctx, 'feather', f.x, f.y + Math.round(Math.sin(t * 2 + f.id) * 2), { t });
    }
  }

  drawPuddles(now) {
    for (const p of this.puddles.values()) {
      const left = p.until - now;
      ART.fx.draw(this.ctx, 'oil', p.x, p.y, { t: (now - p.t0) / 1000, alpha: left < 1000 ? left / 1000 : 1 });
    }
  }

  drawProjectiles(now) {
    for (const pr of this.projectiles.values()) {
      const s = (now - pr.start) / 1000;
      const x = pr.x + pr.vx * s;
      const y = pr.y + pr.vy * s + 0.5 * pr.g * s * s;
      const tb = terrainAt(this.map, x);
      if (y < tb.top || y > tb.bottom) continue;
      ART.fx.draw(this.ctx, pr.kind, x, y, { t: s });
    }
  }

  drawPlayers(t, now) {
    const list = [];
    for (const p of this.players.values()) {
      if (p.id === this.myId) continue;
      const v = p._view;
      if (!v || v.dead) continue;
      if (v.x < this.camX - 40 || v.x > this.camX + VW + 40) continue;
      list.push({ p, x: v.x, y: v.y, anim: v.a || 'fly', e: v.e || '', ghost: v.ghost, shield: v.shield, small: v.small });
    }
    const L = this.L;
    if (!L.dead) {
      list.push({
        p: this.me, x: L.x, y: L.y, anim: this.animOf(), e: this.effFlags(),
        ghost: L.ghost, shield: L.shield, small: now < L.eff.small, self: true,
      });
    }
    for (const d of list) this.drawFlyer(d, t, now);
  }

  drawFlyer(d, t, now) {
    const ctx = this.ctx;
    const atlas = ART.chars[d.p.charId];
    const x = Math.round(d.x);
    const y = Math.round(d.y);
    const blink = d.e.includes('i') && Math.floor(now / 90) % 2 === 0;
    if (d.e.includes('d')) ART.fx.draw(ctx, 'dash', x - 40, y, { t, scale: 1.2 });
    const alpha = d.ghost ? 0.78 : blink ? 0.35 : d.self ? 1 : 0.92;
    const anim = atlas.has(d.anim) ? d.anim : 'fly';
    const at = t + d.p.color * 0.21;
    const sc = d.small ? 0.5 : 1;
    // 가속 바람줄은 몸 뒤에서 뻗어 나가도록 캐릭터보다 먼저 그린다
    if (anim === 'boost' && !d.ghost && ART.particles?.has('streak')) {
      ART.particles.draw(ctx, 'streak', x - 17 * sc, y - 18 * sc, { t, scale: sc * 1.2, alpha });
    }
    this.emitCrumb(d, atlas, anim, at, now, sc);
    atlas.draw(ctx, anim, x, y, { t: at, alpha, scale: sc });
    if (d.shield) ART.fx.draw(ctx, 'shield', x, y, { t, alpha: 0.85, scale: 1.2 });

    // 머리 위: 이름, 상태, 번개 조준
    let iy = y - 42;
    if (this.boltWarn.has(d.p.id) && now < this.boltWarn.get(d.p.id)) ART.fx.draw(ctx, 'warn', x, y, { t });
    const icons = [];
    for (const [c, n] of [['b', 'debuff_blind'], ['h', 'debuff_heavy'], ['s', 'debuff_shake'], ['w', 'debuff_slow'], ['g', 'buff_glide'], ['m', 'buff_shrink']]) {
      if (d.e.includes(c)) icons.push(n);
    }
    if (icons.length) {
      let ix = x - (icons.length * 20) / 2 + 9;
      for (const n of icons) {
        ART.ui.draw(ctx, n, ix, iy);
        ix += 20;
      }
      iy -= 18;
    }
    if (!d.self) {
      ctx.font = FONT_SMALL;
      this.text(d.p.name, x, iy - 12, PLAYER_COLORS[d.p.color], 'center');
    } else if (this.players.size > 1) {
      ART.ui.draw(ctx, 'miniMarker' + d.p.color, x, iy - 2);
    }
    this.drawBubble(d.p.id, x, iy - 17, now);
  }

  // 채팅을 친 사람 머리 위에 잠깐 말풍선을 띄운다. 긴 말일수록 조금 더 오래 남는다
  say(id, text) {
    this.bubbles.set(id, { text, lines: null, t0: performance.now(), ms: Math.min(7000, 3500 + text.length * 60) });
  }

  // 꼬리 끝이 (x, tipY)에 오는 흰 말풍선
  drawBubble(id, x, tipY, now) {
    const b = this.bubbles.get(id);
    if (!b) return;
    const age = now - b.t0;
    if (age > b.ms) {
      this.bubbles.delete(id);
      return;
    }
    const ctx = this.ctx;
    ctx.font = FONT_SMALL;
    if (!b.lines) b.lines = wrapText(ctx, b.text, BUBBLE_W, BUBBLE_LINES);
    const lh = 15;
    const w = Math.ceil(Math.max(...b.lines.map((l) => ctx.measureText(l).width))) + 10;
    const h = b.lines.length * lh + 6;
    const bx = Math.round(x - w / 2);
    const by = Math.round(tipY - 3 - h);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, age / 120, (b.ms - age) / 300));
    // 모서리를 한 칸 깎은 몸통
    ctx.fillStyle = INK;
    ctx.fillRect(bx + 1, by, w - 2, h);
    ctx.fillRect(bx, by + 1, w, h - 2);
    ctx.fillStyle = '#fff';
    ctx.fillRect(bx + 2, by + 1, w - 4, h - 2);
    ctx.fillRect(bx + 1, by + 2, w - 2, h - 4);
    // 아래로 뾰족한 꼬리
    for (let i = 0; i < 4; i++) {
      const half = 3 - i;
      const yy = by + h - 1 + i;
      ctx.fillStyle = INK;
      ctx.fillRect(x - half - 1, yy, half * 2 + 3, 1);
      if (half > 0) {
        ctx.fillStyle = '#fff';
        ctx.fillRect(x - half, yy, half * 2 + 1, 1);
      }
    }
    ctx.fillStyle = INK;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    b.lines.forEach((l, i) => ctx.fillText(l, bx + 5, by + 3 + i * lh));
    ctx.restore();
  }

  // 날개를 내려치는 프레임으로 넘어갈 때마다 그 캐릭터의 부스러기를 하나 떨어뜨린다
  emitCrumb(d, atlas, anim, at, now, sc) {
    const trail = ART.trail[d.p.charId];
    const emit = trail?.def.emit;
    if (!emit || !trail.has('trail') || d.ghost || (anim !== 'fly' && anim !== 'boost')) return;
    const a = atlas.anims[anim];
    const n = a.frames.length;
    const k = ((Math.floor(at * (a.fps || 1)) % n) + n) % n;
    const prev = this.flapIdx.get(d.p.id);
    this.flapIdx.set(d.p.id, k);
    if (k !== emit.flyFrame || prev === emit.flyFrame) return;
    this.crumbs.push({
      charId: d.p.charId,
      x: d.x + emit.at[0] * sc + (Math.random() * 6 - 3),
      y: d.y + emit.at[1] * sc + (Math.random() * 4 - 2),
      vx: -15 - Math.random() * 25,
      vy: 8 + Math.random() * 14,
      s: sc,
      t0: now,
      life: emit.lifeMs || 900,
    });
  }

  // 부스러기는 떨어진 자리에 남아 뒤로 흘러가며 가라앉고, 4프레임에 걸쳐 흩어진다
  drawCrumbs(now) {
    for (const c of this.crumbs) {
      const trail = ART.trail[c.charId];
      const f = (now - c.t0) / c.life;
      if (f >= 1 || !trail) continue;
      const s = (now - c.t0) / 1000;
      const n = trail.frameCount('trail');
      trail.draw(this.ctx, 'trail', c.x + c.vx * s, c.y + c.vy * s + 9 * s * s, {
        index: Math.min(n - 1, Math.floor(f * n)),
        scale: c.s,
        alpha: f > 0.75 ? (1 - f) / 0.25 : 1,
      });
    }
  }

  drawFx(now) {
    for (const f of this.fx) {
      const atlas = f.atlas === 'items' ? ART.items : ART.fx;
      let x = f.x;
      let y = f.y;
      if (f.follow) {
        const pos = this.posOf(f.follow);
        if (!pos) continue;
        x = pos.x;
        y = pos.y;
      }
      const s = (now - f.t0) / 1000;
      if (f.name === 'boltSeg') {
        const top = Math.round(terrainAt(this.map, x).top);
        const bs = atlas.size('boltSeg');
        for (let yy = top; yy < y; yy += bs.h || 32) atlas.drawAt(this.ctx, 'boltSeg', x - bs.w / 2, yy, { t: s });
        continue;
      }
      if (f.name === 'whirl') {
        atlas.draw(this.ctx, 'whirl', x, y - 27, { t: s });
        continue;
      }
      const n = atlas.frameCount(f.name) || 1;
      atlas.draw(this.ctx, f.name, x, y, { index: Math.min(n - 1, Math.floor((s * 1000 * n) / f.dur)) });
    }
  }

  drawPopups(now) {
    const ctx = this.ctx;
    for (const p of this.popups) {
      const k = (now - p.t0) / p.dur;
      const y = p.y - k * 21;
      const alpha = k > 0.7 ? (1 - k) / 0.3 : 1;
      if (p.img) ART.fx.draw(ctx, p.img, p.x, y, { alpha });
      else {
        ctx.globalAlpha = alpha;
        ctx.font = FONT_SMALL;
        this.text(p.text, Math.round(p.x), Math.round(y), p.color || '#fff', 'center');
        ctx.globalAlpha = 1;
      }
    }
  }

  drawParticles(dcam, now) {
    const tiles = this.world.tiles;
    if (!tiles.has('particle')) return;
    const theme = this.theme;
    for (const p of this.particles) {
      if (theme === 'storm') {
        p.x -= 3.3 * p.s + dcam;
        p.y += 10.5 * p.s;
      } else if (theme === 'mushroom') {
        p.x += Math.sin(now / 900 + p.p) * 0.45 - dcam * 0.6;
        p.y += Math.cos(now / 1100 + p.p) * 0.38;
      } else {
        p.x -= 0.75 * p.s + dcam * 0.8;
        p.y += 0.5 * p.s + Math.sin(now / 700 + p.p) * 0.3;
      }
      if (p.x < -10) p.x += W + 20;
      if (p.x > W + 10) p.x -= W + 20;
      if (p.y > H + 10) p.y -= H + 20;
      if (p.y < -10) p.y += H + 20;
      const alpha = theme === 'mushroom' ? 0.45 + 0.55 * Math.abs(Math.sin(now / 600 + p.p)) : 0.85;
      tiles.draw(this.ctx, 'particle', p.x, p.y, { t: now / 1000 + p.p, alpha });
    }
  }

  drawFog(now) {
    const fx = ART.fx;
    const s = now / 1000;
    for (let i = 0; i < 15; i++) {
      const x = 315 + (i % 5) * 144 + Math.sin(s * 0.9 + i) * 15;
      const y = 30 + Math.floor(i / 5) * 180 + ((i * 37) % 90) + Math.cos(s * 0.7 + i) * 12;
      fx.draw(this.ctx, 'fog', x, y, { alpha: 0.95 });
    }
  }

  text(str, x, y, color = '#fff', align = 'left') {
    const ctx = this.ctx;
    ctx.textAlign = align;
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#181425';
    for (const [dx, dy] of OUTLINE) ctx.fillText(str, x + dx, y + dy);
    ctx.fillStyle = color;
    ctx.fillText(str, x, y);
  }

  // 채움 막대를 ratio만큼 그린다. 양 끝 둥근 부분은 그대로 두고 가운데만 늘이고 줄여 짧아져도 끝이 둥글다
  drawFill(name, x, y, ratio) {
    const hud = ART.hud;
    const f = hud.frame(name);
    if (!f) return;
    const k = hud.k;
    const cap = Math.floor(f.sh / 2);
    const full = f.sw;
    const w = Math.max(2, Math.round(full * ratio));
    const ctx = this.ctx;
    if (w <= cap * 2) {
      const half = Math.floor(w / 2);
      ctx.drawImage(hud.img, f.sx, f.sy, half, f.sh, x, y, half * k, f.sh * k);
      ctx.drawImage(hud.img, f.sx + full - (w - half), f.sy, w - half, f.sh, x + half * k, y, (w - half) * k, f.sh * k);
      return;
    }
    ctx.drawImage(hud.img, f.sx, f.sy, cap, f.sh, x, y, cap * k, f.sh * k);
    ctx.drawImage(hud.img, f.sx + cap, f.sy, full - cap * 2, f.sh, x + cap * k, y, (w - cap * 2) * k, f.sh * k);
    ctx.drawImage(hud.img, f.sx + full - cap, f.sy, cap, f.sh, x + (w - cap) * k, y, cap * k, f.sh * k);
  }

  // 시안에서 오려 낸 숫자 글자로 쓴다. size는 S 순위표, M 타이머, L 거리
  numWidth(str, size) {
    const hud = ART.hud;
    let w = 0;
    const o = DIGIT_OVERLAP[size] || 0;
    for (const ch of str) w += hud.size(`digit${size}_${ch === ':' ? 'colon' : ch}`).w - o;
    return w + o;
  }

  drawNum(str, x, y, size, align = 'left') {
    const hud = ART.hud;
    const ctx = this.ctx;
    let cx = align === 'left' ? x : align === 'right' ? x - this.numWidth(str, size) : x - this.numWidth(str, size) / 2;
    const base = hud.size(`digit${size}_0`).h;
    for (const ch of str) {
      const name = `digit${size}_${ch === ':' ? 'colon' : ch}`;
      const g = hud.size(name);
      if (!g.w) continue;
      // 숫자 높이에 맞춰 아래를 맞추고, m과 쌍점은 세로 가운데에 둔다
      const gy = ch === ':' ? y + Math.round((base - g.h) / 2) : y + base - g.h;
      hud.drawAt(ctx, name, Math.round(cx), Math.round(gy));
      cx += g.w - (DIGIT_OVERLAP[size] || 0);
    }
  }

  drawHud(t, now) {
    const ctx = this.ctx;
    const ui = ART.ui;
    const hud = ART.hud;
    const L = this.L;
    const V = this.hudView();
    const M = 12;

    // 생명·HP·거리. 관전 중이면 보고 있는 사람 것
    const hs = hud.size('heartFull');
    for (let i = 0; i < RULES.lives; i++) hud.drawAt(ctx, i < V.lives && !V.dead ? 'heartFull' : 'heartEmpty', M + i * (hs.w + 2), M);
    const hx = M + RULES.lives * (hs.w + 2) + 2;
    const hf = hud.size('hpFrame');
    const hy = M + Math.round((hs.h - hf.h) / 2);
    hud.drawAt(ctx, 'hpFrame', hx, hy);
    const [fx, fy] = hud.def.hpFillRect;
    const ratio = clamp(V.hp / V.maxHp, 0, 1);
    if (ratio > 0) {
      // 30% 이하면 붉은 채움과 번갈아 깜빡인다
      const low = ratio <= 0.3 && Math.floor(now / 250) % 2 === 0;
      this.drawFill(low ? 'hpFillLow' : 'hpFill', hx + fx, hy + fy, ratio);
    }
    if (V.ghost) ui.drawAt(ctx, 'ghostIcon', hx + hf.w + 4, M);
    if (V.dead) ui.drawAt(ctx, 'skull', hx + hf.w + 4, M);
    const dy0 = M + hs.h + 4;
    this.drawNum(`${Math.floor(V.dist)}m`, M, dy0, 'L');
    if (V.feathers > 0) {
      const fs = ui.size('featherIcon');
      const fyy = dy0 + hud.size('digitL_0').h + 6;
      ui.drawAt(ctx, 'featherIcon', M, fyy);
      ctx.font = FONT_HUD;
      this.text(`×${Math.min(V.feathers, RULES.featherMax)}`, M + fs.w + 4, fyy + Math.round((fs.h - 18) / 2), '#fee761');
    }

    // 남은 시간: 타이머 판의 초시계 오른쪽 남색 자리 가운데
    const left = Math.max(0, Math.min(RULES.raceMs, this.init.endAt - serverNow()));
    const sec = Math.ceil(left / 1000);
    const tp = hud.size('timerPlate');
    const tx = Math.round(W / 2 - tp.w / 2);
    hud.drawAt(ctx, 'timerPlate', tx, 6);
    const tStr = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
    const th = hud.size('digitM_0').h;
    if (sec <= 10 && t > 0 && Math.floor(now / 300) % 2 === 0) ctx.globalAlpha = 0.55;
    this.drawNum(tStr, tx + Math.round(tp.w * (hud.def.timerTextX || 0.62)), 6 + Math.round(tp.h * (hud.def.timerTextY || 0.5) - th / 2), 'M', 'center');
    ctx.globalAlpha = 1;

    // 순위표: 구슬에 순위, 판 안에 거리, 판 왼쪽 바깥에 캐릭터와 이름
    const rank = this.standings();
    const [bx, by] = hud.def.rankBadge || [19, 19];
    rank.forEach((s, i) => {
      const row = `rankRow${Math.min(4, i + 1)}`;
      const rs = hud.size(row);
      const x = W - rs.w - M;
      const y = M + i * (rs.h + 2);
      const self = s.p.id === this.myId;
      hud.drawAt(ctx, row, x, y);
      const ds = hud.size('digitS_0');
      this.drawNum(`${i + 1}`, x + bx, y + by - Math.round(ds.h / 2), 'S', 'center');
      this.drawNum(`${Math.floor(s.dist)}`, x + rs.w - 9, y + Math.round((rs.h - ds.h) / 2), 'S', 'right');
      const ca = ART.chars[s.p.charId];
      const cf = ca && ca.frame('fly');
      const cx = x - 18;
      if (cf) ca.draw(ctx, s.ghost && ca.has('ghost') ? 'ghost' : 'fly', cx, y + rs.h / 2 + 4, { index: 0, scale: (rs.h + 2) / (cf.sh * ca.k) });
      if (s.dead) ui.drawAt(ctx, 'skull', cx - Math.round(ui.size('skull').w / 2), y + Math.round((rs.h - ui.size('skull').h) / 2));
      let nx = x - 38;
      if (this.init.mode === 'team' && s.p.team) {
        const tw = ui.size('teamA').w;
        ui.drawAt(ctx, s.p.team === 'A' ? 'teamA' : 'teamB', nx - tw, y + Math.round((rs.h - ui.size('teamA').h) / 2));
        nx -= tw + 3;
      }
      ctx.font = FONT_HUD;
      this.text(s.p.name, nx, y + Math.round(rs.h / 2) - 10, self ? '#fee761' : PLAYER_COLORS[s.p.color], 'right');
    });

    // 기술칸: 커서가 있는 칸은 금색 칸으로
    const ss = hud.size('slotFrame');
    const gap = 2;
    const sx = M;
    const sy = H - ss.h - M + 4;
    V.ch.skills.forEach((sk, i) => {
      const x = sx + i * (ss.w + gap);
      const on = V.slot === i + 1 && !V.ghost && !V.dead;
      ctx.fillStyle = 'rgba(24, 20, 37, 0.55)';
      ctx.fillRect(x + 6, sy + 6, ss.w - 12, ss.h - 12);
      if (on) {
        const as = hud.size('slotActive');
        hud.drawAt(ctx, 'slotActive', x - Math.round((as.w - ss.w) / 2), sy - Math.round((as.h - ss.h) / 2));
      } else hud.drawAt(ctx, 'slotFrame', x, sy);
      const is = hud.size('icon_' + sk);
      hud.drawAt(ctx, 'icon_' + sk, x + Math.round((ss.w - is.w) / 2), sy + Math.round((ss.h - is.h) / 2));
    });
    if (V.slot > 0 && !V.ghost && !V.dead) {
      ctx.font = FONT_HUD;
      this.text(SKILLS[V.ch.skills[V.slot - 1]].name, sx + 4, sy - 24, '#fee761');
    }

    // 진행 막대: 경기 시간이 흐른 만큼 노랗게 차고, 그 끝에 지금 보는 사람의 얼굴, 오른쪽 끝에 골 깃발
    const bs = hud.size('miniBar');
    const slotsEnd = sx + 5 * (ss.w + gap);
    const mx = Math.max(slotsEnd + 16, Math.round(W / 2 - bs.w / 2));
    const my = H - bs.h - M - 4;
    hud.drawAt(ctx, 'miniBar', mx, my);
    const [px, py, pw, ph] = hud.def.miniFillRect || [10, 7, bs.w - 20, bs.h - 14];
    const prog = clamp(Math.max(0, t) / (RULES.raceMs / 1000), 0, 1);
    if (prog > 0) this.drawFill('miniFill', mx + px, my + py, prog);
    if (hud.has('goalFlag')) hud.draw(ctx, 'goalFlag', mx + bs.w - 10, my + Math.round(bs.h / 2) + 6, { t: now / 1000 });
    const face = ART.portraits[(this.spectating || this.me).charId];
    if (face) {
      const fs = 34;
      ctx.drawImage(face, Math.round(mx + px + pw * prog - fs / 2), Math.round(my + bs.h / 2 - fs / 2), fs, fs);
    }

    // 소식
    ctx.font = FONT_HUD;
    const recent = this.feed.slice(-4);
    recent.forEach((f, i) => {
      const age = now - f.t0;
      ctx.globalAlpha = age > 4000 ? (5000 - age) / 1000 : 1;
      this.text(f.text, W / 2, 6 + tp.h + 8 + i * 23, f.color, 'center');
      ctx.globalAlpha = 1;
    });

    // 안내
    ctx.font = FONT;
    const hintY = sy - 52;
    if (L.ghost && !L.dead) this.text('유령 · 우클릭이나 →로 가까운 상대에게 붙어 부활', W / 2, hintY, '#2ce8f5', 'center');
    if (this.spectating) {
      const others = this.specList().length > 1 ? ' · ←→ 다른 사람' : '';
      this.text(`관전 중 · ${this.spectating.name}${others} · Enter 채팅`, W / 2, hintY, '#c0cbdc', 'center');
    }
    else if (L.dead) this.text('탈락 · Enter 채팅', W / 2, hintY, '#c0cbdc', 'center');
    if (this.ended) {
      ctx.font = FONT_BIG;
      this.text('레이스 종료', W / 2, H / 2 - 10, '#fee761', 'center');
    }

    // 출발 카운트다운
    if (t < 0 && t > -3.2) {
      const n = Math.ceil(-t);
      const pop = n + t > 0.85 ? 1.5 : 1;
      ART.ui.draw(ctx, 'num' + Math.min(3, n), W / 2, H / 2 - 30, { scale: pop });
    } else if (t >= 0 && t < 0.8) {
      ART.ui.draw(ctx, 'go', W / 2, H / 2 - 30, { alpha: t > 0.5 ? (0.8 - t) / 0.3 : 1 });
    }
    if (t < -3.2) {
      ctx.font = FONT_BIG;
      this.text(`${MAP_BY_ID[this.theme]?.name ?? ''}`, W / 2, H / 2 - 40, '#ffffff', 'center');
    }
  }
}
