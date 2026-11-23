// 게임 규칙 수치. 서버와 브라우저가 같이 읽는다.
// 출처가 있는 값은 주석에 적었고, 나머지는 인또 기준으로 정한 값이다.

export const RULES = {
  // 방
  maxPlayers: 4,
  minPlayers: 2,
  teamModePlayers: 4, // 2:2 팀전은 4명일 때만

  // 화면, 그림 1픽셀 = 좌표 1단위. 1080p 모니터에서 정확히 2배
  view: { w: 960, h: 540 },
  cameraLead: 200, // 화면 왼쪽에서 내 캐릭터까지, 화면 픽셀
  cameraZoom: 1.5, // 맵을 이 배율로 당겨 본다. 화면에는 맵의 640×360만큼이 보인다
  worldH: 360, // 맵 세로 크기. 화면 높이 540을 배율로 나눈 값이라 맵 위아래가 한 화면에 다 들어온다
  pxPerMeter: 15,
  minimapRangeM: 500, // 미니맵 ±500m, 나무위키 윙또 문서

  // 레이스
  raceMs: 150_000, // 2분 30초, 나무위키 윙또 문서
  countdownMs: 3_000,
  resultHoldMs: 1_500,

  // 생명·체력
  lives: 2, // 두 번의 생명, 나무위키 윙또 문서
  hpDrainPerSec: 1.5,
  foodHeal: 25, // 최대 회복량 25, 나무위키 윙또 문서
  foodEveryM: [300, 400], // 300~400m마다, 나무위키 윙또 문서
  terrainCostsLife: true, // 지형에 부딪히면 하트 1개
  obstacleCostsLife: false, // true로 바꾸면 장애물도 하트 1개
  obstacleDamage: 20,
  lifeLostInvulnMs: 2_000,
  hitInvulnMs: 900,
  killCreditMs: 3_000, // 기술에 맞은 뒤 이 시간 안에 생명을 잃으면 KILL

  // 유령
  ghostLatchRange: 60,

  // 보석은 점수, 기술은 필드의 기술 아이콘을 먹어 하나 든다
  skillSlots: 5,
  redGemChance: 0.03,
  skillItemEveryM: [60, 100], // 기술 아이콘 간격
  skillItemWeights: [30, 20, 20, 15, 15], // 1~5칸이 나올 비율

  // 깃털
  featherSpeedBonus: 10.5, // px/s
  featherMax: 10,

  // 통신
  sendHz: 20,
  interpDelayMs: 110,
};

// 캐릭터 능력치 점수 1~5를 물리값으로 바꾼다. 단위는 px, px/s
export function deriveStats(stats, feathers = 0) {
  const f = Math.min(feathers, RULES.featherMax);
  return {
    maxHp: Math.round(40 + 20 * stats.hp),
    maxSpeed: 240 + 50 * stats.maxSpeed,
    accel: 100 + 60 * stats.accel,
    baseSpeed: 165 + f * RULES.featherSpeedBonus,
    lift: 820 - 50 * stats.weight, // 무거울수록 상승이 느림
    riseMax: 250 - 20 * stats.weight,
    gravity: 560,
    fallMax: 260,
    decel: 260,
    radius: 12,
  };
}

export const PLAYER_COLORS = ['#e43b44', '#0099db', '#63c74d', '#feae34'];
