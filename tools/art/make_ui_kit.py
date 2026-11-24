"""ChatGPT로 받은 UI 그림 두 장으로 로비·대기실 틀과 아이콘을 만든다.

  art_inbox/ui_kit_v1.png    큰 패널, 파란 버튼 셋, 노란 버튼 둘, 카드 둘, 입력칸, 바탕 무늬
  art_inbox/ui_icons_v1.png  왕관, 체크, A·B 깃발, 별 셋, 유령, 해골, 깃털
출력
  public/assets/ui/panel.png, button*.png, card*.png, input.png, lobby_bg.png   CSS border-image로 늘려 쓰는 틀
  public/assets/ui/ui.png, ui.json   아이콘 열 개만 담은 아틀라스. 게임이 쓰는 프레임 이름 그대로
  tools/art/ui_kit.json              틀마다 자르는 폭. CSS에 옮겨 적는 참고값이고 게임은 읽지 않는다
틀은 비율을 바꾸지 않고 FRAME_K로 줄인 뒤, 가운데가 한 색으로 고르게 시작하는 자리를 잘라 쓰는 폭으로 잰다.
아이콘은 res 1920으로 넣어 게임이 0.5배로 그린다. 높이 ICON_H는 res가 없던 예전 아틀라스 11픽셀의 세 배라
화면 크기는 예전에 1.5배로 그리던 크기와 같다.
사용
  python tools/art/make_ui_kit.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import unkey, shrink, crop_box  # noqa: E402
from pack_concept import Packer, write_atlas  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
UI = ROOT / "public" / "assets" / "ui"
SLICES = Path(__file__).resolve().parent / "ui_kit.json"
FRAME_K = 0.4  # 틀 그림을 줄이는 배율
ICON_RES = 1920  # 아이콘 아틀라스 res. 게임은 960 / 1920 = 0.5배로 그린다
ICON_H = 33  # 아이콘 높이, 아틀라스 픽셀. 게임 화면 16.5픽셀, 대기실은 4/3배 더 키워 22픽셀

# 부품 상자: 원본 좌표 x, y, w, h
KIT = {
    "panel": (46, 72, 728, 448),
    "button": (850, 98, 394, 130),
    "button_hover": (850, 248, 396, 134),
    "button_down": (850, 400, 394, 128),
    "button_primary": (1310, 124, 330, 136),
    "button_primary_hover": (1310, 284, 330, 138),
    "card": (46, 594, 266, 256),
    "card_selected": (350, 572, 290, 302),
    "input": (694, 654, 550, 140),
}
TILE = (1318, 550, 308, 316)
ICONS = {
    "crown": (84, 198, 232, 192), "check": (418, 214, 214, 176), "teamA": (736, 182, 224, 224),
    "teamB": (1060, 182, 226, 224), "pipFull": (1374, 194, 218, 208), "pipHalf": (84, 526, 220, 206),
    "pipEmpty": (410, 526, 218, 206), "ghostIcon": (736, 530, 214, 212), "skull": (1072, 528, 196, 196),
    "featherIcon": (1382, 534, 210, 208),
}


def crop(keyed, box):
    """x, y, w, h 상자를 6픽셀 여유를 두고 잘라 그림이 있는 자리만 남긴다"""
    x, y, w, h = box
    return crop_box(keyed, (x, y, x + w, y + h), pad=6)


def seamless_tile(img, n):
    """오른쪽·아래 끝 n줄을 왼쪽·위 시작과 섞어 이어 붙여도 줄이 안 보이게 한다"""
    a = np.array(img).astype(float)
    t = np.linspace(0, 1, n)
    a = a[:, n:]
    a[:, -n:] = a[:, -n:] * (1 - t)[None, :, None] + np.array(img).astype(float)[:, :n] * t[None, :, None]
    b = a[n:]
    b[-n:] = b[-n:] * (1 - t)[:, None, None] + a[:n] * t[:, None, None]
    return Image.fromarray(np.clip(b, 0, 255).astype(np.uint8))


def slice_width(img):
    """가운데 색이 고르게 시작하는 자리. 그 안쪽은 늘려도 모양이 그대로다"""
    a = np.array(img).astype(float)
    h, w = a.shape[:2]
    cy, cx = h // 2, w // 2
    center = a[cy - 2:cy + 3, cx - 2:cx + 3, :3].reshape(-1, 3).mean(0)
    same = (np.abs(a[..., :3] - center).sum(-1) < 60) & (a[..., 3] > 200)
    for s in range(2, min(h, w) // 2):
        ring = np.concatenate([same[s, s:w - s], same[h - 1 - s, s:w - s], same[s:h - s, s], same[s:h - s, w - 1 - s]])
        if ring.mean() > 0.97:
            return s + 1
    return min(h, w) // 3


def main():
    kit = unkey(np.array(Image.open(INBOX / "ui_kit_v1.png").convert("RGB")))
    raw = Image.open(INBOX / "ui_kit_v1.png").convert("RGB")
    slices = {}
    for name, box in KIT.items():
        img = shrink(crop(kit, box), FRAME_K)
        img.save(UI / f"{name}.png")
        slices[name] = {"slice": slice_width(img), "size": img.size}
        print(f"  {name}: {img.size}, 자르는 폭 {slices[name]['slice']}")
    # 바탕 무늬는 마젠타가 없는 네모라 그대로 잘라 줄인다
    x, y, w, h = TILE
    tile = raw.crop((x + 4, y + 4, x + w - 4, y + h - 4))
    tile = tile.resize((round(tile.width * 0.5), round(tile.height * 0.5)), Image.Resampling.LANCZOS)
    tile = seamless_tile(tile, 24)
    tile.save(UI / "lobby_bg.png")
    SLICES.write_text(json.dumps(slices, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  바탕 무늬 {tile.size}, 자르는 폭 저장 {SLICES}")

    # 아이콘: 비율을 지켜 높이 ICON_H로 줄여 한 줄로 늘어놓는다
    icons = unkey(np.array(Image.open(INBOX / "ui_icons_v1.png").convert("RGB")))
    p = Packer(1024)
    anims = {}
    for name, box in ICONS.items():
        img = shrink(crop(icons, box), ICON_H / box[3])
        anims[name] = {"frames": [p.add(img)]}
        print(f"  {name}: {img.width}×{img.height}")
    write_atlas(UI, "ui", p, anims, res=ICON_RES)


if __name__ == "__main__":
    main()
