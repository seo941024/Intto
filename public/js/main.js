// 화면 전환, 로비·방 UI, 레이스 시작과 결과
import { socket, request, syncClock } from './net.js';
import { ART, loadCommonArt, loadWorld, loadImage } from './assets.js';
import { CHARACTERS, CHARACTER_BY_ID, SKILLS, STAT_LABELS } from '/shared/characters.js';
import { MAPS, MAP_BY_ID } from '/shared/mapgen.js';
import { RULES, PLAYER_COLORS } from '/shared/rules.js';
import { Game } from './game.js';
import { TitleScene } from './title.js';
import { sfx, unlockAudio, toggleMute, isMuted } from './sfx.js';
import { music } from './music.js';

const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

const S = {
  myId: null,
  name: '',
  rooms: [],
  room: null,
  game: null,
  build: null,
  pickedChar: 'mongsil',
  viewChar: 'mongsil',
  screen: 'title',
};

const store = {
  get: (k) => {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set: (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch {}
  },
};

// ── 공용 ──
function show(id) {
  S.screen = id;
  if (id === 'title') titleScene.start();
  else titleScene.stop();
  // 배경음: 첫 화면은 첫 화면 곡, 로비와 대기실은 로비 곡. 경기 곡은 startRace에서 맵에 맞춰 튼다
  if (id === 'title') music.play('title');
  else if (id === 'lobby' || id === 'room') music.play('lobby');
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === 'scr-' + id));
}

let toastTimer = 0;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// 아틀라스 한 프레임을 담은 canvas. scale은 경기 화면 1픽셀을 화면에 몇 CSS 픽셀로 보일지다.
// 그림 해상도가 달라도 같은 크기로 보이고, 화면 배율만큼 촘촘히 그려 큰 그림은 매끄럽게 줄이고 작은 도트는 계단 그대로 키운다
function atlasCanvas(atlas, name, scale = 1, opt = {}) {
  const c = document.createElement('canvas');
  const f = atlas && atlas.frame(name, 0, opt.index ?? 0);
  if (!f) {
    c.width = c.height = 1;
    return c;
  }
  const cw = Math.round(f.sw * atlas.k * scale);
  const ch = Math.round(f.sh * atlas.k * scale);
  const dpr = window.devicePixelRatio || 1;
  c.width = Math.max(1, Math.round(cw * dpr));
  c.height = Math.max(1, Math.round(ch * dpr));
  const ctx = c.getContext('2d');
  ctx.imageSmoothingEnabled = c.width < f.sw;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(atlas.img, f.sx, f.sy, f.sw, f.sh, 0, 0, c.width, c.height);
  c.style.width = cw + 'px';
  c.style.height = ch + 'px';
  if (c.width < f.sw) c.style.imageRendering = 'auto';
  return c;
}

function portrait(charId) {
  const img = el('img', 'portrait');
  img.src = `/assets/characters/${charId === 'random' ? 'random' : charId}/portrait.png`;
  img.alt = charId === 'random' ? '랜덤' : CHARACTER_BY_ID[charId]?.name ?? '';
  return img;
}

function pips(value) {
  const box = el('span', 'pips');
  box.style.display = 'inline-flex';
  box.style.gap = '2px';
  for (let i = 1; i <= 5; i++) {
    const name = value >= i ? 'pipFull' : value >= i - 0.5 ? 'pipHalf' : 'pipEmpty';
    box.append(atlasCanvas(ART.ui, name, 4 / 3));
  }
  return box;
}

// 로고 같은 단독 PNG를 정수배로 키운다. 그림이 없으면 글자 로고로 바꾼다
function scaleImages() {
  for (const [sel, k] of [['.logo', 2], ['.logo-sm', 0.5]]) {
    document.querySelectorAll(sel).forEach((img) => {
      const apply = () => {
        img.style.width = img.naturalWidth * k + 'px';
        img.style.height = img.naturalHeight * k + 'px';
      };
      const fail = () => {
        const t = el('span', `${img.className} logo-text`, '인또');
        img.replaceWith(t);
      };
      if (img.complete) img.naturalWidth ? apply() : fail();
      else {
        img.addEventListener('load', apply, { once: true });
        img.addEventListener('error', fail, { once: true });
      }
    });
  }
}

// 테두리 PNG를 읽을 수 있으면 대체 스타일을 끈다
async function checkUiArt() {
  const ok = await loadImage('/assets/ui/button.png');
  document.body.classList.toggle('no-ui-art', !ok);
}

// ── 첫 화면 ──
function initTitle() {
  const saved = store.get('intto.name');
  $('#in-name').value = saved || '';
  const enter = async () => {
    unlockAudio();
    const name = $('#in-name').value.trim().slice(0, 10);
    const res = await request('hello', { name });
    if (!res || !res.id) return toast('서버에 연결되지 않음');
    S.myId = res.id;
    S.name = res.name;
    store.set('intto.name', res.name);
    $('#lobby-me').textContent = res.name;
    sfx.click();
    show('lobby');
  };
  $('#btn-enter').onclick = enter;
  $('#in-name').addEventListener('keydown', (e) => e.key === 'Enter' && enter());
  // 로비에서 처음 화면으로. 이름은 칸에 그대로 남아 바로 다시 들어올 수 있다
  $('#btn-home').onclick = () => {
    sfx.click();
    $('#in-name').value = S.name || store.get('intto.name') || '';
    show('title');
  };
  titleScene.start();
  music.play('title');
}

const titleScene = new TitleScene($('#title-canvas'));

// ── 로비 ──
const KEY_LABELS = {
  keyMouseL: '좌클릭', keyMouseR: '우클릭', keyUp: '↑', keyZ: 'Z', keyX: 'X',
  keyEnter: 'Enter', keyM: 'M',
};

function initLobby() {
  $('#btn-create').onclick = async () => {
    sfx.click();
    const res = await request('room:create', { title: $('#in-room-title').value });
    if (!res.ok) toast(res.error);
  };
  $('#btn-quick').onclick = async () => {
    sfx.click();
    const res = await request('room:quick', {});
    if (!res.ok) toast(res.error);
  };
  const keys = [
    [['keyMouseL', 'keyUp'], '누르는 동안 상승, 떼면 하강'],
    [['keyX'], '누르는 동안 가속'],
    [['keyMouseR', 'keyZ'], '현재 칸 기술 사용'],
    [['keyEnter'], '채팅'],
    [['keyM'], '소리 끄기·켜기'],
  ];
  const ul = $('#help-keys');
  ul.innerHTML = '';
  for (const [caps, desc] of keys) {
    const li = el('li');
    const c = el('span', 'caps');
    for (const k of caps) {
      if (ART.fx.has(k)) c.append(atlasCanvas(ART.fx, k, 4 / 3));
      else c.append(el('span', 'cap-text', KEY_LABELS[k]));
    }
    li.append(c, el('span', '', desc));
    ul.append(li);
  }
}

function renderRooms() {
  const ul = $('#room-list');
  ul.innerHTML = '';
  if (!S.rooms.length) {
    ul.append(el('li', 'empty', '열린 방이 없음'));
    return;
  }
  for (const r of S.rooms) {
    const li = el('li', 'card');
    li.append(
      el('span', 'no', `#${r.id}`),
      el('span', 'title', r.title),
      el('span', '', MAP_BY_ID[r.mapId]?.name ?? '랜덤 맵'),
      el('span', '', `${r.count}/${r.max}`),
      el('span', 'tag' + (r.state === 'playing' ? ' playing' : ''), r.state === 'playing' ? '게임 중' : r.mode === 'team' ? '팀전' : '개인전'),
    );
    li.onclick = async () => {
      sfx.click();
      const res = await request('room:join', { roomId: r.id });
      if (!res.ok) toast(res.error);
    };
    ul.append(li);
  }
}

// ── 방 ──
function initRoom() {
  $('#btn-leave').onclick = () => {
    socket.emit('room:leave');
    S.room = null;
    $('#room-chat-log').innerHTML = '';
    show('lobby');
  };
  const cl = $('#char-list');
  cl.innerHTML = '';
  for (const id of [...CHARACTERS.map((c) => c.id), 'random']) {
    const card = el('div', 'card char-card');
    card.dataset.id = id;
    card.append(portrait(id), el('span', '', id === 'random' ? '랜덤' : CHARACTER_BY_ID[id].name));
    card.onclick = () => {
      sfx.click();
      S.pickedChar = id;
      S.viewChar = id === 'random' ? S.viewChar : id;
      store.set('intto.char', id);
      socket.emit('room:me', { charId: id });
      renderCharInfo();
    };
    card.onmouseenter = () => {
      if (id !== 'random') {
        S.viewChar = id;
        renderCharInfo();
      }
    };
    card.onmouseleave = () => {
      S.viewChar = S.pickedChar === 'random' ? S.viewChar : S.pickedChar;
      renderCharInfo();
    };
    cl.append(card);
  }
  $('#btn-main').onclick = async () => {
    const r = S.room;
    if (!r) return;
    sfx.click();
    if (r.hostId === S.myId) {
      const res = await request('room:start', {});
      if (!res.ok) toast(res.error);
    } else {
      const me = r.players.find((p) => p.id === S.myId);
      socket.emit('room:me', { ready: !(me && me.ready) });
    }
  };
  const chatIn = $('#room-chat-in');
  chatIn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && chatIn.value.trim()) {
      socket.emit('chat', chatIn.value);
      chatIn.value = '';
    }
  });
}

function renderCharInfo() {
  const box = $('#char-info');
  box.innerHTML = '';
  const c = CHARACTER_BY_ID[S.viewChar] || CHARACTERS[0];
  const head = el('div', 'head');
  head.append(el('span', 'nm', c.name), el('span', 'kind', `${c.kind} · ${c.desc}`));
  box.append(head);
  for (const k of ['hp', 'maxSpeed', 'accel', 'weight']) {
    const row = el('div', 'stat');
    row.append(el('span', '', STAT_LABELS[k]), pips(c.stats[k]));
    box.append(row);
  }
  c.skills.forEach((sk, i) => {
    const row = el('div', 'skill');
    row.append(el('span', 'no', `${i + 1}칸`));
    const ic = el('span', 'ic');
    ic.append(atlasCanvas(ART.hud, 'icon_' + sk, 1));
    row.append(ic, el('span', 'nm', SKILLS[sk].name), el('span', 'ds', SKILLS[sk].desc));
    box.append(row);
  });
  document.querySelectorAll('.char-card').forEach((cd) => cd.classList.toggle('selected', cd.dataset.id === S.pickedChar));
}

function renderRoom() {
  const r = S.room;
  if (!r) return;
  const isHost = r.hostId === S.myId;
  const me = r.players.find((p) => p.id === S.myId);
  $('#room-title').textContent = `#${r.id} ${r.title}`;

  // 참가자
  const list = $('#slot-list');
  list.innerHTML = '';
  for (let i = 0; i < RULES.maxPlayers; i++) {
    const p = r.players[i];
    const card = el('div', 'card slot' + (p ? '' : ' empty'));
    if (!p) {
      const ph = el('div', 'portrait');
      card.append(ph);
      const who = el('div', 'who');
      who.append(el('span', 'nm', '빈 자리'));
      card.append(who);
      // 방장은 빈 자리에 봇을 넣어 혼자서도 시작할 수 있다
      if (isHost && r.state === 'waiting') {
        card.classList.add('has-btn');
        const add = el('button', 'pix-btn side', '봇 추가');
        add.onclick = async () => {
          sfx.click();
          const res = await request('room:addBot', {});
          if (res && res.error) toast(res.error);
        };
        card.append(add);
      }
      list.append(card);
      continue;
    }
    card.dataset.id = p.id;
    card.append(portrait(p.charId));
    const who = el('div', 'who');
    const nm = el('span', 'nm', p.name);
    nm.style.color = PLAYER_COLORS[i];
    who.append(nm);
    const sub = el('div', 'sub');
    sub.append(atlasCanvas(ART.fx, 'miniMarker' + i, 4 / 3));
    if (p.id === r.hostId) sub.append(atlasCanvas(ART.ui, 'crown', 4 / 3), el('span', '', '방장'));
    else if (p.ready) sub.append(atlasCanvas(ART.ui, 'check', 4 / 3), el('span', '', '준비'));
    else sub.append(el('span', '', '대기'));
    if (r.mode === 'team') sub.append(atlasCanvas(ART.ui, p.team === 'A' ? 'teamA' : 'teamB', 4 / 3));
    who.append(sub);
    who.append(el('span', 'sub', p.charId === 'random' ? '랜덤' : CHARACTER_BY_ID[p.charId]?.name));
    card.append(who);
    // 방장은 대기 중에 다른 참가자를 내보낼 수 있다
    if (isHost && p.id !== S.myId && r.state === 'waiting') {
      card.classList.add('has-btn');
      const kick = el('button', 'pix-btn side', '강퇴');
      kick.onclick = async () => {
        sfx.click();
        const res = await request('room:kick', { id: p.id });
        if (res && res.error) toast(res.error);
      };
      card.append(kick);
    }
    attachBubble(card, p.id);
    list.append(card);
  }

  // 내 캐릭터
  if (me && me.charId !== S.pickedChar) {
    S.pickedChar = me.charId;
    if (me.charId !== 'random') S.viewChar = me.charId;
  }
  renderCharInfo();

  // 맵
  const tabs = $('#map-tabs');
  tabs.innerHTML = '';
  for (const m of [...MAPS, { id: 'random', name: '랜덤', desc: '시작할 때 셋 중 하나' }]) {
    const b = el('button', 'pix-btn' + (r.mapId === m.id ? ' on' : ''), m.name);
    b.disabled = !isHost && r.mapId !== m.id;
    b.onclick = () => {
      if (!isHost) return;
      sfx.click();
      socket.emit('room:settings', { mapId: m.id });
    };
    tabs.append(b);
  }
  $('#map-preview').src = r.mapId === 'random' ? '/assets/ui/map_random.png' : `/assets/world/${r.mapId}/preview.png`;
  $('#map-desc').textContent = r.mapId === 'random' ? '시작할 때 셋 중 하나' : MAP_BY_ID[r.mapId]?.desc ?? '';

  // 방식
  const modes = $('#mode-tabs');
  modes.innerHTML = '';
  for (const [id, label] of [['solo', '개인전'], ['team', '2:2 팀전']]) {
    const b = el('button', 'pix-btn' + (r.mode === id ? ' on' : ''), label);
    b.disabled = !isHost && r.mode !== id;
    b.onclick = () => {
      if (!isHost) return;
      sfx.click();
      socket.emit('room:settings', { mode: id });
    };
    modes.append(b);
  }
  const teams = $('#team-tabs');
  teams.innerHTML = '';
  teams.classList.toggle('hidden', r.mode !== 'team');
  if (r.mode === 'team' && me) {
    for (const t of ['A', 'B']) {
      const b = el('button', 'pix-btn' + (me.team === t ? ' on' : ''));
      b.append(atlasCanvas(ART.ui, t === 'A' ? 'teamA' : 'teamB', 4 / 3));
      b.append(document.createTextNode(` ${t}팀`));
      b.onclick = () => {
        sfx.click();
        socket.emit('room:me', { team: t });
      };
      teams.append(b);
    }
  }

  // 시작·준비
  const btn = $('#btn-main');
  let hint = '';
  const n = r.players.length;
  if (n < RULES.minPlayers) hint = `${RULES.minPlayers}명 이상 모이면 시작`;
  else if (r.mode === 'team' && n !== 4) hint = '팀전은 4명일 때만';
  else if (r.mode === 'team' && r.players.filter((p) => p.team === 'A').length !== 2) hint = '팀을 2:2로 나누기';
  else if (r.players.some((p) => p.id !== r.hostId && !p.ready)) hint = '모두 준비하면 시작';
  if (isHost) {
    btn.textContent = '시작';
    btn.disabled = !!hint;
  } else {
    btn.textContent = me && me.ready ? '준비 취소' : '준비';
    btn.disabled = false;
  }
  $('#start-hint').textContent = hint;
}

// 대기실 말풍선. 채팅을 친 사람 칸 위에 잠깐 띄운다. 칸을 다시 그려도 남은 시간만큼 이어서 보인다
const roomBubbles = new Map(); // id → { text, ms, until, timer }

function showRoomBubble(m) {
  const old = roomBubbles.get(m.id);
  if (old) clearTimeout(old.timer);
  const ms = Math.min(7000, 3500 + m.text.length * 60);
  const b = { text: m.text, ms, until: Date.now() + ms };
  b.timer = setTimeout(() => {
    roomBubbles.delete(m.id);
    document.querySelector(`.slot[data-id="${CSS.escape(m.id)}"] .bubble`)?.remove();
  }, ms);
  roomBubbles.set(m.id, b);
  const card = document.querySelector(`.slot[data-id="${CSS.escape(m.id)}"]`);
  if (card) attachBubble(card, m.id);
}

function attachBubble(card, id) {
  card.querySelector('.bubble')?.remove();
  const b = roomBubbles.get(id);
  if (!b) return;
  const left = b.until - Date.now();
  if (left <= 0) return;
  const box = el('div', 'bubble');
  box.append(el('span', 'txt', b.text));
  box.style.animationDuration = b.ms + 'ms';
  box.style.animationDelay = -(b.ms - left) + 'ms';
  card.append(box);
}

function addChat(logEl, m) {
  const line = el('div', m.system ? 'sys' : '');
  if (m.system) line.textContent = m.text;
  else {
    const who = el('b', '', m.from);
    who.style.color = PLAYER_COLORS[m.slot] || '#fff';
    line.append(who, document.createTextNode(` ${m.text}`));
  }
  logEl.append(line);
  while (logEl.children.length > 80) logEl.firstChild.remove();
  logEl.scrollTop = logEl.scrollHeight;
}

// ── 레이스 ──
function fitStage() {
  const cv = $('#game');
  // 창을 꽉 채우도록 16:9 그대로 키운다. 정수배로만 키우면 창이 2배에 못 미칠 때 1배로 작게 남는다
  const k = Math.min(window.innerWidth / RULES.view.w, window.innerHeight / RULES.view.h);
  cv.style.width = Math.floor(RULES.view.w * k) + 'px';
  cv.style.height = Math.floor(RULES.view.h * k) + 'px';
}

const gameChat = {
  typing: false,
  open() {
    this.typing = true;
    $('#game-chat').classList.add('typing');
    $('#game-chat-in').focus();
  },
  close() {
    this.typing = false;
    $('#game-chat').classList.remove('typing');
    $('#game-chat-in').blur();
    $('#game').focus();
  },
};

async function startRace(init) {
  await loadWorld(init.mapId);
  if (S.game) S.game.destroy();
  $('#result').classList.add('hidden');
  $('#ghost-choice').classList.add('hidden');
  $('#game-chat-log').innerHTML = '';
  show('game');
  music.play(init.mapId);
  fitStage();
  S.game = new Game($('#game'), init, S.myId, {
    isTyping: () => gameChat.typing,
    onEnd: (d) => showResults(d),
    onGhost: () => $('#ghost-choice').classList.remove('hidden', 'flying'),
    onGhostEnd: () => $('#ghost-choice').classList.add('hidden'),
  });
}

function showResults(d) {
  const body = $('#result-body');
  body.innerHTML = '';
  let title = '결과';
  if (d.mode === 'team') title = d.winnerTeam === 'draw' ? '무승부' : `${d.winnerTeam}팀 승리`;
  else if (d.results[0]) title = `1위 ${d.results[0].name}`;
  $('#result-title').textContent = title;
  for (const r of d.results) {
    const tr = el('tr', r.id === S.myId ? 'me' : '');
    const pc = el('td');
    pc.append(portrait(r.charId));
    const nm = el('td', '', r.name);
    nm.style.color = PLAYER_COLORS[r.color];
    tr.append(el('td', 'rank', `${r.rank}`), pc, nm, el('td', '', `${r.dist.toFixed(1)}m`), el('td', '', r.kills), el('td', '', r.nices), el('td', '', r.gems));
    body.append(tr);
  }
  $('#result').classList.remove('hidden');
}

function backToRoom() {
  if (S.game) S.game.destroy();
  S.game = null;
  $('#result').classList.add('hidden');
  $('#ghost-choice').classList.add('hidden');
  gameChat.close();
  if (S.room) {
    show('room');
    renderRoom();
  } else show('lobby');
}

// ── 서버 신호 ──
socket.on('lobby:rooms', (rooms) => {
  S.rooms = rooms;
  renderRooms();
});

socket.on('room:kicked', () => {
  if (S.game) S.game.destroy();
  S.game = null;
  S.room = null;
  show('lobby');
  toast('방장이 방에서 내보냄');
});

socket.on('room:state', (room) => {
  const fresh = !S.room || S.room.id !== room.id;
  S.room = room;
  if (fresh) {
    $('#room-chat-log').innerHTML = '';
    const saved = store.get('intto.char');
    if (saved && (saved === 'random' || CHARACTER_BY_ID[saved])) socket.emit('room:me', { charId: saved });
  }
  if (S.screen === 'game') return;
  if (S.screen !== 'room') show('room');
  renderRoom();
});

socket.on('chat', (m) => {
  addChat($('#room-chat-log'), m);
  if (!m.system && S.screen === 'room') showRoomBubble(m);
  if (S.screen === 'game') {
    addChat($('#game-chat-log'), m);
    if (!m.system && S.game) S.game.say(m.id, m.text);
  }
});

socket.on('race:init', (init) => startRace(init));

// 서버가 새로 켜졌으면 새 코드를 받도록 페이지를 다시 읽는다. 이름은 저장돼 있어 첫 화면에 그대로 남는다
socket.on('server:build', (b) => {
  if (S.build && b !== S.build) location.reload();
  else S.build = b;
});

socket.on('disconnect', () => {
  toast('연결이 끊김, 다시 연결하는 중');
});
socket.on('connect', () => {
  syncClock();
  if (S.myId) {
    // 다시 연결되면 방 정보는 사라지므로 로비로 돌아간다
    request('hello', { name: S.name }).then((res) => {
      if (res && res.id) S.myId = res.id;
      if (S.game) S.game.destroy();
      S.game = null;
      S.room = null;
      show('lobby');
    });
  }
});

// ── 키 ──
window.addEventListener('keydown', (e) => {
  if (e.code === 'KeyM' && document.activeElement?.tagName !== 'INPUT') {
    const m = toggleMute();
    music.setMuted(m);
    toast(m ? '소리 끔' : '소리 켬');
  }
  if (S.screen !== 'game') return;
  if (e.key === 'Enter') {
    if (!gameChat.typing) {
      e.preventDefault();
      gameChat.open();
    } else {
      const v = $('#game-chat-in').value.trim();
      if (v) socket.emit('chat', v);
      $('#game-chat-in').value = '';
      gameChat.close();
    }
  } else if (e.key === 'Escape' && gameChat.typing) gameChat.close();
});
window.addEventListener('resize', () => {
  if (S.screen === 'game') fitStage();
});
$('#btn-back').onclick = () => {
  sfx.click();
  backToRoom();
};
// 목숨을 다 잃었을 때 고르기. 누른 버튼에 포커스가 남으면 스페이스나 Enter가 버튼을 다시 누르므로 바로 뗀다
// 유령으로 날기를 고르면 창은 접고 관전하기 버튼만 남긴다. 나중에 관전으로 넘어갈 때 누른다
$('#btn-ghost-fly').onclick = (e) => {
  sfx.click();
  e.currentTarget.blur();
  $('#ghost-choice').classList.add('flying');
};
$('#btn-ghost-watch').onclick = (e) => {
  sfx.click();
  e.currentTarget.blur();
  if (S.game) S.game.watch();
};

// ── 시작 ──
(async function boot() {
  scaleImages();
  checkUiArt();
  await Promise.all([
    loadCommonArt(),
    music.init(),
    document.fonts.load('11px Galmuri11'),
    document.fonts.load('11px Galmuri11B'),
    document.fonts.load('14px Galmuri14'),
  ]);
  const saved = store.get('intto.char');
  if (saved && (saved === 'random' || CHARACTER_BY_ID[saved])) S.pickedChar = saved;
  if (saved && CHARACTER_BY_ID[saved]) S.viewChar = saved;
  initTitle();
  initLobby();
  initRoom();
  renderRooms();
  for (const m of MAPS) loadWorld(m.id);
})();
