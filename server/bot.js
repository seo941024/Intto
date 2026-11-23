// 봇. 서버에 Socket.IO로 붙어 사람과 같은 길로 방에 들어가고, 레이스가 시작되면 사람과 같은 규칙으로 난다.
// 앞을 내다보며 누를지 뗄지 고르고, 벽에 부딪히면 사람처럼 생명을 잃는다.
// 서버는 방장이 봇 추가를 누르면 spawnBot으로 자기 자신에게 붙는 봇을 띄운다.
// tools/bots.js도 attachRace로 같은 비행 방식을 쓴다.
import { io } from 'socket.io-client';
import { buildMap, terrainAt, circleHitsTerrain, circleHitsObstacle } from '../shared/mapgen.js';
import { RULES, deriveStats } from '../shared/rules.js';
import { CHARACTER_BY_ID, SKILLS } from '../shared/characters.js';
import { steerFlyer, moveFlyer } from '../shared/flight.js';

export const call = (s, ev, data) => new Promise((res) => s.timeout(4000).emit(ev, data, (err, r) => res(err ? { ok: false, error: 'timeout' } : r)));

// 레이스 이벤트를 받아 봇을 날린다. bot에는 s, i, id, offset이 있어야 한다
export function attachRace(bot, log = () => {}) {
  const { s } = bot;
  s.on('race:init', (init) => startRace(bot, init, log));
  s.on('race:end', (d) => {
    log(bot.name, '결과', d.results.map((r) => `${r.rank}.${r.name} ${r.dist}m K${r.kills}`).join(' | '));
    stopRace(bot);
  });
  s.on('race:snap', (d) => {
    const R = bot.race;
    if (!R) return;
    for (const p of d.p) if (p.id !== bot.id) R.others.set(p.id, p);
  });
  s.on('race:gem', (d) => {
    const R = bot.race;
    if (!R) return;
    R.gemTaken.add(d.id);
    if (d.by === bot.id) R.slot = d.slot;
  });
  s.on('race:grab', (d) => d.by === bot.id && bot.race && (bot.race.slot = d.slot));
  s.on('race:skill', (d) => d.by === bot.id && bot.race && (bot.race.slot = 0));
  s.on('race:self', (d) => bot.race && applySelf(bot.race, d.skill));
  s.on('race:hit', (d) => bot.race && damage(bot, d.dmg, d.by, d.kind));
  s.on('race:debuff', (d) => {
    const R = bot.race;
    const now = Date.now();
    if (!R || R.dead || R.ghost || now < R.invUntil || now < R.dashUntil || !(d.effect in R.eff)) return;
    R.eff[d.effect] = now + d.ms;
    R.lastHit = { by: d.by, at: now };
  });
  s.on('race:drain', (d) => {
    const R = bot.race;
    if (!R || R.ghost || R.dead) return;
    R.hp -= d.amount;
    R.lastHit = { by: d.by, at: Date.now() };
    if (R.hp <= 0) loseLife(bot, 'drain');
  });
  s.on('disconnect', () => stopRace(bot));
}

export function stopRace(bot) {
  if (bot.race) clearInterval(bot.race.timer);
  bot.race = null;
}

const TICK = 1 / 60; // 앞날을 내다볼 때 한 칸
const SUB = 1 / 120; // 실제로 움직일 때 한 칸. 브라우저와 같이 잘게 나눈다
const PLAN_EVERY = 3; // 이만큼 칸마다 다시 계획
const HOLDS = [0, 4, 8, 13, 19, 26, 34, 44];

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

function fxOf(R, now) {
  return { dashing: now < R.dashUntil, slow: now < R.eff.slow, heavy: now < R.eff.heavy, glide: now < R.eff.glide };
}

function stats(R) {
  return deriveStats(R.ch.stats, R.feathers);
}

// 누르고 떼는 순서를 여러 가지로 그려 보고, 같은 규칙으로 미리 날려 본 뒤 가장 나은 것을 고른다
function plan(bot, t, now) {
  const R = bot.race;
  const st = stats(R);
  const fx = fxOf(R, now);
  const r = (now < R.eff.small ? 6 : 12) + R.margin;
  const obs = R.map.obstacles;
  const gems = R.map.gems;
  // 가속은 마음먹은 동안만 고려한다. 사람처럼 늘 꾹 누르고 있지는 않는다
  const boosts = R.boostOn ? [true, false] : [false];
  const hungry = R.hp < R.maxHp * 0.7;
  const foods = R.map.foods;
  const items = R.map.skills;
  const itemGain = R.slot === 0 ? 3 : 0.5; // 든 기술이 없으면 기술 아이콘을 더 노린다
  let best = null;
  for (const boost of boosts) {
    for (const first of [true, false]) {
      for (const h of HOLDS) {
        const B = { x: R.x, y: R.y, vx: R.vx, vy: R.vy, ghost: false, ghostDist: 0 };
        let hit = -1;
        let cost = 0;
        let gain = 0;
        for (let i = 0; i < R.horizon; i++) {
          const up = i < h ? first : !first;
          steerFlyer(B, st, { up, boost }, fx, TICK);
          moveFlyer(B, TICK);
          const at = now + (i + 1) * TICK * 1000;
          const tb = terrainAt(R.map, B.x);
          cost += Math.abs(B.y - (tb.top + tb.bottom) / 2) / Math.max(40, tb.bottom - tb.top);
          if (at < R.dashUntil) continue;
          if (circleHitsTerrain(R.map, B.x, B.y, r)) {
            hit = i;
            break;
          }
          if (R.ghost) continue;
          let bad = false;
          for (let k = lowerBound(obs, B.x - 72); k < obs.length && obs[k].x < B.x + 72; k++) {
            if (circleHitsObstacle(R.map, obs[k], t + (i + 1) * TICK, B.x, B.y, r) === 'damage') bad = true;
          }
          if (bad && at > R.invUntil) {
            hit = i;
            break;
          }
          for (let k = lowerBound(gems, B.x - 20); k < gems.length && gems[k].x < B.x + 20; k++) {
            const g = gems[k];
            if (!R.gemTaken.has(g.id) && (g.x - B.x) ** 2 + (g.y - B.y) ** 2 < 24 * 24) gain += 1;
          }
          for (let k = lowerBound(items, B.x - 20); k < items.length && items[k].x < B.x + 20; k++) {
            const it = items[k];
            if (!R.grabbed.has(it.id) && (it.x - B.x) ** 2 + (it.y - B.y) ** 2 < 26 * 26) gain += itemGain;
          }
          // 체력이 줄었으면 붕어빵 쪽으로
          if (hungry) {
            for (let k = lowerBound(foods, B.x - 20); k < foods.length && foods[k].x < B.x + 20; k++) {
              const f = foods[k];
              if (!R.foodEaten.has(f.id) && (f.x - B.x) ** 2 + (f.y - B.y) ** 2 < 24 * 24) gain += 4;
            }
          }
        }
        // 부딪히지 않는 길이 먼저, 그다음은 늦게 부딪히는 길. 그 안에서는 가속, 통로 가운데, 보석을 따진다
        let score = hit < 0 ? 1000 : hit * 10;
        score += (boost ? R.greed : 0) - (cost / R.horizon) * 6 + gain * 1.5;
        if (first === R.input.up && h > 0) score += 0.3;
        if (!best || score > best.score) best = { boost, first, h, score };
      }
    }
  }
  R.planned = best;
  R.planAt = 0;
}

function applySelf(R, skill) {
  const now = Date.now();
  if (R.dead || R.ghost) return;
  if (skill === 'dash') R.dashUntil = now + SKILLS.dash.ms;
  else if (skill === 'shield') R.shield = true;
  else if (skill === 'repair') R.hp = Math.min(R.maxHp, R.hp + SKILLS.repair.heal);
  else if (skill === 'glide') R.eff.glide = now + SKILLS.glide.ms;
  else if (skill === 'fold') R.eff.small = now + SKILLS.fold.ms;
}

function damage(bot, dmg, by, kind, local = false) {
  const R = bot.race;
  const now = Date.now();
  if (R.dead || R.ghost || now < R.invUntil || now < R.dashUntil) return;
  if (R.shield && !local) {
    R.shield = false;
    return;
  }
  R.hp -= dmg;
  R.hurtUntil = now + 380;
  if (by) R.lastHit = { by, at: now };
  if (R.hp <= 0) loseLife(bot, kind || 'hit');
}

function recenter(R) {
  const tb = terrainAt(R.map, R.x);
  R.y = (tb.top + tb.bottom) / 2;
  R.vy = 0;
}

function pushInside(R, r) {
  const tb = terrainAt(R.map, R.x);
  R.y = Math.min(Math.max(R.y, tb.top + r + 2), tb.bottom - r - 2);
  R.vy = 0;
}

function loseLife(bot, cause) {
  const R = bot.race;
  const now = Date.now();
  if (R.dead || R.ghost) return;
  const by = R.lastHit && now - R.lastHit.at < RULES.killCreditMs ? R.lastHit.by : null;
  R.lives -= 1;
  R.lastHit = null;
  bot.s.emit('race:lifeLost', { by, cause, lv: R.lives });
  bot.log(bot.name, `생명 잃음 ${cause}, 남은 ${R.lives}`);
  for (const k of Object.keys(R.eff)) R.eff[k] = 0;
  // 목숨 둘을 다 잃으면 탈락. 봇은 유령으로 날지 않고 바로 빠진다
  if (R.lives <= 0) {
    R.hp = 0;
    R.shield = false;
    return finalOut(bot);
  } else {
    R.hp = R.maxHp;
    R.invUntil = now + RULES.lifeLostInvulnMs;
  }
  recenter(R);
}

function finalOut(bot) {
  const R = bot.race;
  if (R.dead) return;
  R.dead = true;
  R.ghost = false;
  bot.s.emit('race:final');
  bot.log(bot.name, '탈락');
}

// 한 칸 움직이고 부딪힘, 먹기, 체력을 계산한다. 브라우저 Game.step과 같은 순서
function step(bot, dt, t, now) {
  const R = bot.race;
  const st = stats(R);
  R.maxHp = st.maxHp;
  const dashing = now < R.dashUntil;
  steerFlyer(R, st, R.input, fxOf(R, now), dt);
  if (now < R.eff.shake && now > R.shakeNext) {
    R.vy += (Math.random() * 2 - 1) * 260;
    R.shakeNext = now + 160;
  }
  moveFlyer(R, dt);
  const r = now < R.eff.small ? 6 : 12;
  if (R.wasDashing && !dashing && circleHitsTerrain(R.map, R.x, R.y, r)) recenter(R);
  R.wasDashing = dashing;

  if (!dashing && circleHitsTerrain(R.map, R.x, R.y, r)) {
    if (now < R.invUntil) pushInside(R, r);
    else if (R.shield) {
      R.shield = false;
      R.invUntil = now + 600;
      pushInside(R, r);
    } else if (RULES.terrainCostsLife) loseLife(bot, 'terrain');
    else {
      damage(bot, RULES.obstacleDamage, null, 'terrain', true);
      pushInside(R, r);
    }
  }
  if (R.dead) return;

  if (!R.ghost && !dashing) {
    const obs = R.map.obstacles;
    for (let i = lowerBound(obs, R.x - 72); i < obs.length && obs[i].x < R.x + 72; i++) {
      const res = circleHitsObstacle(R.map, obs[i], t, R.x, R.y, r);
      if (!res) continue;
      if (res === 'bounce') {
        if (R.vy > -200) R.vy = -330;
        continue;
      }
      if (now < R.invUntil || now < R.obsCd) continue;
      if (R.shield) {
        R.shield = false;
        R.obsCd = now + RULES.hitInvulnMs;
      } else if (RULES.obstacleCostsLife) loseLife(bot, 'obstacle');
      else {
        R.obsCd = now + RULES.hitInvulnMs;
        damage(bot, RULES.obstacleDamage, null, 'obstacle', true);
      }
      break;
    }
  }
  if (R.dead) return;

  if (!R.ghost) {
    const reach = (r + 12) ** 2;
    const gems = R.map.gems;
    for (let i = lowerBound(gems, R.x - 30); i < gems.length && gems[i].x < R.x + 30; i++) {
      const g = gems[i];
      if (R.gemTaken.has(g.id) || R.gemAsked.has(g.id)) continue;
      if ((g.x - R.x) ** 2 + (g.y - R.y) ** 2 < reach) {
        R.gemAsked.add(g.id);
        bot.s.emit('race:pickup', g.id);
      }
    }
    const items = R.map.skills;
    for (let i = lowerBound(items, R.x - 30); i < items.length && items[i].x < R.x + 30; i++) {
      const it = items[i];
      if (R.grabbed.has(it.id)) continue;
      if ((it.x - R.x) ** 2 + (it.y - R.y) ** 2 < (r + 16) ** 2) {
        R.grabbed.add(it.id);
        bot.s.emit('race:grab', it.id);
      }
    }
    for (const f of R.map.foods) {
      if (f.x > R.x + 30) break;
      if (R.foodEaten.has(f.id) || f.x < R.x - 30) continue;
      if ((f.x - R.x) ** 2 + (f.y - R.y) ** 2 < reach) {
        R.foodEaten.add(f.id);
        R.hp = Math.min(R.maxHp, R.hp + RULES.foodHeal);
      }
    }
    for (const f of R.map.feathers) {
      if (f.x > R.x + 30) break;
      if (R.featherTaken.has(f.id) || f.x < R.x - 30) continue;
      if ((f.x - R.x) ** 2 + (f.y - R.y) ** 2 < reach) {
        R.featherTaken.add(f.id);
        R.feathers++;
      }
    }
    R.hp -= RULES.hpDrainPerSec * dt;
    if (R.hp <= 0) loseLife(bot, 'hp');
  }

  const nice = R.map.nice;
  while (R.niceIdx < nice.length && nice[R.niceIdx].x < R.x) {
    if (!R.ghost && !R.dead && !dashing) bot.s.emit('race:nice', R.niceIdx);
    R.niceIdx++;
  }
}

function animOf(R, now) {
  if (R.ghost) return 'ghost';
  if (now < R.hurtUntil) return 'hurt';
  if (now < R.dashUntil || (R.input.boost && R.vx > stats(R).baseSpeed + 8)) return 'boost';
  return 'fly';
}

function effFlags(R, now) {
  let s = '';
  if (now < R.dashUntil) s += 'd';
  if (now < R.invUntil) s += 'i';
  for (const [k, c] of [['blind', 'b'], ['heavy', 'h'], ['shake', 's'], ['slow', 'w'], ['glide', 'g'], ['small', 'm']]) {
    if (now < R.eff[k]) s += c;
  }
  return s;
}

function startRace(bot, init, log) {
  stopRace(bot);
  const me = init.players.find((p) => p.id === bot.id);
  if (!me) return;
  bot.log = log;
  const ch = CHARACTER_BY_ID[me.charId];
  const st = deriveStats(ch.stats, 0);
  const map = buildMap(init.seed, init.mapId);
  // 브라우저와 같은 출발 자리
  const startY = (30 + RULES.worldH - 46) / 2 - 30 + (me.color || 0) * 20;
  const R = {
    ch, map, x: 0, y: startY, vx: st.baseSpeed, vy: 0, hp: st.maxHp, maxHp: st.maxHp, lives: RULES.lives,
    ghost: false, dead: false, ghostDist: 0, feathers: 0, slot: 0, lastHit: null,
    invUntil: 0, dashUntil: 0, obsCd: 0, hurtUntil: 0, shield: false, shakeNext: 0, wasDashing: false,
    eff: { blind: 0, heavy: 0, shake: 0, slow: 0, glide: 0, small: 0 },
    gemTaken: new Set(), gemAsked: new Set(), grabbed: new Set(), foodEaten: new Set(), featherTaken: new Set(), niceIdx: 0,
    others: new Map(), input: { up: false, boost: false }, planned: null, planAt: 0,
    // 봇마다 솜씨를 조금씩 다르게. 멀리 볼수록, 여유를 둘수록 덜 부딪히고, 욕심이 많을수록 자주 가속한다
    horizon: 34 + Math.floor(Math.random() * 14),
    margin: 1 + Math.random() * 3,
    greed: 0.4 + Math.random() * 0.8,
    boostRate: 0.45 + Math.random() * 0.3, // 가속을 마음먹는 시간 비율
    boostOn: true, boostUntil: 0,
    skillAt: 0, sendAt: 0,
  };
  bot.race = R;
  let last = Date.now();
  R.timer = setInterval(() => {
    const now = Date.now();
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = (now + bot.offset - init.startAt) / 1000;
    if (t < 0 || R.dead) return;
    // 1~3초마다 가속할지 말지 마음을 바꾼다
    if (now > R.boostUntil) {
      R.boostOn = Math.random() < R.boostRate;
      R.boostUntil = now + 1000 + Math.random() * 2000;
    }
    // 계획한 대로 몇 칸 누르고 떼다가 다시 계획한다
    if (!R.planned || R.planAt >= PLAN_EVERY) plan(bot, t, now);
    const c = R.planned;
    R.input.up = R.planAt < c.h ? c.first : !c.first;
    R.input.boost = c.boost;
    R.planAt++;
    const n = Math.max(1, Math.ceil(dt / SUB));
    for (let i = 0; i < n && !R.dead; i++) step(bot, dt / n, t, now);
    if (R.dead) return;

    // 기술은 받고 잠깐 뒤에 쓴다
    if (!R.ghost && R.slot > 0) {
      if (!R.skillAt) R.skillAt = now + 800 + Math.random() * 2500;
      else if (now > R.skillAt) {
        bot.s.emit('race:skill');
        R.skillAt = 0;
      }
    }
    if (now - R.sendAt >= 1000 / RULES.sendHz) {
      R.sendAt = now;
      bot.s.volatile.emit('race:state', {
        x: Math.round(R.x * 10) / 10, y: Math.round(R.y * 10) / 10, vx: Math.round(R.vx), vy: Math.round(R.vy),
        hp: Math.max(0, Math.ceil(R.hp)), mhp: R.maxHp, lv: R.lives, ghost: R.ghost, dead: R.dead,
        dist: Math.max(0, (R.x - R.ghostDist) / RULES.pxPerMeter),
        inv: now < R.invUntil || now < R.dashUntil, shield: R.shield, small: now < R.eff.small,
        a: animOf(R, now), e: effFlags(R, now),
      });
    }
  }, 1000 / 60);
}

// 서버가 방장 부탁으로 띄우는 봇. 정해진 방에 들어가 준비하고, 강퇴되거나 서버가 끊으면 다시 붙지 않는다
export function spawnBot({ url, key, name, charId, roomId, seat, done }) {
  const s = io(url, { transports: ['websocket'], reconnection: false, auth: { bot: key } });
  const bot = { i: seat, s, name, id: null, race: null, offset: 0 };
  const finish = () => {
    if (done) done();
    done = null;
  };
  s.on('connect', async () => {
    const t0 = Date.now();
    const st = await call(s, 'time:ping', t0);
    if (typeof st === 'number') bot.offset = st + (Date.now() - t0) / 2 - Date.now();
    const h = await call(s, 'hello', { name });
    bot.id = h && h.id;
    const j = await call(s, 'room:join', { roomId });
    finish();
    if (!j || !j.ok) s.disconnect();
  });
  s.on('room:state', (r) => {
    const me = r.players.find((p) => p.id === bot.id);
    if (!me) return;
    if (r.hostId !== bot.id && !me.ready && r.state === 'waiting') s.emit('room:me', { charId, ready: true });
  });
  s.on('room:kicked', () => s.disconnect());
  s.on('connect_error', () => {
    finish();
    s.close();
  });
  s.on('disconnect', () => {
    finish();
    s.close();
  });
  attachRace(bot);
  return bot;
}
