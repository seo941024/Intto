// WebAudio로 합성하는 짧은 효과음. 음원 파일 없이 동작한다.
let ac = null;
let master = null;
let muted = false;
try {
  muted = localStorage.getItem('intto.muted') === '1';
} catch {}

function ctx() {
  if (!ac) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ac = new AC();
    master = ac.createGain();
    master.gain.value = muted ? 0 : 0.32;
    master.connect(ac.destination);
  }
  if (ac.state === 'suspended') ac.resume();
  return ac;
}

export function unlockAudio() {
  ctx();
}

export function toggleMute() {
  muted = !muted;
  try {
    localStorage.setItem('intto.muted', muted ? '1' : '0');
  } catch {}
  if (master) master.gain.value = muted ? 0 : 0.32;
  return muted;
}
export const isMuted = () => muted;

function tone(freq, dur, { type = 'square', vol = 0.5, slide = 0, delay = 0 } = {}) {
  const a = ctx();
  if (!a) return;
  const t = a.currentTime + delay;
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t);
  if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq + slide), t + dur);
  g.gain.setValueAtTime(vol, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + dur);
  o.connect(g).connect(master);
  o.start(t);
  o.stop(t + dur + 0.02);
}

function noise(dur, { vol = 0.4, freq = 1200, delay = 0, q = 1 } = {}) {
  const a = ctx();
  if (!a) return;
  const t = a.currentTime + delay;
  const len = Math.floor(a.sampleRate * dur);
  const buf = a.createBuffer(1, len, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const src = a.createBufferSource();
  src.buffer = buf;
  const f = a.createBiquadFilter();
  f.type = 'bandpass';
  f.frequency.value = freq;
  f.Q.value = q;
  const g = a.createGain();
  g.gain.setValueAtTime(vol, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + dur);
  src.connect(f).connect(g).connect(master);
  src.start(t);
}

export const sfx = {
  gem: () => {
    tone(988, 0.06, { vol: 0.25 });
    tone(1319, 0.09, { vol: 0.25, delay: 0.05 });
  },
  gemRed: () => [784, 988, 1175, 1568].forEach((f, i) => tone(f, 0.08, { vol: 0.22, delay: i * 0.045 })),
  food: () => tone(440, 0.12, { type: 'triangle', vol: 0.4, slide: 300 }),
  feather: () => tone(1046, 0.18, { type: 'sine', vol: 0.3, slide: 600 }),
  skill: () => noise(0.18, { vol: 0.35, freq: 1800, q: 0.7 }),
  shoot: () => tone(660, 0.08, { vol: 0.2, slide: -300 }),
  dash: () => noise(0.25, { vol: 0.4, freq: 900, q: 0.5 }),
  shield: () => tone(523, 0.25, { type: 'sine', vol: 0.3, slide: 520 }),
  heal: () => [523, 659, 784].forEach((f, i) => tone(f, 0.12, { type: 'triangle', vol: 0.3, delay: i * 0.07 })),
  hit: () => {
    noise(0.12, { vol: 0.5, freq: 400 });
    tone(150, 0.15, { vol: 0.35, slide: -80 });
  },
  bounce: () => tone(220, 0.2, { type: 'triangle', vol: 0.45, slide: 440 }),
  lifeLost: () => [440, 330, 220].forEach((f, i) => tone(f, 0.14, { vol: 0.35, delay: i * 0.1 })),
  ghost: () => tone(330, 0.6, { type: 'sine', vol: 0.3, slide: -200 }),
  revive: () => [392, 523, 659, 784].forEach((f, i) => tone(f, 0.1, { vol: 0.25, delay: i * 0.06 })),
  bolt: () => noise(0.35, { vol: 0.6, freq: 2500, q: 0.4 }),
  warn: () => tone(1200, 0.05, { vol: 0.15 }),
  nice: () => [1046, 1319].forEach((f, i) => tone(f, 0.12, { type: 'triangle', vol: 0.3, delay: i * 0.08 })),
  kill: () => [523, 784, 1046].forEach((f, i) => tone(f, 0.1, { vol: 0.3, delay: i * 0.06 })),
  count: () => tone(660, 0.12, { vol: 0.3 }),
  go: () => tone(1320, 0.3, { vol: 0.3 }),
  click: () => tone(880, 0.03, { vol: 0.15 }),
  end: () => [784, 659, 784, 1046].forEach((f, i) => tone(f, 0.14, { type: 'triangle', vol: 0.3, delay: i * 0.12 })),
};
