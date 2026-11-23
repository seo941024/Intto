"""시안 그림체의 큰 배경 그림을 게임 크기로 옮긴다.

몽실처럼 굵은 픽셀 그림은 import_ai.py로 칸을 찾아 줄이지만, 하늘이나 지형처럼 화면을 채우는 그림은
가짜 픽셀이 작아서 칸을 찾으면 위치가 밀리고 거칠어진다. 그래서 게임 크기로 부드럽게 줄인다.

  sky    한 장 전체를 화면 크기로
  band     마젠타 배경 위 가로 띠를 오려, 양 끝이 이어지게 맞춘 뒤 960×540 투명 층의 정해진 높이에 놓는다
  scatter  마젠타 배경 위 물체들을 하나씩 오려 투명 층에 흩어 놓는다. 중간 배경 섬처럼
사용
  python tools/art/import_scene.py sky art_inbox/cloud_sky_v1.webp --out public/assets/world/cloud/sky.png
  python tools/art/import_scene.py band art_inbox/cloud_far_v1.webp --out public/assets/world/cloud/far.png --bottom 470
버섯숲·폭풍협곡. 먼 배경은 폭포와 절벽이 섞여 비치지 않게 --seam cut으로 잇는다
  python tools/art/import_scene.py sky art_inbox/mushroom_sky_v1.png --out public/assets/world/mushroom/sky.png
  python tools/art/import_scene.py band art_inbox/mushroom_far_v1.png --out public/assets/world/mushroom/far.png --bottom 470 --seam cut
  python tools/art/import_scene.py scatter art_inbox/mushroom_mid_v1.png --out public/assets/world/mushroom/mid.png --scale 0.31 --scales 1 --tops 190,290,150,240,320 --haze-color 195,137,157
  python tools/art/import_scene.py sky art_inbox/storm_sky_v1.png --out public/assets/world/storm/sky.png
  python tools/art/import_scene.py band art_inbox/storm_far_v1.png --out public/assets/world/storm/far.png --bottom 470 --seam cut
  python tools/art/import_scene.py scatter art_inbox/storm_mid_v1.png --out public/assets/world/storm/mid.png --scale 0.3 --scales 1 --tops 190,290,150,240,320 --haze-color 73,80,204
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONCEPT_K = 960 / 1672  # 시안 1672×941 → 게임 960×540
MAGENTA = np.array([255, 0, 255], dtype=float)


def cover(img, w, h):
    """비율을 지키며 w×h를 덮도록 줄인 뒤 가운데를 자른다"""
    k = max(w / img.width, h / img.height)
    rw, rh = round(img.width * k), round(img.height * k)
    img = img.resize((rw, rh), Image.Resampling.LANCZOS)
    x0 = (rw - w) // 2
    y0 = (rh - h) // 2
    return img.crop((x0, y0, x0 + w, y0 + h))


def unkey(rgb):
    """마젠타 배경을 투명으로. 경계의 반투명 픽셀은 마젠타 섞인 만큼 색을 되돌린다"""
    a = rgb.astype(float)
    dist = np.abs(a - MAGENTA).sum(-1)
    alpha = np.clip((dist - 70) / 150, 0, 1)
    safe = np.maximum(alpha, 1e-3)[..., None]
    col = (a - (1 - alpha[..., None]) * MAGENTA) / safe
    out = np.zeros(rgb.shape[:2] + (4,), dtype=float)
    out[..., :3] = np.clip(col, 0, 255)
    out[..., 3] = alpha * 255
    return out


def seamless(strip, overlap):
    """오른쪽 끝 overlap 폭을 왼쪽 시작과 섞어, 잘라 낸 띠의 오른쪽 끝이 왼쪽 시작으로 이어지게 한다"""
    h, w = strip.shape[:2]
    pre = strip.copy()
    pre[..., :3] *= pre[..., 3:4] / 255
    body = pre[:, overlap:w].copy()
    n = body.shape[1]
    t = np.linspace(0, 1, overlap)[None, :, None]
    body[:, n - overlap:] = body[:, n - overlap:] * (1 - t) + pre[:, :overlap] * t
    a = np.maximum(body[..., 3:4], 1e-3)
    body[..., :3] = np.where(body[..., 3:4] > 0, body[..., :3] * 255 / a, 0)
    return body


def seamless_cut(strip, overlap):
    """오른쪽 끝 overlap 폭과 왼쪽 시작이 가장 비슷한 세로 경로를 찾아 그 선에서 이어 붙인다.
    섞지 않으므로 버섯이나 폭포 같은 물체가 반투명하게 겹쳐 보이지 않는다. 경로는 물체를 피해 간다"""
    h, w = strip.shape[:2]
    pre = strip.astype(float).copy()
    pre[..., :3] *= pre[..., 3:4] / 255
    a = pre[:, w - overlap:]
    b = pre[:, :overlap]
    cost = ((a - b) ** 2).sum(-1)
    back = np.zeros((h, overlap), dtype=int)
    cols = np.arange(overlap)
    for y in range(1, h):
        prev = cost[y - 1]
        cand = np.vstack([np.r_[np.inf, prev[:-1]], prev, np.r_[prev[1:], np.inf]])
        k = cand.argmin(0)
        cost[y] = cost[y] + cand[k, cols]
        back[y] = cols + k - 1
    path = np.zeros(h, dtype=int)
    path[-1] = int(cost[-1].argmin())
    for y in range(h - 1, 0, -1):
        path[y - 1] = back[y, path[y]]
    body = strip[:, overlap:].astype(float).copy()
    n = body.shape[1]
    for y in range(h):
        c = path[y]
        body[y, n - overlap + c:] = strip[y, c:overlap]
    return body


def run_sky(args):
    img = Image.open(args.input).convert("RGB")
    w, h = (int(v) for v in args.size.lower().split("x"))
    out = cover(img, w, h)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(args.out)
    print(f"{img.width}×{img.height} → {w}×{h} 저장 {args.out}")


def run_band(args):
    rgb = np.array(Image.open(args.input).convert("RGB"))
    keyed = unkey(rgb)
    rows = np.nonzero((keyed[..., 3] > 8).any(1))[0]
    # 띠와 떨어진 곳의 티끌 한두 점은 빼고, 가장 긴 이어진 줄 묶음만 띠로 본다
    runs = np.split(rows, np.nonzero(np.diff(rows) > 3)[0] + 1)
    rows = max(runs, key=len)
    band = keyed[rows.min():rows.max() + 1]
    band = seamless_cut(band, args.overlap) if args.seam == "cut" else seamless(band, args.overlap)
    img = Image.fromarray(np.clip(band, 0, 255).astype(np.uint8), "RGBA")
    k = args.scale
    small = img.convert("RGBa").resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS).convert("RGBA")
    if args.fade > 0:
        # 띠 아래 끝이 일자로 잘려 있으면 하늘 구름 바다와 경계가 보이므로 아래쪽을 서서히 투명하게
        arr = np.array(small).astype(float)
        f = min(args.fade, arr.shape[0])
        ramp = np.linspace(1, 0, f)[:, None]
        arr[-f:, :, 3] *= ramp
        small = Image.fromarray(arr.astype(np.uint8), "RGBA")
    w, h = (int(v) for v in args.size.lower().split("x"))
    canvas = Image.new("RGBA", (small.width, h), (0, 0, 0, 0))
    canvas.alpha_composite(small, (0, args.bottom - small.height))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(f"띠 {img.width}×{img.height} → {small.width}×{small.height}, 이음 {args.overlap}px, 아래 끝 y {args.bottom}, 저장 {args.out} {canvas.width}×{canvas.height}")


def pieces(keyed, min_gap=12):
    """빈 세로줄을 경계로 물체를 하나씩 나눠 투명 여백 없이 자른다"""
    cols = (keyed[..., 3] > 8).any(0)
    out = []
    x = 0
    w = len(cols)
    while x < w:
        if not cols[x]:
            x += 1
            continue
        s = x
        gap = 0
        while x < w and (cols[x] or gap < min_gap):
            gap = 0 if cols[x] else gap + 1
            x += 1
        part = keyed[:, s:x - gap]
        rows = np.nonzero((part[..., 3] > 8).any(1))[0]
        out.append(part[rows.min():rows.max() + 1])
    return out


def haze(arr, color, amount):
    """멀리 있는 느낌이 나도록 하늘색 쪽으로 살짝 섞는다"""
    a = arr.copy()
    a[..., :3] = a[..., :3] * (1 - amount) + np.array(color, dtype=float) * amount
    return a


def run_scatter(args):
    """물체 여러 개를 오려 정해진 자리에 흩어 놓은 투명 층을 만든다. 모두 층 안에 들어가므로 옆으로 이어 붙여도 끊기지 않는다"""
    rgb = np.array(Image.open(args.input).convert("RGB"))
    keyed = unkey(rgb)
    # 마젠타 위에 남은 한두 픽셀 티끌은 물체로 치지 않는다
    parts = [q for q in pieces(keyed) if q.shape[0] >= 8 and q.shape[1] >= 8]
    print(f"물체 {len(parts)}개")
    w, h = (int(v) for v in args.size.lower().split("x"))
    lw = args.layer_width
    canvas = Image.new("RGBA", (lw, h), (0, 0, 0, 0))
    # 자리: 층 폭을 물체 수로 나눠 가운데에, 높이와 크기는 번갈아 바꾼다
    tops = [int(v) for v in args.tops.split(",")]
    scales = [float(v) for v in args.scales.split(",")]
    step = lw / len(parts)
    for i, part in enumerate(parts):
        part = haze(part, tuple(int(v) for v in args.haze_color.split(",")), args.haze)
        img = Image.fromarray(np.clip(part, 0, 255).astype(np.uint8), "RGBA")
        k = args.scale * scales[i % len(scales)]
        img = img.convert("RGBa").resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS).convert("RGBA")
        x = round(step * i + (step - img.width) / 2)
        canvas.alpha_composite(img, (x, tops[i % len(tops)]))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(f"층 {lw}×{h} 저장 {args.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sky", "band", "scatter"])
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="960x540")
    ap.add_argument("--scale", type=float, default=CONCEPT_K, help="시안 크기 대비 줄이는 비율")
    ap.add_argument("--overlap", type=int, default=160, help="양 끝을 섞어 잇는 폭, 원본 픽셀")
    ap.add_argument("--seam", choices=["blend", "cut"], default="blend", help="양 끝 잇기: blend 섞기, cut 가장 비슷한 선에서 자르기")
    ap.add_argument("--bottom", type=int, default=470, help="띠 아래 끝이 놓일 화면 y")
    ap.add_argument("--fade", type=int, default=24, help="띠 아래쪽을 서서히 투명하게 하는 높이, 게임 픽셀")
    ap.add_argument("--layer-width", type=int, default=1400, help="scatter 층 폭")
    ap.add_argument("--tops", default="200,300,170,260,330", help="scatter 물체마다 위 끝 y")
    ap.add_argument("--scales", default="1,0.85,1.1,0.9,1", help="scatter 물체마다 크기 배율")
    ap.add_argument("--haze", type=float, default=0.12, help="하늘색으로 섞는 정도")
    ap.add_argument("--haze-color", default="150,205,240", help="섞는 하늘색 R,G,B")
    args = ap.parse_args()
    if args.mode == "sky":
        run_sky(args)
    elif args.mode == "band":
        run_band(args)
    else:
        run_scatter(args)


if __name__ == "__main__":
    main()
