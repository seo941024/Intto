// 배경음. 화면마다 곡 하나를 끊김 없이 되풀이한다.
// <audio> 둘을 번갈아 쓴다. 곡 끝 직전에 다음 회차를 처음부터 겹쳐 틀어 소리를 넘기고, 곡을 바꿀 때도 서로 줄이고 키운다.
// 곡 목록과 음량 보정은 tools/make_music.py가 만든 /assets/music/music.json
const VOL = 0.4; // 배경음 크기. 효과음보다 작게 깐다
const XFADE = 2; // 곡 끝과 처음을 겹치는 길이, 초
const SWITCH = 0.8; // 다른 곡으로 넘어갈 때 줄이고 키우는 길이, 초

let spec = null;
let ext = 'ogg';
let muted = false;
let want = null; // 지금 틀어야 할 곡 이름
let main = null; // 지금 곡을 이끄는 소리
const voices = new Set(); // 소리를 내는 중인 <audio>와 그 줄이고 키우기 상태
let timer = 0;
let waitingGesture = false;

const now = () => performance.now() / 1000;

function level(v) {
  const t = Math.min(1, (now() - v.t0) / v.dur);
  return v.from + (v.to - v.from) * t;
}

function apply(v) {
  const g = spec?.[v.name]?.gain ?? 1;
  v.el.volume = Math.max(0, Math.min(1, level(v) * VOL * g));
  v.el.muted = muted;
}

function fade(v, to, dur) {
  v.from = level(v);
  v.to = to;
  v.t0 = now();
  v.dur = Math.max(0.01, dur);
}

// 처음 화면을 누르기 전에는 브라우저가 소리 재생을 막는다. 막히면 첫 클릭이나 키 입력 때 다시 튼다
function start(v) {
  const p = v.el.play();
  if (p && p.catch) {
    p.catch(() => {
      if (waitingGesture) return;
      waitingGesture = true;
      const retry = () => {
        waitingGesture = false;
        window.removeEventListener('pointerdown', retry, true);
        window.removeEventListener('keydown', retry, true);
        for (const w of voices) if (w.el.paused) w.el.play().catch(() => {});
      };
      window.addEventListener('pointerdown', retry, true);
      window.addEventListener('keydown', retry, true);
    });
  }
}

function voice(name, fadeIn) {
  const el = new Audio(`/assets/music/${name}.${ext}`);
  el.preload = 'auto';
  const v = { el, name, from: 0, to: 1, t0: now(), dur: fadeIn, ending: false };
  apply(v);
  voices.add(v);
  start(v);
  return v;
}

function stop(v, dur) {
  fade(v, 0, dur);
  v.ending = true;
}

function tick() {
  for (const v of [...voices]) {
    apply(v);
    if (v.ending && level(v) <= 0.001 && now() - v.t0 >= v.dur) {
      v.el.pause();
      v.el.removeAttribute('src');
      v.el.load();
      voices.delete(v);
    }
  }
  // 곡 끝 XFADE초 전에 같은 곡을 처음부터 겹쳐 튼다
  const end = main && spec?.[main.name]?.end;
  if (main && end && !main.ending && main.el.currentTime >= end - XFADE) {
    const old = main;
    stop(old, XFADE);
    main = voice(old.name, XFADE);
  }
}

function play(name) {
  want = name;
  if (!spec) return;
  if (!name || !spec[name]) {
    if (main) stop(main, SWITCH);
    main = null;
    return;
  }
  if (main && main.name === name) return;
  if (main) stop(main, SWITCH);
  main = voice(name, SWITCH);
}

async function init() {
  const probe = document.createElement('audio');
  ext = probe.canPlayType('audio/ogg; codecs="vorbis"') ? 'ogg' : 'mp3';
  try {
    spec = await (await fetch('/assets/music/music.json', { cache: 'no-cache' })).json();
  } catch {
    spec = {};
  }
  if (!timer) timer = setInterval(tick, 100);
  if (want) play(want);
}

function setMuted(m) {
  muted = m;
  for (const v of voices) apply(v);
}

export const music = { init, play, setMuted };
