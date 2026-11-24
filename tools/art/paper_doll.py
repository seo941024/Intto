"""몸은 한 프레임으로 고정하고 움직이는 부분만 프레임마다 바꿔 끼운다.

AI는 프레임마다 몸을 조금씩 다르게 그려서 애니메이션이 커졌다 작아졌다 한다.
이 도구는 외곽선으로 둘러싸인 조각을 찾아, 움직이는 부분 조건에 맞는 조각만 각 프레임에서 오려
기준 프레임의 몸 위에 붙인다.
지금은 pieces_of, components, leg_inner, dangle, shift_y를 다른 그림 도구가 가져다 쓰는 도우미로 쓴다.
아래 예의 art_inbox/out 그림은 git에 올리지 않는 예전 중간 결과다.

사용
  python tools/art/paper_doll.py art_inbox/out/mongsil_flap_v1.png --out art_inbox/out/mongsil_flap_doll.png \
      --body 1 --part-top 34 --part-x 32 --tint blue
  --part-top  조각 맨 윗줄이 이 값보다 위면 움직이는 부분 후보
  --part-x    조각 가운데 x가 이 값보다 왼쪽이면 후보
  --tint      blue면 푸른 기가 도는 조각만 후보
"""
import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import lum, dilate  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def components(f):
    """외곽선이 아닌 불투명 픽셀을 4방향으로 이어 조각을 나눈다"""
    a = f[..., 3] > 0
    outline = a & (lum(f.astype(float)) < 90)
    inner = a & ~outline
    h, w = a.shape
    label = -np.ones((h, w), dtype=int)
    comps = []
    for y in range(h):
        for x in range(w):
            if not inner[y, x] or label[y, x] >= 0:
                continue
            q = deque([(y, x)])
            label[y, x] = len(comps)
            pts = []
            while q:
                cy, cx = q.popleft()
                pts.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and inner[ny, nx] and label[ny, nx] < 0:
                        label[ny, nx] = len(comps)
                        q.append((ny, nx))
            comps.append(np.array(pts))
    return comps, outline, label


def part_mask(f, part_top, part_x, tint):
    comps, outline, label = components(f)
    h, w = outline.shape
    mask = np.zeros((h, w), dtype=bool)
    for pts in comps:
        if len(pts) < 4:
            continue
        ys, xs = pts[:, 0], pts[:, 1]
        if ys.min() >= part_top or xs.mean() >= part_x:
            continue
        if tint == "blue":
            c = f[ys, xs].astype(int)
            blue = ((c[:, 2] - c[:, 0]) > 12) & (lum(c.astype(float)) > 140)
            if blue.mean() < 0.12:
                continue
        mask[ys, xs] = True
    # 조각을 둘러싼 외곽선도 조각에 넣는다
    grown = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return mask | (grown & outline)


def body_only(f, part):
    """조각을 빼되, 몸 속살과 닿은 외곽선은 몸 외곽선으로 남긴다"""
    a = f[..., 3] > 0
    outline = a & (lum(f.astype(float)) < 90)
    inner_body = a & ~outline & ~part
    near_body = np.zeros_like(a)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            near_body |= np.roll(np.roll(inner_body, dy, 0), dx, 1)
    keep = a & ~(part & ~(outline & near_body))
    out = f.copy()
    out[~keep] = 0
    return out


def best_shift(ref_mask, mask, r=6):
    best = (-1e9, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            m = np.roll(np.roll(mask, dy, 0), dx, 1)
            s = (m & ref_mask).sum() - 0.5 * (m ^ ref_mask).sum()
            if s > best[0]:
                best = (s, dx, dy)
    return best[1], best[2]


def pieces_of(mask):
    """8방향으로 이어진 조각들"""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            q = deque([(y, x)])
            seen[y, x] = True
            m = np.zeros_like(mask)
            while q:
                cy, cx = q.popleft()
                m[cy, cx] = True
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            out.append(m)
    return out


def rotate_piece(f, mask, root, angle, outline_color):
    """조각 속살을 뿌리 기준으로 돌리고 외곽선을 새로 두른다. angle은 화면 기준 반시계 방향 도"""
    a = f[..., 3] > 0
    inner = mask & a & (lum(f.astype(float)) >= 90)
    src = np.zeros_like(f)
    src[inner] = f[inner]
    img = Image.fromarray(src)
    rot = np.array(img.rotate(angle, resample=Image.Resampling.NEAREST, center=(root[0] + 0.5, root[1] + 0.5)))
    rin = rot[..., 3] > 0
    # 돌리며 생긴 작은 구멍 메우기
    n = sum(np.roll(np.roll(rin, dy, 0), dx, 1).astype(int) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    holes = ~rin & (n >= 5)
    for y, x in zip(*np.nonzero(holes)):
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if rin[y + dy, x + dx]:
                rot[y, x] = rot[y + dy, x + dx]
                break
    rin = rot[..., 3] > 0
    ring = dilate(rin) & ~rin
    out = rot.copy()
    out[ring] = outline_color
    return out


def leg_inner(f, below):
    """몸 아래쪽의 어두운 속살 조각을 다리로 본다"""
    comps, _, _ = components(f)
    a = f[..., 3] > 0
    ys, _ = np.nonzero(a)
    if below is None:
        below = ys.min() + int((ys.max() - ys.min()) * 0.75)
    mask = np.zeros(a.shape, dtype=bool)
    for pts in comps:
        py, px = pts[:, 0], pts[:, 1]
        if py.mean() < below:
            continue
        if lum(f[py, px].astype(float)).mean() > 150:
            continue
        mask[py, px] = True
    return mask


def dangle(img, legs, rel):
    """다리가 있는 세로줄만 다리 윗부분부터 rel픽셀 늘이거나 줄인다. 몸통 크기는 그대로다"""
    if rel == 0 or not legs.any():
        return img
    out = img.copy()
    h, w = legs.shape
    tops = {}
    for x in range(w):
        ys = np.nonzero(legs[:, x])[0]
        if len(ys):
            tops[x] = ys.min()
    cols = dict(tops)
    # 다리 옆 외곽선 세로줄도 같이 움직여야 다리 테두리가 끊기지 않는다
    for x, t in tops.items():
        for nx in (x - 1, x + 1):
            if 0 <= nx < w and nx not in tops:
                cols[nx] = min(cols.get(nx, h), t)
    for x, s in cols.items():
        col = img[:, x].copy()
        if rel > 0:
            out[s + rel:, x] = col[s:h - rel]
        else:
            out[s:h + rel, x] = col[s - rel:]
            out[h + rel:, x] = 0
    return out


def shift_y(img, dy):
    if dy == 0:
        return img
    out = np.zeros_like(img)
    if dy > 0:
        out[dy:] = img[:-dy]
    else:
        out[:dy] = img[-dy:]
    return out


def flap(args, frames):
    base = frames[args.body]
    part = part_mask(base, args.part_top, args.part_x, args.tint)
    body = body_only(base, part)
    n_frames = len(args.rotate.split(","))
    bob = [int(v) for v in args.bob.split(",")] if args.bob else [0] * n_frames
    legs = leg_inner(body, args.legs_below) if args.legs else np.zeros(body.shape[:2], dtype=bool)
    a = base[..., 3] > 0
    ol = base[a & (lum(base.astype(float)) < 90)]
    vals, cnt = np.unique(ol, axis=0, return_counts=True)
    outline_color = vals[cnt.argmax()]
    inner_part = part & (lum(base.astype(float)) >= 90)
    wings = sorted([p for p in pieces_of(inner_part) if p.sum() >= 6], key=lambda m: -m.sum())
    angles = [float(v) for v in args.rotate.split(",")]
    frames_out = []
    for fi, ang in enumerate(angles):
        # 몸이 떠오를 때 다리가 한 박자 늦게 따라오도록, 가장 높이 뜬 프레임에서만 다리를 늘인다
        frame_body = dangle(body, legs, max(bob[fi], 0) * args.legs)
        comp = frame_body.copy()
        # 작은 날개를 먼저, 큰 날개를 나중에 그려 앞에 오게 한다
        for wi, wm in enumerate(reversed(wings)):
            ys, xs = np.nonzero(wm)
            k = np.argmax(xs + ys)
            root = (xs[k], ys[k])
            amp = 1.0 if wm is wings[0] else args.back_amp
            piece = rotate_piece(base, dilate(wm) & part, root, ang * amp, outline_color)
            m = piece[..., 3] > 0
            comp[m] = piece[m]
        # 날개 뿌리보다 오른쪽의 뿔과 머리는 날개 앞에 오도록 몸을 다시 덮는다
        ys, xs = np.nonzero(wings[0])
        rx = xs[np.argmax(xs + ys)] - args.front_margin
        front = (frame_body[..., 3] > 0) & (np.arange(body.shape[1])[None, :] > rx)
        comp[front] = frame_body[front]
        # 날갯짓에 맞춰 몸 전체가 위아래로 살짝 오르내린다
        frames_out.append(shift_y(comp, -bob[fi]))
    print(f"  날개 {len(wings)}장, 각도 {angles}, 위아래 {bob}, 다리 {int(legs.sum())}픽셀")
    return frames_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--out", required=True)
    ap.add_argument("--body", type=int, default=1)
    ap.add_argument("--part-top", type=int, default=34)
    ap.add_argument("--part-x", type=int, default=32)
    ap.add_argument("--tint", default="blue")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--rotate", default=None, help="날개를 돌려 만들 프레임 각도들, 예: -24,-8,14,-8")
    ap.add_argument("--back-amp", type=float, default=0.7, help="뒤쪽 작은 날개 회전 비율")
    ap.add_argument("--front-margin", type=int, default=2, help="날개 뿌리에서 이만큼 왼쪽부터 몸을 날개 앞에 그린다")
    ap.add_argument("--bob", default=None, help="프레임마다 몸이 위로 뜨는 픽셀, 예: -1,0,1,0")
    ap.add_argument("--legs", type=int, default=0, help="1이면 몸이 떠오를 때 다리가 늦게 따라오며 늘어난다")
    ap.add_argument("--legs-below", type=int, default=None, help="이 줄보다 아래 어두운 조각을 다리로 본다")
    args = ap.parse_args()

    sheet = np.array(Image.open(args.sheet).convert("RGBA"))
    size = sheet.shape[0]
    frames = [sheet[:, i * size:(i + 1) * size] for i in range(sheet.shape[1] // size)]
    if args.rotate:
        out = flap(args, frames)
        Image.fromarray(np.concatenate(out, axis=1)).save(args.out)
        print(f"저장 {args.out}")
        if args.preview:
            big = Image.fromarray(np.concatenate(out, axis=1))
            big = big.resize((big.width * 6, big.height * 6), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", big.size, (38, 43, 68, 255))
            bg.alpha_composite(big)
            bg.save(args.preview)
        return
    parts = [part_mask(f, args.part_top, args.part_x, args.tint) for f in frames]
    base = frames[args.body]
    body = body_only(base, parts[args.body])
    body_mask = body[..., 3] > 0
    out = []
    for i, (f, p) in enumerate(zip(frames, parts)):
        own_body = (f[..., 3] > 0) & ~p
        dx, dy = best_shift(body_mask, own_body)
        piece = np.zeros_like(f)
        piece[p] = f[p]
        piece = np.roll(np.roll(piece, dy, 0), dx, 1)
        comp = body.copy()
        m = piece[..., 3] > 0
        comp[m] = piece[m]
        out.append(comp)
        print(f"  {i + 1}번 프레임: 움직이는 조각 {int(p.sum())}픽셀, 몸 기준 이동 ({dx}, {dy})")
    Image.fromarray(np.concatenate(out, axis=1)).save(args.out)
    print(f"저장 {args.out}")
    if args.preview:
        big = Image.fromarray(np.concatenate(out, axis=1))
        big = big.resize((big.width * 6, big.height * 6), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", big.size, (38, 43, 68, 255))
        bg.alpha_composite(big)
        bg.save(args.preview)


if __name__ == "__main__":
    main()
