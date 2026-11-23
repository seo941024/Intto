// Socket.IO 연결과 서버 시계 맞추기
/* global io */
export const socket = io({ transports: ['websocket', 'polling'] });

let offset = 0; // 서버 시각 - 내 시각
let bestRtt = Infinity;

export const serverNow = () => Date.now() + offset;

function ping() {
  const c = Date.now();
  socket.timeout(2000).emit('time:ping', c, (err, s) => {
    if (err || typeof s !== 'number') return;
    const now = Date.now();
    const rtt = now - c;
    // 왕복 시간이 짧았던 측정을 더 믿는다
    if (rtt <= bestRtt * 1.3) {
      bestRtt = Math.min(bestRtt, rtt);
      offset = s + rtt / 2 - now;
    }
  });
}

export function syncClock() {
  bestRtt = Infinity;
  for (let i = 0; i < 6; i++) setTimeout(ping, i * 150);
}

socket.on('connect', syncClock);
setInterval(ping, 5000);

export function request(ev, data) {
  return new Promise((resolve) => {
    socket.timeout(4000).emit(ev, data, (err, res) => resolve(err ? { ok: false, error: '서버 응답 없음' } : res));
  });
}
