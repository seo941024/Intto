// 한 판의 레이스. 각자 비행은 브라우저가 계산해 보내고,
// 서버는 보석 소유·기술칸·발사체 명중·유령 부활·시간·순위를 판정한다.
import { buildMap, terrainAt, MAPS } from '../shared/mapgen.js';
import { RULES } from '../shared/rules.js';
import { CHARACTERS, CHARACTER_BY_ID, SKILLS } from '../shared/characters.js';

const TICK_MS = 33;
const SNAP_MS = 1000 / RULES.sendHz;
const PROJ_R = 8;

const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d);

export class Race {
  // isBot(id)는 서버가 띄운 봇인지. 사람이 모두 탈락하면 일찍 끝낼 때 쓴다
  constructor(io, room, onEnd, isBot = () => false) {
    this.io = io;
    this.room = room;
    this.chan = `room:${room.id}`;
    this.onEnd = onEnd;
    this.seed = Math.floor(Math.random() * 2 ** 31);
    this.mapId = room.mapId === 'random' ? MAPS[Math.floor(Math.random() * MAPS.length)].id : room.mapId;
    this.map = buildMap(this.seed, this.mapId);
    this.mode = room.mode;
    this.players = new Map();
    room.ordered().forEach((m, i) => {
      const charId = m.charId === 'random' ? CHARACTERS[Math.floor(Math.random() * CHARACTERS.length)].id : m.charId;
      this.players.set(m.id, {
        id: m.id,
        name: m.name,
        bot: isBot(m.id),
        charId,
        team: this.mode === 'team' ? m.team : null,
        color: i,
        slot: 0,
        s: null, // 마지막으로 받은 비행 상태
        at: 0,
        ghost: false,
        dead: false,
        dist: 0,
        kills: 0,
        nices: 0,
        gems: 0,
        grabbed: new Set(), // 먹은 기술 아이콘. 아이콘은 사람마다 따로 먹는다
        niceSeen: new Set(),
        connected: true,
      });
    });
    this.gemTaken = new Set();
    this.projectiles = [];
    this.puddles = [];
    this.pending = []; // 시간차 발사·번개
    this.nextId = 1;
    const now = Date.now();
    this.startAt = now + 1200 + RULES.countdownMs; // 그림을 읽을 여유 1.2초
    this.endAt = this.startAt + RULES.raceMs;
    this.lastTick = now;
    this.lastSnap = 0;
    this.ended = false;
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  initPayload() {
    return {
      seed: this.seed,
      mapId: this.mapId,
      mode: this.mode,
      startAt: this.startAt,
      endAt: this.endAt,
      players: [...this.players.values()].map((p) => ({
        id: p.id, name: p.name, charId: p.charId, team: p.team, color: p.color,
      })),
    };
  }

  // ── 도우미 ──
  emitTo(pid, ev, data) {
    this.io.to(pid).emit(ev, data);
  }
  broadcast(ev, data) {
    this.io.to(this.chan).emit(ev, data);
  }
  running(now = Date.now()) {
    return !this.ended && now >= this.startAt && now < this.endAt;
  }
  alive(p) {
    return p && p.connected && !p.dead && !p.ghost && p.s;
  }
  sameTeam(a, b) {
    return this.mode === 'team' && a.team && a.team === b.team;
  }
  posOf(p, now) {
    const s = p.s;
    const lag = Math.min(150, Math.max(0, now - p.at)) / 1000;
    return { x: s.x + s.vx * lag, y: s.y + s.vy * lag };
  }
  bodyR(p) {
    return p.s && p.s.small ? 6 : 12;
  }

  // ── 브라우저에서 오는 신호 ──
  onState(pid, s) {
    const p = this.players.get(pid);
    if (!p || this.ended || !s || typeof s !== 'object') return;
    p.s = {
      x: num(s.x), y: num(s.y), vx: num(s.vx), vy: num(s.vy),
      hp: num(s.hp), mhp: num(s.mhp, 100), lv: num(s.lv),
      ghost: !!s.ghost, dead: !!s.dead,
      inv: !!s.inv, shield: !!s.shield, small: !!s.small,
      a: typeof s.a === 'string' ? s.a.slice(0, 8) : 'fly',
      e: typeof s.e === 'string' ? s.e.slice(0, 16) : '',
    };
    p.at = Date.now();
    p.ghost = p.s.ghost;
    p.dist = Math.max(0, num(s.dist));
    // 목숨 둘을 다 잃어 유령이 되면 그 자리에서 기록이 끝난다. 유령으로 같이 날아도 순위와 끝내기 판정에서는 빠진다
    if ((p.s.dead || p.s.ghost) && !p.dead) this.markOut(p);
  }

  onPickup(pid, gemId) {
    const p = this.players.get(pid);
    const gem = this.map.gems[gemId];
    if (!this.running() || !this.alive(p) || !gem || this.gemTaken.has(gemId)) return;
    if (Math.abs(this.posOf(p, Date.now()).x - gem.x) > 390) return;
    this.gemTaken.add(gemId);
    p.gems++;
    this.broadcast('race:gem', { id: gemId, by: pid, slot: p.slot });
  }

  // 기술 아이콘을 먹으면 그 칸의 기술을 하나 든다. 들고 있던 기술은 새 것으로 바뀐다
  onGrab(pid, itemId) {
    const p = this.players.get(pid);
    const it = this.map.skills[itemId];
    if (!this.running() || !this.alive(p) || !it || p.grabbed.has(itemId)) return;
    if (Math.abs(this.posOf(p, Date.now()).x - it.x) > 390) return;
    p.grabbed.add(itemId);
    p.slot = it.slot;
    this.broadcast('race:grab', { id: itemId, by: pid, slot: p.slot });
  }

  onSkill(pid) {
    const p = this.players.get(pid);
    const now = Date.now();
    if (!this.running(now) || !this.alive(p) || p.slot <= 0) return;
    const skillId = CHARACTER_BY_ID[p.charId].skills[p.slot - 1];
    const sk = SKILLS[skillId];
    p.slot = 0;
    this.broadcast('race:skill', { by: pid, skill: skillId, slot: 0 });
    const pos = this.posOf(p, now);

    if (sk.kind === 'self') {
      this.emitTo(pid, 'race:self', { skill: skillId });
    } else if (sk.kind === 'proj') {
      for (let i = 0; i < sk.count; i++) {
        this.pending.push({ at: now + i * (sk.gapMs || 0), type: 'proj', by: pid, skill: skillId, idx: i });
      }
    } else if (sk.kind === 'debuff') {
      const targets = [];
      for (const q of this.players.values()) {
        if (q === p || !this.alive(q) || this.sameTeam(p, q)) continue;
        const dx = this.posOf(q, now).x - pos.x;
        const ok =
          (sk.area === 'behind' && dx < 0 && -dx <= sk.range) ||
          (sk.area === 'ahead' && dx > 0 && dx <= sk.range) ||
          (sk.area === 'around' && Math.abs(dx) <= sk.range);
        if (!ok) continue;
        targets.push(q.id);
        this.emitTo(q.id, 'race:debuff', { effect: sk.effect, ms: sk.ms, by: pid });
      }
      this.broadcast('race:fx', { type: sk.effect, by: pid, targets });
    } else if (sk.kind === 'bolt') {
      let best = null;
      let bestDx = Infinity;
      for (const q of this.players.values()) {
        if (q === p || !this.alive(q) || this.sameTeam(p, q)) continue;
        const dx = this.posOf(q, now).x - pos.x;
        if (dx > 0 && dx <= sk.range && dx < bestDx) {
          best = q;
          bestDx = dx;
        }
      }
      if (best) {
        this.pending.push({ at: now + sk.delayMs, type: 'bolt', by: pid, target: best.id, dmg: sk.dmg });
        this.broadcast('race:fx', { type: 'boltWarn', by: pid, target: best.id, ms: sk.delayMs });
      } else {
        this.broadcast('race:fx', { type: 'boltMiss', by: pid });
      }
    } else if (sk.kind === 'puddle') {
      const pd = {
        id: this.nextId++, by: pid, x: pos.x - 51, y: pos.y, r: sk.r,
        until: now + sk.lifeMs, effect: sk.effect, ms: sk.ms, hitSet: new Set(),
      };
      this.puddles.push(pd);
      this.broadcast('race:puddle', { id: pd.id, by: pid, x: pd.x, y: pd.y, r: pd.r, lifeMs: sk.lifeMs });
    }
  }

  onLifeLost(pid, d) {
    const p = this.players.get(pid);
    if (!p || this.ended) return;
    const by = d && typeof d.by === 'string' ? this.players.get(d.by) : null;
    const lv = num(d && d.lv);
    if (by && by !== p && !this.sameTeam(by, p)) {
      by.kills++;
      this.broadcast('race:event', { type: 'kill', by: by.id, target: pid, lv });
    } else {
      this.broadcast('race:event', { type: 'crash', target: pid, lv });
    }
  }

  onNice(pid, idx) {
    const p = this.players.get(pid);
    if (!this.running() || !this.alive(p) || !Number.isInteger(idx) || !this.map.nice[idx] || p.niceSeen.has(idx)) return;
    p.niceSeen.add(idx);
    p.nices++;
    this.broadcast('race:event', { type: 'nice', target: pid });
  }

  onFinal(pid) {
    const p = this.players.get(pid);
    if (p && !p.dead) this.markOut(p);
  }

  onLeave(pid) {
    const p = this.players.get(pid);
    if (!p) return;
    p.connected = false;
    if (!p.dead) this.markOut(p, 'left');
  }

  markOut(p, why = 'out') {
    p.dead = true;
    p.ghost = false;
    this.broadcast('race:event', { type: why, target: p.id });
    this.checkEnd();
  }

  checkEnd() {
    if (this.ended) return;
    const list = [...this.players.values()];
    const anyLeft = list.some((p) => p.connected && !p.dead);
    if (!anyLeft || Date.now() >= this.endAt) return this.end();
    // 사람이 모두 탈락했고 남은 봇이 모두 사람보다 멀리 갔으면 사람 순위가 더 바뀌지 않으니 바로 끝낸다
    const humans = list.filter((p) => !p.bot);
    if (!humans.length || !humans.every((p) => p.dead)) return;
    const best = Math.max(...humans.map((p) => p.dist));
    if (list.every((p) => !p.bot || p.dead || !p.connected || p.dist > best)) this.end();
  }

  // ── 서버 시계 ──
  tick() {
    const now = Date.now();
    const dt = Math.min(0.1, (now - this.lastTick) / 1000);
    this.lastTick = now;
    if (this.ended) return;
    if (now >= this.endAt) return this.end();
    if (now < this.startAt) return;
    this.checkEnd();
    if (this.ended) return;

    // 시간차 실행
    if (this.pending.length) {
      const due = this.pending.filter((e) => e.at <= now);
      this.pending = this.pending.filter((e) => e.at > now);
      for (const e of due) this.runPending(e, now);
    }

    // 발사체
    for (let i = this.projectiles.length - 1; i >= 0; i--) {
      const pr = this.projectiles[i];
      pr.x += pr.vx * dt;
      pr.y += pr.vy * dt;
      pr.vy += pr.g * dt;
      const tb = terrainAt(this.map, pr.x);
      if (now > pr.until || pr.y - PROJ_R < tb.top || pr.y + PROJ_R > tb.bottom) {
        this.projectiles.splice(i, 1);
        this.broadcast('race:projGone', { id: pr.id, x: pr.x, y: pr.y, hit: false });
        continue;
      }
      const owner = this.players.get(pr.by);
      for (const q of this.players.values()) {
        if (q.id === pr.by || !this.alive(q) || (owner && this.sameTeam(owner, q))) continue;
        const qp = this.posOf(q, now);
        const rr = PROJ_R + this.bodyR(q) + 1;
        if ((qp.x - pr.x) ** 2 + (qp.y - pr.y) ** 2 > rr * rr) continue;
        if (q.s.inv) continue; // 대시·무적 중에는 통과
        this.projectiles.splice(i, 1);
        this.emitTo(q.id, 'race:hit', { dmg: pr.dmg, by: pr.by, kind: pr.kind });
        this.broadcast('race:projGone', { id: pr.id, x: pr.x, y: pr.y, hit: true, target: q.id });
        break;
      }
    }

    // 기름 구름
    for (let i = this.puddles.length - 1; i >= 0; i--) {
      const pd = this.puddles[i];
      if (now > pd.until) {
        this.puddles.splice(i, 1);
        continue;
      }
      const owner = this.players.get(pd.by);
      for (const q of this.players.values()) {
        if (q.id === pd.by || pd.hitSet.has(q.id) || !this.alive(q) || (owner && this.sameTeam(owner, q))) continue;
        const qp = this.posOf(q, now);
        if (Math.abs(qp.x - pd.x) < pd.r + 9 && Math.abs(qp.y - pd.y) < pd.r * 0.55 + 9) {
          pd.hitSet.add(q.id);
          if (!q.s.inv) {
            this.emitTo(q.id, 'race:debuff', { effect: pd.effect, ms: pd.ms, by: pd.by });
            this.broadcast('race:fx', { type: 'oilHit', by: pd.by, targets: [q.id] });
          }
        }
      }
    }

    if (now - this.lastSnap >= SNAP_MS) {
      this.lastSnap = now;
      this.broadcast('race:snap', {
        t: now,
        p: [...this.players.values()]
          .filter((p) => p.s)
          .map((p) => ({ id: p.id, ...p.s, dist: p.dist, slot: p.slot, dead: p.dead })),
      });
    }
  }

  runPending(e, now) {
    const p = this.players.get(e.by);
    if (e.type === 'proj') {
      if (!this.alive(p)) return;
      const sk = SKILLS[e.skill];
      const pos = this.posOf(p, now);
      let vx = p.s.vx + sk.speed;
      let vy = 0;
      let g = 0;
      let life = 1600;
      let y = pos.y;
      if (sk.proj === 'paper') {
        const a = (e.idx - 1) * sk.spread;
        vx = p.s.vx + Math.cos(a) * sk.speed;
        vy = Math.sin(a) * sk.speed;
      } else if (sk.proj === 'acorn') {
        vx = p.s.vx * 0.85;
        vy = sk.speed;
        g = sk.gravity;
        life = 2600;
        y = pos.y + 12;
      }
      const pr = {
        id: this.nextId++, by: e.by, kind: sk.proj, x: pos.x + 15, y, vx, vy, g,
        dmg: sk.dmg, until: now + life,
      };
      this.projectiles.push(pr);
      this.broadcast('race:proj', { id: pr.id, by: pr.by, kind: pr.kind, x: pr.x, y: pr.y, vx, vy, g, lifeMs: life, t: now });
    } else if (e.type === 'bolt') {
      const q = this.players.get(e.target);
      if (!this.alive(q)) return;
      this.broadcast('race:fx', { type: 'bolt', by: e.by, target: q.id });
      if (!q.s.inv) this.emitTo(q.id, 'race:hit', { dmg: e.dmg, by: e.by, kind: 'bolt' });
    }
  }

  end() {
    if (this.ended) return;
    this.ended = true;
    clearInterval(this.timer);
    const results = [...this.players.values()]
      .map((p) => ({
        id: p.id, name: p.name, charId: p.charId, team: p.team, color: p.color,
        dist: Math.round(p.dist * 10) / 10, kills: p.kills, nices: p.nices, gems: p.gems,
      }))
      .sort((a, b) => b.dist - a.dist);
    results.forEach((r, i) => (r.rank = i + 1));
    let winnerTeam = null;
    if (this.mode === 'team') {
      const best = { A: -1, B: -1 };
      for (const r of results) if (r.team && r.dist > best[r.team]) best[r.team] = r.dist;
      winnerTeam = best.A === best.B ? 'draw' : best.A > best.B ? 'A' : 'B';
    }
    const payload = { mapId: this.mapId, mode: this.mode, results, winnerTeam };
    this.broadcast('race:end', payload);
    this.onEnd(payload);
  }

  dispose() {
    this.ended = true;
    clearInterval(this.timer);
  }
}
