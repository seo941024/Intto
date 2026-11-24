// 인또 서버: 정적 파일, 로비·방, 레이스 중계
import http from 'node:http';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { Server } from 'socket.io';
import { RULES } from '../shared/rules.js';
import { CHARACTERS, CHARACTER_BY_ID } from '../shared/characters.js';
import { MAP_BY_ID } from '../shared/mapgen.js';
import { Race } from './race.js';
import { spawnBot } from './bot.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 3000;

const app = express();
app.use(express.static(path.join(ROOT, 'public')));
app.use('/shared', express.static(path.join(ROOT, 'shared')));
app.use('/fonts', express.static(path.join(ROOT, 'node_modules', 'galmuri', 'dist')));
app.get('/healthz', (_req, res) => res.json({ ok: true, rooms: rooms.size, players: players.size }));

const server = http.createServer(app);
const io = new Server(server, { pingInterval: 5000, pingTimeout: 8000 });

const players = new Map(); // socket.id → { id, name, roomId, bot }
const rooms = new Map(); // roomId → Room
let roomSeq = 1;
// 서버가 띄운 봇만 아는 열쇠. 이 값을 들고 붙은 연결만 봇으로 친다
const BOT_KEY = crypto.randomUUID();
const BOT_NAMES = ['봇하나', '봇둘', '봇셋'];
const isBot = (id) => !!players.get(id)?.bot;

const cleanText = (s, max) => (typeof s === 'string' ? s.replace(/[\u0000-\u001f<>]/g, '').trim().slice(0, max) : '');

class Room {
  constructor(title, host) {
    this.id = String(roomSeq++);
    this.title = title || `${host.name}의 방`;
    this.hostId = host.id;
    this.members = new Map(); // id → { id, name, charId, team, ready, joinedAt }
    this.mapId = 'cloud';
    this.mode = 'solo';
    this.state = 'waiting';
    this.race = null;
    this.botsComing = new Set(); // 들어오는 중인 봇 이름
  }
  ordered() {
    return [...this.members.values()].sort((a, b) => a.joinedAt - b.joinedAt);
  }
  summary() {
    return {
      id: this.id, title: this.title, count: this.members.size, max: RULES.maxPlayers,
      state: this.state, mode: this.mode, mapId: this.mapId,
    };
  }
  view() {
    return {
      id: this.id, title: this.title, hostId: this.hostId, state: this.state,
      mapId: this.mapId, mode: this.mode,
      players: this.ordered().map((m, i) => ({
        id: m.id, name: m.name, charId: m.charId, team: m.team, ready: m.ready, slot: i,
      })),
    };
  }
  startProblem() {
    const list = this.ordered();
    if (list.length < RULES.minPlayers) return `${RULES.minPlayers}명 이상 모여야 시작할 수 있음`;
    if (list.some((m) => m.id !== this.hostId && !m.ready)) return '모두 준비해야 시작할 수 있음';
    if (this.mode === 'team') {
      if (list.length !== RULES.teamModePlayers) return '팀전은 4명이 모여야 할 수 있음';
      const a = list.filter((m) => m.team === 'A').length;
      if (a !== 2) return '팀을 2명씩 나눠야 시작할 수 있음';
    }
    return null;
  }
}

function lobbyList() {
  return [...rooms.values()].map((r) => r.summary());
}
function pushLobby() {
  io.to('lobby').emit('lobby:rooms', lobbyList());
}
function pushRoom(room) {
  io.to(`room:${room.id}`).emit('room:state', room.view());
  pushLobby();
}
function systemChat(room, text) {
  io.to(`room:${room.id}`).emit('chat', { system: true, text, at: Date.now() });
}

function joinRoom(socket, me, room) {
  if (room.members.size >= RULES.maxPlayers) return '방이 가득 참';
  if (room.state !== 'waiting') return '이미 게임 중인 방';
  const teamA = room.ordered().filter((m) => m.team === 'A').length;
  room.members.set(me.id, {
    id: me.id, name: me.name, charId: 'mongsil',
    team: teamA <= room.members.size - teamA ? 'A' : 'B',
    ready: false, joinedAt: Date.now() + Math.random(),
  });
  me.roomId = room.id;
  socket.leave('lobby');
  socket.join(`room:${room.id}`);
  systemChat(room, `${me.name} 입장`);
  pushRoom(room);
  return null;
}

function leaveRoom(socket, me, how = '퇴장') {
  const room = rooms.get(me.roomId);
  me.roomId = null;
  if (!room) return;
  room.members.delete(me.id);
  if (socket) {
    socket.leave(`room:${room.id}`);
    socket.join('lobby');
  }
  if (room.race) room.race.onLeave(me.id);
  if (room.members.size === 0) {
    if (room.race) room.race.dispose();
    rooms.delete(room.id);
    pushLobby();
    return;
  }
  const left = room.ordered();
  if (room.hostId === me.id) room.hostId = (left.find((m) => !isBot(m.id)) || left[0]).id;
  systemChat(room, `${me.name} ${how}`);
  pushRoom(room);
  // 사람이 다 나가고 봇만 남으면 봇도 내보내 방을 닫는다
  if (left.every((m) => isBot(m.id))) {
    setImmediate(() => left.forEach((m) => io.sockets.sockets.get(m.id)?.disconnect(true)));
  }
}

const BUILD = Date.now().toString(36);

io.on('connection', (socket) => {
  const bot = socket.handshake.auth?.bot === BOT_KEY;
  const me = { id: socket.id, name: `손님${Math.floor(Math.random() * 900 + 100)}`, roomId: null, bot };
  players.set(socket.id, me);
  socket.join('lobby');
  // 서버가 새로 켜질 때마다 바뀌는 값. 브라우저가 예전 코드로 다시 붙었으면 이 값을 보고 새로 고친다
  socket.emit('server:build', BUILD);

  const myRoom = () => rooms.get(me.roomId);
  const ack = (fn, v) => typeof fn === 'function' && fn(v);

  socket.on('time:ping', (_c, fn) => ack(fn, Date.now()));

  socket.on('hello', (d, fn) => {
    const name = cleanText(d && d.name, 10);
    if (name) me.name = name;
    ack(fn, { id: me.id, name: me.name });
    socket.emit('lobby:rooms', lobbyList());
  });

  socket.on('lobby:list', () => socket.emit('lobby:rooms', lobbyList()));

  socket.on('room:create', (d, fn) => {
    if (me.roomId) leaveRoom(socket, me);
    const room = new Room(cleanText(d && d.title, 16), me);
    rooms.set(room.id, room);
    const err = joinRoom(socket, me, room);
    ack(fn, err ? { ok: false, error: err } : { ok: true });
  });

  socket.on('room:join', (d, fn) => {
    const room = rooms.get(String(d && d.roomId));
    if (!room) return ack(fn, { ok: false, error: '없는 방' });
    if (me.roomId) leaveRoom(socket, me);
    const err = joinRoom(socket, me, room);
    ack(fn, err ? { ok: false, error: err } : { ok: true });
  });

  socket.on('room:quick', (_d, fn) => {
    const room = [...rooms.values()].find((r) => r.state === 'waiting' && r.members.size < RULES.maxPlayers);
    if (!room) return ack(fn, { ok: false, error: '들어갈 수 있는 방이 없음' });
    if (me.roomId) leaveRoom(socket, me);
    const err = joinRoom(socket, me, room);
    ack(fn, err ? { ok: false, error: err } : { ok: true });
  });

  socket.on('room:leave', () => leaveRoom(socket, me));

  // 방장이 대기 중인 방에서 다른 참가자를 내보낸다
  socket.on('room:kick', (d, fn) => {
    const room = myRoom();
    if (!room) return ack(fn, { error: '방에 있지 않음' });
    if (room.hostId !== me.id) return ack(fn, { error: '방장만 내보낼 수 있음' });
    if (room.state !== 'waiting') return ack(fn, { error: '게임 중에는 내보낼 수 없음' });
    const target = players.get(d && d.id);
    if (!target || target.roomId !== room.id || target.id === me.id) return ack(fn, { error: '내보낼 수 없는 참가자' });
    const ts = io.sockets.sockets.get(target.id);
    leaveRoom(ts, target, '강퇴');
    if (ts) ts.emit('room:kicked');
    ack(fn, { ok: true });
  });

  // 방장이 대기 중인 방에 봇을 넣는다. 혼자서도 시작할 수 있게
  socket.on('room:addBot', (_d, fn) => {
    const room = myRoom();
    if (!room) return ack(fn, { error: '방에 있지 않음' });
    if (room.hostId !== me.id) return ack(fn, { error: '방장만 봇을 넣을 수 있음' });
    if (room.state !== 'waiting') return ack(fn, { error: '게임 중에는 봇을 넣을 수 없음' });
    if (room.members.size + room.botsComing.size >= RULES.maxPlayers) return ack(fn, { error: '방이 가득 참' });
    const used = new Set([...room.ordered().map((m) => m.name), ...room.botsComing]);
    const name = BOT_NAMES.find((n) => !used.has(n));
    if (!name) return ack(fn, { error: '봇은 3명까지 넣을 수 있음' });
    room.botsComing.add(name);
    const seat = BOT_NAMES.indexOf(name);
    spawnBot({
      url: `http://127.0.0.1:${PORT}`, key: BOT_KEY, name, seat, roomId: room.id,
      charId: CHARACTERS[Math.floor(Math.random() * CHARACTERS.length)].id,
      done: () => room.botsComing.delete(name),
    });
    ack(fn, { ok: true });
  });

  socket.on('room:me', (d) => {
    const room = myRoom();
    const m = room && room.members.get(me.id);
    if (!m || room.state !== 'waiting' || !d) return;
    if (typeof d.charId === 'string' && (d.charId === 'random' || CHARACTER_BY_ID[d.charId])) m.charId = d.charId;
    if (d.team === 'A' || d.team === 'B') m.team = d.team;
    if (typeof d.ready === 'boolean' && me.id !== room.hostId) m.ready = d.ready;
    pushRoom(room);
  });

  socket.on('room:settings', (d) => {
    const room = myRoom();
    if (!room || room.hostId !== me.id || room.state !== 'waiting' || !d) return;
    if (typeof d.mapId === 'string' && (d.mapId === 'random' || MAP_BY_ID[d.mapId])) room.mapId = d.mapId;
    if (d.mode === 'solo' || d.mode === 'team') room.mode = d.mode;
    if (typeof d.title === 'string' && cleanText(d.title, 16)) room.title = cleanText(d.title, 16);
    pushRoom(room);
  });

  socket.on('room:start', (_d, fn) => {
    const room = myRoom();
    if (!room || room.hostId !== me.id) return ack(fn, { ok: false, error: '방장만 시작할 수 있음' });
    if (room.state !== 'waiting') return ack(fn, { ok: false, error: '이미 게임 중인 방' });
    const problem = room.startProblem();
    if (problem) return ack(fn, { ok: false, error: problem });
    room.state = 'playing';
    room.race = new Race(io, room, () => {
      room.state = 'waiting';
      room.race = null;
      for (const m of room.members.values()) m.ready = false;
      pushRoom(room);
    }, isBot);
    io.to(`room:${room.id}`).emit('race:init', room.race.initPayload());
    pushRoom(room);
    ack(fn, { ok: true });
  });

  socket.on('chat', (text) => {
    const room = myRoom();
    const t = cleanText(text, 80);
    if (!room || !t) return;
    const m = room.members.get(me.id);
    const slot = room.ordered().findIndex((x) => x.id === me.id);
    io.to(`room:${room.id}`).emit('chat', { from: me.name, id: me.id, slot, team: m && m.team, text: t, at: Date.now() });
  });

  // 레이스
  const race = () => {
    const room = myRoom();
    return room && room.race;
  };
  socket.on('race:state', (s) => race()?.onState(me.id, s));
  socket.on('race:pickup', (id) => race()?.onPickup(me.id, id));
  socket.on('race:grab', (id) => race()?.onGrab(me.id, id));
  socket.on('race:skill', () => race()?.onSkill(me.id));
  socket.on('race:lifeLost', (d) => race()?.onLifeLost(me.id, d));
  socket.on('race:nice', (i) => race()?.onNice(me.id, i));
  socket.on('race:final', () => race()?.onFinal(me.id));

  socket.on('disconnect', () => {
    leaveRoom(null, me);
    players.delete(socket.id);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`인또 서버 실행: http://localhost:${PORT}`);
});
