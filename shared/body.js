// 캐릭터 몸 하나의 규칙: 비행, 지형·장애물 충돌, 먹기, 피해, 생명.
// 브라우저의 내 캐릭터와 서버의 봇이 같은 함수로 난다. 시간 now는 부르는 쪽 시계를 쓴다.
// 효과음, 화면 효과, 서버로 보내기는 부르는 쪽이 makeHooks로 넘긴다.
import { RULES, deriveStats } from './rules.js';
import { SKILLS } from './characters.js';
import { terrainAt, circleHitsTerrain, circleHitsObstacle, startY } from './mapgen.js';
import { steerFlyer, moveFlyer } from './flight.js';
import { clamp, lowerBound } from './util.js';

// 걸리는 효과, race:state의 e로 보내는 글자, 머리 위 아이콘. d는 대시, i는 무적
export const EFFECTS = [
  { k: 'blind', c: 'b', icon: 'debuff_blind' },
  { k: 'heavy', c: 'h', icon: 'debuff_heavy' },
  { k: 'shake', c: 's', icon: 'debuff_shake' },
  { k: 'slow', c: 'w', icon: 'debuff_slow' },
  { k: 'glide', c: 'g', icon: 'buff_glide' },
  { k: 'small', c: 'm', icon: 'buff_shrink' },
];
// 보석을 먹었다고 보낸 뒤 이만큼 답이 없으면 다시 먹을 수 있게 둔다
export const GEM_RETRY_MS = 1200;

const NOOP = () => {};
// emit(ev, data): 서버로 보내기, fx(name, x, y, ms): 화면 효과, sound(name): 효과음, shake(ms): 화면 흔들기,
// squash(obstacle, until): 버섯 눌림, nice(x, y): NICE 표시, out(): 생명을 다 잃음
export function makeHooks(h) {
  return { emit: NOOP, fx: NOOP, sound: NOOP, shake: NOOP, squash: NOOP, nice: NOOP, out: NOOP, ...h };
}

export function newBody(map, ch, color) {
  const st = deriveStats(ch.stats, 0);
  const y0 = startY(color);
  return {
    map, ch, x: 0, y: y0, startY: y0, vx: st.baseSpeed, vy: 0,
    hp: st.maxHp, maxHp: st.maxHp, lives: RULES.lives,
    ghost: false, dead: false, ghostDist: 0, feathers: 0,
    invUntil: 0, dashUntil: 0, obsCd: 0, hurtUntil: 0, shield: false,
    eff: { blind: 0, heavy: 0, shake: 0, slow: 0, glide: 0, small: 0 },
    shakeNext: 0, lastHit: null, niceIdx: 0, wasDashing: false,
    boostLeft: RULES.boostSec, boosting: false, move: { up: false, boost: false },
    gemTaken: new Set(), gemAsked: new Map(), grabbed: new Set(), foodEaten: new Set(), featherTaken: new Set(),
    st, stFeathers: 0,
    fx: { dashing: false, slow: false, heavy: false },
  };
}

// 능력치는 깃털 수가 바뀔 때만 다시 계산한다
export function bodyStats(B) {
  if (B.stFeathers !== B.feathers) {
    B.st = deriveStats(B.ch.stats, B.feathers);
    B.stFeathers = B.feathers;
  }
  return B.st;
}

// 이번 순간 비행에 걸린 효과
export function bodyFx(B, now) {
  const f = B.fx;
  f.dashing = now < B.dashUntil;
  f.slow = now < B.eff.slow;
  f.heavy = now < B.eff.heavy;
  return f;
}

export const bodyRadius = (B, now) => (now < B.eff.small ? RULES.bodyRSmall : RULES.bodyR);
// 날아간 거리 m. 유령으로 난 거리는 빼서 기록이 끝난 자리에 멈춘다
export const bodyDist = (B) => Math.max(0, (B.x - B.ghostDist) / RULES.pxPerMeter);

export function recenter(B) {
  const tb = terrainAt(B.map, B.x);
  B.y = (tb.top + tb.bottom) / 2;
  B.vy = 0;
}

function pushInside(B, r) {
  const tb = terrainAt(B.map, B.x);
  B.y = clamp(B.y, tb.top + r + 2, tb.bottom - r - 2);
  B.vy = 0;
}

// 한 칸 움직이고 부딪힘, 먹기, 체력을 계산한다
export function stepBody(B, input, dt, t, now, h) {
  if (B.dead) return;
  const map = B.map;
  const st = bodyStats(B);
  B.maxHp = st.maxHp;
  const fx = bodyFx(B, now);
  const dashing = fx.dashing;

  // 가속 게이지. 누르는 동안 줄고, 떼고 있으면 그 두 배 시간에 다시 찬다. 남은 만큼 바로 쓸 수 있다
  B.boosting = input.boost && B.boostLeft > 0;
  if (B.boosting) B.boostLeft = Math.max(0, B.boostLeft - dt);
  else if (!input.boost) B.boostLeft = Math.min(RULES.boostSec, B.boostLeft + (dt * RULES.boostSec) / RULES.boostRefillSec);
  B.move.up = input.up;
  B.move.boost = B.boosting;
  steerFlyer(B, st, B.move, fx, dt);
  if (now < B.eff.shake && now > B.shakeNext) {
    B.vy += (Math.random() * 2 - 1) * 260;
    B.shakeNext = now + 160;
  }
  moveFlyer(B, dt);

  const r = bodyRadius(B, now);
  if (B.wasDashing && !dashing && circleHitsTerrain(map, B.x, B.y, r)) recenter(B);
  B.wasDashing = dashing;

  // 지형. 유령과 활공 중인 몸은 다치지 않고 땅 안쪽으로 밀려나 미끄러지기만 한다
  if (!dashing && circleHitsTerrain(map, B.x, B.y, r)) {
    if (B.ghost || now < B.invUntil || now < B.eff.glide) pushInside(B, r);
    else if (B.shield) {
      B.shield = false;
      B.invUntil = now + 600;
      pushInside(B, r);
      h.fx('hit', B.x, B.y, 280);
      h.sound('shield');
    } else if (RULES.terrainCostsLife) loseLife(B, 'terrain', now, h);
    else {
      damageBody(B, RULES.obstacleDamage, null, 'terrain', now, h, true);
      pushInside(B, r);
    }
  }
  if (B.dead) return;

  // 장애물
  if (!B.ghost && !dashing) {
    const obs = map.obstacles;
    for (let i = lowerBound(obs, B.x - 72); i < obs.length && obs[i].x < B.x + 72; i++) {
      const o = obs[i];
      const res = circleHitsObstacle(map, o, t, B.x, B.y, r);
      if (!res) continue;
      if (res === 'bounce') {
        if (B.vy > -200) {
          B.vy = -330;
          h.squash(o, now + 260);
          h.sound('bounce');
        }
        continue;
      }
      if (now < B.invUntil || now < B.obsCd) continue;
      if (B.shield) {
        B.shield = false;
        B.obsCd = now + RULES.hitInvulnMs;
        h.fx('hit', B.x, B.y, 280);
        h.sound('shield');
      } else if (RULES.obstacleCostsLife) loseLife(B, 'obstacle', now, h);
      else {
        B.obsCd = now + RULES.hitInvulnMs;
        damageBody(B, RULES.obstacleDamage, null, 'obstacle', now, h, true);
      }
      break;
    }
  }
  if (B.dead) return;

  // 보석·고기·깃털·기술 아이콘 먹기와 시간이 지나며 줄어드는 HP
  if (!B.ghost) {
    const reach = (r + 12) ** 2;
    const gems = map.gems;
    for (let i = lowerBound(gems, B.x - 30); i < gems.length && gems[i].x < B.x + 30; i++) {
      const g = gems[i];
      if (B.gemTaken.has(g.id) || B.gemAsked.has(g.id)) continue;
      if ((g.x - B.x) ** 2 + (g.y - B.y) ** 2 < reach) {
        B.gemAsked.set(g.id, now);
        h.emit('race:pickup', g.id);
        h.fx('pickup', g.x, g.y, 260);
      }
    }
    const foods = map.foods;
    for (let i = lowerBound(foods, B.x - 30); i < foods.length && foods[i].x < B.x + 30; i++) {
      const f = foods[i];
      if (B.foodEaten.has(f.id) || (f.x - B.x) ** 2 + (f.y - B.y) ** 2 >= reach) continue;
      B.foodEaten.add(f.id);
      B.hp = Math.min(B.maxHp, B.hp + RULES.foodHeal);
      h.fx('pickup', f.x, f.y, 260);
      h.sound('food');
    }
    const feathers = map.feathers;
    for (let i = lowerBound(feathers, B.x - 30); i < feathers.length && feathers[i].x < B.x + 30; i++) {
      const f = feathers[i];
      if (B.featherTaken.has(f.id) || (f.x - B.x) ** 2 + (f.y - B.y) ** 2 >= reach) continue;
      B.featherTaken.add(f.id);
      B.feathers++;
      h.fx('pickup', f.x, f.y, 260);
      h.sound('feather');
    }
    // 기술 아이콘: 먹으면 그 칸 기술을 하나 든다
    const sk = map.skills;
    for (let i = lowerBound(sk, B.x - 30); i < sk.length && sk[i].x < B.x + 30; i++) {
      const it = sk[i];
      if (B.grabbed.has(it.id) || (it.x - B.x) ** 2 + (it.y - B.y) ** 2 >= (r + 16) ** 2) continue;
      B.grabbed.add(it.id);
      h.emit('race:grab', it.id);
      h.fx('pickup', it.x, it.y, 260);
      h.sound('gem');
    }
    B.hp -= RULES.hpDrainPerSec * dt;
    if (B.hp <= 0) loseLife(B, 'hp', now, h);
  }

  // 좁은 목 통과
  const nice = map.nice;
  while (B.niceIdx < nice.length && nice[B.niceIdx].x < B.x) {
    if (!B.ghost && !B.dead && !dashing) {
      h.emit('race:nice', B.niceIdx);
      h.nice(B.x, B.y);
    }
    B.niceIdx++;
  }
}

// local은 내가 장애물에 부딪힌 피해. 보호막은 남이 쏜 공격만 막는다
export function damageBody(B, dmg, by, kind, now, h, local = false) {
  if (B.dead || B.ghost || now < B.invUntil || now < B.dashUntil) return;
  if (B.shield && !local) {
    B.shield = false;
    h.fx('hit', B.x, B.y, 280);
    h.sound('shield');
    return;
  }
  B.hp -= dmg;
  B.hurtUntil = now + 380;
  if (by) B.lastHit = { by, at: now };
  h.shake(180);
  h.fx('hit', B.x, B.y, 280);
  h.sound('hit');
  if (B.hp <= 0) loseLife(B, kind || 'hit', now, h);
}

export function debuffBody(B, effect, ms, by, now, h) {
  if (B.dead || B.ghost || now < B.invUntil || now < B.dashUntil) return;
  if (!Object.hasOwn(B.eff, effect)) return;
  B.eff[effect] = now + ms;
  B.lastHit = { by, at: now };
  h.sound('hit');
}

// 내게 쓰는 기술
export function applySelf(B, skill, now, h) {
  if (B.dead || B.ghost) return;
  if (skill === 'dash') {
    B.dashUntil = now + SKILLS.dash.ms;
    h.sound('dash');
  } else if (skill === 'shield') {
    B.shield = true;
    h.sound('shield');
  } else if (skill === 'repair') {
    B.hp = Math.min(B.maxHp, B.hp + SKILLS.repair.heal);
    h.sound('heal');
  } else if (skill === 'glide') {
    B.eff.glide = now + SKILLS.glide.ms;
    h.sound('feather');
  } else if (skill === 'fold') {
    B.eff.small = now + SKILLS.fold.ms;
    h.sound('feather');
  }
}

// 생명 하나를 잃는다. 기술에 맞은 지 얼마 안 됐으면 그 상대를 함께 알린다. 둘 다 잃으면 out을 부른다
export function loseLife(B, cause, now, h) {
  if (B.dead || B.ghost) return;
  const by = B.lastHit && now - B.lastHit.at < RULES.killCreditMs ? B.lastHit.by : null;
  B.lives -= 1;
  B.lastHit = null;
  h.emit('race:lifeLost', { by, cause, lv: B.lives });
  h.fx('hit', B.x, B.y, 320);
  h.shake(300);
  for (const k of Object.keys(B.eff)) B.eff[k] = 0;
  if (B.lives <= 0) {
    B.hp = 0;
    B.shield = false;
    h.out();
  } else {
    B.hp = B.maxHp;
    B.invUntil = now + RULES.lifeLostInvulnMs;
    h.sound('lifeLost');
  }
  recenter(B);
}

export function animOf(B, now) {
  if (B.ghost) return 'ghost';
  if (now < B.hurtUntil) return 'hurt';
  if (now < B.dashUntil || (B.boosting && B.vx > bodyStats(B).baseSpeed + 8)) return 'boost';
  return 'fly';
}

export function effFlags(B, now) {
  let s = '';
  if (now < B.dashUntil) s += 'd';
  if (now < B.invUntil) s += 'i';
  for (const e of EFFECTS) if (now < B.eff[e.k]) s += e.c;
  return s;
}

// 서버로 보내는 비행 상태 race:state
export function bodyState(B, now) {
  return {
    x: Math.round(B.x * 10) / 10,
    y: Math.round(B.y * 10) / 10,
    vx: Math.round(B.vx),
    vy: Math.round(B.vy),
    hp: Math.max(0, Math.ceil(B.hp)),
    mhp: B.maxHp,
    lv: B.lives,
    ghost: B.ghost,
    dead: B.dead,
    dist: bodyDist(B),
    inv: now < B.invUntil || now < B.dashUntil,
    shield: B.shield,
    small: now < B.eff.small,
    a: animOf(B, now),
    e: effFlags(B, now),
  };
}
