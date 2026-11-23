"""ChatGPT로 받은 효과·아이콘 시트 한 장으로 경기 효과, 작은 아이콘, 조작 키 그림을 만든다.

  art_inbox/fx_sheet_v1.webp  마젠타 바탕 다섯 줄
    1줄 공격  솜뭉치 너트 도토리 표창 번개줄기 번개맞음 기름 회오리
    2줄 효과  맞음 보호막 대시 부활반짝이 보석반짝이 경고 먹구름 가속바람줄 구름부스러기
    3줄 상태  비구름 무게 흔들림 달팽이 날개 안쪽화살표 / 플레이어 화살표 빨강 파랑 초록 노랑 / 별
    4줄 글자  3 2 1 GO! NICE! KILL!
    5줄 키    마우스왼쪽 마우스오른쪽 SPACE ↑ → Enter W D M
  art_inbox/keys_zx_v1.webp   같은 모양으로 따로 받은 Z, X 키. 기술 Z, 가속 X
출력
  public/assets/fx/fx.png, fx.json                       효과, 상태 아이콘, 플레이어 화살표, 카운트다운, 조작 키
  public/assets/fx/particles.png, particles.json         가속 바람줄
  public/assets/characters/mongsil/trail.png, trail.json 몽실 구름 부스러기
크기는 게임에서 그 그림이 차지하던 칸에 비율을 지켜 맞춘다. 단위는 경기 화면 960×540 기준 픽셀이고 월드 그림은 맵 단위다.
같은 줄에서 나란히 쓰는 숫자와 키는 한 배율로 줄여 그림 속 크기 차이를 그대로 둔다.
따로 받은 Z, X 키는 W 키와 같은 높이로 맞춘다. 지금 조작에 없는 SPACE, →, W, D 키는 싣지 않는다.
res 2880으로 넣어 큰 화면에서도 늘리지 않고 줄여 그린다.
대시 줄은 받은 그림이 왼쪽으로 달리는 모양이라 좌우만 뒤집어, 오른쪽으로 나는 캐릭터 뒤에 꼬리가 남게 한다.
부활 반짝이와 별은 지금 쓰는 곳이 없어 싣지 않는다.
사용
  python tools/art/make_fx.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_scene import unkey  # noqa: E402
from pack_concept import Packer, write_atlas, scaled  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art_inbox" / "fx_sheet_v1.webp"
ZX_SRC = ROOT / "art_inbox" / "keys_zx_v1.webp"
ASSETS = ROOT / "public" / "assets"
RES = 2880
PX = RES / 960  # 게임 1픽셀에 담는 그림 픽셀 수

# 줄마다 왼쪽부터의 이름과, 한 그림 안에서 떨어진 조각을 하나로 붙이는 틈 범위
ROWS = [
    (["puff", "nut", "acorn", "paper", "boltSeg", "boltHit", "oil", "whirl"], (0, 0)),
    (["hit", "shield", "dash", "revive", "pickup", "warn", "fog", "streak", "trail"], (0, 5)),
    (["debuff_blind", "debuff_heavy", "debuff_shake", "debuff_slow", "buff_glide", "buff_shrink",
      "miniMarker0", "miniMarker1", "miniMarker2", "miniMarker3", "star"], (20, 30)),
    (["num3", "num2", "num1", "go", "nice", "kill"], (0, 0)),
    (["keyMouseL", "keyMouseR", "keySpace", "keyUp", "keyRight", "keyEnter", "keyW", "keyD", "keyM"], (0, 0)),
]
SKIP = {"revive", "star"}
UNUSED_KEYS = {"keySpace", "keyRight", "keyW", "keyD"}  # 기술 Z, 가속 X로 바뀌어 쓰지 않는 키
FLIP = {"dash"}

# 칸 크기, 게임 픽셀. 그림을 비율 그대로 이 칸 안에 넣는다
BOX = {
    "puff": (24, 24), "nut": (24, 24), "acorn": (24, 24), "paper": (24, 24),
    "boltSeg": (24, 48), "boltHit": (48, 48),
    "oil": (72, 72),  # 기름 구름 판정 반지름 33에 맞춘다
    "whirl": (36, 36), "hit": (48, 48),
    "shield": (60, 60),  # 캐릭터 몸을 감싸는 크기
    "dash": (72, 36), "pickup": (32, 32), "warn": (36, 36),
    "fog": (144, 110),  # 눈가림. 화면 좌표로 그린다
    "nice": (96, 36), "kill": (96, 36),
    "debuff_blind": (18, 18), "debuff_heavy": (18, 18), "debuff_shake": (18, 18),
    "debuff_slow": (18, 18), "buff_glide": (18, 18), "buff_shrink": (18, 18),
}
# 한 배율로 맞추는 묶음: 이름들, 기준 이름의 높이
GROUPS = [
    (["miniMarker0", "miniMarker1", "miniMarker2", "miniMarker3"], 12),
    (["num3", "num2", "num1", "go"], 72),  # 출발 카운트다운. 화면 좌표로 그린다
    (["keyMouseL", "keyMouseR", "keySpace", "keyUp", "keyRight", "keyEnter", "keyW", "keyD", "keyM"], 21),
]
STREAK_BOX = (40, 12)  # 가속 바람줄. 오른쪽 끝을 캐릭터 뒤에 붙인다
TRAIL_BOX = (12, 12)  # 몽실 부스러기
TRAIL_EMIT = {"flyFrame": 2, "at": [-22, -6], "lifeMs": 900}  # 날개를 내려치는 프레임에서 몸 뒤쪽 아래에 떨어뜨린다


def pieces(src=SRC, rows_spec=None):
    """줄마다 빈 세로줄로 그림을 가르고, 틈이 범위 안인 조각은 한 그림으로 붙인다"""
    rows_spec = rows_spec or ROWS
    k = unkey(np.asarray(Image.open(src).convert("RGB")))
    img = Image.fromarray(np.clip(k, 0, 255).astype(np.uint8), "RGBA")
    a = k[..., 3] > 100
    rows = a.any(1)
    bands = []
    y = 0
    while y < a.shape[0]:
        if rows[y]:
            y0 = y
            while y < a.shape[0] and rows[y]:
                y += 1
            if y - y0 > 20:
                bands.append((y0, y))
        y += 1
    assert len(bands) == len(rows_spec), f"줄 {len(bands)}개"
    out = {}
    for (names, (lo, hi)), (y0, y1) in zip(rows_spec, bands):
        cols = a[y0:y1].any(0)
        segs = []
        x = 0
        while x < len(cols):
            if cols[x]:
                x0 = x
                while x < len(cols) and cols[x]:
                    x += 1
                if segs and lo < x0 - segs[-1][1] <= hi:
                    segs[-1] = (segs[-1][0], x)
                else:
                    segs.append((x0, x))
            x += 1
        assert len(segs) == len(names), f"{names[0]} 줄 조각 {len(segs)}개, 이름 {len(names)}개"
        for n, (x0, x1) in zip(names, segs):
            c = img.crop((x0, y0, x1, y1))
            out[n] = c.crop(c.getbbox())
    return out


def fit(img, box):
    k = min(box[0] * PX / img.width, box[1] * PX / img.height)
    return scaled(img, k)


def main():
    src = pieces()
    for n in FLIP:
        src[n] = ImageOps.mirror(src[n])
    imgs = {}
    for n, box in BOX.items():
        imgs[n] = fit(src[n], box)
    for names, h in GROUPS:
        k = h * PX / max(src[n].height for n in names)
        for n in names:
            imgs[n] = scaled(src[n], k)
    zx = pieces(ZX_SRC, [(["keyZ", "keyX"], (0, 0))])
    for n, im in zx.items():
        imgs[n] = scaled(im, imgs["keyW"].height / im.height)
    for n in UNUSED_KEYS:
        del imgs[n]

    p = Packer(2048)
    anims = {}
    for n, im in imgs.items():
        anims[n] = {"frames": [p.add(im)]}
    write_atlas(ASSETS / "fx", "fx", p, anims, res=RES)

    st = fit(src["streak"], STREAK_BOX)
    p = Packer(512)
    rect = p.add(st)
    write_atlas(ASSETS / "fx", "particles", p, {"streak": {"frames": [rect], "anchor": [st.width - 1, st.height // 2]}}, res=RES)

    tr = fit(src["trail"], TRAIL_BOX)
    p = Packer(256)
    rect = p.add(tr)
    write_atlas(ASSETS / "characters" / "mongsil", "trail", p, {"trail": {"frames": [rect], "anchor": [tr.width // 2, tr.height // 2]}},
                extra={"emit": TRAIL_EMIT}, res=RES)
    for n in sorted(set(src) - set(imgs) - {"streak", "trail"} - SKIP - UNUSED_KEYS):
        print("쓰지 않은 조각", n)


if __name__ == "__main__":
    main()
