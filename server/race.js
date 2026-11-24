// 한 판의 레이스. 각자 비행은 브라우저가 계산해 보내고,
// 서버는 보석·기술 아이콘·발사체 명중·생명·탈락·시간·점수와 순위를 판정한다.
import { cachedMap, terrainAt, MAPS } from '../shared/mapgen.js';
import { RULES } from '../shared/rules.js';
import { CHARACTER_BY_ID, SKILLS, randomCharId } from '../shared/characters.js';
import { DASH_VX } from '../shared/flight.js';
import { EFFECTS } from '../shared/body.js';

const TICK_MS = 25; // 두 번에 한 번 스냅샷을 보내 초당 sendHz번이 되게 한다
const SNAP_MS = 1000 / RULES.sendHz;
const PROJ_R = 8;

const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const ANIMS = new Set(['fly', 'boost', 'hurt', 'ghost']);
const EFFECT_FLAGS = new RegExp(`^[di${EFFECTS.map((e) => e.c).join('')}]*$`); // 대시, 무적, 걸린 효과 글자만
const CAUSES = new Set(['terrain', 'obstacle', 'hp', 'hit', 'puff', 'nut', 'acorn', 'paper', 'bolt']);
// 생명을 잃게 한 공격을 KILL로 쳐 주는 시간. 클라이언트 쪽 판정보다 조금 넉넉히 둔다
const KILL_WINDOW_MS = RULES.killCreditMs + 1000;

export class Race {
  // isBot(id)는 서버가 띄운 봇인지. 사람이 모두 탈락하면 일찍 끝낼 때 쓴다
  constructor(io, room, onEnd, isBot = () => false) {
    this.io = io;
    this.room = room;
    this.chan = `room:${room.id}`;
    this.onEnd = onEnd;
    this.seed = Math.floor(Math.random() * 2 ** 31);
    this.mapId = room.mapId === 'random' ? MAPS[Math.floor(Math.random() * MAPS.length)].id : room.mapId;
    this.map = cachedMap(this.seed, this.mapId);
    this.mode = room.mode;
    this.players = new Map();
    room.ordered().forEach((m, i) => {
      const charId = m.charId === 'random' ? randomCharId() : m.charId;
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
        dead: false, // 기록이 끝남. 목숨을 다 잃었거나 나갔다
        dist: 0,
        gemScore: 0,
        livesLost: 0,
        hitBy: null, // 마지막으로 이 사람에게 피해나 방해를 준 상대 { by, at }
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
    // 한 번 계산하다 오류가 나도 레이스와 서버가 멈추지 않게 다음 계산으로 넘어간다
    this.timer = setInterval(() => {
      try {
        this.tick();
      } catch (err) {
        console.error('[race tick]', err);
      }
    }, TICK_MS);
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
    return p && p.connected && !p.dead && p.s;
  }
  // 화면 순위표처럼 소수점은 버린다
  score(p) {
    return Math.floor(p.dist + p.gemScore);
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
    return p.s && p.s.small ? RULES.bodyRSmall : RULES.bodyR;
  }

  // ── 브라우저에서 오는 신호 ──
  onState(pid, s) {
    const p = this.players.get(pid);
    if (!p || this.ended || !s || typeof s !== 'object') return;
    const now = Date.now();
    p.s = {
      x: num(s.x), y: num(s.y), vx: num(s.vx), vy: num(s.vy),
      hp: num(s.hp), mhp: num(s.mhp, 100), lv: num(s.lv),
      ghost: !!s.ghost, dead: !!s.dead,
      inv: !!s.inv, shield: !!s.shield, small: !!s.small,
      a: ANIMS.has(s.a) ? s.a : 'fly',
      e: typeof s.e === 'string' && EFFECT_FLAGS.test(s.e) ? s.e.slice(0, 8) : '',
    };
    p.at = now;
    // 거리는 기록이 끝나기 전까지만 받는다. 보낸 위치와 시간 안에 낼 수 있는 가장 빠른 거리를 넘지 못한다
    if (!p.dead && now >= this.startAt) {
      const cap = Math.min(p.s.x, (DASH_VX * (now - this.startAt + 1000)) / 1000) / RULES.pxPerMeter;
      p.dist = Math.max(p.dist, Math.min(Math.max(0, num(s.dist)), cap));
    }
    // 목숨 둘을 다 잃어 유령이 되면 그 자리에서 기록이 끝난다. 유령으로 같이 날아도 순위와 끝내기 판정에서는 빠진다
    if ((p.s.dead || p.s.ghost) && !p.dead) this.markOut(p);
  }

  onPickup(pid, gemId) {
    const p = this.players.get(pid);
    if (!Number.isInteger(gemId)) return;
    const gem = this.map.gems[gemId];
    if (!this.running() || !this.alive(p) || !gem || this.gemTaken.has(gemId)) return;
    if (Math.abs(this.posOf(p, Date.now()).x - gem.x) > 390) return;
    this.gemTaken.add(gemId);
    p.gems++;
    p.gemScore += gem.red ? RULES.redGemScore : RULES.gemScore;
    this.broadcast('race:gem', { id: gemId, by: pid });
  }

  // 기술 아이콘을 먹으면 그 칸의 기술을 하나 든다. 들고 있던 기술은 새 것으로 바뀐다
  onGrab(pid, itemId) {
    const p = this.players.get(pid);
    if (!Number.isInteger(itemId)) return;
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
    if (!this.running(now) || !this.alive(p) || !Number.isInteger(p.slot) || p.slot < 1) return;
    const skillId = CHARACTER_BY_ID[p.charId]?.skills[p.slot - 1];
    const sk = Object.hasOwn(SKILLS, skillId) ? SKILLS[skillId] : null;
    if (!sk) return;
    p.slot = 0;
    this.broadcast('race:skill', { by: pid, skill: skillId });
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
        q.hitBy = { by: pid, at: now };
        this.emitTo(q.id, 'race:debuff', { effect: sk.effect, ms: sk.ms, by: pid });
      }
      // 다른 사람 화면에도 그리는 방해는 회오리뿐이다
      if (sk.effect === 'shake') this.broadcast('race:fx', { type: sk.effect, by: pid, targets });
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

  // 생명은 한 판에 RULES.lives번까지만 잃는다. KILL은 서버가 그 사람에게 피해나 방해를 준 기록과 맞을 때만 친다
  onLifeLost(pid, d) {
    const p = this.players.get(pid);
    const now = Date.now();
    if (!this.running(now) || !p || p.dead || p.livesLost >= RULES.lives) return;
    p.livesLost++;
    const lv = RULES.lives - p.livesLost;
    const cause = d && CAUSES.has(d.cause) ? d.cause : 'terrain';
    const claim = d && typeof d.by === 'string' ? d.by : null;
    const by = claim && p.hitBy && p.hitBy.by === claim && now - p.hitBy.at < KILL_WINDOW_MS ? this.players.get(claim) : null;
    if (by && by !== p && !this.sameTeam(by, p)) {
      by.kills++;
      this.broadcast('race:event', { type: 'kill', by: by.id, target: pid, lv });
    } else {
      this.broadcast('race:event', { type: 'crash', target: pid, lv, cause });
    }
  }

  onNice(pid, idx) {
    const p = this.players.get(pid);
    if (!this.running() || !this.alive(p) || !Number.isInteger(idx) || !this.map.nice[idx] || p.niceSeen.has(idx)) return;
    // 좁은 목을 지나는 그 자리에서만 받는다
    if (Math.abs(this.posOf(p, Date.now()).x - this.map.nice[idx].x) > 400) return;
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
    this.broadcast('race:event', { type: why, target: p.id });
    this.checkEnd();
  }

  checkEnd() {
    if (this.ended) return;
    const list = [...this.players.values()];
    const anyLeft = list.some((p) => p.connected && !p.dead);
    if (!anyLeft || Date.now() >= this.endAt) return this.end();
    // 사람이 모두 탈락했으면 결과가 더 바뀔 수 있는지 본다. 남은 봇의 점수는 늘기만 한다
    const humans = list.filter((p) => !p.bot);
    if (!humans.length || !humans.every((p) => p.dead)) return;
    const racing = list.filter((p) => p.bot && !p.dead && p.connected);
    // 남은 봇이 모두 사람보다 앞서야 사람 순위가 굳는다
    const best = Math.max(...humans.map((p) => this.score(p)));
    if (!racing.every((p) => this.score(p) > best)) return;
    // 팀전은 팀 합계가 뒤집힐 수 없어야 끝낸다. 남은 봇이 모두 이미 앞선 팀이면 그 팀이 더 앞서 갈 뿐이다
    if (this.mode === 'team') {
      const totals = this.teamTotals();
      const lead = totals.A === totals.B ? null : totals.A > totals.B ? 'A' : 'B';
      if (!lead || racing.some((p) => p.team !== lead)) return;
    }
    this.end();
  }

  teamTotals() {
    const totals = { A: 0, B: 0 };
    for (const p of this.players.values()) if (p.team) totals[p.team] += this.score(p);
    return totals;
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
        q.hitBy = { by: pr.by, at: now };
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
            q.hitBy = { by: pd.by, at: now };
            this.emitTo(q.id, 'race:debuff', { effect: pd.effect, ms: pd.ms, by: pd.by });
          }
        }
      }
    }

    // dead는 그 사람이 화면에서 사라졌는지, out은 기록이 끝났는지. 유령으로 나는 사람은 out이지만 dead가 아니라 다른 화면에도 그린다
    // 타이머가 늦게 돌아도 평균 초당 sendHz번이 되도록 보낼 시각을 쌓아 간다
    if (now - this.lastSnap >= SNAP_MS - TICK_MS / 2) {
      this.lastSnap = Math.max(this.lastSnap + SNAP_MS, now - SNAP_MS);
      this.broadcast('race:snap', {
        t: now,
        p: [...this.players.values()]
          .filter((p) => p.s)
          .map((p) => ({
            id: p.id, ...p.s, dist: p.dist, score: this.score(p), slot: p.slot,
            dead: p.s.dead || !p.connected || (p.bot && p.dead), out: p.dead,
          })),
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
      if (!q.s.inv) {
        q.hitBy = { by: e.by, at: now };
        this.emitTo(q.id, 'race:hit', { dmg: e.dmg, by: e.by, kind: 'bolt' });
      }
    }
  }

  end() {
    if (this.ended) return;
    this.ended = true;
    clearInterval(this.timer);
    // 순위는 점수 순. 점수 = 거리 + 보석 점수. 팀전은 팀원 점수 합계가 큰 팀이 이긴다
    const results = [...this.players.values()]
      .map((p) => ({
        id: p.id, name: p.name, charId: p.charId, team: p.team, color: p.color,
        dist: Math.round(p.dist * 10) / 10, score: this.score(p),
        kills: p.kills, nices: p.nices, gems: p.gems,
      }))
      .sort((a, b) => b.score - a.score || b.dist - a.dist);
    results.forEach((r, i) => (r.rank = i + 1));
    let winnerTeam = null;
    let teamScores = null;
    if (this.mode === 'team') {
      teamScores = this.teamTotals();
      winnerTeam = teamScores.A === teamScores.B ? 'draw' : teamScores.A > teamScores.B ? 'A' : 'B';
    }
    const payload = { mapId: this.mapId, mode: this.mode, results, winnerTeam, teamScores };
    this.broadcast('race:end', payload);
    this.onEnd(payload);
  }

  dispose() {
    this.ended = true;
    clearInterval(this.timer);
  }
}
