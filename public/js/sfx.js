// 인또 효과음. 패미컴·NES의 2A03 음원 칩을 흉내 내 WebAudio로 실시간 합성한다. 음원 파일은 쓰지 않는다.
//
// 칩에 있던 세 가지 소리만 쓴다.
//   펄스: 듀티 12.5% · 25% · 50% 사각파, 볼륨은 0~15 계단
//   삼각: 32계단 삼각파, 볼륨 없이 켜고 끄기만
//   노이즈: 15비트 LFSR, 쉬익 하는 긴 주기 모드와 금속성 짧은 주기 모드
// 효과음 하나는 옛 사운드 드라이버처럼 1/60초 프레임마다 음높이·볼륨·듀티를 적은 표다.
// 스윕만 실제 칩처럼 1/120초마다 타이머 주기를 바꾼다.

let ac = null;
let master = null;
let muted = false;
try {
  muted = localStorage.getItem('intto.muted') === '1';
} catch {}

const MASTER_VOL = 0.32;
const CPU = 1789773; // NTSC 2A03 클럭, 음높이 계산의 기준
const LEAD = 0.01; // 예약 여유, 초
const HARM = 128; // 펄스·삼각 파형에 담는 배음 수
// 채널별 최대 크기. 볼륨이 없는 삼각은 늘 최대로 울리므로 펄스보다 조금 낮춰 귀에 비슷하게 맞춘다
const LEVEL = { pulse: 0.3, tri: 0.26, noise: 0.31 };

function ctx() {
  if (!ac) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ac = new AC();
    master = ac.createGain();
    master.gain.value = muted ? 0 : MASTER_VOL;
    if (ac.createIIRFilter) {
      master.connect(outputFilter(ac, 'high', 90)).connect(outputFilter(ac, 'low', 14000)).connect(ac.destination);
    } else {
      master.connect(ac.destination);
    }
  }
  if (ac.state === 'suspended') ac.resume();
  return ac;
}

// NES 출력단과 같은 1차 필터. 90Hz 아래 울림과 14kHz 위 쇳소리를 부드럽게 깎는다
function outputFilter(a, type, fc) {
  const k = Math.tan((Math.PI * fc) / a.sampleRate);
  const ff = type === 'high' ? [1 / (1 + k), -1 / (1 + k)] : [k / (1 + k), k / (1 + k)];
  return a.createIIRFilter(ff, [1, (k - 1) / (k + 1)]);
}

export function unlockAudio() {
  const a = ctx();
  if (a) warm(a);
}

export function toggleMute() {
  muted = !muted;
  try {
    localStorage.setItem('intto.muted', muted ? '1' : '0');
  } catch {}
  if (master) master.gain.value = muted ? 0 : MASTER_VOL;
  return muted;
}
export const isMuted = () => muted;

// ── 파형 ──
const waves = new Map();

// 듀티 d 펄스파. 0과 1을 오가는 칩 파형의 푸리에 계수로 만들고, 정규화를 꺼서 듀티가 달라도 높낮이 폭이 같게 둔다
function pulseWave(a, d) {
  const key = 'p' + d;
  if (!waves.has(key)) {
    const re = new Float32Array(HARM);
    const im = new Float32Array(HARM);
    for (let n = 1; n < HARM; n++) {
      re[n] = Math.sin(2 * Math.PI * n * d) / (Math.PI * n);
      im[n] = (1 - Math.cos(2 * Math.PI * n * d)) / (Math.PI * n);
    }
    waves.set(key, a.createPeriodicWave(re, im, { disableNormalization: true }));
  }
  return waves.get(key);
}

// 15에서 0으로 내려갔다 다시 15로 오르는 32계단 삼각파. 계단이 만드는 특유의 거친 배음까지 계산에 넣는다
function triWave(a) {
  if (!waves.has('t')) {
    const re = new Float32Array(HARM);
    const im = new Float32Array(HARM);
    for (let j = 0; j < 32; j++) {
      const s = (j < 16 ? 15 - j : j - 16) / 15 - 0.5;
      const x0 = (2 * Math.PI * j) / 32;
      const x1 = (2 * Math.PI * (j + 1)) / 32;
      for (let n = 1; n < HARM; n++) {
        re[n] += (s * (Math.sin(n * x1) - Math.sin(n * x0))) / (Math.PI * n);
        im[n] += (s * (Math.cos(n * x0) - Math.cos(n * x1))) / (Math.PI * n);
      }
    }
    waves.set('t', a.createPeriodicWave(re, im, { disableNormalization: true }));
  }
  return waves.get('t');
}

// ── 노이즈 ──
// NTSC 노이즈 주기표. 번호가 클수록 LFSR이 느리게 돌아 낮고 거친 소리가 난다
const NOISE_PERIOD = [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068];
const noiseBufs = new Map();

// 주기 번호와 모드마다 LFSR 출력을 작은 버퍼에 한 번만 구워 두고 반복 재생한다.
// 긴 모드는 0번과 1번 비트, 짧은 모드는 0번과 6번 비트를 XOR해 되먹이고, 0번 비트가 0일 때만 소리가 난다.
// 한 샘플 동안 LFSR이 여러 번 움직이면 그 사이 출력을 평균 내 칩 소리를 고르게 옮긴다
function noiseBuf(a, idx, short) {
  const key = (short ? 's' : 'l') + idx;
  let buf = noiseBufs.get(key);
  if (buf) return buf;
  const rate = a.sampleRate;
  const clock = CPU / NOISE_PERIOD[idx];
  const per = clock / rate;
  const cycleSec = (short ? 93 : 32767) / clock;
  // 한 바퀴를 여러 번 담아 이음매 없이 돌게 하고, 한 바퀴가 1초를 넘으면 1초에서 자른다
  const sec = cycleSec >= 1 ? 1 : cycleSec * Math.ceil(0.25 / cycleSec);
  const len = Math.max(1, Math.round(sec * rate));
  buf = a.createBuffer(1, len, rate);
  const d = buf.getChannelData(0);
  const tap = short ? 6 : 1;
  let reg = 1;
  let phase = 0;
  let sum = 0;
  for (let i = 0; i < len; i++) {
    let left = per;
    let on = 0;
    while (left > 1e-9) {
      const take = Math.min(left, 1 - phase);
      if (!(reg & 1)) on += take;
      phase += take;
      left -= take;
      if (phase >= 1 - 1e-9) {
        phase = 0;
        reg = (reg >> 1) | (((reg ^ (reg >> tap)) & 1) << 14);
      }
    }
    d[i] = on / per;
    sum += d[i];
  }
  const mean = sum / len;
  for (let i = 0; i < len; i++) d[i] -= mean;
  noiseBufs.set(key, buf);
  return buf;
}

// ── 표 만들기 도우미 ──
// 'C4'가 가온 도. 'F#5' · 'Bb3' 같은 음 이름을 주파수로 바꾼다. 숫자는 그대로 둔다
const SEMI = { C: -9, D: -7, E: -5, F: -4, G: -2, A: 0, B: 2 };
function hz(note) {
  if (typeof note === 'number') return note;
  const [, l, acc, oct] = /^([A-G])([#b]?)(\d)$/.exec(note);
  return 440 * 2 ** ((SEMI[l] + (acc === '#') - (acc === 'b') + (oct - 4) * 12) / 12);
}

// 채널 한 줄. 칸 = [주파수, 볼륨 0~15, 듀티], 노이즈 칸 = [주기 번호, 볼륨, 짧은 모드].
// at은 시작 프레임, rate는 1초에 넘기는 칸 수. 삼각은 볼륨 자리에 1을 적으면 켜진다
const pulse = (steps, at = 0, rate = 60) => ({ ch: 'pulse', steps, at, rate });
const tri = (steps, at = 0, rate = 60) => ({ ch: 'tri', steps, at, rate });
const noise = (steps, at = 0) => ({ ch: 'noise', steps, at, rate: 60 });

// 한 음을 볼륨 표 길이만큼 낸다
const hold = (note, vols, duty = 0.5) => vols.map((v) => [hz(note), v, duty]);

// 끊어 치는 음. 마지막 프레임을 비워 다음 음과 사이를 띄운다
const blip = (note, len, vol, duty = 0.5) => [...hold(note, Array(len - 1).fill(vol), duty), [0, 0, duty]];

// 아르페지오. 음마다 len 프레임씩 빠르게 넘긴다
const arp = (notes, len, vol, duty = 0.5) => notes.flatMap((n) => hold(n, Array(len).fill(vol), duty));

// 두 음을 every 칸마다 번갈아 떠는 트릴
const trill = (a, b, vols, every = 1, duty = 0.5) => vols.map((v, i) => [hz(Math.floor(i / every) % 2 ? b : a), v, duty]);

// 계단 감쇠. from에서 1까지 every 프레임마다 한 칸씩 줄인다
const decay = (from, every = 1) => Array.from({ length: from * every }, (_, i) => from - Math.floor(i / every));

// 듀티를 12.5%와 25%로 every 칸마다 번갈아 바꿔 소리를 일렁이게 한다
const shimmer = (steps, every = 1) => steps.map(([f, v], i) => [f, v, Math.floor(i / every) % 2 ? 0.25 : 0.125]);

// NES 스윕 유닛. 반프레임마다 타이머 주기를 주기 >> shift 만큼 줄이거나 늘린다. up이면 음이 오른다.
// 칩이 낼 수 없는 범위로 나가면 그 칸부터 소리를 끈다
function sweep(note, shift, up, count, isTri = false) {
  const k = isTri ? 32 : 16;
  let t = Math.round(CPU / (k * hz(note)) - 1);
  const out = [];
  for (let i = 0; i < count; i++) {
    out.push(t >= 8 && t <= 2047 ? CPU / (k * (t + 1)) : 0);
    t += (up ? -1 : 1) * (t >> shift);
  }
  return out;
}

// 1/120초 칸의 스윕 음높이에 프레임 단위 볼륨·듀티 표를 입힌다. 볼륨 표가 끝나면 소리를 끈다
const swept = (freqs, vols, duty = 0.5) =>
  freqs.map((f, i) => [f, vols[i >> 1] ?? 0, Array.isArray(duty) ? duty[Math.min(i >> 1, duty.length - 1)] : duty]);

// 비브라토. delay 칸 뒤부터 period 칸 주기로 음높이를 ±cents만큼 흔든다. 칩 주기로 맞추면 계단처럼 떨린다
const vibrato = (steps, cents, period, delay = 0) =>
  steps.map(([f, v, d], i) =>
    i < delay || !f ? [f, v, d] : [f * 2 ** ((cents / 1200) * Math.sin((2 * Math.PI * (i - delay)) / period)), v, d],
  );

// 메아리. 같은 줄을 frames 프레임 늦게, 볼륨을 줄여 남는 펄스 채널로 한 번 더 낸다
const echo = (track, frames = 3, keep = 0.4, duty) => ({
  ...track,
  at: track.at + frames,
  steps: track.steps.map(([f, v, d]) => [f, Math.round(v * keep), duty ?? d]),
});

// 노이즈 표. idx가 배열이면 프레임마다 주기 번호를 바꾸고, 짧으면 마지막 번호를 끝까지 쓴다
const nz = (idx, vols, short = false) =>
  vols.map((v, i) => [Array.isArray(idx) ? idx[Math.min(i, idx.length - 1)] : idx, v, short]);

// ── 효과음 표 ──
const SOUNDS = {
  // 파란 보석: 동전처럼 한 단 뛰어올라 맑게 사라진다. 50%에서 25% 듀티로 바꿔 끝을 가늘게
  gem: () => [pulse([...hold('B5', [10, 10]), ...hold('E6', [10, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1], 0.25)])],

  // 빨간 보석: 두 옥타브를 훑는 빠른 아르페지오 뒤 반짝이는 트릴, 메아리로 넓게
  gemRed: () => {
    const lead = pulse([
      ...arp(['G5', 'B5', 'D6', 'G6', 'B6', 'D7'], 2, 11, 0.125),
      ...trill('G6', 'D7', [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1], 2, 0.25),
    ]);
    return [lead, echo(lead, 3, 0.4, 0.5)];
  },

  // 고기: 삼각파로 냠냠 두 번 베어 물고, 밝은 장화음으로 회복을 알린다
  food: () => {
    const bite = arp(['A4', 'E4', 'A3'], 1, 1);
    return [
      tri([...bite, [0, 0], [0, 0], ...bite]),
      noise(nz(6, [5, 2, 0, 0, 0, 5, 2])),
      pulse([...arp(['C6', 'E6', 'G6'], 2, 10), ...hold('C7', [9, 7, 5, 3, 1], 0.25)], 8),
    ];
  },

  // 깃털: 12.5% 펄스가 온음 음계를 한 프레임씩 날아오르고, 높은 쉬익 소리와 메아리로 가볍게
  feather: () => {
    const lead = pulse([
      ...arp(['C6', 'D6', 'E6', 'F#6', 'G#6', 'A#6', 'C7', 'D7'], 1, 11, 0.125),
      ...hold('D7', [10, 8, 6, 4, 2, 1], 0.125),
    ]);
    return [lead, echo(lead, 3, 0.4, 0.25), noise(nz(0, [3, 4, 4, 3, 3, 2, 1, 1]))];
  },

  // 스킬 사용: 짧게 솟구치는 스윕에 금속성 노이즈 한 번. 모든 스킬에 함께 나므로 짧게, 듀티를 점점 가늘게
  skill: () => [
    pulse(swept(sweep('E5', 4, true, 14), [11, 11, 10, 9, 7, 5, 3], [0.5, 0.5, 0.25, 0.25, 0.25, 0.125]), 0, 120),
    noise(nz(4, [6, 3, 1], true)),
  ],

  // 발사: 높은 곳에서 빠르게 떨어지는 스윕, 듀티를 줄여 꼬리를 가늘게 하고 12.5% 메아리를 붙인다
  shoot: () => {
    const zap = pulse(swept(sweep('C7', 3, false, 14), [12, 12, 11, 10, 9, 7, 5], [0.5, 0.5, 0.25]), 0, 120);
    return [zap, echo(zap, 2, 0.35, 0.125), noise(nz(2, [6, 3]))];
  },

  // 대시: 밝은 쉬익에서 어둡게 가라앉는 노이즈 바람과 위로 치솟는 가는 펄스 스윕
  dash: () => [
    noise(nz([3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9], [10, 12, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1])),
    pulse(swept(sweep('C4', 4, true, 16), [9, 9, 8, 8, 7, 6, 5, 4], 0.125), 0, 120),
  ],

  // 보호막: 켤 때와 막아 낼 때 함께 쓴다. 금속성 '팅' 위로 듀티를 번갈아 바꾸며 오르는 스윕, 끝은 떨며 사라지고 메아리가 따른다
  shield: () => {
    const rise = sweep('C5', 4, true, 12);
    const up = pulse(shimmer(swept(rise, [11, 11, 11, 11, 11, 11]), 2), 0, 120);
    const ring = pulse(shimmer(vibrato(hold(rise.at(-1), [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]), 30, 4)), 6);
    return [up, ring, echo(up, 3, 0.4, 0.5), echo(ring, 3, 0.4, 0.5), noise(nz(1, [7, 5, 3, 1], true))];
  },

  // 자가수리: 장조 아르페지오를 세 번 굴리며 한 단씩 오르고, 떨리는 끝음과 메아리
  heal: () => {
    const lead = pulse([
      ...arp(['C5', 'E5', 'G5', 'C6'], 2, 10, 0.25),
      ...arp(['E5', 'G5', 'C6', 'E6'], 2, 10, 0.25),
      ...arp(['G5', 'C6', 'E6', 'G6'], 2, 10, 0.25),
      ...vibrato(hold('G6', [9, 8, 7, 6, 5, 4, 3, 2, 1]), 25, 8, 2),
    ]);
    return [lead, echo(lead, 3, 0.35, 0.125)];
  },

  // 피격: 거칠게 낮아지는 노이즈와 곤두박질치는 펄스 스윕, 듀티를 매 프레임 바꿔 지직거리게
  hit: () => [
    noise(nz([6, 8, 10, 11, 12, 12, 13], [12, 11, 10, 8, 6, 4, 2])),
    pulse(swept(sweep('A4', 2, false, 12), [11, 10, 8, 6, 4, 2], [0.5, 0.25, 0.5, 0.25, 0.5, 0.25]), 0, 120),
  ],

  // 버섯 튕기기: 낮은 곳에서 휘어 오르는 '뾰잉' 스윕에 떨림을 넣고 듀티를 점점 가늘게, 삼각파가 몸통을 받친다
  bounce: () => [
    pulse(
      vibrato(swept(sweep('G3', 4, true, 18), [11, 11, 10, 10, 9, 8, 7, 6, 5], [0.5, 0.5, 0.5, 0.25, 0.25, 0.25, 0.125]), 40, 6),
      0,
      120,
    ),
    tri(swept(sweep('G2', 4, true, 12, true), [1, 1, 1, 1, 1, 1]), 0, 120),
  ],

  // 생명 하나 잃기: 반음씩 처지는 세 음, 떨리는 끝음이 스윕으로 주저앉는다. 삼각파가 같은 길을 낮게 따라간다
  lifeLost: () => [
    pulse([...hold('G5', [11, 11, 10, 9, 8, 0]), ...hold('F#5', [11, 11, 10, 9, 8, 0]), ...hold('F5', [11, 11, 10, 9, 8, 0])]),
    pulse(vibrato(hold('E5', [11, 11, 10, 10, 10, 9, 9, 9], 0.25), 30, 6, 2), 18),
    pulse(swept(sweep('E5', 4, false, 16), [8, 7, 6, 5, 4, 3, 2, 1], 0.25), 26, 120),
    tri([...blip('G3', 6, 1), ...blip('F#3', 6, 1), ...blip('F3', 6, 1), ...hold('E3', Array(12).fill(1))]),
  ],

  // 탈락해 유령이 됨: 삼각파가 뚝 떨어진 뒤, 가는 펄스가 크게 떨며 길게 가라앉고 메아리가 뒤따른다
  ghost: () => {
    const wail = pulse(vibrato(swept(sweep('E5', 6, false, 108), decay(12, 4), 0.125), 50, 12), 2, 120);
    return [tri(swept(sweep('E4', 3, false, 12, true), [1, 1, 1, 1, 1, 1]), 0, 120), wail, echo(wail, 6, 0.4, 0.25)];
  },

  // 번개 맞음: 금속성 '딱'으로 갈라진 뒤 밝은 노이즈가 점점 어둡게 우르르 잦아든다. 가는 펄스 지직임과 삼각파 쿵을 겹친다
  bolt: () => [
    noise([
      ...nz(3, [14, 12], true),
      ...nz([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14], [13, 12, 11, 10, 9, 9, 8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1, 1]),
    ]),
    pulse(swept(sweep('C7', 2, false, 10), [12, 10, 8, 6, 4], 0.125), 0, 120),
    tri(swept(sweep('C3', 3, false, 16, true), [1, 1, 1, 1, 1, 1, 1, 1]), 0, 120),
  ],

  // 번개 예고: 아주 작고 짧은 '틱'. 여러 번 울려도 거슬리지 않게
  warn: () => [pulse([...hold('B6', [6], 0.25), ...hold('B6', [4, 2], 0.125)])],

  // 좁은 틈 통과: 12.5% 펄스가 장화음을 한 프레임씩 두 번 훑고 맑게 울린 뒤 메아리
  nice: () => {
    const lead = pulse([
      ...arp(['B5', 'D#6', 'F#6', 'B6', 'B5', 'D#6', 'F#6', 'B6'], 1, 10, 0.125),
      ...hold('B6', [9, 8, 7, 6, 5, 4, 3, 2, 1], 0.25),
    ]);
    return [lead, echo(lead, 4, 0.4, 0.5)];
  },

  // 상대 탈락시킴: 노이즈 스네어와 삼각파 베이스 위로 '따따 따안' 팡파르, 끝음은 떨며 길게
  kill: () => {
    const lead = pulse([
      ...hold('G5', [9, 9, 6, 0], 0.25),
      ...hold('G5', [9, 9, 6, 0], 0.25),
      ...vibrato(hold('C6', [10, 10, 10, 9, 9, 8, 8, 7, 6, 5, 4, 3, 2, 1]), 25, 8, 5),
    ]);
    return [
      lead,
      echo(lead, 3, 0.35, 0.125),
      tri([...blip('G3', 4, 1), ...blip('G3', 4, 1), ...hold('C4', Array(10).fill(1))]),
      noise(nz([4, 6, 7, 8], [8, 6, 3, 1])),
      noise(nz([4, 6, 7, 8, 9], [9, 7, 4, 2, 1]), 8),
    ];
  },

  // 카운트다운 3·2·1: 꾸밈 없는 50% 펄스 '삐'와 한 옥타브 아래 삼각파
  count: () => [pulse(hold('A4', [11, 11, 11, 11, 10, 10, 9, 9, 7, 5, 3, 1])), tri(hold('A3', Array(8).fill(1)))],

  // 출발: 한 옥타브 높은 '삐이'를 길게. 노이즈 심벌을 치고, 듀티를 25%로 바꾼 뒤 떨림을 넣는다
  go: () => [
    pulse(
      vibrato(
        [...hold('A5', Array(6).fill(11)), ...hold('A5', [10, 10, 10, 10, 9, 9, 9, 8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 1], 0.25)],
        20,
        8,
        10,
      ),
    ),
    tri(hold('A4', Array(10).fill(1))),
    noise(nz([1, 2, 3, 4, 5], [7, 6, 5, 4, 3, 2, 1])),
  ],

  // 버튼 누름: 아주 작고 부드러운 두 프레임짜리 '톡'
  click: () => [pulse(hold('E6', [4, 2]))],

  // 레이스 끝: 도·솔·도·미·솔로 올라 높은 도에서 떨며 맺는 짧은 승리 징글. 12.5% 메아리, 삼각파 베이스, 노이즈 스네어
  end: () => {
    const lead = pulse([
      ...blip('C5', 6, 10, 0.25),
      ...blip('G4', 3, 10, 0.25),
      ...blip('C5', 3, 10, 0.25),
      ...blip('E5', 6, 10, 0.25),
      ...blip('G5', 6, 10, 0.25),
      ...blip('E5', 3, 10, 0.25),
      ...blip('G5', 3, 10, 0.25),
      ...vibrato(hold('C6', [11, 11, 11, 11, 11, 11, 10, 10, 9, 9, 8, 8, 7, 7, 6, 5, 4, 3, 2, 1]), 25, 8, 6),
    ]);
    const snare = nz([5, 7, 9], [7, 4, 2]);
    return [
      lead,
      echo(lead, 2, 0.4, 0.125),
      tri([...blip('C3', 6, 1), ...blip('G3', 6, 1), ...blip('C3', 6, 1), ...blip('E3', 6, 1), ...blip('G3', 6, 1), ...hold('C3', Array(14).fill(1))]),
      noise(snare, 0),
      noise(snare, 12),
      noise(snare, 24),
      noise(nz([3, 5, 7, 9], [8, 6, 3, 1]), 30),
    ];
  },
};

// ── 재생 ──
// 표의 음높이를 칩 타이머 주기로 맞춘다. 실제 NES처럼 높은 음일수록 살짝 어긋나고, 낼 수 없는 음은 끈다
function finalize(tr) {
  const out = { ...tr, at: tr.at / 60 };
  if (tr.ch === 'noise') return out;
  const k = tr.ch === 'tri' ? 32 : 16;
  out.steps = tr.steps.map(([f, v, d = 0.5]) => {
    const t = f > 0 ? Math.round(CPU / (k * f) - 1) : -1;
    return t >= 8 && t <= 2047 && v > 0 ? [CPU / (k * (t + 1)), v | 0, d] : [0, 0, d];
  });
  return out;
}

// 표는 효과음마다 처음 한 번만 만들어 둔다
const built = new Map();
function tracksOf(name) {
  let tracks = built.get(name);
  if (!tracks) {
    tracks = SOUNDS[name]().map(finalize);
    built.set(name, tracks);
  }
  return tracks;
}

// 파형과 노이즈 버퍼를 미리 구워 첫 재생 때 끊기지 않게 한다
function warm(a) {
  pulseWave(a, 0.125);
  pulseWave(a, 0.25);
  pulseWave(a, 0.5);
  triWave(a);
  for (const name of Object.keys(SOUNDS)) {
    for (const tr of tracksOf(name)) {
      if (tr.ch === 'noise') for (const [idx, v, short] of tr.steps) if (v > 0) noiseBuf(a, idx, short);
    }
  }
}

// 펄스·삼각 한 줄. 듀티마다 오실레이터를 하나씩 두고 칸마다 소리 낼 쪽만 켠다.
// 모두 같은 음높이·같은 위상으로 돌기 때문에 칩에서 듀티를 바로 바꾼 것처럼 들린다
function playTone(a, tr, t0, nodes) {
  const isTri = tr.ch === 'tri';
  const dt = 1 / tr.rate;
  const start = t0 + tr.at;
  const end = start + tr.steps.length * dt;
  const voices = new Map();
  for (const [, , d] of tr.steps) {
    const key = isTri ? 't' : d;
    if (voices.has(key)) continue;
    const osc = a.createOscillator();
    osc.setPeriodicWave(isTri ? triWave(a) : pulseWave(a, d));
    const gain = a.createGain();
    gain.gain.value = 0;
    osc.connect(gain).connect(master);
    voices.set(key, { osc, gain, lv: 0 });
  }
  let lastF = 0;
  tr.steps.forEach(([f, v, d], i) => {
    const t = start + i * dt;
    if (f && f !== lastF) {
      for (const x of voices.values()) x.osc.frequency.setValueAtTime(f, t);
      lastF = f;
    }
    for (const [key, x] of voices) {
      const lv = f && (isTri || key === d) ? (isTri ? LEVEL.tri : (v / 15) * LEVEL.pulse) : 0;
      if (lv !== x.lv) {
        x.gain.gain.setValueAtTime(lv, t);
        x.lv = lv;
      }
    }
  });
  for (const x of voices.values()) {
    x.gain.gain.setValueAtTime(0, end);
    x.osc.start(start);
    x.osc.stop(end + 0.01);
    x.osc.onended = () => x.gain.disconnect();
    nodes.push({ src: x.osc, gain: x.gain });
  }
  return end;
}

// 노이즈 한 줄. 볼륨은 프레임마다 계단으로 바꾸고, 주기 번호나 모드가 바뀌는 곳마다 구워 둔 버퍼를 갈아 끼운다
function playNoise(a, tr, t0, nodes) {
  const dt = 1 / 60;
  const steps = tr.steps;
  const start = t0 + tr.at;
  const end = start + steps.length * dt;
  const gain = a.createGain();
  gain.gain.value = 0;
  gain.connect(master);
  let lv = 0;
  steps.forEach(([, v], i) => {
    const next = (v / 15) * LEVEL.noise;
    if (next !== lv) {
      gain.gain.setValueAtTime(next, start + i * dt);
      lv = next;
    }
  });
  gain.gain.setValueAtTime(0, end);
  let last = null;
  for (let i = 0; i < steps.length; ) {
    const [idx, , short] = steps[i];
    let j = i + 1;
    let loud = steps[i][1] > 0;
    while (j < steps.length && steps[j][0] === idx && steps[j][2] === short) {
      if (steps[j][1] > 0) loud = true;
      j++;
    }
    if (loud) {
      const src = a.createBufferSource();
      src.buffer = noiseBuf(a, idx, short);
      src.loop = true;
      src.connect(gain);
      src.start(start + i * dt, Math.random() * src.buffer.duration);
      src.stop(start + j * dt);
      nodes.push({ src, gain });
      last = src;
    }
    i = j;
  }
  if (last) last.onended = () => gain.disconnect();
  else gain.disconnect();
  return end;
}

// 칩의 효과음 채널처럼 같은 효과음은 한 줄만 울린다. 다시 부르면 앞 소리를 끊고 처음부터 낸다.
// 한꺼번에 여러 발 쏘는 스킬도 소리가 겹쳐 커지지 않는다
const playing = new Map();
function cut(prev, t) {
  for (const { src, gain } of prev.nodes) {
    gain.gain.cancelScheduledValues(t);
    gain.gain.setValueAtTime(0, t);
    try {
      src.stop(t);
    } catch {}
  }
}

function play(name) {
  const a = ctx();
  if (!a || muted) return;
  const t0 = a.currentTime + LEAD;
  const prev = playing.get(name);
  if (prev && prev.end > t0) cut(prev, t0);
  const nodes = [];
  let end = t0;
  for (const tr of tracksOf(name)) {
    end = Math.max(end, (tr.ch === 'noise' ? playNoise : playTone)(a, tr, t0, nodes));
  }
  playing.set(name, { nodes, end });
}

export const sfx = Object.fromEntries(Object.keys(SOUNDS).map((name) => [name, () => play(name)]));
