"""ChatGPT로 받은 UI 그림 두 장으로 로비·대기실 틀과 아이콘을 만든다.

  art_inbox/ui_kit_v1.png    큰 패널, 파란 버튼 셋, 노란 버튼 둘, 카드 둘, 입력칸, 바탕 무늬
  art_inbox/ui_icons_v1.png  왕관, 체크, A·B 깃발, 별 셋, 유령, 해골, 깃털
출력
  public/assets/ui/panel.png, button*.png, card*.png, input.png, lobby_bg.png   CSS border-image로 늘려 쓰는 틀
  public/assets/ui/ui.png, ui.json   아이콘 열 개를 새 그림으로 바꿔 끼운다
  public/assets/ui/ui_kit.json       틀마다 자르는 폭. CSS에 적는 값
틀은 비율을 바꾸지 않고 FRAME_K로 줄인 뒤, 가운데가 한 색으로 고르게 시작하는 자리를 잘라 쓰는 폭으로 잰다.
사용
  python tools/art/make_ui_kit.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_scene import unkey  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
UI = ROOT / "public" / "assets" / "ui"
FRAME_K = 0.4  # 틀 그림을 줄이는 배율
ICON_H = 11  # 아이콘 높이, ui 아틀라스 픽셀. 게임에서는 1.5배, 대기실에서는 2배로 그린다

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


def crop(keyed, box, pad=6):
    x, y, w, h = box
    a = keyed[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    return img.crop(img.getbbox())


def shrink(img, k):
    return img.convert("RGBa").resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS).convert("RGBA")


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
    backup = ROOT / "art_inbox" / "out" / "placeholder_backup" / "ui"
    backup.mkdir(parents=True, exist_ok=True)
    slices = {}
    for name, box in KIT.items():
        img = shrink(crop(kit, box), FRAME_K)
        if not (backup / f"{name}.png").exists() and (UI / f"{name}.png").exists():
            (backup / f"{name}.png").write_bytes((UI / f"{name}.png").read_bytes())
        img.save(UI / f"{name}.png")
        slices[name] = {"slice": slice_width(img), "size": img.size}
        print(f"  {name}: {img.size}, 자르는 폭 {slices[name]['slice']}")
    # 바탕 무늬는 마젠타가 없는 네모라 그대로 잘라 줄인다
    x, y, w, h = TILE
    tile = raw.crop((x + 4, y + 4, x + w - 4, y + h - 4))
    tile = tile.resize((round(tile.width * 0.5), round(tile.height * 0.5)), Image.Resampling.LANCZOS)
    tile = seamless_tile(tile, 24)
    if not (backup / "lobby_bg.png").exists():
        (backup / "lobby_bg.png").write_bytes((UI / "lobby_bg.png").read_bytes())
    tile.save(UI / "lobby_bg.png")
    (UI / "ui_kit.json").write_text(json.dumps(slices, ensure_ascii=False, indent=2), encoding="utf-8")

    # 아이콘: ui 아틀라스 아래에 새 그림을 붙이고 그 이름의 프레임만 새 자리로 바꾼다
    icons = unkey(np.array(Image.open(INBOX / "ui_icons_v1.png").convert("RGB")))
    spec = json.loads((UI / "ui.json").read_text(encoding="utf-8"))
    sheet = Image.open(UI / spec["image"]).convert("RGBA")
    if not (backup / "ui.png").exists():
        sheet.save(backup / "ui.png")
        (backup / "ui.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # 다시 돌릴 때는 원래 아틀라스에서 시작한다
        sheet = Image.open(backup / "ui.png").convert("RGBA")
        spec = json.loads((backup / "ui.json").read_text(encoding="utf-8"))
    parts = {n: shrink(crop(icons, b), ICON_H / b[3]) for n, b in ICONS.items()}
    y0 = sheet.height + 2
    width = max(sheet.width, sum(p.width + 2 for p in parts.values()))
    out = Image.new("RGBA", (width, y0 + max(p.height for p in parts.values())), (0, 0, 0, 0))
    out.alpha_composite(sheet, (0, 0))
    x = 0
    for n, p in parts.items():
        out.alpha_composite(p, (x, y0))
        spec["animations"][n] = {"frames": [[x, y0, p.width, p.height]]}
        x += p.width + 2
    out.save(UI / spec["image"])
    (UI / "ui.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"아이콘 {len(parts)}개 바꿈, 바탕 무늬 {tile.size}")


if __name__ == "__main__":
    main()
