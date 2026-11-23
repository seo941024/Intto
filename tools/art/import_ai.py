"""AI가 만든 '도트처럼 보이는 큰 그림'을 진짜 도트 PNG로 바꾼다.

하는 일
1. 배경 빼기: 투명 배경이면 그대로, 단색 배경이면 가장자리 색을 찾아 지운다. 마젠타 번짐도 지운다.
2. 가짜 픽셀 크기 찾기: 색이 바뀌는 위치 간격을 모아 한 칸 크기와 격자 시작점을 추정한다.
3. 줄이기: 칸마다 가운데 부분의 대표색을 골라 한 픽셀로 만든다.
4. 색 정리: 색 수를 줄여 번진 경계를 없앤다.
5. 프레임 맞추기: --frame을 주면 그 크기 캔버스 가운데에 놓는다.

사용
  python tools/art/import_ai.py art_inbox/mongsil.png --out public/assets/characters/mongsil/raw.png --frame 48
  옵션: --grid 21.3 처럼 칸 크기를 직접 줄 수 있다. --colors 24, --key auto|alpha|magenta|green
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KEYS = {"magenta": (255, 0, 255), "green": (0, 255, 0)}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(path):
    img = Image.open(path).convert("RGBA")
    return np.array(img).astype(np.int32)


def border_color(rgb):
    h, w, _ = rgb.shape
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    q = (edge // 16) * 16 + 8
    vals, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    c = vals[counts.argmax()]
    near = edge[np.abs(q - c).sum(1) == 0]
    return tuple(int(v) for v in near.mean(0))


def foreground(a, key):
    alpha = a[..., 3]
    rgb = a[..., :3]
    if key == "alpha" or (key == "auto" and (alpha < 250).mean() > 0.02):
        return alpha >= 128, "투명 배경"
    kc = KEYS.get(key) or border_color(rgb)
    dist = np.abs(rgb - np.array(kc)).sum(-1)
    fg = dist > 110
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if kc[0] > 180 and kc[2] > 180 and kc[1] < 90:  # 마젠타 번짐
        fg &= ~((r - g > 90) & (b - g > 90) & (np.abs(r - b) < 90))
    if kc[1] > 180 and kc[0] < 90 and kc[2] < 90:  # 초록 번짐
        fg &= ~((g - r > 90) & (g - b > 90))
    return fg, f"단색 배경 {kc}"


def change_runs(rgb, fg, axis):
    """axis 방향으로 색이 바뀌는 지점 사이 간격들"""
    d = np.abs(np.diff(rgb, axis=axis)).sum(-1)
    m = np.diff(fg.astype(np.int8), axis=axis) != 0
    edge = (d > 60) | m
    runs = []
    positions = []
    lines = edge if axis == 1 else edge.T
    for line in lines[::2]:
        pos = np.flatnonzero(line)
        if len(pos) < 2:
            continue
        # 흐림 때문에 붙어 나오는 연속 위치는 하나로 묶는다
        keep = [pos[0]]
        for p in pos[1:]:
            if p - keep[-1] > 1:
                keep.append(p)
        keep = np.array(keep)
        positions.append(keep)
        runs.extend(np.diff(keep).tolist())
    return np.array(runs, dtype=float), positions


def estimate_scale(rgb, fg):
    rx, px = change_runs(rgb, fg, 1)
    ry, py = change_runs(rgb, fg, 0)
    runs = np.concatenate([rx, ry])
    runs = runs[runs >= 3]
    if len(runs) < 20:
        return None, px, py
    best = []
    for s in np.arange(3.0, 80.0, 0.05):
        k = np.round(runs / s)
        ok = k >= 1
        if ok.sum() < len(runs) * 0.5:
            continue
        err = np.abs(runs[ok] / s - k[ok])
        score = (err < 0.18).mean() * ok.mean()
        best.append((s, score))
    if not best:
        return None, px, py
    top = max(sc for _, sc in best)
    # 배수 관계의 작은 칸도 점수가 높으므로, 최고점 근처에서 가장 큰 칸을 고른다
    cands = [s for s, sc in best if sc >= top * 0.93]
    return max(cands), px, py


def estimate_offset(positions, s):
    pts = np.concatenate([p for p in positions if len(p)]) + 0.5
    ang = (pts % s) / s * 2 * np.pi
    mean = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    return (mean / (2 * np.pi) * s) % s


def grid_lines(rgb, fg, s, axis):
    """격자선 위치를 고른다. 간격은 s의 0.75~1.3배로 두고, 색 경계가 센 곳을 지나도록 동적 계획법으로 찾는다.
    AI 그림은 가짜 픽셀 크기가 조금씩 틀어지므로 고정 격자보다 정확하다."""
    d = np.abs(np.diff(rgb, axis=axis)).sum(-1).astype(float)
    d += np.abs(np.diff(fg.astype(int), axis=axis)) * 300
    prof = d.sum(0) if axis == 1 else d.sum(1)
    prof = np.convolve(prof, [0.5, 1, 0.5], "same")
    # 선을 많이 긋는 것만으로 점수가 오르지 않게, 경계가 약한 자리는 손해가 되도록 기준값을 뺀다
    prof = prof - np.percentile(prof, 70)
    n = len(prof)
    lo = max(1, int(round(s * 0.82)))
    hi = max(lo + 1, int(round(s * 1.22)))
    best = np.full(n, -np.inf)
    prev = np.full(n, -1, dtype=int)
    start = int(np.ceil(s))
    best[:start] = prof[:start]
    for i in range(start, n):
        j0, j1 = max(0, i - hi), i - lo
        if j1 < j0:
            continue
        seg = best[j0:j1 + 1]
        k = int(seg.argmax())
        if np.isfinite(seg[k]):
            best[i] = seg[k] + prof[i]
            prev[i] = j0 + k
    tail = max(0, n - int(np.ceil(s)))
    i = tail + int(best[tail:].argmax())
    lines = []
    while i >= 0:
        lines.append(i + 1)
        i = prev[i]
    return np.array(sorted(lines))


def downsample(a, fg, s, ox, oy):
    rgb = a[..., :3]
    bx = grid_lines(rgb, fg, s, 1)
    by = grid_lines(rgb, fg, s, 0)
    nx = len(bx) - 1
    ny = len(by) - 1
    out = np.zeros((ny, nx, 4), dtype=np.uint8)
    for j in range(ny):
        y0, y1 = by[j], by[j + 1]
        for i in range(nx):
            x0, x1 = bx[i], bx[i + 1]
            ix = max(1, int((x1 - x0) * 0.22))
            iy = max(1, int((y1 - y0) * 0.22))
            cy0, cy1 = y0 + iy, max(y0 + iy + 1, y1 - iy)
            cx0, cx1 = x0 + ix, max(x0 + ix + 1, x1 - ix)
            cell_fg = fg[cy0:cy1, cx0:cx1]
            if cell_fg.size == 0 or cell_fg.mean() < 0.5:
                continue
            cell = a[cy0:cy1, cx0:cx1, :3][cell_fg]
            # 배경색이 번져 든 픽셀은 대표색 고를 때 빼고 본다
            r, g, b = cell[:, 0], cell[:, 1], cell[:, 2]
            clean = ~((r - g > 50) & (b - g > 50)) & ~((g - r > 60) & (g - b > 60))
            if clean.sum() >= max(1, len(cell) // 4):
                cell = cell[clean]
            q = (cell // 8) * 8
            vals, idx, counts = np.unique(q, axis=0, return_inverse=True, return_counts=True)
            pick = cell[idx.reshape(-1) == counts.argmax()].mean(0)
            out[j, i, :3] = np.clip(pick, 0, 255)
            out[j, i, 3] = 255
    return out


def quantize(px, colors, merge=26):
    """비슷한 색끼리만 합친다. 적게 쓰인 색이라도 다른 색이면 살린다"""
    alpha = px[..., 3] > 0
    if not alpha.any():
        return px
    cols = px[..., :3][alpha].astype(int)
    vals, counts = np.unique(cols, axis=0, return_counts=True)
    order = np.argsort(-counts)
    palette = []
    weights = []
    for k in order:
        c = vals[k]
        if palette:
            d = np.abs(np.array(palette) - c).sum(1)
            j = d.argmin()
            if d[j] < merge:
                continue
        palette.append(c)
        weights.append(counts[k])
    # 그래도 너무 많으면 가장 적게 쓰인 색부터 가장 가까운 색으로 합친다
    palette = np.array(palette)
    while len(palette) > colors:
        palette = palette[:-1]
    out = px.copy()
    flat = px[..., :3].reshape(-1, 3).astype(int)
    d = np.abs(flat[:, None, :] - palette[None, :, :]).sum(-1)
    out[..., :3] = palette[d.argmin(1)].reshape(px.shape[:2] + (3,))
    out[..., 3] = np.where(alpha, 255, 0)
    return out


def drop_specks(px):
    """이웃이 하나도 없는 외톨이 픽셀을 지운다"""
    a = px[..., 3] > 0
    h, w = a.shape
    pad = np.pad(a, 1)
    n = sum(pad[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    lone = a & (n == 0)
    px[lone, 3] = 0
    return px


def crop(px):
    a = px[..., 3] > 0
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return px
    return px[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def place(px, frame):
    fw, fh = frame
    h, w = px.shape[:2]
    if w > fw or h > fh:
        print(f"  경고: 결과 {w}×{h}가 프레임 {fw}×{fh}보다 큼, 프레임을 키워 저장")
        fw, fh = max(fw, w), max(fh, h)
    out = np.zeros((fh, fw, 4), dtype=np.uint8)
    x0 = (fw - w) // 2
    y0 = (fh - h) // 2
    out[y0:y0 + h, x0:x0 + w] = px
    return out


def preview(src, res, path, zoom=8):
    src_img = Image.fromarray(src.astype(np.uint8))
    hgt = res.shape[0] * zoom
    sw = int(src_img.width * hgt / src_img.height)
    src_img = src_img.resize((sw, hgt), Image.Resampling.LANCZOS)
    big = Image.fromarray(res).resize((res.shape[1] * zoom, hgt), Image.Resampling.NEAREST)
    W = sw + big.width + 24
    canvas = Image.new("RGBA", (W, hgt), (0, 0, 0, 255))
    tile = zoom * 2
    chk = np.indices((hgt, big.width)).sum(0)
    chk = ((np.indices((hgt, big.width))[0] // tile + np.indices((hgt, big.width))[1] // tile) % 2)
    bg = np.where(chk[..., None] == 0, np.array([200, 200, 210, 255]), np.array([150, 150, 165, 255])).astype(np.uint8)
    bg_img = Image.fromarray(bg)
    bg_img.alpha_composite(big)
    canvas.paste(src_img.convert("RGBA"), (0, 0))
    canvas.paste(bg_img, (sw + 24, 0))
    canvas.save(path)


def split_columns(fg, min_gap):
    """배경만 있는 세로줄을 경계로 그림 덩어리를 나눈다"""
    cols = fg.sum(0) > 0
    segs = []
    x = 0
    w = len(cols)
    while x < w:
        if not cols[x]:
            x += 1
            continue
        x0 = x
        gap = 0
        while x < w and (cols[x] or gap < min_gap):
            gap = 0 if cols[x] else gap + 1
            x += 1
        segs.append((x0, x - gap))
    return segs


def place_bottom(px, frame):
    """아래 가운데 기준으로 프레임에 놓는다"""
    fw, fh = frame
    h, w = px.shape[:2]
    out = np.zeros((fh, fw, 4), dtype=np.uint8)
    x0 = (fw - w) // 2
    y0 = fh - h - 2
    out[max(0, y0):y0 + h, max(0, x0):x0 + w] = px[max(0, -y0):, max(0, -x0):][: fh - max(0, y0), : fw - max(0, x0)]
    return out


def shift(img, dx, dy):
    out = np.zeros_like(img)
    h, w = img.shape[:2]
    xs, xd = (0, dx) if dx >= 0 else (-dx, 0)
    ys, yd = (0, dy) if dy >= 0 else (-dy, 0)
    out[yd:h - ys if ys else h, xd:w - xs if xs else w] = img[ys:h - yd if yd else h, xs:w - xd if xd else w]
    return out


def align_to(ref, img, body_from):
    """몸통 아래쪽이 기준 프레임과 가장 많이 겹치도록 옮긴다"""
    ra = ref[..., 3] > 0
    ys = np.nonzero(ra.any(1))[0]
    cut = int(ys.min() + (ys.max() - ys.min()) * body_from)
    best = (-1, 0, 0)
    for dy in range(-6, 7):
        for dx in range(-8, 9):
            m = shift(img, dx, dy)[..., 3] > 0
            score = (m[cut:] & ra[cut:]).sum() - 0.5 * (m[cut:] ^ ra[cut:]).sum()
            if score > best[0]:
                best = (score, dx, dy)
    return shift(img, best[1], best[2]), best[1:]


def save_gif(frames, path, zoom=6, fps=8):
    imgs = []
    for f in frames:
        big = Image.fromarray(f).resize((f.shape[1] * zoom, f.shape[0] * zoom), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", big.size, (38, 43, 68, 255))
        bg.alpha_composite(big)
        imgs.append(bg.convert("P", palette=Image.Palette.ADAPTIVE))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(1000 / fps), loop=0, disposal=2)


def run_sheet(args, a, fg, s):
    h = a.shape[0]
    segs = split_columns(fg, min_gap=max(4, int(s * 1.5)))
    print(f"그림 덩어리 {len(segs)}개 발견")
    frames = []
    for x0, x1 in segs:
        pad = int(s * 2)
        sub = a[:, max(0, x0 - pad):x1 + pad]
        sfg = fg[:, max(0, x0 - pad):x1 + pad]
        _, px, py = estimate_scale(sub[..., :3], sfg)
        ox = estimate_offset(px, s)
        oy = estimate_offset(py, s)
        res = drop_specks(downsample(sub, sfg, s, ox, oy))
        frames.append(crop(res))
    # 모든 프레임을 한 팔레트로
    wsum = sum(f.shape[1] for f in frames)
    hmax = max(f.shape[0] for f in frames)
    strip = np.zeros((hmax, wsum, 4), dtype=np.uint8)
    x = 0
    for f in frames:
        strip[: f.shape[0], x:x + f.shape[1]] = f
        x += f.shape[1]
    strip = quantize(strip, args.colors)
    x = 0
    for i, f in enumerate(frames):
        frames[i] = strip[: f.shape[0], x:x + f.shape[1]]
        x += f.shape[1]
    parts = (args.frame or "56").lower().split("x")
    fw = int(parts[0])
    fh = int(parts[1]) if len(parts) > 1 else fw
    placed = [place_bottom(f, (fw, fh)) for f in frames]
    ref = placed[min(args.ref, len(placed) - 1)]
    out = []
    for i, f in enumerate(placed):
        if f is ref:
            out.append(f)
            continue
        g, (dx, dy) = align_to(ref, f, args.body_from)
        print(f"  {i + 1}번 프레임 몸통 맞춤 이동 ({dx}, {dy})")
        out.append(g)
    sheet = np.concatenate(out, axis=1)
    n_colors = len(np.unique(sheet[sheet[..., 3] > 0][:, :3], axis=0))
    print(f"시트 {sheet.shape[1]}×{sheet.shape[0]}, 프레임 {len(out)}개 {fw}×{fh}, {n_colors}색")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(args.out)
    if args.preview:
        Path(args.preview).parent.mkdir(parents=True, exist_ok=True)
        save_gif(out, args.preview, fps=args.fps)
        print(f"움직임 미리보기 {args.preview}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frame", type=str, default=None, help="48 또는 48x48")
    ap.add_argument("--grid", type=float, default=None)
    ap.add_argument("--colors", type=int, default=40)
    ap.add_argument("--key", default="auto")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--sheet", action="store_true", help="한 줄로 늘어선 여러 프레임을 나눠 시트로 만든다")
    ap.add_argument("--ref", type=int, default=1, help="몸통 맞춤 기준 프레임 번호, 0부터")
    ap.add_argument("--body-from", type=float, default=0.45, help="그림 높이의 이 비율 아래를 몸통으로 보고 맞춘다")
    ap.add_argument("--fps", type=int, default=8)
    args = ap.parse_args()

    a = load(args.input)
    fg, how = foreground(a, args.key)
    print(f"입력 {a.shape[1]}×{a.shape[0]}, {how}, 전경 {fg.mean() * 100:.1f}%")
    rgb = a[..., :3]
    s, px, py = estimate_scale(rgb, fg)
    if args.grid:
        s = args.grid
    if not s:
        sys.exit("칸 크기를 찾지 못함, --grid로 직접 지정")
    if args.sheet:
        print(f"가짜 픽셀 한 칸 {s:.2f}px")
        return run_sheet(args, a, fg, s)
    ox = estimate_offset(px, s)
    oy = estimate_offset(py, s)
    print(f"가짜 픽셀 한 칸 {s:.2f}px, 격자 시작 ({ox:.1f}, {oy:.1f})")
    res = downsample(a, fg, s, ox, oy)
    res = drop_specks(res)
    res = quantize(res, args.colors)
    res = crop(res)
    if args.frame:
        parts = args.frame.lower().split("x")
        fw = int(parts[0])
        fh = int(parts[1]) if len(parts) > 1 else fw
        res = place(res, (fw, fh))
    n_colors = len(np.unique(res[res[..., 3] > 0][:, :3], axis=0))
    print(f"출력 {res.shape[1]}×{res.shape[0]}, {n_colors}색")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(res).save(out)
    if args.preview:
        Path(args.preview).parent.mkdir(parents=True, exist_ok=True)
        preview(a, res, args.preview)
        print(f"비교 미리보기 {args.preview}")


if __name__ == "__main__":
    main()
