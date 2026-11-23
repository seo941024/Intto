// 캐릭터와 기술 정의. 그림은 public/assets/characters/<id>/ 폴더의 PNG와 sprite.json을 읽는다.
// 능력치는 1~5 점수, 0.5 단위 가능.
// 기술칸은 5칸: 1칸 공격기, 2칸 대시, 3·4칸 고유기, 5칸 보호막.

export const SKILLS = {
  puff: { name: '솜뭉치', desc: '앞으로 솜뭉치를 날려 피해 25', kind: 'proj', proj: 'puff', count: 1, dmg: 25, speed: 495 },
  dash: { name: '대시', desc: '잠깐 무적이 되어 앞으로 돌진, 벽도 통과', kind: 'self', ms: 450 },
  cloud: { name: '먹구름', desc: '뒤따라오는 상대 화면을 3.5초 가림', kind: 'debuff', effect: 'blind', ms: 3500, area: 'behind', range: 780 },
  bolt: { name: '번개', desc: '앞쪽 가장 가까운 상대에게 번개 피해 30', kind: 'bolt', dmg: 30, range: 1050, delayMs: 550 },
  shield: { name: '보호막', desc: '피해를 한 번 막음', kind: 'self' },
  nut: { name: '너트 연사', desc: '너트 세 발, 한 발에 피해 12', kind: 'proj', proj: 'nut', count: 3, gapMs: 120, dmg: 12, speed: 570 },
  repair: { name: '자가수리', desc: 'HP 60 회복', kind: 'self', heal: 60 },
  oil: { name: '기름', desc: '뒤에 기름 구름을 남겨 닿은 상대 상승력 저하', kind: 'puddle', effect: 'heavy', ms: 3000, lifeMs: 9000, r: 33 },
  acorn: { name: '도토리 폭탄', desc: '아래로 떨어지는 폭탄, 피해 30', kind: 'proj', proj: 'acorn', count: 1, dmg: 30, speed: 60, gravity: 780 },
  glide: { name: '활공', desc: '5초 동안 천천히 떨어짐', kind: 'self', ms: 5000 },
  whirl: { name: '회오리', desc: '앞쪽 상대를 2.5초 동안 흔듦', kind: 'debuff', effect: 'shake', ms: 2500, area: 'ahead', range: 690 },
  paper: { name: '종이 표창', desc: '세 갈래 표창, 한 발에 피해 14', kind: 'proj', proj: 'paper', count: 3, spread: 0.26, dmg: 14, speed: 510 },
  fold: { name: '납작 접기', desc: '6초 동안 몸이 작아져 충돌 범위 절반', kind: 'self', ms: 6000 },
  pinwheel: { name: '바람개비', desc: '주변 상대 속도를 3초 동안 낮춤', kind: 'debuff', effect: 'slow', ms: 3000, area: 'around', range: 450 },
};

export const CHARACTERS = [
  {
    id: 'mongsil',
    name: '몽실',
    kind: '구름 양',
    desc: '무엇이든 무난한 균형형',
    stats: { hp: 3, maxSpeed: 3, accel: 3, weight: 3 },
    skills: ['puff', 'dash', 'cloud', 'bolt', 'shield'],
  },
  {
    id: 'kkangdong',
    name: '깡동',
    kind: '깡통 로봇',
    desc: '튼튼하지만 무거워 상승이 느림',
    stats: { hp: 4, maxSpeed: 3, accel: 2, weight: 4 },
    skills: ['nut', 'dash', 'repair', 'oil', 'shield'],
  },
  {
    id: 'doto',
    name: '도토',
    kind: '날다람쥐',
    desc: '가볍고 빠른 기동형',
    stats: { hp: 2, maxSpeed: 4, accel: 4, weight: 2 },
    skills: ['acorn', 'dash', 'glide', 'whirl', 'shield'],
  },
  {
    id: 'palang',
    name: '팔랑',
    kind: '종이비행기',
    desc: '가장 빠르지만 한 대에 약함',
    stats: { hp: 1, maxSpeed: 5, accel: 4, weight: 1 },
    skills: ['paper', 'dash', 'fold', 'pinwheel', 'shield'],
  },
];

export const CHARACTER_BY_ID = Object.fromEntries(CHARACTERS.map((c) => [c.id, c]));

export const STAT_LABELS = { hp: 'HP', maxSpeed: '최대속도', accel: '가속력', weight: '무게' };
