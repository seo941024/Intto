// 봇. 서버에 Socket.IO로 붙어 사람과 같은 길로 방에 들어가고, 레이스가 시작되면 사람과 같은 규칙으로 난다.
// 앞을 내다보며 누를지 뗄지 고르고, 벽에 부딪히면 사람처럼 생명을 잃는다.
// 서버는 방장이 봇 추가를 누르면 spawnBot으로 자기 자신에게 붙는 봇을 띄운다.
// tools/bots.js도 attachRace로 같은 비행 방식을 쓴다.
import { io } from 'socket.io-client';
import { cachedMap, terrainAt, circleHitsTerrain, circleHitsObstacle } from '../shared/mapgen.js';
import { RULES } from '../shared/rules.js';
import { CHARACTER_BY_ID } from '../shared/characters.js';
import { steerFlyer, moveFlyer } from '../shared/flight.js';
import {
  newBody, makeHooks, stepBody, damageBody, debuffBody, applySelf, bodyStats, bodyFx, bodyRadius, bodyState,
} from '../shared/body.js';
import { lowerBound } from '../shared/util.js';

export const call = (s, ev, data) => new Promise((res) => s.timeout(4000).emit(ev, data, (err, r) => res(err ? { ok: false, error: 'timeout' } : r)));

// 레이스 이벤트를 받아 봇을 날린다. bot에는 s, name, id, offset이 있어야 한다
export function attachRace(bot, log = () => {}) {
  const { s } = bot;
  s.on('race:init', (init) => startRace(bot, init, log));
  s.on('race:end', (d) => {
    log(bot.name, '결과', d.results.map((r) => `${r.rank}.${r.name} ${r.dist}m K${r.kills}`).join(' | '));
    stopRace(bot);
  });
  s.on('race:gem', (d) => bot.race && bot.race.gemTaken.add(d.id));
  s.on('race:grab', (d) => d.by === bot.id && bot.race && (bot.race.slot = d.slot));
  s.on('race:skill', (d) => d.by === bot.id && bot.race && (bot.race.slot = 0));
  s.on('race:self', (d) => bot.race && applySelf(bot.race, d.skill, Date.now(), bot.race.hooks));
  s.on('race:hit', (d) => bot.race && damageBody(bot.race, d.dmg, d.by, d.kind, Date.now(), bot.race.hooks));
  s.on('race:debuff', (d) => bot.race && debuffBody(bot.race, d.effect, d.ms, d.by, Date.now(), bot.race.hooks));
  s.on('disconnect', () => stopRace(bot));
}

function stopRace(bot) {
  if (bot.race) clearInterval(bot.race.timer);
  bot.race = null;
}

const TICK = 1 / 60; // 앞날을 내다볼 때 한 칸
const SUB = 1 / 120; // 실제로 움직일 때 한 칸. 브라우저와 같이 잘게 나눈다
const PLAN_EVERY = 3; // 이만큼 칸마다 다시 계획
const HOLDS = [0, 4, 8, 13, 19, 26, 34, 44];

// 누르고 떼는 순서를 여러 가지로 그려 보고, 같은 규칙으로 미리 날려 본 뒤 가장 나은 것을 고른다
function plan(R, t, now) {
  const st = bodyStats(R);
  const fx = { ...bodyFx(R, now) };
  const r = bodyRadius(R, now) + R.margin;
  const obs = R.map.obstacles;
  const gems = R.map.gems;
  // 가속은 마음먹은 동안만 고려한다. 사람처럼 늘 꾹 누르고 있지는 않는다
  const boosts = R.boostOn ? [true, false] : [false];
  const hungry = R.hp < R.maxHp * 0.7;
  const foods = R.map.foods;
  const items = R.map.skills;
  const itemGain = R.slot === 0 ? 3 : 0.5; // 든 기술이 없으면 기술 아이콘을 더 노린다
  const B = { x: 0, y: 0, vx: 0, vy: 0 };
  let best = null;
  for (const boost of boosts) {
    for (const first of [true, false]) {
      for (const h of HOLDS) {
        B.x = R.x;
        B.y = R.y;
        B.vx = R.vx;
        B.vy = R.vy;
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
          // 체력이 줄었으면 고기 쪽으로
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

// 목숨 둘을 다 잃으면 탈락. 봇은 유령으로 날지 않고 바로 빠지고 비행 계산을 멈춘다
function finalOut(bot) {
  const R = bot.race;
  if (!R || R.dead) return;
  // 기록이 끝나는 자리를 서버가 알도록 탈락을 알리기 전에 지금 상태를 한 번 더 보낸다
  bot.s.emit('race:state', bodyState(R, R.input, Date.now()));
  R.dead = true;
  bot.s.emit('race:final');
  bot.log(bot.name, '탈락');
  stopRace(bot);
}

function startRace(bot, init, log) {
  stopRace(bot);
  const me = init.players.find((p) => p.id === bot.id);
  if (!me) return;
  bot.log = log;
  const map = cachedMap(init.seed, init.mapId);
  const R = Object.assign(newBody(map, CHARACTER_BY_ID[me.charId], me.color || 0), {
    slot: 0, input: { up: false, boost: false }, planned: null, planAt: 0,
    // 봇마다 솜씨를 조금씩 다르게. 멀리 볼수록, 여유를 둘수록 덜 부딪히고, 욕심이 많을수록 자주 가속한다
    horizon: 34 + Math.floor(Math.random() * 14),
    margin: 1 + Math.random() * 3,
    greed: 0.4 + Math.random() * 0.8,
    boostRate: 0.45 + Math.random() * 0.3, // 가속을 마음먹는 시간 비율
    boostOn: true, boostUntil: 0,
    skillAt: 0, sendAt: 0,
  });
  R.hooks = makeHooks({
    emit: (ev, d) => {
      bot.s.emit(ev, d);
      if (ev === 'race:lifeLost') log(bot.name, `생명 잃음 ${d.cause}, 남은 ${d.lv}`);
    },
    out: () => finalOut(bot),
  });
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
    if (!R.planned || R.planAt >= PLAN_EVERY) plan(R, t, now);
    const c = R.planned;
    R.input.up = R.planAt < c.h ? c.first : !c.first;
    R.input.boost = c.boost;
    R.planAt++;
    const n = Math.max(1, Math.ceil(dt / SUB));
    for (let i = 0; i < n && !R.dead; i++) stepBody(R, R.input, dt / n, t, now, R.hooks);
    if (R.dead) return;

    // 기술은 받고 잠깐 뒤에 쓴다
    if (R.slot > 0) {
      if (!R.skillAt) R.skillAt = now + 800 + Math.random() * 2500;
      else if (now > R.skillAt) {
        bot.s.emit('race:skill');
        R.skillAt = 0;
      }
    }
    if (now - R.sendAt >= 1000 / RULES.sendHz) {
      R.sendAt = now;
      bot.s.volatile.emit('race:state', bodyState(R, R.input, now));
    }
  }, 1000 / 60);
}

// 서버가 방장 부탁으로 띄우는 봇. 정해진 방에 들어가 준비하고, 강퇴되거나 서버가 끊으면 다시 붙지 않는다
export function spawnBot({ url, key, name, charId, roomId, done }) {
  const s = io(url, { transports: ['websocket'], reconnection: false, auth: { bot: key } });
  const bot = { s, name, id: null, race: null, offset: 0 };
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
