// 시드로 맵을 만든다. 서버와 브라우저가 같은 시드로 같은 지형·장애물·보석을 얻는다.
// 가로는 960 화면 기준 픽셀, 세로는 맵 높이 RULES.worldH 안에서 만든다.
import { mulberry32, hashString } from './rng.js';
import { RULES } from './rules.js';

export const MAPS = [
  { id: 'cloud', name: '구름섬', desc: '넓은 하늘길, 떠 있는 바위와 가시 풍선' },
  { id: 'mushroom', name: '버섯숲', desc: '튕겨 올리는 버섯과 가시덤불' },
  { id: 'storm', name: '폭풍협곡', desc: '예고 뒤 내리치는 번개 기둥' },
];
export const MAP_BY_ID = Object.fromEntries(MAPS.map((m) => [m.id, m]));

export const SEG = 4; // 지형 표본 간격, 화면도 4픽셀 세로줄로 그린다
export const MAP_LENGTH = 120_000; // 8000m
const H = RULES.worldH;
// 맵 위아래 끝에서 지형이 최소한 차지하는 두께. 위는 하트·타이머, 아래는 기술칸이 지형 위에 오도록 넉넉히 둔다
const EDGE_TOP = 30;
const EDGE_BOT = 46;
const MIN_PASS = 70; // 장애물 옆으로 반드시 남기는 통로 높이
const MIN_GAP = 78; // 통로가 이보다 좁아지지 않게
const START_GAP = 262; // 출발 직후 통로 폭

// 장애물 충돌 범위. 그림은 public/assets/world/<theme>/obstacles.json
export const OBSTACLE_GEOM = {
  rock: { shape: 'circle', r: 18, variants: ['rock_a', 'rock_b', 'rock_c'] },
  bigrock: { shape: 'circle', r: 27, variants: ['bigrock'] },
  balloon: { shape: 'circle', r: 16, variants: ['balloon'], moving: true },
  thorn: { shape: 'circle', r: 18, variants: ['thorn_a', 'thorn_b'] },
  spore: { shape: 'circle', r: 14, variants: ['spore'], moving: true },
  crystal: { shape: 'circle', r: 18, variants: ['crystal_a', 'crystal_b'] },
  stormorb: { shape: 'circle', r: 16, variants: ['stormorb'], moving: true },
  mushroom: { shape: 'mushroom', capW: 60, capTop: 55, capBottom: 34, stemW: 18, bounce: true }, // 버섯숲 그림의 높은 갓에 맞춘 높이
  bolt: { shape: 'column', w: 18 },
};

const THEMES = {
  cloud: {
    gapStart: 262, gapEnd: 146, wobble: 62,
    obstacles: [['rock', 5], ['bigrock', 2], ['balloon', 3]],
    spacing: [1350, 645],
  },
  mushroom: {
    gapStart: 268, gapEnd: 150, wobble: 54,
    obstacles: [['thorn', 5], ['spore', 3]],
    spacing: [1500, 720],
    mushroomEvery: [975, 1725],
  },
  storm: {
    gapStart: 262, gapEnd: 144, wobble: 66,
    obstacles: [['crystal', 4], ['stormorb', 4]],
    spacing: [1575, 780],
    boltEvery: [1650, 2550],
  },
};

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const clamp01 = (v) => clamp(v, 0, 1);
const lerp = (a, b, t) => a + (b - a) * t;

function catmull(arr, f) {
  const n = arr.length;
  const i = Math.floor(f);
  const t = f - i;
  const p0 = arr[clamp(i - 1, 0, n - 1)];
  const p1 = arr[clamp(i, 0, n - 1)];
  const p2 = arr[clamp(i + 1, 0, n - 1)];
  const p3 = arr[clamp(i + 2, 0, n - 1)];
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t);
}

function weightedPick(rng, list) {
  const total = list.reduce((s, [, w]) => s + w, 0);
  let r = rng.next() * total;
  for (const [v, w] of list) {
    r -= w;
    if (r <= 0) return v;
  }
  return list[list.length - 1][0];
}

export function buildMap(seed, mapId) {
  const theme = THEMES[mapId] ?? THEMES.cloud;
  const rng = mulberry32((seed ^ hashString(mapId)) >>> 0);
  const n = Math.ceil(MAP_LENGTH / SEG) + 1;
  const top = new Float32Array(n);
  const bottom = new Float32Array(n);
  const START = 1650; // 출발 직후 평평한 구간

  // 큰 흐름: 480px마다 통로 중심과 폭
  const CP = 480;
  const ncp = Math.ceil(MAP_LENGTH / CP) + 4;
  const cCenter = new Float32Array(ncp);
  const cGap = new Float32Array(ncp);
  let c = (EDGE_TOP + H - EDGE_BOT) / 2;
  for (let i = 0; i < ncp; i++) {
    const x = i * CP;
    const prog = clamp01((x - 1800) / 67_500);
    let g = lerp(theme.gapStart, theme.gapEnd, prog) * rng.range(0.86, 1.14);
    c += rng.range(-theme.wobble, theme.wobble);
    if (x < START) {
      g = START_GAP;
      c = (EDGE_TOP + H - EDGE_BOT) / 2;
    }
    const half = g / 2;
    c = clamp(c, EDGE_TOP + half + 6, Math.max(EDGE_TOP + half + 6, H - EDGE_BOT - half - 6));
    cCenter[i] = c;
    cGap[i] = g;
  }

  // 잔결: 72px마다 위아래 경계를 따로 흔든다
  const DCP = 72;
  const nd = Math.ceil(MAP_LENGTH / DCP) + 4;
  const dTop = new Float32Array(nd);
  const dBot = new Float32Array(nd);
  for (let i = 0; i < nd; i++) {
    dTop[i] = rng.range(-1, 1);
    dBot[i] = rng.range(-1, 1);
  }

  // 좁은 목: 아슬아슬하게 지나면 NICE
  const chokes = [];
  let cx = 4800 + rng.range(0, 1200);
  while (cx < MAP_LENGTH - 2250) {
    chokes.push({ x: cx, w: rng.range(255, 390), k: rng.range(0.5, 0.62) });
    cx += rng.range(3900, 6300);
  }

  let ci = 0;
  for (let i = 0; i < n; i++) {
    const x = i * SEG;
    const center = catmull(cCenter, x / CP);
    let gap = catmull(cGap, x / CP);
    while (ci < chokes.length && chokes[ci].x + chokes[ci].w / 2 < x) ci++;
    const ch = chokes[ci];
    if (ch && Math.abs(x - ch.x) < ch.w / 2) {
      const f = 0.5 + 0.5 * Math.cos((Math.PI * (x - ch.x)) / (ch.w / 2));
      gap = lerp(gap, Math.max(84, gap * ch.k), f);
    }
    const amp = x < START ? 0 : x < START + 750 ? ((x - START) / 750) * 8 : 8;
    let t = center - gap / 2 + catmull(dTop, x / DCP) * amp;
    let b = center + gap / 2 + catmull(dBot, x / DCP) * amp;
    t = Math.max(EDGE_TOP, t);
    b = Math.min(H - EDGE_BOT, b);
    if (b - t < MIN_GAP) {
      const mid = (t + b) / 2;
      t = mid - MIN_GAP / 2;
      b = mid + MIN_GAP / 2;
    }
    top[i] = t;
    bottom[i] = b;
  }

  const map = {
    id: mapId, seed, seg: SEG, length: MAP_LENGTH,
    top, bottom,
    obstacles: [], gems: [], foods: [], feathers: [], nice: [], skills: [],
  };

  for (const chk of chokes) {
    const tb = terrainAt(map, chk.x);
    map.nice.push({ x: chk.x, gap: tb.bottom - tb.top });
  }

  const nearChoke = (x, pad) => chokes.some((k) => Math.abs(x - k.x) < k.w / 2 + pad);
  const nearObstacle = (x, pad) => map.obstacles.some((o) => Math.abs(o.x - x) < pad);
  let oid = 0;

  // 번개 기둥
  if (theme.boltEvery) {
    let x = 2850;
    while (x < MAP_LENGTH - 900) {
      if (!nearChoke(x, 240)) {
        const period = rng.range(3.2, 4.4);
        map.obstacles.push({ id: oid++, type: 'bolt', x, period, phase: rng.range(0, period), warn: 1.0, active: 0.75 });
      }
      const prog = clamp01(x / 75_000);
      x += lerp(theme.boltEvery[1], theme.boltEvery[0], prog) * rng.range(0.8, 1.2);
    }
  }

  // 튕김 버섯
  if (theme.mushroomEvery) {
    let x = 2250;
    while (x < MAP_LENGTH - 900) {
      x += rng.range(theme.mushroomEvery[0], theme.mushroomEvery[1]);
      for (let tries = 0; tries < 8; tries++, x += 36) {
        if (nearChoke(x, 180) || nearObstacle(x, 120)) continue;
        const l = terrainAt(map, x - 30);
        const r = terrainAt(map, x + 30);
        const m = terrainAt(map, x);
        if (Math.abs(l.bottom - r.bottom) > 13) continue;
        if (m.bottom - m.top < 156) continue;
        map.obstacles.push({ id: oid++, type: 'mushroom', x, floorY: Math.round(m.bottom) + 3 });
        break;
      }
    }
  }

  // 일반 장애물
  {
    let x = 2250;
    while (x < MAP_LENGTH - 600) {
      const prog = clamp01(x / 75_000);
      x += lerp(theme.spacing[0], theme.spacing[1], prog) * rng.range(0.6, 1.3);
      if (nearChoke(x, 180) || nearObstacle(x, 135)) continue;
      const type = weightedPick(rng, theme.obstacles);
      const g = OBSTACLE_GEOM[type];
      const r = g.r;
      const amp = g.moving ? rng.range(20, 48) : 0;
      let tMax = -Infinity;
      let bMin = Infinity;
      for (let sx = x - r; sx <= x + r; sx += SEG) {
        const tb = terrainAt(map, sx);
        tMax = Math.max(tMax, tb.top);
        bMin = Math.min(bMin, tb.bottom);
      }
      if (bMin - tMax < 2 * r + 2 * amp + MIN_PASS + 6) continue;
      for (let tries = 0; tries < 6; tries++) {
        const y0 = rng.range(tMax + r + amp + 3, bMin - r - amp - 3);
        const above = y0 - amp - r - tMax;
        const below = bMin - (y0 + amp + r);
        if (Math.max(above, below) >= MIN_PASS) {
          const o = { id: oid++, type, x, y: y0, r, variant: rng.pick(g.variants) };
          if (g.moving) {
            o.amp = amp;
            o.period = rng.range(2.2, 4.0);
            o.phase = rng.range(0, Math.PI * 2);
          }
          map.obstacles.push(o);
          break;
        }
      }
    }
  }
  map.obstacles.sort((a, b) => a.x - b.x);

  const blocked = (x, y, pad) => {
    const tb = terrainAt(map, x);
    if (y < tb.top + pad || y > tb.bottom - pad) return true;
    for (const o of map.obstacles) {
      if (Math.abs(o.x - x) > 90) continue;
      if (o.type === 'bolt') {
        if (Math.abs(o.x - x) < 27) return true;
      } else if (o.type === 'mushroom') {
        if (Math.abs(o.x - x) < 45 && y > o.floorY - OBSTACLE_GEOM.mushroom.capTop - 21) return true;
      } else {
        const dy = Math.abs(y - o.y);
        if (Math.abs(o.x - x) < o.r + pad && dy < o.r + (o.amp || 0) + pad) return true;
      }
    }
    return false;
  };
  const centerAt = (x) => {
    const tb = terrainAt(map, x);
    return { c: (tb.top + tb.bottom) / 2, g: tb.bottom - tb.top };
  };

  // 보석
  {
    let gid = 0;
    let gx = 690;
    const addGem = (x, y, red) => {
      if (blocked(x, y, 18)) return;
      map.gems.push({ id: gid++, x, y, red });
    };
    while (gx < MAP_LENGTH - 300) {
      gx += rng.range(165, 330);
      if (rng.chance(0.3)) {
        const k = rng.int(3, 5);
        const off = rng.range(-0.25, 0.25);
        const arc = rng.range(12, 33) * (rng.chance(0.5) ? 1 : -1);
        for (let j = 0; j < k; j++) {
          const x = gx + j * 33;
          const { c: cc, g } = centerAt(x);
          addGem(x, cc + off * g - Math.sin((j / (k - 1)) * Math.PI) * arc, false);
        }
        gx += k * 33;
      } else {
        const { c: cc, g } = centerAt(gx);
        addGem(gx, cc + rng.range(-0.3, 0.3) * g, rng.chance(RULES.redGemChance));
      }
    }
  }

  // 회복 아이템과 깃털
  const placeSeries = (list, first, step, spread) => {
    let id = 0;
    let x = first;
    while (x < MAP_LENGTH - 450) {
      for (let tries = 0; tries < 10; tries++, x += 45) {
        const { c: cc, g } = centerAt(x);
        const y = cc + rng.range(-spread, spread) * g;
        if (!blocked(x, y, 21)) {
          list.push({ id: id++, x, y });
          break;
        }
      }
      x += rng.range(step[0], step[1]);
    }
  };
  const fm = RULES.foodEveryM.map((m) => m * RULES.pxPerMeter);
  placeSeries(map.foods, rng.range(fm[0], fm[1]), fm, 0.1);
  placeSeries(map.feathers, rng.range(6750, 9000), [7500, 10500], 0.25);

  // 기술 아이콘. 자리마다 1~5칸 중 하나가 정해지고, 각자 자기 캐릭터의 그 칸 기술로 보인다
  const sm = RULES.skillItemEveryM.map((m) => m * RULES.pxPerMeter);
  placeSeries(map.skills, rng.range(600, 900), sm, 0.28);
  const wsum = RULES.skillItemWeights.reduce((a, b) => a + b, 0);
  for (const s of map.skills) {
    let r = rng.range(0, wsum);
    s.slot = 1;
    for (let i = 0; i < RULES.skillItemWeights.length; i++) {
      if (r < RULES.skillItemWeights[i]) {
        s.slot = i + 1;
        break;
      }
      r -= RULES.skillItemWeights[i];
    }
  }

  return map;
}

export function terrainAt(map, x) {
  const f = x / map.seg;
  const n = map.top.length;
  if (f <= 0) return { top: map.top[0], bottom: map.bottom[0] };
  if (f >= n - 1) return { top: map.top[n - 1], bottom: map.bottom[n - 1] };
  const i = Math.floor(f);
  const t = f - i;
  return {
    top: map.top[i] + (map.top[i + 1] - map.top[i]) * t,
    bottom: map.bottom[i] + (map.bottom[i + 1] - map.bottom[i]) * t,
  };
}

export function circleHitsTerrain(map, x, y, r) {
  for (const dx of [-r * 0.7, 0, r * 0.7]) {
    const tb = terrainAt(map, x + dx);
    const rr = dx === 0 ? r : r * 0.7;
    if (y - rr < tb.top || y + rr > tb.bottom) return true;
  }
  return false;
}

export function obstacleY(o, t) {
  if (!o.amp) return o.y;
  return o.y + o.amp * Math.sin((Math.PI * 2 * t) / o.period + o.phase);
}

// 번개 기둥 상태: idle, warn, active
export function boltState(o, t) {
  if (t < 0) return 'idle';
  const local = (t + o.phase) % o.period;
  if (local >= o.period - o.active) return 'active';
  if (local >= o.period - o.active - o.warn) return 'warn';
  return 'idle';
}

// 원과 장애물 충돌. 결과: null, 'damage', 'bounce'
export function circleHitsObstacle(map, o, t, x, y, r) {
  if (o.type === 'bolt') {
    if (Math.abs(x - o.x) > OBSTACLE_GEOM.bolt.w / 2 + r) return null;
    return boltState(o, t) === 'active' ? 'damage' : null;
  }
  if (o.type === 'mushroom') {
    const g = OBSTACLE_GEOM.mushroom;
    const cap = rectCircle(o.x - g.capW / 2, o.floorY - g.capTop, g.capW, g.capTop - g.capBottom, x, y, r);
    const stem = rectCircle(o.x - g.stemW / 2, o.floorY - g.capBottom, g.stemW, g.capBottom, x, y, r);
    return cap || stem ? 'bounce' : null;
  }
  const oy = obstacleY(o, t);
  const dx = x - o.x;
  const dy = y - oy;
  const rr = r + o.r;
  return dx * dx + dy * dy < rr * rr ? 'damage' : null;
}

function rectCircle(rx, ry, rw, rh, cx, cy, r) {
  const nx = clamp(cx, rx, rx + rw);
  const ny = clamp(cy, ry, ry + rh);
  const dx = cx - nx;
  const dy = cy - ny;
  return dx * dx + dy * dy < r * r;
}
