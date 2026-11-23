"""대기실 맵 미리보기를 맵의 실제 그림으로 만든다.

하늘, 먼 배경, 중간 섬, 천장, 땅과 띠에서 떼어 낸 장식, 장애물 몇 개와 보석을 게임 화면과 같은 배율로 한 장에 놓고
320×180으로 줄인다. 대기실은 이 그림을 320×180으로 보여 준다.
사용
  python tools/art/make_preview.py --theme cloud
  python tools/art/make_preview.py --theme mushroom
  python tools/art/make_preview.py --theme storm
"""
import argparse
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
    ceil_line = round(40 * ZOOM)
    floor_line = round(300 * ZOOM)
    for y in range(ceil_line - ceil_body.height, -ceil_body.height, -ceil_body.height):
        tile_x(c, ceil_body, y)
    tile_x(c, ceil_edge, ceil_line - ca[1])
    for y in range(floor_line, H, floor_body.height):
        tile_x(c, floor_body, y)
    tile_x(c, floor_edge, floor_line - fa[1])
    # 띠에서 떼어 낸 장식을 원래 자리에 세운다. 미리보기는 땅이 평평해서 띠와 똑같이 이어진다
    for kind, edge, line in (("floor", floor_edge, floor_line), ("ceil", ceil_edge, ceil_line)):
        for d in td.get("decor", {}).get(kind, []):
            im, an = frame(td, timg, d["name"])
            y = line - d["dy"] if kind == "floor" else line + d["dy"]
            for x0 in range(0, W + edge.width, edge.width):
                x = round(x0 + d["x"]) - an[0]
                if -im.width < x < W:
                    c.alpha_composite(im, (x, round(y - an[1])))

    od, oimg = atlas(folder / "obstacles.json")
    idef, iimg = atlas(ROOT / "public" / "assets" / "items" / "items.json")
    for name, (x, y) in OBSTACLES.get(args.theme, ()):
        if name in od["animations"]:
            im, an = frame(od, oimg, name)
            c.alpha_composite(im, (x - an[0], y - an[1]))
    if "mushroom" in od["animations"]:
        # 게임처럼 그림 아래 가운데를 땅 경계선보다 3 맵 단위 아래에
        im, _ = frame(od, oimg, "mushroom")
        c.alpha_composite(im, (MUSHROOM_X - im.width // 2, floor_line + round(3 * ZOOM) - im.height))
    if "beam" in od["animations"]:
        # 번개 기둥: 줄기 한 장을 위아래 땅 사이 가운데에 놓고 땅 밖은 자른다
        im, an = frame(od, oimg, "beam")
        layer = Image.new("RGBA", (W, H))
        layer.alpha_composite(im, (BOLT_X - an[0], (ceil_line + floor_line) // 2 - an[1]))
        layer = layer.crop((0, ceil_line, W, floor_line))
        c.alpha_composite(layer, (0, ceil_line))
        for name, y in (("pylonTop", ceil_line), ("pylonBottom", floor_line)):
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
