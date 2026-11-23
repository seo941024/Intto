# 인또 그림 규격서

게임 화면에 보이는 그림은 모두 이 규격의 PNG 도트 파일이다. 브라우저는 JSON 아틀라스를 읽어 PNG에서 잘라 그린다. 도형·CSS로 그림을 대신 그리지 않는다.

## 공통 원칙

- 게임 내부 해상도 640×360, 브라우저가 정수배로 확대한다. 그림 1픽셀 = 게임 좌표 1단위.
- RGBA PNG, 안티앨리어싱 없음. 반투명은 유령·안개·빛처럼 꼭 필요할 때만.
- 팔레트는 Endesga 32를 기본으로 쓴다. 꼭 필요할 때만 같은 계열 중간색을 조금 더한다.
  `be4a2f d77643 ead4aa e4a672 b86f50 733e39 3e2731 a22633 e43b44 f77622 feae34 fee761 63c74d 3e8948 265c42 193c3e 124e89 0099db 2ce8f5 ffffff c0cbdc 8b9bb4 5a6988 3a4466 262b44 181425 ff0044 68386c b55088 f6757a e8b796 c28569`
- 외곽선은 순검정 대신 `181425` 또는 해당 색의 어두운 단계. 광원은 왼쪽 위.
- 원작 게임의 그림·캐릭터·로고를 참고하거나 닮게 그리지 않는다. 모두 새 디자인이다.
- 생성 스크립트는 Python 3.10 + Pillow. 실행할 때마다 같은 결과가 나오도록 난수는 고정 시드를 쓴다.
- 미리보기 확대본은 `tools/art/_preview/`에 저장한다. 이 폴더는 git에서 뺀다.

## JSON 아틀라스 형식

```json
{
  "image": "sheet.png",
  "frameWidth": 32,
  "frameHeight": 32,
  "animations": {
    "fly":    { "frames": [0, 1, 2, 3], "fps": 10, "anchor": [16, 17] },
    "rock_a": { "frames": [[0, 64, 32, 32]], "anchor": [16, 16] }
  }
}
```

- `image`는 JSON 파일 기준 상대 경로.
- 숫자 프레임 i는 격자 칸이다. 열 수 = 이미지 너비 / frameWidth, 칸 = `(i % 열 수, floor(i / 열 수))`.
- 배열 프레임 `[x, y, w, h]`는 픽셀 사각형이다. 생성 스크립트가 쓰는 아틀라스는 이 방식이 편하다.
- `anchor`는 프레임 안에서 게임 좌표가 가리키는 점. 생략하면 프레임 중앙.
- `fps` 생략 시 1. `loop` 생략 시 true.
- 필요한 경우 애니메이션에 `"hit": {"r": 12}` 또는 `"hit": {"x": -20, "y": -10, "w": 40, "h": 20}`처럼 충돌 범위를 적는다. 좌표는 anchor 기준.

## 1. 캐릭터 — 담당 A

경로 `public/assets/characters/<id>/sheet.png`, `sprite.json`, `portrait.png`

| id | 이름 | 콘셉트 | 대표 색 |
|---|---|---|---|
| mongsil | 몽실 | 구름처럼 몽글몽글한 양털 몸, 짙은 얼굴과 큰 눈, 작은 구름 조각을 날개처럼 퍼덕임 | 흰색·하늘색 |
| kkangdong | 깡동 | 원통 깡통 로봇, 빨간 라벨 띠와 리벳, 머리 위 프로펠러로 날고 렌즈 눈 두 개 | 은색·빨강 |
| doto | 도토 | 날다람쥐, 주황 갈색 털과 크림색 배, 앞뒤 다리 사이 비막을 펼쳐 활공, 큰 꼬리 | 주황·갈색 |
| palang | 팔랑 | 살아 있는 종이비행기, 크림색 종이 몸에 파란 접힘선, 그려 넣은 듯한 귀여운 눈 | 크림·파랑 |

- 프레임 32×32, 모두 오른쪽을 본다. 한 줄로 9프레임, 이미지 288×32.
  - 0~3 `fly` 날갯짓 반복, fps 10
  - 4~5 `boost` 가속 중 자세, 몸을 앞으로 기울이고 뒤로 바람 줄, fps 14
  - 6 `hurt` 맞았을 때, 눈을 질끈 감거나 X눈
  - 7~8 `ghost` 유령 상태, 창백한 반투명 하늘색, 아래가 물결 꼬리, fps 4
- 몸통 중심이 anchor. 몸통은 대략 20×18 픽셀 안에 들어오게 하고 `sprite.json`에 `"hitRadius": 8`을 적는다.
- `portrait.png` 48×48, 로비 캐릭터 선택 카드에 쓰는 상반신 또는 전신 정면 그림. 투명 배경.
- 지수가 나중에 이 폴더의 PNG와 JSON을 자기 그림으로 바꿔 넣는다. 그래서 JSON은 사람이 읽기 쉬운 숫자 프레임 방식으로 쓴다.

```json
{
  "image": "sheet.png",
  "frameWidth": 32,
  "frameHeight": 32,
  "hitRadius": 8,
  "animations": {
    "fly":   { "frames": [0, 1, 2, 3], "fps": 10, "anchor": [16, 17] },
    "boost": { "frames": [4, 5], "fps": 14, "anchor": [16, 17] },
    "hurt":  { "frames": [6], "anchor": [16, 17] },
    "ghost": { "frames": [7, 8], "fps": 4, "anchor": [16, 17] }
  }
}
```

## 2. 아이템 — 담당 A

`public/assets/items/items.png`, `items.json`, 프레임 16×16

- `gemBlue` 4프레임 반짝임 또는 회전, fps 8. 파란 보석, 기술칸 한 칸 이동
- `gemRed` 4프레임, fps 8. 빨간 보석, 보호막 칸으로 바로 이동. 파란 것보다 화려하게
- `food` 2프레임 둥실, fps 3. 회복 아이템 붕어빵
- `feather` 4프레임 살랑, fps 6. 기본 속도를 올리는 깃털, 흰색·금색

## 3. 효과·발사체 — 담당 A

`public/assets/fx/fx.png`, `fx.json`, 배열 프레임 방식

| 이름 | 크기 | 프레임 | 용도 |
|---|---|---|---|
| puff | 16×16 | 2 | 몽실 솜뭉치 발사체 |
| nut | 16×16 | 4 | 깡동 너트, 회전 |
| acorn | 16×16 | 2 | 도토 도토리 폭탄, 아래로 떨어짐 |
| paper | 16×16 | 4 | 팔랑 종이 표창, 회전 |
| boltSeg | 16×32 | 3 | 번개 줄기, 세로로 이어 붙임 |
| boltHit | 32×32 | 3 | 번개가 떨어진 자리 |
| warn | 24×24 | 2 | 번개 조준 표시, 대상 머리 위 |
| oil | 48×16 | 2 | 깡동 기름 웅덩이, 공중에 떠 있는 끈적한 기름 구름 |
| hit | 32×32 | 4 | 피해를 입은 순간 터짐 |
| shield | 32×32 | 2 | 보호막, 캐릭터 위에 겹쳐 그림, 반투명 |
| dash | 48×24 | 3 | 대시 잔상, 캐릭터 뒤에 그림 |
| revive | 32×32 | 4 | 유령이 부활할 때 |
| pickup | 16×16 | 4 | 보석·아이템을 먹을 때 반짝 |
| whirl | 24×24 | 3 | 회오리에 흔들리는 대상 위 |
| fog | 96×48 | 1 | 먹구름에 가려진 화면을 덮는 구름 덩어리, 반투명 |
| nice | 64×24 | 1 | NICE 글자 |
| kill | 64×24 | 1 | KILL 글자 |

## 4. HUD — 담당 A

`public/assets/ui/ui.png`, `ui.json`, 배열 프레임 방식

| 이름 | 크기 | 비고 |
|---|---|---|
| heartFull, heartEmpty | 13×12 | 생명 하트 |
| hpFrame | 106×12 | 안쪽 채움 영역은 (3,3)부터 100×6 |
| hpFill, hpFillLow | 1×6 | 가로로 늘려 그림. Low는 HP 30% 이하 |
| slotFrame | 26×26 | 기술칸 테두리 |
| slotActive | 30×30, 2프레임 | 현재 칸 표시, 깜빡임 |
| icon_puff, icon_dash, icon_cloud, icon_bolt, icon_shield, icon_nut, icon_repair, icon_oil, icon_acorn, icon_glide, icon_whirl, icon_paper, icon_fold, icon_pinwheel | 18×18 | 기술 아이콘 |
| rankRow, rankRowSelf | 150×18 | 순위표 한 줄 배경, Self는 내 줄 강조 |
| miniBar | 240×12 | 미니맵 막대 |
| miniMarker0~3 | 7×8 | 플레이어 1~4 색 표식, 아래를 가리키는 화살 모양 |
| miniMarkerSelf | 9×10 | 내 표식, 흰 테두리 |
| timerPlate | 64×20 | 남은 시간 판 |
| crown, check, ghostIcon, skull, featherIcon | 11×10 이하 | 방장·준비·유령·탈락·깃털 수 |
| debuff_blind, debuff_heavy, debuff_shake, debuff_slow, buff_glide, buff_shrink | 12×12 | 캐릭터 머리 위 상태 표시 |
| teamA, teamB | 14×14 | 팀 표식, A는 빨강 계열, B는 파랑 계열 |
| num3, num2, num1, go | 64×48 이하 | 출발 카운트다운 큰 글자 |

플레이어 색: P1 `e43b44`, P2 `0099db`, P3 `63c74d`, P4 `feae34`.

## 5. 로비 화면 — 담당 A

`public/assets/ui/` 아래. HTML 화면이 CSS `border-image`와 `background-image`로 쓴다.

| 파일 | 크기 | 비고 |
|---|---|---|
| panel.png | 24×24 | 9-slice, 테두리 8px, 안쪽은 반복 가능한 무늬 |
| button.png, button_hover.png, button_down.png | 24×24 | 9-slice, 테두리 6px |
| button_primary.png, button_primary_hover.png | 24×24 | 시작·준비 같은 주 버튼, 노랑 계열 |
| input.png | 24×24 | 9-slice, 테두리 6px, 글 입력칸 |
| card.png, card_selected.png | 24×24 | 9-slice, 테두리 8px, 캐릭터·맵 선택 카드 |
| logo.png | 가로 200 안팎 | 게임 이름 "인또" 로고. `node_modules/galmuri/dist/Galmuri11-Bold.ttf`를 원본 크기로 찍어 정수배 확대 후 외곽선·그림자·하이라이트를 더하거나 손으로 그린다. 날개 모티프 가능 |
| lobby_bg.png | 128×128 | 로비 배경 반복 무늬, 차분하게 |

## 6. 월드 — 담당 B

테마 3개: `cloud` 구름섬, `mushroom` 버섯숲, `storm` 폭풍협곡. 경로 `public/assets/world/<theme>/`

| 테마 | 분위기 |
|---|---|
| cloud | 맑은 낮 하늘, 흰 구름 바다, 바닥은 풀이 덮인 떠 있는 섬 바위, 천장은 뒤집힌 구름 덩어리 |
| mushroom | 해 질 녘 보라·분홍 숲, 바닥은 이끼와 버섯이 자라는 흙, 천장은 얽힌 뿌리와 나뭇잎 |
| storm | 밤의 남색 폭풍, 비, 바닥과 천장은 어두운 협곡 바위에 빛나는 수정 |

### 배경

- `sky.png` 640×360, 움직이지 않는 하늘. 디더링으로 그라데이션, 해·달·별 등
- `far.png` 640×360, 가로로 끊김 없이 반복, 빈 곳 투명. 스크롤 배율 0.15
- `mid.png` 640×360, 가로 반복, 빈 곳 투명. 스크롤 배율 0.4
- 배경은 지형보다 채도·명도 대비를 낮춰 지형과 장애물이 잘 보이게 한다.
- `preview.png` 160×90, 로비 맵 선택 카드용 축소 장면. 스크립트에서 합성해도 된다.

### 지형 타일

`tiles.png`, `tiles.json`, 배열 프레임 방식. 지형은 위아래 경계선이 매끄러운 높이 함수라서, 엔진이 4픽셀 폭 세로줄로 잘라 경계선 높이에 맞춰 찍는다.

| 이름 | 크기 | 비고 |
|---|---|---|
| floorEdge | 16×12 | 바닥 윗면 띠, 가로 반복. anchor y = 실제 경계선 위치. 풀·이끼가 경계선 위로 2~3픽셀 삐져나와도 됨 |
| floorBody | 32×32 | 바닥 속, 상하좌우 반복 |
| ceilEdge | 16×12 | 천장 아랫면 띠, 가로 반복. anchor y = 경계선 위치. 고드름·뿌리가 아래로 삐져나와도 됨 |
| ceilBody | 32×32 | 천장 속, 상하좌우 반복 |

장식은 충돌 없이 경계선에 붙여 찍는다. `decor_floor_a`, `decor_floor_b`, `decor_floor_c`는 anchor가 아래 가운데, `decor_ceil_a`, `decor_ceil_b`는 anchor가 위 가운데, 크기 16×16 또는 16×24.

입자 하나: `particle`, 8×8 이하 1~2프레임. cloud는 작은 꽃잎이나 구름 조각, mushroom은 반딧불, storm은 빗방울.

### 장애물

`obstacles.png`, `obstacles.json`, 배열 프레임 방식. 이름과 충돌 범위는 엔진과 맞춰야 하므로 아래를 그대로 따른다. 충돌 원 반지름보다 그림이 1~3픽셀 크게.

| 테마 | 이름 | 크기 | 프레임 | 충돌 | 설명 |
|---|---|---|---|---|---|
| cloud | rock_a, rock_b, rock_c | 32×32 | 1 | 원 r=12 | 떠 있는 바위 조각, 아래에 작은 풀·뿌리 |
| cloud | bigrock | 48×48 | 1 | 원 r=18 | 큰 떠 있는 바위 |
| cloud | balloon | 32×32 | 2 | 원 r=11 | 위아래로 떠다니는 가시 풍선 |
| mushroom | mushroom | 48×32 | 2 | 사각 x -20, y -6, w 40, h 16 | 바닥에 붙은 튕김 버섯. anchor는 버섯 갓 윗면 가운데에서 6픽셀 아래, 1프레임은 평소, 2프레임은 눌린 모양. 줄기 아래 끝이 프레임 바닥 |
| mushroom | thorn_a, thorn_b | 32×32 | 1 | 원 r=12 | 가시덤불 덩어리 |
| mushroom | spore | 24×24 | 2 | 원 r=9 | 떠다니는 독 포자 |
| storm | crystal_a, crystal_b | 32×32 | 1 | 원 r=12 | 떠 있는 날카로운 수정 |
| storm | stormorb | 32×32 | 3 | 원 r=11 | 위아래로 움직이는 전기 구슬 |
| storm | pylonTop | 24×24 | 1 | 없음 | 천장에 붙은 번개 발생기, anchor 위 가운데 |
| storm | pylonBottom | 24×24 | 1 | 없음 | 바닥에 붙은 번개 발생기, anchor 아래 가운데 |
| storm | beam | 16×32 | 3 | 엔진이 폭 12 | 번개 기둥, 세로로 이어 붙임, 깜빡임 |
| storm | beamWarn | 16×32 | 2 | 없음 | 번개 직전 예고, 얇은 점선 빛 |

## 7. 완료 확인

- 모든 JSON이 가리키는 PNG가 존재하고, 프레임 사각형이 이미지 안에 있다.
- `tools/art/_preview/`에 확대 미리보기를 만들어 직접 보고, 어색한 그림은 고친다.
- 스크립트 하나만 다시 돌리면 모든 그림이 다시 만들어진다.
