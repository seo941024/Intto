"""cut_concept.py로 오려 낸 구름섬 시안 조각을 게임 아틀라스로 묶는다. HUD는 make_hud.py가 만든다.

  public/assets/items/items.png, items.json          보석, 회복 고기, 깃털
  public/assets/world/cloud/obstacles.png, .json      떠 있는 바위, 가시 풍선

크기는 게임의 부딪힘 크기에 맞추고, 카메라가 1.5배 당겨 보므로 res 1440으로 넣어 화면에서 1:1로 그려지게 한다.
Packer, write_atlas는 다른 도구도 가져다 쓰고, icon_images는 make_hud.py가 쓴다.
사용
  python tools/art/cut_concept.py
  python tools/art/pack_concept.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import unkey, shrink, to_img  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CUT = ROOT / "art_inbox" / "out" / "cut"
ASSETS = ROOT / "public" / "assets"


def load(name):
    return Image.open(CUT / f"{name}.png").convert("RGBA")


def trim(img):
    box = img.getbbox()
    return img.crop(box) if box else img


def to_width(img, w):
    return shrink(img, w / img.width)


class Packer:
    """가로 줄 단위로 그림을 늘어놓고 [x, y, w, h]를 돌려준다"""

    def __init__(self, width=1024, gap=2):
        self.width = width
        self.gap = gap
        self.items = []
        self.x = self.y = self.row_h = 0

    def add(self, img):
        if self.x + img.width > self.width:
            self.x = 0
            self.y += self.row_h + self.gap
            self.row_h = 0
        rect = [self.x, self.y, img.width, img.height]
        self.items.append((img, rect))
        self.x += img.width + self.gap
        self.row_h = max(self.row_h, img.height)
        return rect

    def save(self, path):
        h = self.y + self.row_h
        w = max(r[0] + r[2] for _, r in self.items)
        sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for img, r in self.items:
            sheet.alpha_composite(img, (r[0], r[1]))
        sheet.save(path)
        return w, h


# 맵 위 그림은 카메라가 1.5배 당겨 보므로, 그만큼 큰 그림을 res 1440으로 넣어 화면에서 1:1로 선명하게 그려지게 한다
WORLD_RES = 1440
ART_SCALE = 1.0  # 그림만 키우는 배율. 1이면 그림 크기가 부딪힘 크기와 같다. 키우면 원본보다 크게 늘어나 흐려진다
WK = WORLD_RES / 960 * ART_SCALE


def write_atlas(folder, name, packer, anims, extra=None, res=960):
    folder.mkdir(parents=True, exist_ok=True)
    w, h = packer.save(folder / f"{name}.png")
    spec = {"image": f"{name}.png", "res": res, "animations": anims}
    if extra:
        spec.update(extra)
    (folder / f"{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 {folder / name}.png {w}×{h}, 그림 {len(anims)}개")


def pack_items():
    """보석·고기·깃털. 지금 게임 아이템 크기인 24px 안팎에 맞춘다"""
    p = Packer(512)
    anims = {}
    for key, src, width in (("gemBlue", "gem_blue_a", 28), ("gemRed", "gem_red", 28), ("food", "meat", 34), ("feather", "feather", 30)):
        img = to_width(trim(load(src)), round(width * WK))
        rect = p.add(img)
        anims[key] = {"frames": [rect], "anchor": [img.width // 2, img.height // 2]}
    write_atlas(ASSETS / "items", "items", p, anims, res=WORLD_RES)


def pack_obstacles():
    """바위와 가시 풍선. 부딪힘 반지름 바위 18, 큰 바위 27, 풍선 16에 맞춘 크기"""
    p = Packer(512)
    anims = {}
    rock = trim(load("rock"))
    for key, width, flip, r in (("rock_a", 50, False, 18), ("rock_b", 50, True, 18), ("rock_c", 44, False, 18), ("bigrock", 74, False, 27)):
        img = to_width(rock, round(width * WK))
        if flip:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        rect = p.add(img)
        # 바위 덩어리 가운데를 부딪힘 중심으로. 풀 덮인 윗부분이 있어 살짝 아래
        anims[key] = {"frames": [rect], "anchor": [img.width // 2, round(img.height * 0.52)], "hit": {"r": r}}
    balloon = trim(load("balloon_a"))
    img = to_width(balloon, round(50 * WK))
    rect = p.add(img)
    # 가시 공 가운데가 부딪힘 중심. 바구니가 아래로 달려 있어 그림 위쪽 40% 자리
    anims["balloon"] = {"frames": [rect], "anchor": [img.width // 2, round(img.height * 0.4)], "hit": {"r": 16}}
    write_atlas(ASSETS / "world" / "cloud", "obstacles", p, anims, res=WORLD_RES)


# 기술 아이콘 시트: 7열 2줄, 순서는 아래와 같다
ICON_ORDER = ["puff", "dash", "cloud", "bolt", "shield", "nut", "repair",
              "oil", "acorn", "glide", "whirl", "paper", "fold", "pinwheel"]
ICON_BOX = 38  # 기술칸 안쪽에 들어가는 아이콘 최대 크기, 게임 픽셀


def icon_images():
    """ChatGPT 아이콘 시트를 칸마다 잘라 마젠타를 걷고 같은 크기 상자에 맞춘다"""
    src = ROOT / "art_inbox" / "icons_v1.webp"
    if not src.exists():
        return {}
    keyed = unkey(np.array(Image.open(src).convert("RGB")))
    h, w = keyed.shape[:2]
    alpha = keyed[..., 3] > 40
    # 줄 경계: 두 줄 사이 빈 가로줄 가운데
    rows = np.nonzero(alpha.any(1))[0]
    empty = [y for y in range(rows.min(), rows.max()) if not alpha[y].any()]
    split = empty[len(empty) // 2] if empty else h // 2
    out = {}
    cw = w / 7
    for i, name in enumerate(ICON_ORDER):
        r, c = divmod(i, 7)
        y0, y1 = (0, split) if r == 0 else (split, h)
        x0, x1 = round(c * cw), round((c + 1) * cw)
        cell = keyed[y0:y1, x0:x1].copy()
        img = trim(to_img(cell))
        k = ICON_BOX / max(img.width, img.height)
        out[name] = shrink(img, k)
    return out


def main():
    pack_items()
    pack_obstacles()


if __name__ == "__main__":
    main()
