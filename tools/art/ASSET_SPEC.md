# 인또 그림 규격서

게임 그림은 ChatGPT로 받은 원본을 `art_inbox/`에 두고, `tools/art/`의 파이썬 도구로 잘라 `public/assets/`에 넣는다. 원본은 대개 마젠타 바탕이고 도구가 마젠타를 걷어 투명하게 만든다. 브라우저는 JSON 아틀라스를 읽어 PNG에서 잘라 그린다.

- 도구는 모두 프로젝트 루트에서 돌린다. Python 3.10, Pillow, numpy를 쓰고 `tools/make_music.py`는 soundfile도 쓴다.
- 받은 그림은 비율을 바꾸지 않고 원본보다 키우지 않는다.
- `art_inbox/out/`은 도구가 다시 만드는 중간 결과라 git에 올리지 않는다. `pack_concept.py`가 읽는 `art_inbox/out/cut/` 조각 여섯 장만 올린다.
- `tools/art/_preview/`는 확인용 확대본을 두는 곳이고 git에 올리지 않는다.

## 크기 규칙

- 첫 화면과 경기 화면은 960×540 게임 픽셀이다. 그림이 원본 픽셀 그대로 보이는 이 크기까지만 키우고, 창이 더 크면 남는 곳은 어두운 여백으로 둔다.
- 아틀라스의 `res`는 그림을 몇 픽셀 폭 화면 기준으로 담았는지다. 게임은 그림 1픽셀을 k = 960 / res 좌표 단위로 그린다. `res`가 없으면 640 기준 임시 그림으로 보고 k = 1.5로 그린다.
- 맵은 카메라가 `cameraZoom` 1.5배로 당겨 본다. 그래서 맵 위 그림은 res 1440으로 넣는다. k = 2/3에 1.5배가 곱해져 그림 1픽셀이 화면 1픽셀이 된다.
- 화면 좌표로 그리는 그림은 res 960이면 1:1이다. res 1920, 2880은 두 배, 세 배 픽셀로 담아 줄여 그린다.
- 땅 그림은 `make_terrain.py`의 ART_SCALE 2/3을 더 곱한다. 카메라가 당겨도 시안을 960 화면에 맞춘 크기 그대로 보인다. 지형 경계선 좌표는 그대로다.
- 장애물과 아이템은 `pack_concept.py`의 ART_SCALE 1.0이다. 그림 크기가 부딪힘 크기와 같다.
- 배경 `sky.png`, `far.png`, `mid.png`는 아틀라스가 아닌 PNG다. 높이 540으로 화면 좌표에 그린다. far와 mid는 가로로 이어 붙이고 경기에서 0.15배, 0.4배로 흐른다.

| 아틀라스 | res | 그리는 자리 |
|---|---|---|
| `characters/<id>/sprite.json`, `items/items.json`, `world/<theme>/tiles.json`, `obstacles.json` | 1440 | 맵 |
| `fx/fx.json`, `fx/particles.json`, `characters/mongsil/trail.json` | 2880 | 맵, 카운트다운과 눈가림은 화면 |
| `ui/ui.json` | 1920 | 경기 HUD와 대기실 아이콘 |
| `ui/hud.json`, `ui/logo_parts.json` | 960 | 화면 |

## JSON 아틀라스 형식

```json
{
  "image": "sheet.png",
  "res": 1440,
  "frameWidth": 112,
  "frameHeight": 96,
  "animations": {
    "fly":  { "frames": [0, 1, 2, 3], "fps": 10, "anchor": [56, 58] },
    "rock_a": { "frames": [[0, 0, 75, 70]], "anchor": [37, 36], "hit": { "r": 18 } }
  }
}
```

- `image`는 JSON 파일 기준 상대 경로다.
- 숫자 프레임 i는 frameWidth×frameHeight 격자 칸이고, 배열 프레임 `[x, y, w, h]`는 픽셀 사각형이다.
- `anchor`는 게임 좌표가 가리키는 프레임 안의 점이다. 없으면 프레임 가운데다.
- `fps`가 없으면 1, `loop`가 없으면 되풀이한다.
- `hit`은 anchor 기준 부딪힘 범위를 맵 단위로 적은 참고값이다. 원은 `{"r"}`, 네모는 `{"x", "y", "w", "h"}`다. 실제 판정은 `shared/mapgen.js`의 OBSTACLE_GEOM이 정하므로 크기를 바꾸면 그쪽과 맞춘다.
- 파일마다 덧붙는 값: `sprite.json`의 `hitRadius`, `trail`, `trail.json`의 `emit`, `tiles.json`의 `decor`, `bodyGap`, `hud.json`의 `hpFillRect`, `miniFillRect`, `timerTextX`, `timerTextY`, `rankBadge`, `logo_parts.json`의 `layout`, `follow`, `order`.

## 도구와 출력

### 배경 `import_scene.py`

`world/<theme>/sky.png`, `far.png`, `mid.png`

```
python tools/art/import_scene.py sky art_inbox/cloud_sky_v1.webp --out public/assets/world/cloud/sky.png
python tools/art/import_scene.py band art_inbox/cloud_far_v1.webp --out public/assets/world/cloud/far.png --bottom 478
python tools/art/import_scene.py scatter art_inbox/cloud_mid_v1.webp --out public/assets/world/cloud/mid.png --scale 0.42 --scales 1,0.9,1.1,0.85,1 --tops 190,290,150,240,320
python tools/art/import_scene.py sky art_inbox/mushroom_sky_v1.png --out public/assets/world/mushroom/sky.png
python tools/art/import_scene.py band art_inbox/mushroom_far_v1.png --out public/assets/world/mushroom/far.png --bottom 470 --seam cut
python tools/art/import_scene.py scatter art_inbox/mushroom_mid_v1.png --out public/assets/world/mushroom/mid.png --scale 0.31 --scales 1 --tops 190,290,150,240,320 --haze-color 195,137,157
python tools/art/import_scene.py sky art_inbox/storm_sky_v1.png --out public/assets/world/storm/sky.png
python tools/art/import_scene.py band art_inbox/storm_far_v1.png --out public/assets/world/storm/far.png --bottom 470 --seam cut
python tools/art/import_scene.py scatter art_inbox/storm_mid_v1.png --out public/assets/world/storm/mid.png --scale 0.3 --scales 1 --tops 190,290,150,240,320 --haze-color 73,80,204
```

### 땅 `compose_ceiling.py`, `make_terrain.py`

`compose_ceiling.py`는 구름섬 지형 원본에 외곽선 있는 천장 띠를 옮겨 붙여 `art_inbox/cloud_terrain_v2.png`를 만든다. `make_terrain.py`는 `world/<theme>/tiles.png`, `tiles.json`을 만든다. 입자 `particle` 프레임은 원본에서 만들지 않고 덮어쓰기 전 `tiles.json`에서 그대로 옮겨 싣는다.

```
python tools/art/compose_ceiling.py
python tools/art/make_terrain.py art_inbox/cloud_terrain_v2.png --theme cloud --floor-pct 80 --tall 10 --cut 4 --ceil-tall 9999 --seam cut --ceil-solid 62
python tools/art/make_terrain.py art_inbox/mushroom_terrain_v1.png --theme mushroom --ceil-pct 15 --floor-pct 85 --ceil-grow --ceil-body 510:1150 --seam cut
python tools/art/make_terrain.py art_inbox/storm_terrain_v1.png --theme storm --floor-pct 85 --ceil-tall 9999 --cut 16 --seam cut
```

### 아이템·장애물 `cut_concept.py`, `pack_concept.py`, `pack_world_obstacles.py`

`cut_concept.py`는 구름섬 시안 `concept_cloud_v1.webp`에서 조각을 오려 `art_inbox/out/cut/`에 둔다. `pack_concept.py`는 그중 여섯 장으로 `items/items.png`, `items.json`과 `world/cloud/obstacles.png`, `obstacles.json`을 만든다. `pack_world_obstacles.py`는 `<theme>_obstacles_v1.png`로 버섯숲·폭풍협곡 `obstacles.png`, `obstacles.json`을 만든다.

```
python tools/art/cut_concept.py
python tools/art/pack_concept.py
python tools/art/pack_world_obstacles.py --theme mushroom
python tools/art/pack_world_obstacles.py --theme storm
```

### 맵 미리보기 `make_preview.py`

맵의 실제 그림을 게임 배율로 한 장에 놓아 `world/<theme>/preview.png` 320×180을 만든다.

```
python tools/art/make_preview.py --theme cloud
python tools/art/make_preview.py --theme mushroom
python tools/art/make_preview.py --theme storm
```

### 효과 `make_fx.py`

`fx_sheet_v1.webp`, `keys_zx_v1.webp`로 `fx/fx.png`, `fx.json`, `fx/particles.png`, `particles.json`, `characters/mongsil/trail.png`, `trail.json`을 만든다.

```
python tools/art/make_fx.py
```

### 캐릭터 `build_hd_character.py`, `make_portraits.py`

`build_hd_character.py`는 자세 세 개 그림과 나는 모습 4프레임 그림으로 `characters/<id>/sheet.png`, `sprite.json`을 만든다. 같은 폴더에 `trail.json`이 있으면 `sprite.json`에 이어 적는다. `make_portraits.py`는 `hud_faces_flag_v1.png`의 얼굴과 `random_sheet_v1.png`의 물음표로 `characters/<id>/portrait.png` 96×96 다섯 장을 만든다.

```
python tools/art/build_hd_character.py art_inbox/mongsil_v2.webp --id mongsil --mode bob --src-scale 0.214876 --fly-frames art_inbox/mongsil_fly_v1.png
python tools/art/build_hd_character.py art_inbox/kkangdong_v1.webp --id kkangdong --mode bob --src-scale 0.214876 --fly-frames art_inbox/kkangdong_fly_v1.png
python tools/art/build_hd_character.py art_inbox/doto_v1.webp --id doto --mode bob --src-scale 0.214876 --fly-frames art_inbox/doto_fly_v1.png
python tools/art/build_hd_character.py art_inbox/palang_v1.webp --id palang --mode bob --strip-left --src-scale 0.214876 --fly-frames art_inbox/palang_fly_v1.png
python tools/art/make_portraits.py
```

### HUD·화면 `make_hud.py`, `make_ui_kit.py`, `make_logo.py`, `make_random.py`, `make_press_start.py`

| 도구 | 입력 | 출력 |
|---|---|---|
| `make_hud.py` | `hud_parts_v1.png`, `hud_digits_v1.png`, `hud_faces_flag_v1.png`, `icons_v1.webp` | `ui/hud.png`, `hud.json` |
| `make_ui_kit.py` | `ui_kit_v1.png`, `ui_icons_v1.png` | `ui/panel.png`, `button*.png`, `card*.png`, `input.png`, `lobby_bg.png`, `ui/ui.png`, `ui.json`, 그리고 CSS에 옮겨 적는 자르는 폭 `tools/art/ui_kit.json` |
| `make_logo.py` | `logo_v2.webp` | `ui/logo_parts.png`, `logo_parts.json`, `ui/logo.png` |
| `make_random.py` | `random_sheet_v2.png` | `ui/map_random.png` |
| `make_press_start.py` | `press_start_v1.png` | `ui/press_start.png` |

```
python tools/art/make_hud.py
python tools/art/make_ui_kit.py
python tools/art/make_logo.py art_inbox/logo_v2.webp
python tools/art/make_random.py
python tools/art/make_press_start.py
```

### 배경음 `tools/make_music.py`

`art_inbox/music/<이름>_v1.ogg`로 `music/<이름>.ogg`, `<이름>.mp3`, `music.json`을 만든다.

```
python tools/make_music.py
```

`artlib.py`와 `paper_doll.py`는 직접 돌리지 않는다. 다른 도구가 마젠타 걷기, 알파를 곱한 줄이기, 밝기, 조각 찾기 같은 함수를 가져다 쓴다.

## 돌리는 순서

순서가 정해진 것만 적는다. 나머지는 아무 때나 돌려도 된다.

1. `compose_ceiling.py`를 먼저, 그다음 `make_terrain.py --theme cloud`. 구름섬 땅은 `cloud_terrain_v2.png`를 읽는다.
2. `cut_concept.py`를 먼저, 그다음 `pack_concept.py`.
3. 땅, 장애물, 아이템, 배경을 모두 만든 뒤 `make_preview.py`. 미리보기는 이 그림들을 읽어 합친다.
4. `make_fx.py`를 먼저, 그다음 `build_hd_character.py`. 그래야 몽실 `sprite.json`에 `trail.json`이 이어진다.
5. `make_terrain.py`는 지금 `tiles.json`의 입자 프레임을 옮겨 실으므로, 돌리기 전에 `tiles.json`을 지우지 않는다.
