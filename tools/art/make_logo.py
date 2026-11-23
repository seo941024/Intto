"""마젠타 배경 위에 따로 놓인 로고 부품 그림 한 장에서 타이틀 로고를 만든다.

입력 그림 윗줄은 왼쪽부터 "인", "또", 왼날개, 오른날개, 아랫줄은 큰 별, 반짝이, 작은 반짝이, 큰 구름, 작은 구름이다.
  ui/logo_parts.png, logo_parts.json   부품마다 따로 담은 아틀라스와 배치. 타이틀 화면이 부품을 하나씩 움직인다
  ui/logo.png                          날개와 글자만 합친 한 장. 로비와 대기실 위쪽에 작게 쓴다
배치 layout의 x, y는 부품 기준점 위치, 기준점은 글자는 아래 가운데, 날개는 뿌리, 나머지는 가운데다.
사용
  python tools/art/make_logo.py art_inbox/logo_v2.webp
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_scene import unkey, pieces  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "public" / "assets" / "ui"
K = 0.5  # 원본 그림을 이만큼 줄여 담는다. 타이틀이 다시 줄이고 키울 때 부드럽게 보이도록 여유를 둔다
HEADER_K = 0.5  # logo.png는 부품 크기의 이만큼. 페이지가 그 절반으로 보여 준다
TOP_NAMES = ["in", "tto", "wingL", "wingR"]
BOT_NAMES = ["star", "sparkle", "sparkleS", "cloud", "cloudS"]

# 부품 배치. 글자 바닥선이 y=0, "인" 왼쪽 끝이 x=0
GAP = 8


def to_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def shrink(img, k):
    return img.convert("RGBa").resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--split-y", type=int, default=570, help="윗줄과 아랫줄을 나누는 원본 높이")
    args = ap.parse_args()

    keyed = unkey(np.array(Image.open(args.input).convert("RGB")))
    top = pieces(keyed[: args.split_y], min_gap=16)
    bot = pieces(keyed[args.split_y:], min_gap=16)
    if len(top) != len(TOP_NAMES) or len(bot) != len(BOT_NAMES):
        sys.exit(f"부품 수가 다름: 윗줄 {len(top)}개, 아랫줄 {len(bot)}개")
    parts = {n: shrink(to_img(p), K) for n, p in zip(TOP_NAMES + BOT_NAMES, top + bot)}

    w = {n: im.width for n, im in parts.items()}
    h = {n: im.height for n, im in parts.items()}
    # 기준점: 글자는 아래 가운데, 왼날개는 오른쪽 아래 뿌리, 오른날개는 왼쪽 아래 뿌리, 나머지는 가운데
    anchors = {
        "in": [w["in"] // 2, h["in"]],
        "tto": [w["tto"] // 2, h["tto"]],
        "wingL": [round(w["wingL"] * 0.82), round(h["wingL"] * 0.78)],
        "wingR": [round(w["wingR"] * 0.18), round(h["wingR"] * 0.78)],
    }
    for n in BOT_NAMES:
        anchors[n] = [w[n] // 2, h[n] // 2]

    x_in = w["in"] / 2
    x_tto = w["in"] + GAP + w["tto"] / 2
    layout = {
        "wingL": [8, -h["in"] * 0.52],
        "wingR": [w["in"] + GAP + w["tto"] - 8, -h["tto"] * 0.55],
        "in": [x_in, 0],
        "tto": [x_tto, 0],
        "cloud": [-44, 16],
        "cloudS": [w["in"] + GAP + w["tto"] + 30, 14],
        "sparkle": [-38, -h["in"] - 10],
        "star": [w["in"] + GAP + w["tto"] + 34, -h["tto"] - 18],
        "sparkleS": [w["in"] + GAP / 2, -h["in"] + 6],
    }
    # 날개는 맞닿은 글자를 따라 뛴다
    follow = {"wingL": "in", "wingR": "tto"}
    order = ["wingL", "wingR", "in", "tto", "cloud", "cloudS", "sparkle", "star", "sparkleS"]

    # 아틀라스: 한 줄로 늘어놓는다
    sheet_w = sum(w[n] + 2 for n in order)
    sheet_h = max(h.values())
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    anims = {}
    x = 0
    for n in order:
        sheet.alpha_composite(parts[n], (x, 0))
        anims[n] = {"frames": [[x, 0, w[n], h[n]]], "anchor": anchors[n]}
        x += w[n] + 2
    sheet.save(UI / "logo_parts.png")
    spec = {
        "image": "logo_parts.png",
        "res": 960,
        "animations": anims,
        "layout": {n: [round(v[0]), round(v[1])] for n, v in layout.items()},
        "follow": follow,
        "order": order,
    }
    (UI / "logo_parts.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    # 로비용 한 장: 날개와 글자만 제자리에 합친다
    boxes = []
    for n in ["wingL", "wingR", "in", "tto"]:
        lx, ly = layout[n]
        ax, ay = anchors[n]
        boxes.append((n, round(lx - ax), round(ly - ay)))
    x0 = min(b[1] for b in boxes)
    y0 = min(b[2] for b in boxes)
    x1 = max(b[1] + w[b[0]] for b in boxes)
    y1 = max(b[2] + h[b[0]] for b in boxes)
    comp = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for n, bx, by in boxes:
        comp.alpha_composite(parts[n], (bx - x0, by - y0))
    backup = ROOT / "art_inbox" / "out" / "placeholder_backup" / "ui"
    backup.mkdir(parents=True, exist_ok=True)
    if not (backup / "logo.png").exists() and (UI / "logo.png").exists():
        (backup / "logo.png").write_bytes((UI / "logo.png").read_bytes())
    shrink(comp, HEADER_K).save(UI / "logo.png")
    print("부품", {n: (w[n], h[n]) for n in order})
    print(f"저장 {UI / 'logo_parts.png'} {sheet.size}, {UI / 'logo.png'} {shrink(comp, HEADER_K).size}")


if __name__ == "__main__":
    main()
