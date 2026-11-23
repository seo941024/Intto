"""대기실 맵 미리보기를 맵의 실제 그림으로 만든다.

하늘, 먼 배경, 중간 섬, 천장, 땅과 띠에서 떼어 낸 장식, 장애물 몇 개와 보석을 게임 화면과 같은 배율로 한 장에 놓고
320×180으로 줄인다. 대기실은 이 그림을 320×180으로 보여 준다.
사용
  python tools/art/make_preview.py --theme cloud
  python tools/art/make_preview.py --theme mushroom
  python tools/art/make_preview.py --theme storm
"""
import argparse
import math
import json
import sys
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
W, H = 960, 540
ZOOM = 1.5  # 게임 카메라 배율. res 1440 그림은 화면에서 1:1
# 맵마다 미리보기에 놓을 떠 있는 장애물과 화면 자리
OBSTACLES = {
    "cloud": (("balloon", (430, 190)), ("bigrock", (700, 260)), ("rock_b", (250, 330))),
    "mushroom": (("spore", (430, 190)), ("thorn_b", (700, 260)), ("thorn_a", (250, 330))),
    "storm": (("stormorb", (430, 190)), ("crystal_a", (700, 280)), ("crystal_b", (250, 330))),
}
MUSHROOM_X = 840  # 바닥에 선 튕김 버섯 자리
BOLT_X = 850  # 번개 기둥 자리


def atlas(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    img = Image.open(path.parent / d["image"]).convert("RGBA")
    return d, img


def frame(d, img, name):
    a = d["animations"][name]
    x, y, w, h = a["frames"][0]
    return img.crop((x, y, x + w, y + h)), a.get("anchor", [w // 2, h // 2])


def tile_x(dst, src, y):
    for x in range(0, W, src.width):
        dst.alpha_composite(src, (x, y))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="cloud")
    args = ap.parse_args()
    folder = ROOT / "public" / "assets" / "world" / args.theme
    c = Image.new("RGBA", (W, H))
    c.alpha_composite(Image.open(folder / "sky.png").convert("RGBA").resize((W, H)))
    far = Image.open(folder / "far.png").convert("RGBA")
    tile_x(c, far, 0)
    mid = Image.open(folder / "mid.png").convert("RGBA")
    c.alpha_composite(mid.crop((200, 0, 200 + W, H)))

    td, timg = atlas(folder / "tiles.json")
    ceil_body, _ = frame(td, timg, "ceilBody")
    ceil_edge, ca = frame(td, timg, "ceilEdge")
    floor_body, _ = frame(td, timg, "floorBody")
    floor_edge, fa = frame(td, timg, "floorEdge")
    # 땅은 게임처럼 오르내린다. 게임과 같이 4 맵 단위 폭 세로줄로 잘라 줄마다 높이를 다르게 붙인다
    ceil_line = round(40 * ZOOM)
    floor_line = round(300 * ZOOM)
    col = round(4 * ZOOM)
    cy = lambda x: ceil_line + 16 * math.sin(x / 150 + 0.6) + 7 * math.sin(x / 47 + 2.0)
    fy = lambda x: floor_line + 20 * math.sin(x / 170 + 2.4) + 8 * math.sin(x / 53)
    gap = td.get("bodyGap", {"floor": 0, "ceil": 0})

    def body_col(src, x, y0, y1):
        sx = x % src.width
        piece = src.crop((sx, 0, min(src.width, sx + col), src.height))
        y = y0
        while y < y1:
            c.alpha_composite(piece, (x, round(y)))
            y += src.height

    for x in range(0, W, col):
        top = cy(x + col / 2)
        bot = fy(x + col / 2)
        y = top - gap["ceil"] - ceil_body.height
        while y > -ceil_body.height:
            body_col(ceil_body, x, y, y + 1)
            y -= ceil_body.height
        body_col(ceil_body, x, top - gap["ceil"] - ceil_body.height, top - gap["ceil"] - ceil_body.height + 1)
        body_col(floor_body, x, bot + gap["floor"], H)
        for edge, an, line in ((ceil_edge, ca, top), (floor_edge, fa, bot)):
            sx = x % edge.width
            c.alpha_composite(edge.crop((sx, 0, min(edge.width, sx + col), edge.height)), (x, round(line - an[1])))
    # 띠에서 떼어 낸 장식을 그 자리 땅 높이에 통째로 세운다
    for kind, edge in (("floor", floor_edge), ("ceil", ceil_edge)):
        for d in td.get("decor", {}).get(kind, []):
            im, an = frame(td, timg, d["name"])
            for x0 in range(0, W + edge.width, edge.width):
                x = x0 + d["x"]
                if -im.width < x - an[0] < W:
                    y = fy(x) - d["dy"] if kind == "floor" else cy(x) + d["dy"]
                    c.alpha_composite(im, (round(x - an[0]), round(y - an[1])))

    od, oimg = atlas(folder / "obstacles.json")
    idef, iimg = atlas(ROOT / "public" / "assets" / "items" / "items.json")
    for name, (x, y) in OBSTACLES.get(args.theme, ()):
        if name in od["animations"]:
            im, an = frame(od, oimg, name)
            c.alpha_composite(im, (x - an[0], y - an[1]))
    if "mushroom" in od["animations"]:
        # 게임처럼 그림 아래 가운데를 땅 경계선보다 3 맵 단위 아래에
        im, _ = frame(od, oimg, "mushroom")
        c.alpha_composite(im, (MUSHROOM_X - im.width // 2, round(fy(MUSHROOM_X)) + round(3 * ZOOM) - im.height))
    if "beam" in od["animations"]:
        # 번개 기둥: 줄기 한 장을 위아래 땅 사이 가운데에 놓고 땅 밖은 자른다
        im, an = frame(od, oimg, "beam")
        layer = Image.new("RGBA", (W, H))
        top, bot = round(cy(BOLT_X)), round(fy(BOLT_X))
        layer.alpha_composite(im, (BOLT_X - an[0], (top + bot) // 2 - an[1]))
        layer = layer.crop((0, top, W, bot))
        c.alpha_composite(layer, (0, top))
        for name, y in (("pylonTop", top), ("pylonBottom", bot)):
            im, an = frame(od, oimg, name)
            c.alpha_composite(im, (BOLT_X - an[0], y - an[1]))
    for i in range(5):
        im, an = frame(idef, iimg, "gemRed" if i == 2 else "gemBlue")
        c.alpha_composite(im, (520 + i * 46 - an[0], 150 + abs(2 - i) * 14 - an[1]))

    out = c.convert("RGB").resize((320, 180), Image.Resampling.LANCZOS)
    out.save(folder / "preview.png")
    print(f"저장 {folder / 'preview.png'} 320×180")


if __name__ == "__main__":
    main()
