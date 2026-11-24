// 비행 계산. 브라우저의 내 캐릭터와 서버의 봇이 같은 규칙으로 난다.
// L은 x, y, vx, vy를 가진 몸, st는 deriveStats 결과. 유령으로 나는 브라우저 몸은 ghost와 ghostDist도 가진다
import { RULES } from './rules.js';
import { clamp } from './util.js';

export const DASH_VX = 1140;

// 속도만 바꾼다. input은 { up, boost }, fx는 이번 순간 걸린 효과 { dashing, slow, heavy }
export function steerFlyer(L, st, input, fx, dt) {
  const slowF = fx.slow ? 0.6 : 1;
  const target = input.boost ? st.maxSpeed * slowF : st.baseSpeed * slowF;
  if (fx.dashing) L.vx = DASH_VX;
  else if (L.vx < target) L.vx = Math.min(target, L.vx + st.accel * dt);
  else L.vx = Math.max(target, L.vx - (L.vx > st.maxSpeed ? st.decel * 3 : st.decel) * dt);
  if (input.up) L.vy -= st.lift * (fx.heavy ? 0.55 : 1) * dt;
  else L.vy += st.gravity * dt;
  L.vy = clamp(L.vy, -st.riseMax * (fx.heavy ? 0.6 : 1), st.fallMax);
}

// 속도대로 옮긴다. 맵 위아래 끝 밖으로는 나가지 않는다
export function moveFlyer(L, dt) {
  L.x += L.vx * dt;
  L.y = clamp(L.y + L.vy * dt, 2, RULES.worldH - 2);
  if (L.ghost) L.ghostDist += L.vx * dt;
}
