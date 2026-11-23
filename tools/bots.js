// 혼자 테스트할 때 쓰는 봇. 열린 방에 들어가 준비하고, 레이스가 시작되면 통로 가운데를 따라 난다.
// 사용: node tools/bots.js [봇 수=3] [방 번호 또는 wait] [서버 주소=http://localhost:3000]
// wait를 주면 누군가 방을 만들 때까지 기다렸다가 그 방에 들어간다.
// 방 번호를 빼면 대기 중인 첫 방에 들어가고, 방이 없으면 첫 봇이 방을 만든 뒤 모두 모이면 시작한다.
import { io } from 'socket.io-client';
import { RULES } from '../shared/rules.js';
import { CHARACTERS } from '../shared/characters.js';
import { attachRace, call } from '../server/bot.js';

const COUNT = Number(process.argv[2] || 3);
const ROOM = process.argv[3] && process.argv[3] !== '-' ? process.argv[3] : null;
const URL = process.argv[4] || 'http://localhost:3000';
const NAMES = ['봇하나', '봇둘', '봇셋', '봇넷'];

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

function makeBot(i) {
  const s = io(URL, { transports: ['websocket'] });
  const bot = { i, s, name: NAMES[i] || `봇${i + 1}`, id: null, room: null, race: null, offset: 0 };

  s.on('connect', async () => {
    const t0 = Date.now();
    const st = await call(s, 'time:ping', t0);
    bot.offset = st + (Date.now() - t0) / 2 - Date.now();
    const h = await call(s, 'hello', { name: bot.name });
    bot.id = h.id;
    log(bot.name, '접속');
  });

  s.on('room:state', (r) => {
    bot.room = r;
    const me = r.players.find((p) => p.id === bot.id);
    if (!me) return;
    if (r.hostId === bot.id) {
      // 봇이 방장이면 사람 없이도 다 모이면 시작
      if (r.state === 'waiting' && r.players.length >= Math.min(COUNT, RULES.maxPlayers) && r.players.every((p) => p.id === r.hostId || p.ready)) {
        setTimeout(() => call(s, 'room:start', {}).then((x) => !x.ok && log(bot.name, '시작 실패', x.error)), 800);
      }
    } else if (!me.ready && r.state === 'waiting') {
      s.emit('room:me', { charId: CHARACTERS[(i + 1) % CHARACTERS.length].id, ready: true });
    }
  });

  attachRace(bot, log);
  return bot;
}

const bots = [];
for (let i = 0; i < COUNT; i++) bots.push(makeBot(i));

// 방 찾기
setTimeout(async () => {
  const first = bots[0];
  let roomId = ROOM === 'wait' ? null : ROOM;
  if (ROOM === 'wait') {
    // 사람이 방을 만들 때까지 기다렸다가 들어간다
    log('방이 생기기를 기다리는 중');
    while (!roomId) {
      const rooms = await new Promise((res) => {
        first.s.once('lobby:rooms', res);
        first.s.emit('lobby:list');
      });
      const open = rooms.find((r) => r.state === 'waiting' && r.count + COUNT <= r.max);
      if (open) roomId = open.id;
      else await new Promise((res) => setTimeout(res, 1000));
    }
  }
  if (!roomId) {
    const rooms = await new Promise((res) => {
      first.s.once('lobby:rooms', res);
      first.s.emit('lobby:list');
    });
    const open = rooms.find((r) => r.state === 'waiting' && r.count < r.max);
    if (open) roomId = open.id;
  }
  if (!roomId) {
    const r = await call(first.s, 'room:create', { title: '봇 연습방' });
    log('방 만들기', r.ok ? '성공' : r.error);
    await new Promise((res) => setTimeout(res, 300));
    roomId = first.room && first.room.id;
    for (const b of bots.slice(1)) {
      const j = await call(b.s, 'room:join', { roomId });
      log(b.name, '입장', j.ok ? '성공' : j.error);
    }
  } else {
    for (const b of bots) {
      const j = await call(b.s, 'room:join', { roomId });
      log(b.name, `방 #${roomId} 입장`, j.ok ? '성공' : j.error);
    }
  }
}, 700);
