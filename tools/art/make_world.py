#!/usr/bin/env python3
"""인또 월드 그림 생성기, ASSET_SPEC.md 6장.

프로젝트 루트에서 `python tools/art/make_world.py`를 실행하면
public/assets/world/<cloud|mushroom|storm>/ 의 PNG·JSON과
tools/art/_preview/world_* 미리보기를 다시 만든다. 난수는 모두 고정 시드라서
몇 번을 돌려도 같은 그림이 나온다.
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'world')
PREV = os.path.join(HERE, '_preview')
VW, VH = 640, 360

# ====================================================================== 팔레트
_E32 = ('be4a2f d77643 ead4aa e4a672 b86f50 733e39 3e2731 a22633 e43b44 f77622 feae34 '
        'fee761 63c74d 3e8948 265c42 193c3e 124e89 0099db 2ce8f5 ffffff c0cbdc 8b9bb4 '
        '5a6988 3a4466 262b44 181425 ff0044 68386c b55088 f6757a e8b796 c28569').split()
_NAMES = ('rust clay cream tan brownl brown brownd redd red orange gold yellow green greend '
          'forest teal blued blue cyan white gray1 gray2 gray3 gray4 navy ink hot purple pink '
          'salmon skin skind').split()


def hexc(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


PAL = {n: hexc(h) for n, h in zip(_NAMES, _E32)}


def col(c):
    if isinstance(c, str):
        return PAL[c] if c in PAL else hexc(c)
    return tuple(int(v) for v in c)


def mix(a, b, t):
    a, b = col(a), col(b)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# 테마별로 더한 중간색. 모두 Endesga 32 두 색 사이의 같은 계열 색이다.
SKY1 = hexc('3db0e5')   # 0099db와 c0cbdc 사이 하늘
SKY2 = hexc('7fcaee')
SKY3 = hexc('bfe6f4')
NIGHT1 = mix('ink', 'navy', 0.5)
NIGHT3 = mix('navy', 'gray4', 0.5)

LIGHT = np.array([-0.55, -0.72, 0.42])
LIGHT = LIGHT / np.linalg.norm(LIGHT)

# ====================================================================== 기본 도구


def bayer(n):
    m = np.array([[0, 2], [3, 1]], dtype=float)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / m.size


B4, B8 = bayer(4), bayer(8)


def thr(shape, B, yy=None, xx=None):
    n = B.shape[0]
    if yy is None:
        h, w = shape
        return B[np.ix_(np.arange(h) % n, np.arange(w) % n)]
    return B[np.asarray(yy, int) % n, np.asarray(xx, int) % n]


def ramp(field, cols, sharp=1.0, B=B8, yy=None, xx=None):
    """실수 필드를 색 단계로 바꾼다. 단계 사이는 Bayer 디더링, sharp가 크면 띠가 또렷해진다."""
    ca = np.array([col(c) for c in cols], np.uint8)
    n = len(ca)
    field = np.asarray(field, float)
    if n == 1:
        return np.broadcast_to(ca[0], field.shape + (3,)).copy()
    f = np.clip(field, 0, n - 1)
    i = np.minimum(np.floor(f).astype(int), n - 2)
    fr = np.clip((f - i - 0.5) * sharp + 0.5, 0, 1)
    idx = i + (fr > thr(field.shape, B, yy, xx))
    return ca[idx]


def new(w, h):
    return np.zeros((h, w, 4), np.uint8)


def rgba(rgb, a=255):
    out = np.empty(rgb.shape[:2] + (4,), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = a
    return out


def paint(img, mask, c, a=255):
    img[mask, :3] = col(c)
    img[mask, 3] = a


def paint_rgb(img, mask, rgb):
    img[mask, :3] = rgb[mask]
    img[mask, 3] = 255


def put(img, x, y, c, a=255, wrap=False):
    h, w = img.shape[:2]
    x, y = int(x), int(y)
    if wrap:
        x %= w
        y %= h
    if 0 <= x < w and 0 <= y < h:
        img[y, x, :3] = col(c)
        img[y, x, 3] = a


def opaque(img):
    return img[..., 3] > 0


def grid(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    return xx + 0.5, yy + 0.5


def igrid(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    return xx, yy


def wrapd(d, p):
    return (d + p / 2) % p - p / 2


def _sh(m, d, axis):
    if d == 0:
        return m
    out = np.zeros_like(m)
    if axis == 1:
        if d > 0:
            out[:, d:] = m[:, :-d]
        else:
            out[:, :d] = m[:, -d:]
    else:
        if d > 0:
            out[d:] = m[:-d]
        else:
            out[:d] = m[-d:]
    return out


def shift(m, dx, dy, wrapx=False, wrapy=False):
    """result[y, x] = m[y - dy, x - dx]. 밖에서 들어오는 칸은 False."""
    r = np.roll(m, dx, axis=1) if wrapx else _sh(m, dx, 1)
    r = np.roll(r, dy, axis=0) if wrapy else _sh(r, dy, 0)
    return r


N4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
N8 = N4 + [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def dilate(m, dirs=N8, wrapx=False, wrapy=False):
    r = m.copy()
    for dx, dy in dirs:
        r |= shift(m, dx, dy, wrapx, wrapy)
    return r


def outline(img, c, dirs=N4, wrapx=False):
    m = opaque(img)
    ring = dilate(m, dirs, wrapx) & ~m
    paint(img, ring, c)
    return ring


def glow(img, c, alphas, dirs_cycle=(N4, N8)):
    """불투명 그림 둘레에 반투명 빛 고리. alphas는 안쪽 고리부터."""
    m = opaque(img)
    cur = m.copy()
    for k, a in enumerate(alphas):
        nxt = dilate(cur, dirs_cycle[k % len(dirs_cycle)])
        ring = nxt & ~cur & (img[..., 3] == 0)
        paint(img, ring, c, a)
        cur = nxt


def blit(dst, src, x, y, wrapx=False):
    offs = (x - dst.shape[1], x, x + dst.shape[1]) if wrapx else (x,)
    for ox in offs:
        _blit(dst, src, ox, y)


def _blit(dst, src, x, y):
    sh, sw = src.shape[:2]
    dh, dw = dst.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + sw, dw), min(y + sh, dh)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    sa = s[..., 3:4] / 255.0
    da = d[..., 3:4] / 255.0
    oa = sa + da * (1 - sa)
    oc = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    out = np.concatenate([oc, oa * 255], axis=-1)
    dst[y0:y1, x0:x1] = np.clip(np.round(out), 0, 255).astype(np.uint8)


def vnoise(h, w, cy, cx, seed, wrap_y):
    rng = np.random.default_rng(seed)
    gy = cy if wrap_y else cy + 1
    g = rng.random((gy, cx))
    y = (np.arange(h) + 0.5) * cy / h
    x = (np.arange(w) + 0.5) * cx / w
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    sy, sx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    if wrap_y:
        y0 %= gy
        y1 = (y0 + 1) % gy
    else:
        y1 = np.minimum(y0 + 1, gy - 1)
    x0 %= cx
    x1 = (x0 + 1) % cx
    a, b = g[np.ix_(y0, x0)], g[np.ix_(y0, x1)]
    c, d = g[np.ix_(y1, x0)], g[np.ix_(y1, x1)]
    top = a + (b - a) * sx[None, :]
    bot = c + (d - c) * sx[None, :]
    return top + (bot - top) * sy[:, None]


def fbm(h, w, cy, cx, octaves=3, seed=0, wrap_y=False, gain=0.5):
    """가로는 항상 w 주기로 이어진다. wrap_y면 세로도 h 주기."""
    tot, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        tot = tot + amp * vnoise(h, w, cy * 2 ** o, cx * 2 ** o, seed + 101 * o, wrap_y)
        norm += amp
        amp *= gain
    return tot / norm


def fbm1(w, cells, octaves=3, seed=0):
    return fbm(1, w, 1, cells, octaves, seed)[0]


def pil_mask(w, h, fn, wrapx=False):
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    for o in ((-w, 0, w) if wrapx else (0,)):
        fn(d, o)
    return np.array(im) > 0


def poly_mask(w, h, pts, wrapx=False):
    return pil_mask(w, h, lambda d, o: d.polygon([(x + o, y) for x, y in pts], fill=255), wrapx)


def line_pts(x0, y0, x1, y1):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    pts = []
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def draw_line(img, x0, y0, x1, y1, c, a=255, wrap=False):
    for x, y in line_pts(x0, y0, x1, y1):
        put(img, x, y, c, a, wrap)


def polyline(img, pts, c, a=255):
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        draw_line(img, x0, y0, x1, y1, c, a)


def ellipse_mask(w, h, cx, cy, rx, ry):
    xx, yy = grid(w, h)
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0


def sphere(w, h, cx, cy, rx, ry, cols, sharp=4.0, B=B4, bias=0.0, gain=1.0):
    xx, yy = grid(w, h)
    nx, ny = (xx - cx) / rx, (yy - cy) / ry
    m = nx * nx + ny * ny <= 1.0
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    lum = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
    v = (np.clip(lum * gain, -1, 1) * 0.5 + 0.5) * (len(cols) - 1) + bias
    return m, ramp(v, cols, sharp, B)


def save(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(img, 'RGBA').save(path)


def up(img, s):
    im = Image.fromarray(img, 'RGBA')
    return np.array(im.resize((im.width * s, im.height * s), Image.NEAREST))


def flat(img, bg):
    out = rgba(np.broadcast_to(np.array(col(bg), np.uint8), img.shape[:2] + (3,)).copy())
    blit(out, img, 0, 0)
    return out


# ====================================================================== 공용 그림 부품


def sky_field(stops):
    y = np.arange(VH) + 0.5
    v = np.interp(y, stops, np.arange(len(stops), dtype=float))
    return np.repeat(v[:, None], VW, axis=1)


def draw_puffs(img, puffs, cols, sharp=2.4, B=B4, under=0.0, wrapx=True, gain=1.0):
    """구름 덩어리를 원 여러 개로 그린다. 뒤에 그린 원이 앞으로 온다."""
    h, w = img.shape[:2]
    n = len(cols)
    for cx, cy, r in puffs:
        y0 = max(int(math.floor(cy - r)) - 1, 0)
        y1 = min(int(math.ceil(cy + r)) + 1, h)
        if y0 >= y1:
            continue
        xs = np.arange(int(math.floor(cx - r)) - 1, int(math.ceil(cx + r)) + 2)
        ys = np.arange(y0, y1)
        X, Y = np.meshgrid(xs, ys)
        dx, dy = X + 0.5 - cx, Y + 0.5 - cy
        m = dx * dx + dy * dy <= r * r
        nx, ny = dx / r, dy / r
        nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
        lum = np.clip((nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]) * gain, -1, 1)
        v = (lum * 0.5 + 0.5) * (n - 1) - under * np.clip(ny, 0, 1)
        XI = X % w if wrapx else X
        if not wrapx:
            m &= (X >= 0) & (X < w)
        rgb = ramp(v, cols, sharp, B, Y, XI)
        img[Y[m], XI[m], :3] = rgb[m]
        img[Y[m], XI[m], 3] = 255


def puffs_torus(img, puffs, cols, sharp=2.4, B=B4, under=0.0):
    s = img.shape[0]
    xx, yy = grid(s, s)
    ix, iy = igrid(s, s)
    for cx, cy, r in puffs:
        dx, dy = wrapd(xx - cx, s), wrapd(yy - cy, s)
        m = dx * dx + dy * dy <= r * r
        nx, ny = dx / r, dy / r
        nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
        lum = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
        v = (lum * 0.5 + 0.5) * (len(cols) - 1) - under * np.clip(ny, 0, 1)
        paint_rgb(img, m, ramp(v, cols, sharp, B, iy, ix))


def rim_light(img, mask, c, k=1, wrapx=True, dither=None):
    """윗왼쪽 가장자리 k픽셀을 밝게. dither는 두 번째 줄의 밀도."""
    edge = mask & ~shift(mask, k, k, wrapx)
    edge |= mask & ~shift(mask, 0, k, wrapx)
    paint(img, edge, c)
    return edge


def alpha_fade_rows(img, rows, B=B4):
    """rows: {y: 남길 비율}. 몸통 타일과 섞이도록 띠의 안쪽 끝을 디더링으로 비운다."""
    h, w = img.shape[:2]
    t = thr((h, w), B)
    for y, keep in rows.items():
        kill = t[y] >= keep
        img[y, kill, 3] = 0


def stamp_torus(img, spr, x, y):
    s = img.shape[0]
    h, w = spr.shape[:2]
    for yy in range(h):
        for xx in range(w):
            if spr[yy, xx, 3]:
                img[(y + yy) % s, (x + xx) % s] = spr[yy, xx]


def facet_rock(size, r, seed, cols, cx=None, cy=None, squash=1.0, cells=10, harm=0.08,
               spikes=0, spike_h=(1.5, 2.5)):
    """깎아 낸 듯한 면이 있는 바위 덩어리. 면마다 왼쪽 위 빛으로 평면 음영."""
    rng = np.random.default_rng(seed)
    cx = size / 2 if cx is None else cx
    cy = size / 2 if cy is None else cy
    xx, yy = grid(size, size)
    dx, dy = xx - cx, (yy - cy) / squash
    ang = np.arctan2(dy, dx)
    d = np.hypot(dx, dy)
    rr = np.full_like(d, r)
    for k in (2, 3, 5):
        rr += r * harm * rng.uniform(0.4, 1.0) * np.cos(k * ang + rng.uniform(0, 2 * np.pi))
    for _ in range(spikes):
        a0 = rng.uniform(0.2 * np.pi, 0.8 * np.pi)
        da = np.angle(np.exp(1j * (ang - a0)))
        rr += np.clip(1 - np.abs(da) / 0.2, 0, 1) * rng.uniform(*spike_h)
    mask = d <= rr
    pts = []
    while len(pts) < cells:
        px, py = rng.uniform(cx - r, cx + r), rng.uniform(cy - r * squash, cy + r * squash)
        if math.hypot(px - cx, (py - cy) / squash) < r * 0.9:
            pts.append((px, py))
    P = np.array(pts)
    dist = (xx[..., None] - P[:, 0]) ** 2 + (yy[..., None] - P[:, 1]) ** 2
    owner = dist.argmin(-1)
    lev = np.zeros(cells)
    for i, (px, py) in enumerate(pts):
        nx = (px - cx) / r + rng.normal(0, 0.16)
        ny = (py - cy) / (r * squash) + rng.normal(0, 0.16)
        nz = math.sqrt(max(0.1, 1 - nx * nx - ny * ny))
        nv = np.array([nx, ny, nz])
        nv /= np.linalg.norm(nv)
        lev[i] = (nv @ LIGHT * 0.5 + 0.5) * (len(cols) - 1)
    v = lev[owner]
    crack = np.zeros_like(mask)
    crack[:, :-1] |= (owner[:, :-1] != owner[:, 1:]) & (lev[owner[:, :-1]] > lev[owner[:, 1:]])
    crack[:, 1:] |= (owner[:, 1:] != owner[:, :-1]) & (lev[owner[:, 1:]] < lev[owner[:, :-1]])
    crack[:-1, :] |= (owner[:-1, :] != owner[1:, :]) & (lev[owner[:-1, :]] < lev[owner[1:, :]])
    v = np.where(crack, v - 0.9, v)
    tl = mask & ~shift(mask, 1, 1)
    br = mask & ~shift(mask, -1, -1)
    v = np.where(tl, v + 0.7, v)
    v = np.where(br, v - 0.8, v)
    img = new(size, size)
    paint_rgb(img, mask, ramp(v, cols, 5.0, B4))
    return img, mask


def shard(img, bx, by, ang, length, width, cols, tip=0.38, edge_c=None):
    """수정 조각. cols는 어두운 면, 밝은 면, 능선 순."""
    h, w = img.shape[:2]
    ax, ay = math.cos(ang), math.sin(ang)
    px, py = -ay, ax
    hw = width / 2
    body = length * (1 - tip)
    pts = [(bx + px * hw * 0.55, by + py * hw * 0.55),
           (bx + ax * body + px * hw, by + ay * body + py * hw),
           (bx + ax * length, by + ay * length),
           (bx + ax * body - px * hw, by + ay * body - py * hw),
           (bx - px * hw * 0.55, by - py * hw * 0.55)]
    m = poly_mask(w, h, pts)
    xx, yy = grid(w, h)
    s = (xx - bx) * px + (yy - by) * py
    lit_sign = 1 if (px * LIGHT[0] + py * LIGHT[1]) > 0 else -1
    face = np.where(s * lit_sign > 0, 1, 0)
    rgb = np.zeros((h, w, 3), np.uint8)
    rgb[:] = col(cols[0])
    rgb[face == 1] = col(cols[1])
    ridge = np.abs(s) < 0.55
    rgb[ridge] = col(cols[2])
    paint_rgb(img, m, rgb)
    if edge_c is not None:
        e = m & ~(shift(m, 1, 0) & shift(m, -1, 0) & shift(m, 0, 1) & shift(m, 0, -1))
        e &= ~ridge
        dark_side = (s * lit_sign) <= 0
        paint(img, e & dark_side, edge_c)
    return m


def radial_profile(img, ax, ay):
    """앵커에서 불투명 그림 끝까지의 거리. 각도별 최대 반지름의 최소·평균·최대."""
    a = img[..., 3] >= 200
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return 0, 0, 0
    dx, dy = xs + 0.5 - ax, ys + 0.5 - ay
    ang = np.arctan2(dy, dx)
    d = np.hypot(dx, dy)
    bins = np.linspace(-np.pi, np.pi, 49)
    idx = np.digitize(ang, bins) - 1
    rad = np.zeros(48)
    for i in range(48):
        sel = idx == i
        if sel.any():
            rad[i] = d[sel].max()
    return rad.min(), rad.mean(), rad.max()


# ====================================================================== 지형 띠 공용


def edge_floor(spec):
    """바닥 윗면 띠 16×12. spec은 열마다 값을 주는 손그림 표."""
    w, h, ay = 16, 12, spec['ay']
    img = new(w, h)
    t4 = thr((h, w), B4)
    for x in range(w):
        # 경계선 위로 삐져나온 풀·이끼·돌기
        for k in range(1, spec['above'][x] + 1):
            c = spec['tip'] if k == spec['above'][x] else spec['tipbase']
            put(img, x, ay - k, c)
        th = spec['thick'][x]
        for k in range(th):
            y = ay + k
            if k == 0:
                c = spec['top'][x] if 'top' in spec else spec['band'][0]
            elif k == th - 1:
                c = spec['band'][-1]
            else:
                bi = min(k, len(spec['band']) - 2)
                c = spec['band'][bi]
                if k == 1 and t4[y, x] < spec.get('mix1', 0.5):
                    c = spec['band'][0]
            put(img, x, y, c)
        y = ay + th
        for k, c in enumerate(spec['under']):
            if y + k < h:
                cc = c[0] if t4[y + k, x] < c[1] else c[2]
                put(img, x, y + k, cc)
        for yy in range(y + len(spec['under']), h):
            cc = spec['fill'][0] if t4[yy, x] < spec['fill'][1] else spec['fill'][2]
            put(img, x, yy, cc)
    for (x, y, c) in spec.get('dots', []):
        put(img, x, y, c)
    alpha_fade_rows(img, {h - 3: 0.8, h - 2: 0.55, h - 1: 0.3})
    return img


# ====================================================================== 테마 cloud


def cloud_sky():
    cols = ['blued', 'blue', SKY1, SKY2, SKY3, 'white']
    f = sky_field([0, 54, 128, 192, 256, 352])
    xx, yy = grid(VW, VH)
    sx, sy = 104, 84
    d = np.hypot(xx - sx, yy - sy)
    f = f + 1.3 * np.exp(-(d / 30) ** 2) + 0.8 * np.exp(-(d / 92) ** 2)
    for cx, cy, rx, ry, a in [(322, 40, 74, 4.5, 0.85), (372, 47, 44, 3.5, 0.6), (548, 96, 62, 5, 0.8),
                              (596, 89, 30, 3, 0.55), (236, 124, 48, 4, 0.65), (462, 150, 40, 3, 0.5),
                              (26, 168, 36, 3, 0.45)]:
        e = 1 - ((xx - cx) / rx) ** 2 - ((yy - cy) / ry) ** 2
        f = f + a * np.clip(e, 0, 1) ** 0.5
    img = rgba(ramp(f, cols, 2.6, B8))
    paint(img, (d > 10.3) & (d <= 11.8), 'yellow')
    paint(img, d <= 10.3, 'white')
    return img


def cloud_far():
    img = new(VW, VH)
    rng = np.random.default_rng(1101)
    x = np.arange(VW) + 0.5
    xx, yy = grid(VW, VH)
    peaks = []
    p = 0.0
    while p < VW - 40:
        peaks.append((p + rng.uniform(0, 18), rng.uniform(36, 86), rng.uniform(0.8, 1.3),
                      rng.uniform(0.8, 1.3), rng.uniform(-0.45, 0.45)))
        p += rng.uniform(72, 120)
    base = 266.0
    prof = np.full(VW, -1e9)
    owner = np.zeros(VW, int)
    side = np.zeros(VW)
    for i, (pp, ph, sl, sr, _) in enumerate(peaks):
        dx = wrapd(x - pp, VW)
        hh = ph - np.where(dx < 0, -dx * sl, dx * sr)
        better = hh > prof
        prof[better], owner[better], side[better] = hh[better], i, dx[better]
    jag = (fbm1(VW, 80, 3, 1102) - 0.5) * 7
    top = base - prof - jag
    inside = yy >= top[None, :]
    ph_o = np.array([peaks[i][1] for i in owner])[None, :]
    tilt = np.array([peaks[i][4] for i in owner])[None, :]
    depth = yy - (base - ph_o)
    n = fbm(VH, VW, 24, 96, 3, 1103)
    ridge = side[None, :] + depth * tilt + (n - 0.5) * 10
    lit = ridge < 0
    snow = depth < ph_o * 0.5 + (n - 0.5) * 16
    gully = (np.sin((side[None, :] * 0.9 + depth * 0.7) * 0.55 + n * 5) > 0.8) & (depth > 6)
    MT_SH = mix(SKY2, SKY1, 0.35)
    c = np.zeros((VH, VW, 3), np.uint8)
    c[:] = SKY1
    c[lit & ~snow] = SKY3
    c[lit & snow] = col('white')
    c[~lit & snow] = MT_SH
    c[lit & gully] = SKY2 if True else SKY2
    c[~lit & gully] = SKY1
    paint_rgb(img, inside, c)
    # 구름 바다
    puffs = []
    for row, (cy0, r0, r1, step) in enumerate([(250, 12, 20, 26), (266, 15, 24, 30), (290, 18, 28, 34),
                                                (320, 22, 32, 40)]):
        xq = rng.uniform(0, step)
        while xq < VW:
            puffs.append((xq, cy0 + rng.uniform(-5, 5), rng.uniform(r0, r1)))
            xq += step * rng.uniform(0.7, 1.15)
    draw_puffs(img, puffs, [SKY2, SKY3, 'white', 'white'], sharp=2.2, under=0.6)
    paint(img, (yy > 330), 'white')
    return img


def cloud_island(img, cx, ty, wd, dp, seed, tree=False, fall=None):
    rng = np.random.default_rng(seed)
    haze = SKY2
    G1, G2 = mix('green', haze, 0.42), mix('greend', haze, 0.42)
    R = [mix('brownd', haze, 0.5), mix('brown', haze, 0.48), mix('brownl', haze, 0.46)]
    n = 16
    xl = cx - wd / 2
    pts = []
    for i in range(n + 1):
        t = i / n
        yq = ty + dp * math.sin(math.pi * t) ** 0.75 + (rng.uniform(-2.5, 2.5) if 0 < i < n else 0)
        pts.append((xl + t * wd, yq))
    pts[n // 2] = (pts[n // 2][0] + rng.uniform(-4, 4), ty + dp + 4)
    top = [(xl + wd, ty), (xl + wd - 2, ty - 2)]
    for i in range(1, 6):
        top.append((xl + wd - wd * i / 6, ty - 2 - rng.uniform(0, 1.5)))
    top.append((xl + 2, ty - 2))
    poly = pts + top
    m = poly_mask(VW, VH, poly, wrapx=True)
    xx, yy = grid(VW, VH)
    ix, iy = igrid(VW, VH)
    rel = wrapd(xx - cx, VW) / (wd / 2)
    v = 1.5 - rel * 0.8 - np.clip((yy - ty) / dp, 0, 1) * 0.9
    strata = (np.sin((yy - ty) * 1.25 + rel * 1.3) > 0.75)
    v = np.where(strata, v - 0.6, v)
    paint_rgb(img, m, ramp(v, R, 2.5, B4, iy, ix))
    # 풀 덮개
    colsx = np.nonzero(m.any(axis=0))[0]
    for xq in colsx:
        ys = np.nonzero(m[:, xq])[0]
        y0 = ys[0]
        th = 2 + (hash((seed, int(xq))) % 3 == 0)
        for k in range(th + 1):
            if y0 + k <= ys[-1]:
                put(img, xq, y0 + k, G1 if k == 0 else G2)
    if tree:
        tx = int(cx + wd * 0.18)
        for yq in range(ty - 7, ty - 1):
            put(img, tx, yq, R[0], wrap=True)
        mk, rgb = sphere(VW, VH, tx + 0.5, ty - 11, 6, 5.5, [G2, G1, mix('green', 'white', 0.3)], 4)
        paint_rgb(img, mk, rgb)
    if fall is not None:
        fx = int(xl + wd * fall)
        ys = np.nonzero(m[:, fx % VW])[0]
        y0 = ys[0] + 1 if len(ys) else ty
        t8 = thr((VH, VW), B8)
        for yq in range(y0, min(VH, y0 + 120)):
            fade = 1 - (yq - y0) / 120
            for dxq, c in ((-1, SKY3), (0, 'white'), (1, 'white'), (2, SKY3)):
                xq = (fx + dxq) % VW
                if m[yq, xq]:
                    continue
                if t8[yq, xq] < fade ** 1.2:
                    put(img, xq, yq, c)


def cloud_mid():
    img = new(VW, VH)
    rng = np.random.default_rng(1201)
    cloud_island(img, 92, 150, 78, 46, 11, tree=True, fall=0.72)
    cloud_island(img, 286, 204, 44, 28, 12)
    cloud_island(img, 452, 118, 96, 58, 13, tree=False, fall=0.3)
    cloud_island(img, 590, 178, 40, 26, 14, tree=True)
    puffs = []
    for cy0, r0, r1, step in [(292, 13, 22, 30), (306, 16, 26, 34), (330, 20, 30, 38), (356, 24, 32, 40)]:
        xq = rng.uniform(0, step)
        while xq < VW:
            puffs.append((xq, cy0 + rng.uniform(-6, 6), rng.uniform(r0, r1)))
            xq += step * rng.uniform(0.75, 1.2)
    draw_puffs(img, puffs, [SKY1, SKY2, SKY3, 'white'], sharp=2.4, under=0.5)
    return img


def cloud_floor_body():
    s = 32
    xx, yy = grid(s, s)
    n1 = fbm(s, s, 2, 2, 3, 301, wrap_y=True)
    n2 = fbm(s, s, 8, 8, 2, 302, wrap_y=True)
    strata = np.sin(2 * np.pi * (yy / 16 + (n1 - 0.5) * 0.8))
    v = 1.05 + 0.45 * strata + 1.0 * (n2 - 0.5)
    img = rgba(ramp(v, ['brownd', 'brown', 'brownl'], 1.5, B4))
    rng = np.random.default_rng(303)
    for _ in range(7):
        cx, cy = rng.uniform(0, s, 2)
        rx = rng.uniform(1.4, 2.8)
        ry = rx * rng.uniform(0.6, 0.85)
        dx, dy = wrapd(xx - cx, s), wrapd(yy - cy, s)
        e = (dx / rx) ** 2 + (dy / ry) ** 2
        m = e <= 1
        lum = -(dx / rx) * 0.6 - (dy / ry) * 0.8
        paint(img, m, 'brownl')
        paint(img, m & (lum > 0.45), 'tan')
        paint(img, m & (lum < -0.55), 'skind')
        paint(img, (e > 1) & (e <= 1.9) & (dy > 0.2), 'brownd')
    return img


def cloud_floor_edge():
    return edge_floor({
        'ay': 3,
        'above':  [1, 0, 2, 3, 1, 0, 1, 2, 0, 0, 2, 1, 3, 1, 0, 1],
        'thick':  [4, 4, 5, 5, 4, 3, 4, 5, 6, 5, 4, 4, 5, 4, 3, 4],
        'tip': 'green', 'tipbase': 'green',
        'band': ['green', 'greend', 'greend', 'forest'],
        'mix1': 0.45,
        'under': [('brownd', 1.1, 'brownd'), ('brownd', 0.55, 'brown')],
        'fill': ('brown', 0.75, 'brownl'),
        'dots': [(5, 4, 'green'), (10, 5, 'green'), (14, 4, 'green')],
    })


def cloud_ceil_body():
    s = 32
    img = rgba(np.broadcast_to(np.array(col('gray1'), np.uint8), (s, s, 3)).copy())
    rng = np.random.default_rng(311)
    puffs = []
    for gy in range(3):
        for gx in range(3):
            puffs.append((gx * s / 3 + rng.uniform(0, s / 3), gy * s / 3 + rng.uniform(0, s / 3),
                          rng.uniform(4.5, 7.5)))
    rng.shuffle(puffs)
    puffs_torus(img, puffs, ['gray2', 'gray1', 'gray1', 'white'], sharp=2.2, under=0.4)
    return img


def cloud_ceil_edge():
    w, h, ay = 16, 12, 7
    img = new(w, h)
    depth = [2, 3, 3, 2, 1, 2, 2, 1, 3, 4, 4, 3, 1, 2, 2, 2]
    t4 = thr((h, w), B4)
    for x in range(w):
        bot = ay + depth[x]
        for y in range(bot):
            k = bot - 1 - y
            if k == 0:
                c = 'gray3'
            elif k <= 2:
                c = 'gray2'
            elif k == 3:
                c = 'gray2' if t4[y, x] < 0.5 else 'gray1'
            elif k == 4:
                c = 'gray1' if t4[y, x] < 0.8 else 'gray2'
            else:
                c = 'gray1'
            put(img, x, y, c)
        # 덩어리 사이 주름
        if depth[x] < depth[(x - 1) % w] and depth[x] < depth[(x + 1) % w] or depth[x] == 1:
            for y in range(ay - 2, bot - 1):
                put(img, x, y, 'gray2')
    # 덩어리 윗부분 흰 테
    for x, y in [(1, 6), (2, 6), (9, 7), (10, 7), (5, 6), (14, 6)]:
        put(img, x, y, 'gray1')
    alpha_fade_rows(img, {0: 0.3, 1: 0.55, 2: 0.8})
    return img


def cloud_decor():
    d = {}
    # a: 데이지 세 송이
    a = new(16, 16)
    for (x0, y0, x1, y1) in [(6, 15, 5, 7), (8, 15, 9, 4), (10, 15, 12, 9)]:
        draw_line(a, x0, y0, x1, y1, 'greend')
    for x, y in [(4, 12), (5, 11), (3, 11), (10, 12), (11, 11), (12, 11), (7, 13), (6, 14), (9, 14)]:
        put(a, x, y, 'green')
    for fx, fy in [(5, 6), (9, 3), (12, 8)]:
        for dx, dy in N4:
            put(a, fx + dx, fy + dy, 'white')
        for dx, dy in [(1, 1), (-1, 1)]:
            put(a, fx + dx, fy + dy, 'gray1')
        for dx, dy in [(1, -1), (-1, -1)]:
            put(a, fx + dx, fy + dy, 'white')
        put(a, fx, fy, 'gold')
    for x in range(3, 13):
        put(a, x, 15, 'greend' if x % 3 else 'forest')
    d['decor_floor_a'] = (a, [8, 14])
    # b: 파란 초롱꽃
    b = new(16, 24)
    stem = [(8, 23), (8, 18), (7, 13), (7, 8), (8, 5), (10, 4), (11, 5)]
    polyline(b, stem, 'greend')
    for x, y in [(6, 21), (5, 20), (4, 20), (9, 20), (10, 19), (11, 19), (6, 16), (5, 15)]:
        put(b, x, y, 'green')
    for bx, by in [(11, 6), (6, 9), (9, 13)]:
        put(b, bx, by, 'blue')
        for x in range(bx - 1, bx + 2):
            put(b, x, by + 1, 'blue')
        put(b, bx - 1, by + 1, SKY1)
        for x in range(bx - 1, bx + 2):
            put(b, x, by + 2, 'blued')
        put(b, bx - 2, by + 3, 'blued')
        put(b, bx + 2, by + 3, 'blued')
        put(b, bx - 1, by + 1, 'white')
    for x in range(5, 12):
        put(b, x, 23, 'greend' if x % 2 else 'forest')
    d['decor_floor_b'] = (b, [8, 22])
    # c: 이끼 낀 돌
    c = new(16, 16)
    m, rgb = sphere(16, 16, 8, 11.5, 6.5, 4.6, ['brownd', 'brown', 'brownl', 'tan'], 4)
    paint_rgb(c, m, rgb)
    for x in range(3, 13):
        ys = np.nonzero(m[:, x])[0]
        if len(ys):
            put(c, x, ys[0], 'green')
            if x % 3:
                put(c, x, ys[0] + 1, 'greend')
    for x, y in [(4, 6), (6, 5), (10, 6), (11, 5)]:
        put(c, x, y, 'green')
    outline(c, 'brownd')
    c[15, :, 3] = np.where(c[15, :, 3] > 0, 255, 0)
    d['decor_floor_c'] = (c, [8, 14])
    # ceil a: 늘어진 구름 덩굴과 물방울
    e = new(16, 24)
    draw_puffs(e, [(8, 2, 6), (6.5, 8, 4.6), (9.5, 13, 3.6), (7.5, 17.5, 2.6)],
               ['gray3', 'gray2', 'gray1', 'white'], sharp=3, under=0.6, wrapx=False)
    outline(e, 'gray3')
    for y, cc in [(21, 'blue'), (22, SKY1), (23, 'blued')]:
        put(e, 8, y, cc)
    put(e, 7, 22, 'white')
    e[0, :, 3] = 0
    d['decor_ceil_a'] = (e, [8, 1])
    # ceil b: 물방울 송이
    f = new(16, 16)
    draw_puffs(f, [(4, 0, 4), (11, 0, 4.5), (8, 1, 3.5)], ['gray3', 'gray2', 'gray1', 'white'],
               sharp=3, under=0.6, wrapx=False)
    for dx0, y0, ln in [(4, 4, 3), (9, 5, 6), (12, 4, 2)]:
        for y in range(y0, y0 + ln):
            put(f, dx0, y, SKY2 if y < y0 + ln - 1 else SKY1)
        yb = y0 + ln
        put(f, dx0, yb, 'blue')
        for xq in (dx0 - 1, dx0, dx0 + 1):
            put(f, xq, yb + 1, 'blue')
            put(f, xq, yb + 2, 'blued')
        put(f, dx0 - 1, yb + 1, 'white')
    d['decor_ceil_b'] = (f, [8, 1])
    return d


def cloud_particle():
    fr = []
    a = new(8, 8)
    for x, y, c in [(3, 2, 'salmon'), (4, 2, 'skin'), (2, 3, 'salmon'), (3, 3, 'skin'), (4, 3, 'white'),
                    (5, 3, 'skin'), (3, 4, 'salmon'), (4, 4, 'skin'), (4, 5, 'salmon')]:
        put(a, x, y, c)
    fr.append(a)
    b = new(8, 8)
    for x, y, c in [(2, 4, 'salmon'), (3, 4, 'skin'), (4, 4, 'white'), (5, 4, 'skin'), (6, 3, 'salmon'),
                    (3, 5, 'salmon'), (4, 5, 'salmon')]:
        put(b, x, y, c)
    fr.append(b)
    return fr


def cloud_rock(seed, size, r, cells, spikes, squash=1.0, roots=None):
    img, m = facet_rock(size, r, seed, ['brownd', 'brown', 'brownl', 'tan'], squash=squash,
                        cells=cells, spikes=spikes, spike_h=(1.6, 2.6))
    rng = np.random.default_rng(seed + 7)
    c = size / 2
    for x in range(size):
        ys = np.nonzero(m[:, x])[0]
        if not len(ys):
            continue
        y0 = ys[0]
        if y0 > c - r * 0.25:
            continue
        th = int(rng.integers(2, 4)) + (1 if rng.random() < 0.25 else 0)
        for k in range(th):
            if m[y0 + k, x]:
                put(img, x, y0 + k, 'green' if k == 0 else ('forest' if k == th - 1 else 'greend'))
        if rng.random() < 0.35 and math.hypot(x + 0.5 - c, y0 - 0.5 - c) < r + 2.2:
            put(img, x, y0 - 1, 'green')
    for rx, ln in (roots or []):
        ys = np.nonzero(m[:, rx])[0]
        y1 = ys[-1]
        for k in range(1, ln + 1):
            put(img, rx + (1 if k == ln and rx < c else 0) * 0, y1 + k, 'brownd' if k < ln else 'brown')
    outline(img, 'ink')
    return img


def cloud_balloon(i):
    S, c = 32, 16.0
    img = new(S, S)
    xx, yy = grid(S, S)
    dx, dy = xx - c, yy - c
    ang = np.arctan2(dy, dx)
    rad = np.hypot(dx, dy)
    off = (np.pi / 8) if i else 0.0
    ry = 10.6 if i == 0 else 10.0
    rx = 10.6 if i == 0 else 11.2
    # 가시
    for k in range(8):
        a0 = k * np.pi / 4 + off + np.pi / 8
        if abs(np.angle(np.exp(1j * (a0 - np.pi / 2)))) < 0.45:
            continue
        ux, uy = math.cos(a0), math.sin(a0)
        along = dx * ux + dy * uy
        perp = -dx * uy + dy * ux
        rb, rt = 8.5, 14.2
        m = (along >= rb) & (along <= rt) & (np.abs(perp) <= 1.9 * (1 - (along - rb) / (rt - rb)) + 0.15)
        lit = (perp * (-uy * LIGHT[0] + ux * LIGHT[1])) > 0
        paint(img, m, 'gray2')
        paint(img, m & lit, 'gray1')
        tipm = m & (along > rt - 1.6)
        paint(img, tipm, 'white')
    m, rgb = sphere(S, S, c, c, rx, ry, ['redd', 'red', 'red', 'salmon'], 3.5)
    paint_rgb(img, m, rgb)
    # 이음선과 반사광
    for yq in range(int(c - ry) + 2, int(c + ry) - 1):
        put(img, 16 + (1 if i else 0), yq, 'redd')
    put(img, 16 + (1 if i else 0), int(c - ry) + 1, 'red')
    for x, y in [(11, 9), (12, 9), (11, 10), (10, 11), (13, 8)]:
        put(img, x + (1 if i else 0), y + (1 if i else 0), 'white')
    put(img, 12 + (1 if i else 0), 10 + (1 if i else 0), 'salmon')
    # 매듭과 끈
    kn = int(c + ry) + 1
    put(img, 15, kn - 1, 'redd')
    put(img, 16, kn - 1, 'redd')
    put(img, 15, kn, 'redd')
    put(img, 16, kn, 'red')
    tail = [(16, kn + 1), (15, kn + 2), (15, kn + 3)] if i == 0 else [(16, kn + 1), (17, kn + 2), (17, kn + 3)]
    for x, y in tail:
        put(img, x, y, 'gray3')
    outline(img, 'ink')
    return img


def cloud_obstacles():
    o = {}
    o['rock_a'] = ([cloud_rock(41, 32, 12.6, 9, 2, roots=[(13, 2), (19, 3)])], [16, 16], {'r': 12})
    o['rock_b'] = ([cloud_rock(52, 32, 12.4, 11, 3, squash=0.95, roots=[(17, 2)])], [16, 16], {'r': 12})
    o['rock_c'] = ([cloud_rock(63, 32, 12.8, 8, 1, squash=0.9, roots=[(11, 3), (20, 2)])], [16, 16], {'r': 12})
    o['bigrock'] = ([cloud_rock(74, 48, 19.0, 16, 3, roots=[(18, 3), (27, 2), (31, 3)])], [24, 24], {'r': 18})
    o['balloon'] = ([cloud_balloon(0), cloud_balloon(1)], [16, 16], {'r': 11}, 4)
    return o


# ====================================================================== 테마 mushroom


def mushroom_sky():
    cols = ['gray4', 'purple', 'pink', 'salmon', 'skin', 'yellow']
    f = sky_field([0, 92, 168, 232, 290, 420])
    xx, yy = grid(VW, VH)
    sx, sy = 156, 262
    d = np.hypot(xx - sx, yy - sy)
    f = f + 1.2 * np.exp(-(d / 44) ** 2) + 0.7 * np.exp(-(d / 130) ** 2)
    # 길게 누운 저녁 구름: 몸은 한 단계 어둡고 아랫면은 노을빛
    for cx, cy, rx, ry in [(300, 176, 120, 4), (360, 183, 60, 3), (520, 150, 90, 3.5), (90, 196, 70, 3),
                           (610, 206, 70, 3), (230, 132, 50, 2.5)]:
        e = 1 - (wrapd(xx - cx, VW) / rx) ** 2 - ((yy - cy) / ry) ** 2
        body = e > 0
        under = (e > -0.6) & (e <= 0) & (yy > cy)
        f = np.where(body, f - 0.9, f)
        f = np.where(under, f + 0.6, f)
    img = rgba(ramp(f, cols, 2.6, B8))
    rng = np.random.default_rng(2101)
    for _ in range(110):
        x, y = int(rng.uniform(0, VW)), int(rng.uniform(0, 150))
        if f[y, x] > 1.25:
            continue
        b = rng.random()
        put(img, x, y, 'gray1' if b > 0.7 else 'gray2')
        if b > 0.96:
            for dx, dy in N4:
                put(img, x + dx, y + dy, 'gray2')
            put(img, x, y, 'white')
    # 해: 아래쪽으로 갈수록 진해지고 가로 틈이 있는 큰 원
    sun = d <= 27
    sm = ramp((yy - (sy - 27)) / 54 * 2.0, ['yellow', 'gold', 'orange'], 2.5, B4)
    paint_rgb(img, sun, sm)
    for y0, th in [(sy + 7, 1), (sy + 13, 2), (sy + 19, 2)]:
        cut = sun & (yy >= y0) & (yy < y0 + th)
        img[cut] = rgba(ramp(f, cols, 2.6, B8))[cut]
    return img


def mushroom_shape(d, o, cx, base, h, sw, rx, ry):
    d.rectangle([cx - sw / 2 + o, base - h, cx + sw / 2 + o, base], fill=255)
    d.pieslice([cx - rx + o, base - h - ry, cx + rx + o, base - h + ry * 0.5], 180, 360, fill=255)


def mushroom_far():
    img = new(VW, VH)
    rng = np.random.default_rng(2201)
    x = np.arange(VW) + 0.5
    hill = 300 - 16 * (np.sin(2 * np.pi * x / VW * 3 + 1) * 0.5 + 0.5) - 14 * (fbm1(VW, 24, 3, 2202) - 0.3)
    xx, yy = grid(VW, VH)
    m = yy >= hill[None, :]
    ops = []
    for k in range(9):
        cx = k * VW / 9 + rng.uniform(0, 40)
        base = float(np.interp(cx % VW, x, hill)) + 4
        kind = rng.random()
        if kind < 0.45:
            ops.append(('m', cx, base, rng.uniform(26, 60), rng.uniform(3, 6), rng.uniform(10, 22), rng.uniform(6, 11)))
        else:
            ops.append(('t', cx, base, rng.uniform(18, 40), rng.uniform(8, 14)))

    def draw(d, o):
        for op in ops:
            if op[0] == 'm':
                _, cx, base, h, sw, rx, ry = op
                mushroom_shape(d, o, cx, base, h, sw, rx, ry)
            else:
                _, cx, base, h, r = op
                d.rectangle([cx - 1 + o, base - h, cx + 1 + o, base], fill=255)
                for j in range(4):
                    a = j * 1.7
                    ox, oy = math.cos(a) * r * 0.55, math.sin(a) * r * 0.35
                    rr = r * (0.75 - 0.08 * j)
                    d.ellipse([cx + ox - rr + o, base - h + oy - rr, cx + ox + rr + o, base - h + oy + rr], fill=255)
    m |= pil_mask(VW, VH, draw, wrapx=True)
    paint(img, m, 'pink')
    rim_light(img, m, 'salmon')
    return img


def mushroom_mid():
    img = new(VW, VH)
    rng = np.random.default_rng(2301)
    x = np.arange(VW) + 0.5
    ground = 318 - 10 * (fbm1(VW, 16, 3, 2302) - 0.5) - 6 * np.sin(2 * np.pi * x / VW * 2)
    xx, yy = grid(VW, VH)
    m = yy >= ground[None, :]
    trees, shrooms = [], []
    xs = 10.0
    while xs < VW - 20:
        if rng.random() < 0.55:
            trees.append((xs, rng.uniform(8, 13), rng.uniform(110, 190), rng.uniform(22, 34), int(rng.integers(0, 1 << 30))))
        else:
            shrooms.append((xs, rng.uniform(7, 11), rng.uniform(70, 130), rng.uniform(22, 36), rng.uniform(10, 15)))
        xs += rng.uniform(55, 95)

    def draw(d, o):
        for cx, tw, ty, cr, sd in trees:
            r2 = np.random.default_rng(sd)
            d.polygon([(cx - tw / 2 + o, 360), (cx - tw * 0.3 + o, ty + 20), (cx + tw * 0.3 + o, ty + 20),
                       (cx + tw / 2 + o, 360)], fill=255)
            for j in range(7):
                ox = r2.uniform(-cr, cr)
                oy = r2.uniform(-cr * 0.55, cr * 0.45)
                rr = r2.uniform(cr * 0.45, cr * 0.75)
                d.ellipse([cx + ox - rr + o, ty + oy - rr, cx + ox + rr + o, ty + oy + rr], fill=255)
            for side in (-1, 1):
                by = ty + r2.uniform(40, 90)
                d.line([(cx + o, by), (cx + side * r2.uniform(10, 18) + o, by - r2.uniform(8, 14))], fill=255, width=2)
        for cx, sw, ty, rx, ry in shrooms:
            d.polygon([(cx - sw / 2 - 2 + o, 360), (cx - sw / 2 + o, ty), (cx + sw / 2 + o, ty),
                       (cx + sw / 2 + 2 + o, 360)], fill=255)
            d.pieslice([cx - rx + o, ty - ry, cx + rx + o, ty + ry * 0.7], 180, 360, fill=255)
    m |= pil_mask(VW, VH, draw, wrapx=True)
    DEEP = mix('purple', 'navy', 0.45)
    paint(img, m, 'purple')
    # 버섯 갓 아랫면 주름
    for cx, sw, ty, rx, ry in shrooms:
        for xq in range(int(cx - rx + 3), int(cx + rx - 2)):
            if abs(xq - cx) <= sw / 2 + 1:
                continue
            k = 1 + (abs(xq - int(cx)) % 3 == 0)
            for yq in range(int(ty), int(ty) + k):
                put(img, xq, yq, DEEP, wrap=True)
        for j in range(5):
            sx = cx + rng.uniform(-rx * 0.7, rx * 0.7)
            sy = ty - ry * rng.uniform(0.35, 0.8) * math.sqrt(max(0, 1 - ((sx - cx) / rx) ** 2))
            put(img, sx, sy, 'pink', wrap=True)
            put(img, sx + 1, sy, 'pink', wrap=True)
    rim_light(img, m, 'pink')
    # 숲 바닥의 아주 작은 빛점
    for _ in range(26):
        xq = int(rng.uniform(0, VW))
        yq = int(ground[xq] + rng.uniform(6, 30))
        put(img, xq, yq, 'salmon')
    return img


def mushroom_floor_body():
    s = 32
    xx, yy = grid(s, s)
    n1 = fbm(s, s, 4, 4, 3, 401, wrap_y=True)
    n2 = fbm(s, s, 8, 8, 2, 402, wrap_y=True)
    v = 1.0 + (n1 - 0.5) * 1.5 + (n2 - 0.5) * 0.9
    img = rgba(ramp(v, ['ink', 'brownd', 'brown'], 1.6, B4))
    rng = np.random.default_rng(403)
    for k in range(3):
        y0, a, p = rng.uniform(0, s), rng.uniform(1.5, 3.5), rng.uniform(0, 2 * np.pi)
        for x in range(s):
            y = y0 + a * math.sin(2 * np.pi * x / s + p) + 1.2 * math.sin(4 * np.pi * x / s + p * 2)
            put(img, x, int(y), 'brown', wrap=True)
            if x % 5 == k:
                put(img, x, int(y) - 1, 'brownl', wrap=True)
    for _ in range(5):
        cx, cy = int(rng.uniform(0, s)), int(rng.uniform(0, s))
        put(img, cx, cy, 'gray3', wrap=True)
        put(img, cx + 1, cy, 'gray4', wrap=True)
        put(img, cx, cy - 1, 'gray2', wrap=True) if rng.random() < 0.5 else None
    return img


def mushroom_floor_edge():
    return edge_floor({
        'ay': 3,
        'above':  [1, 2, 2, 1, 0, 1, 1, 0, 1, 2, 2, 1, 0, 0, 1, 1],
        'thick':  [3, 4, 4, 3, 3, 3, 4, 3, 3, 4, 5, 4, 3, 3, 3, 4],
        'tip': 'green', 'tipbase': 'greend',
        'band': ['green', 'greend', 'forest'],
        'mix1': 0.35,
        'under': [('ink', 1.1, 'ink'), ('ink', 0.5, 'brownd')],
        'fill': ('brownd', 0.8, 'brown'),
        'dots': [(2, 0, 'green'), (9, 0, 'green'), (6, 4, 'green'), (12, 4, 'green')],
    })


def mushroom_ceil_body():
    s = 32
    n1 = fbm(s, s, 4, 4, 3, 411, wrap_y=True)
    img = rgba(ramp(1.0 + (n1 - 0.5) * 1.4, ['ink', 'brownd', 'brown'], 1.5, B4))
    rng = np.random.default_rng(412)
    # 가로로 얽힌 뿌리
    for k in range(4):
        y0, a, p, f = rng.uniform(0, s), rng.uniform(2, 5), rng.uniform(0, 6.28), int(rng.integers(1, 3))
        for x in range(s):
            y = int(round(y0 + a * math.sin(2 * np.pi * f * x / s + p)))
            put(img, x, y - 1, 'brownl', wrap=True)
            put(img, x, y, 'brown', wrap=True)
            put(img, x, y + 1, 'brown', wrap=True)
            put(img, x, y + 2, 'ink', wrap=True)
    # 세로 잔뿌리
    for k in range(3):
        x0, a, p = rng.uniform(0, s), rng.uniform(1, 3), rng.uniform(0, 6.28)
        for y in range(s):
            x = int(round(x0 + a * math.sin(2 * np.pi * y / s + p)))
            put(img, x, y, 'brown', wrap=True)
            put(img, x + 1, y, 'brownd', wrap=True)
    # 잎 뭉치
    for _ in range(6):
        cx, cy = int(rng.uniform(0, s)), int(rng.uniform(0, s))
        for dx, dy, c in [(0, 0, 'greend'), (1, 0, 'forest'), (-1, 1, 'forest'), (0, 1, 'forest'),
                          (1, 1, 'teal'), (0, -1, 'greend'), (-1, 0, 'green')]:
            put(img, cx + dx, cy + dy, c, wrap=True)
    return img


def mushroom_ceil_edge():
    w, h, ay = 16, 12, 6
    img = new(w, h)
    t4 = thr((h, w), B4)
    tips = [1, 2, 1, 0, 2, 3, 2, 1, 0, 1, 2, 1, 2, 1, 0, 1]
    for x in range(w):
        bot = ay + tips[x]
        for y in range(bot):
            k = bot - 1 - y
            if k == 0:
                c = 'greend'
            elif k == 1:
                c = 'green' if t4[y, x] < 0.3 else 'greend'
            elif k <= 3:
                c = 'forest' if t4[y, x] < 0.75 else 'greend'
            elif k == 4:
                c = 'teal'
            else:
                c = 'brownd' if t4[y, x] < 0.6 else 'ink'
            put(img, x, y, c)
    # 잎맥처럼 밝은 잎 끝
    for x, y in [(1, 6), (5, 7), (6, 7), (10, 6), (12, 6), (4, 4), (13, 4), (8, 3)]:
        put(img, x, y, 'green')
    # 늘어진 뿌리 끝
    for x, ln in [(3, 4), (8, 5), (14, 3)]:
        y0 = ay + tips[x]
        for k in range(ln):
            put(img, x, y0 + k, 'brown' if k < ln - 1 else 'brownd')
        put(img, x - 1, y0, 'brownl')
    alpha_fade_rows(img, {0: 0.3, 1: 0.6})
    return img


def mushroom_cap(img, cx, cy, rx, ry, cols, spots, under_c, stem):
    """작은 버섯 하나: 반원 갓, 점, 줄기."""
    sx0, sx1, sy0, sy1 = stem
    for x in range(sx0, sx1 + 1):
        for y in range(sy0, sy1 + 1):
            put(img, x, y, 'cream' if x == sx0 else 'tan')
    m, rgb = sphere(img.shape[1], img.shape[0], cx, cy, rx, ry, cols, 4)
    xx, yy = grid(img.shape[1], img.shape[0])
    m &= yy <= cy + 0.5
    paint_rgb(img, m, rgb)
    for x in range(int(cx - rx + 1), int(cx + rx)):
        put(img, x, int(cy + 0.5), under_c)
    for x, y in spots:
        put(img, x, y, 'white')


def mushroom_decor():
    d = {}
    a = new(16, 16)
    mushroom_cap(a, 6, 8.5, 4.6, 3.6, ['redd', 'red', 'salmon'], [(5, 6), (7, 7), (3, 8)], 'skind', (5, 9, 6, 15))
    mushroom_cap(a, 11.5, 10.5, 3.1, 2.6, ['redd', 'red', 'salmon'], [(11, 9)], 'skind', (11, 11, 11, 15))
    mushroom_cap(a, 2.5, 12.5, 1.9, 1.6, ['redd', 'red', 'salmon'], [], 'skind', (2, 13, 2, 15))
    outline(a, 'brownd')
    for x in range(1, 15):
        put(a, x, 15, 'greend' if x % 3 else 'green')
    a[:, :, 3] = np.where(a[:, :, 3] > 0, 255, 0)
    d['decor_floor_a'] = (a, [8, 14])
    b = new(16, 24)
    pts = [(8, 23), (8, 19), (7, 15), (7, 12), (8, 10)]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        for x, y in line_pts(x0, y0, x1, y1):
            put(b, x, y, 'cream')
            put(b, x + 1, y, 'tan')
    m, rgb = sphere(16, 24, 8.5, 9.5, 5.6, 5.2, ['blue', 'cyan', 'white'], 3.5)
    xx, yy = grid(16, 24)
    m &= yy <= 9.6
    paint_rgb(b, m, rgb)
    for x in range(3, 15):
        put(b, x, 9, 'blued' if x % 2 else 'blue')
    for x, y in [(6, 6), (10, 5), (8, 7), (12, 7)]:
        put(b, x, y, 'white')
    outline(b, 'teal')
    for x in range(5, 12):
        put(b, x, 23, 'greend' if x % 2 else 'forest')
    glow(b, 'cyan', [70, 35])
    for x, y in [(2, 13), (13, 15), (4, 2)]:
        put(b, x, y, 'cyan', 160)
    d['decor_floor_b'] = (b, [8, 22])
    c = new(16, 16)
    frond = [(7, 15), (7, 12), (6, 9), (4, 6), (2, 5)]
    polyline(c, frond, 'greend')
    for x, y in [(8, 11), (9, 10), (7, 9), (8, 8), (5, 7), (6, 6), (5, 9), (4, 8), (3, 7), (6, 11), (5, 11)]:
        put(c, x, y, 'green')
    frond2 = [(9, 15), (10, 12), (12, 9), (13, 7)]
    polyline(c, frond2, 'forest')
    for x, y in [(11, 12), (12, 11), (13, 10), (11, 9), (9, 11)]:
        put(c, x, y, 'greend')
    for fx, fy in [(12, 5), (4, 11)]:
        for dx, dy in N4:
            put(c, fx + dx, fy + dy, 'pink')
        put(c, fx, fy, 'yellow')
    for x in range(4, 13):
        put(c, x, 15, 'greend' if x % 2 else 'forest')
    d['decor_floor_c'] = (c, [8, 14])
    e = new(16, 24)
    vx = [8, 8, 9, 9, 9, 8, 8, 7, 7, 7, 8, 8, 9, 9, 9, 8, 8, 7, 7, 7, 8]
    for y, x in enumerate(vx):
        put(e, x, y, 'greend')
    for k, y in enumerate(range(3, 21, 4)):
        side = -1 if k % 2 else 1
        bx = vx[y] + side
        for dx, dy, cc in [(0, 0, 'green'), (side, 0, 'green'), (side, 1, 'greend'), (0, 1, 'green'),
                           (2 * side, 1, 'forest'), (side, 2, 'forest')]:
            put(e, bx + dx, y + dy, cc)
    put(e, 8, 21, 'greend')
    put(e, 9, 22, 'greend')
    put(e, 9, 21, 'green')
    outline(e, 'teal')
    e[0, :, 3] = np.where(e[0, :, 3] > 0, e[0, :, 3], 0)
    d['decor_ceil_a'] = (e, [8, 1])
    f = new(16, 16)
    for x0, ln in [(4, 5), (9, 8), (12, 4)]:
        for y in range(0, ln):
            put(f, x0, y, 'brown')
        mk, rgb = sphere(16, 16, x0 + 0.5, ln + 1.5, 2, 2, ['orange', 'gold', 'yellow'], 3)
        paint_rgb(f, mk, rgb)
        put(f, x0, ln + 1, 'white')
    glow(f, 'gold', [80, 40])
    d['decor_ceil_b'] = (f, [8, 1])
    return d


def mushroom_particle():
    a = new(8, 8)
    for x, y in [(3, 3), (4, 3), (3, 4), (4, 4)]:
        put(a, x, y, 'yellow')
    put(a, 3, 3, 'white')
    glow(a, 'gold', [110, 45])
    b = new(8, 8)
    put(b, 3, 3, 'yellow')
    put(b, 4, 4, 'gold')
    put(b, 4, 3, 'gold')
    put(b, 3, 4, 'gold')
    glow(b, 'gold', [55])
    return [a, b]


def bounce_mushroom(squash):
    W, Hh = 48, 32
    img = new(W, Hh)
    if not squash:
        top, rim, rx, sx0, sx1 = 6, 17, 21.5, 18, 29
    else:
        top, rim, rx, sx0, sx1 = 11, 20, 23.5, 17, 30
    # 줄기
    for y in range(rim - 1, Hh):
        flare = 1 if y >= Hh - 3 else 0
        for x in range(sx0 - flare, sx1 + 1 + flare):
            t = (x - (sx0 - flare)) / max(1, (sx1 - sx0 + 2 * flare))
            put(img, x, y, 'white' if t < 0.18 else ('cream' if t < 0.62 else ('tan' if t < 0.86 else 'skind')))
    # 얼굴
    ey = rim + (4 if not squash else 3)
    if not squash:
        for ex in (sx0 + 3, sx1 - 3):
            put(img, ex, ey, 'ink')
            put(img, ex, ey + 1, 'ink')
            put(img, ex, ey, 'white') if False else None
        put(img, sx0 + 3, ey - 1, 'ink')
        put(img, sx1 - 3, ey - 1, 'ink')
        put(img, sx0 + 3, ey - 1, 'white')
        put(img, sx1 - 3, ey - 1, 'white')
        put(img, (sx0 + sx1) // 2, ey + 2, 'brownd')
        put(img, (sx0 + sx1) // 2 + 1, ey + 2, 'brownd')
    else:
        for ex in (sx0 + 3, sx1 - 3):
            put(img, ex - 1, ey + 1, 'ink')
            put(img, ex, ey, 'ink')
            put(img, ex + 1, ey + 1, 'ink')
        for x in range((sx0 + sx1) // 2 - 1, (sx0 + sx1) // 2 + 3):
            put(img, x, ey + 2, 'brownd')
    for bx in (sx0 + 1, sx1 - 2):
        put(img, bx, ey + 2, 'salmon')
        put(img, bx + 1, ey + 2, 'salmon')
    # 갓
    cx = 24.0
    ry = rim - top + 0.5
    m, rgb = sphere(W, Hh, cx, rim + 0.5, rx, ry, ['orange', 'gold', 'gold', 'yellow'], 3.2)
    xx, yy = grid(W, Hh)
    m &= yy <= rim + 0.5
    paint_rgb(img, m, rgb)
    # 갓 테두리 아래로 말린 띠와 주름
    for x in range(int(cx - rx) + 1, int(cx + rx)):
        put(img, x, rim, 'orange')
        if abs(x + 0.5 - cx) > rx - 3:
            continue
        put(img, x, rim + 1, 'skind' if x % 2 else 'tan')
    spots = [(-12, 5, 2.4), (-2, 2.5, 3.0), (9, 4.5, 2.3), (16, 8, 1.6), (-18, 9, 1.5), (3, 8.5, 1.4)]
    for ox, oy, r in spots:
        sx = cx + ox * (rx / 21.5)
        sy = top + oy * (ry / 11.5)
        sm = ellipse_mask(W, Hh, sx, sy, r * 1.15, r * 0.85) & m
        paint(img, sm, 'cream')
        paint(img, sm & ellipse_mask(W, Hh, sx - 0.6, sy - 0.5, r * 0.6, r * 0.45), 'white')
    # 반짝임
    for x, y in [(int(cx - rx * 0.55), top + 3), (int(cx - rx * 0.55) + 1, top + 2), (int(cx - rx * 0.45), top + 2)]:
        put(img, x, y, 'white')
    outline(img, 'brownd')
    return img


def thorn(seed, berries):
    S, c = 32, 16.0
    img = new(S, S)
    rng = np.random.default_rng(seed)
    xx, yy = grid(S, S)
    dx, dy = xx - c, yy - c
    rad = np.hypot(dx, dy)
    # 가시
    n = 13
    for k in range(n):
        a0 = k * 2 * np.pi / n + rng.uniform(-0.15, 0.15)
        ux, uy = math.cos(a0), math.sin(a0)
        along = dx * ux + dy * uy
        perp = -dx * uy + dy * ux
        rb, rt = 9.0, 14.0 + rng.uniform(-0.6, 0.4)
        bend = 0.18 * (along - rb) ** 2 / (rt - rb) * (1 if k % 2 else -1)
        m = (along >= rb) & (along <= rt) & (np.abs(perp - bend) <= 1.7 * (1 - (along - rb) / (rt - rb)) + 0.2)
        paint(img, m, 'skind')
        paint(img, m & (along > rb + 1.8), 'cream')
        paint(img, m & (along > rt - 1.4), 'white')
    # 속이 어두운 덤불
    core = rad <= 10.6 + 0.8 * np.cos(5 * np.arctan2(dy, dx) + seed)
    paint(img, core, 'teal')
    # 얽힌 줄기
    for k in range(7):
        a = rng.uniform(0, 2 * np.pi)
        b = a + rng.uniform(1.6, 3.0)
        r1, r2 = rng.uniform(7, 10), rng.uniform(7, 10)
        p0 = (c + math.cos(a) * r1, c + math.sin(a) * r1)
        p2 = (c + math.cos(b) * r2, c + math.sin(b) * r2)
        mid = (a + b) / 2
        p1 = (c + math.cos(mid) * rng.uniform(-2, 4), c + math.sin(mid) * rng.uniform(-2, 4))
        pts = []
        for t in np.linspace(0, 1, 24):
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            pts.append((x, y))
        for (x, y) in pts:
            put(img, int(x) + 1, int(y) + 1, 'ink')
        for (x, y) in pts:
            put(img, int(x), int(y), 'forest')
            put(img, int(x) + 1, int(y), 'forest')
        for (x, y) in pts:
            put(img, int(x), int(y) - 1, 'greend')
    for x, y in berries:
        put(img, x, y, 'red')
        put(img, x + 1, y, 'redd')
        put(img, x, y + 1, 'redd')
        put(img, x + 1, y + 1, 'redd')
        put(img, x, y, 'salmon')
        put(img, x + 1, y, 'red')
    outline(img, 'ink')
    return img


def spore(i):
    S, c = 24, 12.0
    img = new(S, S)
    xx, yy = grid(S, S)
    dx, dy = xx - c, yy - c
    off = np.pi / 10 if i else 0
    for k in range(10):
        a0 = k * np.pi / 5 + off
        ux, uy = math.cos(a0), math.sin(a0)
        along = dx * ux + dy * uy
        perp = -dx * uy + dy * ux
        rt = 11.6 if i == 0 else 11.0
        m = (along >= 8) & (along <= rt) & (np.abs(perp) <= 1.3 * (1 - (along - 8) / (rt - 8)) + 0.2)
        paint(img, m, 'greend')
        paint(img, m & (along > rt - 1.5), 'yellow')
    r = 9.3 if i == 0 else 9.8
    m, rgb = sphere(S, S, c, c, r, r * (1.0 if i == 0 else 0.94), ['forest', 'greend', 'green', 'yellow'], 3.2)
    paint_rgb(img, m, rgb)
    spots = [(8, 13), (14, 9), (13, 15), (9, 8)] if i == 0 else [(9, 14), (15, 11), (12, 16), (10, 8)]
    for x, y in spots:
        put(img, x, y, 'purple')
        put(img, x + 1, y, 'pink')
        put(img, x, y + 1, 'purple')
    put(img, 8, 7, 'white')
    put(img, 9, 6, 'white') if i == 0 else put(img, 7, 8, 'white')
    outline(img, 'ink')
    glow(img, 'green', [70, 30] if i == 0 else [100, 50])
    return img


def mushroom_obstacles():
    o = {}
    o['mushroom'] = ([bounce_mushroom(False), bounce_mushroom(True)], [24, 12],
                     {'x': -20, 'y': -6, 'w': 40, 'h': 16}, None)
    o['thorn_a'] = ([thorn(81, [(9, 12), (20, 18), (14, 21)])], [16, 16], {'r': 12})
    o['thorn_b'] = ([thorn(97, [(17, 10), (10, 19)])], [16, 16], {'r': 12})
    o['spore'] = ([spore(0), spore(1)], [12, 12], {'r': 9}, 4)
    return o


# ====================================================================== 테마 storm


def storm_sky():
    cols = ['ink', NIGHT1, 'navy', NIGHT3, 'gray4', 'gray3', 'gray2']
    f = sky_field([0, 96, 196, 300, 400, 460, 520])
    xx, yy = grid(VW, VH)
    mx, my = 116, 66
    d = np.hypot(xx - mx, yy - my)
    f = f + 1.4 * np.exp(-(d / 26) ** 2) + 0.8 * np.exp(-(d / 80) ** 2)
    sky = f.copy()
    # 폭풍 구름
    n = fbm(VH, VW, 3, 6, 5, 3101)
    n2 = fbm(VH, VW, 6, 12, 3, 3102)
    dens = n + 0.32 * np.clip(1 - yy / 170, 0, 1) - 0.12 * np.clip((yy - 170) / 80, 0, 1)
    cloud = dens > 0.62
    nl = np.roll(np.roll(n, 4, axis=0), 4, axis=1)
    lit = (n - nl) * 9
    cv = 1.4 + np.clip(lit, -1.0, 1.4) + (n2 - 0.5) * 0.5
    cv = cv + 1.6 * np.exp(-(d / 70) ** 2)
    for gx, gy, gr in [(470, 70, 56), (300, 118, 40)]:
        g = np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / gr ** 2)
        cv = cv + 1.5 * g * cloud
    edge = cloud & ~(dens > 0.66)
    cv = np.where(edge, cv + 0.5, cv)
    f = np.where(cloud, cv, f)
    img = rgba(ramp(f, cols, 2.2, B8))
    # 달
    md = np.hypot(xx - mx, yy - my)
    moon = md <= 12.2
    shade = np.hypot(xx - (mx - 4), yy - (my - 3)) > 12.4
    mc = np.zeros((VH, VW, 3), np.uint8)
    mc[:] = col('gray1')
    mc[shade] = col('gray2')
    for cx, cy, r in [(mx - 4, my + 2, 2.2), (mx + 3, my - 4, 1.6), (mx + 5, my + 5, 1.4)]:
        mc[np.hypot(xx - cx, yy - cy) <= r] = col('gray2')
    mc[(np.hypot(xx - (mx - 5), yy - (my - 6)) <= 2.0)] = col('white')
    moon_vis = moon & ~(cloud & (dens > 0.66) & (yy > my + 3))
    paint_rgb(img, moon_vis, mc)
    return img


def spire_poly(cx, base, top, wb, wt, rng, pointed=False, wobble=0.18):
    n = max(5, int((base - top) / 7))
    left, right = [], []
    ph = rng.uniform(0, 6.28)
    for i in range(n + 1):
        t = i / n
        y = top + t * (base - top)
        hw = wt / 2 + (wb / 2 - wt / 2) * t ** 1.8
        hw *= 1 + wobble * math.sin(t * 9 + ph)
        left.append((cx - hw - rng.uniform(0, 2.2), y))
        right.append((cx + hw + rng.uniform(0, 2.2), y))
    if pointed:
        tip = (cx + rng.uniform(-2, 2), top - rng.uniform(6, 12))
        return [tip] + left[1:] + right[1:][::-1]
    return left + right[::-1]


def storm_layer(seed, base, n_sp, hrange, wrange, body, rim, strata_c, arch=False, glints=0):
    img = new(VW, VH)
    rng = np.random.default_rng(seed)
    x = np.arange(VW) + 0.5
    ground = base - 8 * (fbm1(VW, 20, 3, seed + 1) - 0.5)
    xx, yy = grid(VW, VH)
    m = yy >= ground[None, :]
    polys = []
    for k in range(n_sp):
        cx = k * VW / n_sp + rng.uniform(0, VW / n_sp * 0.6)
        h = rng.uniform(*hrange)
        wb = rng.uniform(*wrange)
        kind = rng.random()
        if kind < 0.3:
            polys.append(spire_poly(cx, base + 10, base - h * 0.6, wb * 2.2, wb * 1.8, rng, wobble=0.05))
        elif kind < 0.7:
            polys.append(spire_poly(cx, base + 10, base - h, wb, wb * 0.45, rng))
        else:
            polys.append(spire_poly(cx, base + 10, base - h * 0.9, wb * 0.8, wb * 0.2, rng, pointed=True))

    def draw(d, o):
        for p in polys:
            d.polygon([(px + o, py) for px, py in p], fill=255)
    m |= pil_mask(VW, VH, draw, wrapx=True)
    if arch:
        ax = rng.uniform(100, 500)
        h = hrange[1] * 0.7

        def da(d, o):
            d.polygon([(ax - 46 + o, base + 10), (ax - 40 + o, base - h), (ax + 44 + o, base - h - 4),
                       (ax + 50 + o, base + 10)], fill=255)
        m |= pil_mask(VW, VH, da, wrapx=True)
        hole = pil_mask(VW, VH, lambda d, o: d.ellipse([ax - 26 + o, base - h * 0.62, ax + 28 + o, base + 30],
                                                         fill=255), wrapx=True)
        m &= ~hole | (yy > base + 2)
    paint(img, m, body)
    if strata_c is not None:
        n = fbm(VH, VW, 20, 80, 2, seed + 2)
        st = ((yy + (n - 0.5) * 6).astype(int) % 9 == 0) & m & shift(m, 3, 0, True) & shift(m, -3, 0, True)
        t4 = thr((VH, VW), B4)
        paint(img, st & (t4 < 0.5), strata_c)
    rim_light(img, m, rim)
    for _ in range(glints):
        for tries in range(40):
            gx, gy = int(rng.uniform(0, VW)), int(rng.uniform(base - hrange[1], base + 30))
            if m[gy, gx] and m[gy - 2, gx] and m[gy, (gx + 2) % VW]:
                put(img, gx, gy, 'blue')
                put(img, gx, gy - 1, 'blued')
                break
    return img, m


def storm_far():
    img, m = storm_layer(3201, 286, 9, (40, 95), (24, 46), 'navy', NIGHT3, None, glints=0)
    # 멀리 내리는 빗줄기 장막
    t4 = thr((VH, VW), B4)
    xx, yy = igrid(VW, VH)
    n = fbm(VH, VW, 2, 8, 2, 3203)
    curtain = (n > 0.55) & (yy > 120) & ~m
    fade = np.clip((yy - 120) / 60, 0, 1) * np.clip((300 - yy) / 40, 0, 1)
    streak = ((xx + yy // 3) % 4 == 0) & (t4 < 0.45 * fade)
    paint(img, curtain & streak, NIGHT3)
    return img


def storm_mid():
    img, m = storm_layer(3301, 318, 7, (70, 170), (30, 56), NIGHT1, 'navy', 'navy', arch=True, glints=9)
    return img


def storm_rock_body(seed, dark=0.0):
    s = 32
    xx, yy = grid(s, s)
    ix, iy = igrid(s, s)
    n1 = fbm(s, s, 2, 4, 3, seed, wrap_y=True)
    n2 = fbm(s, s, 8, 8, 2, seed + 1, wrap_y=True)
    bounds = [0, 7, 12, 21, 26, 32]
    tones = [1.25, 0.8, 1.45, 0.95, 1.15]
    yw = (yy + (n1 - 0.5) * 7) % s
    band = np.digitize(yw, bounds[1:-1])
    v = np.array(tones)[band] + (n2 - 0.5) * 0.9 - dark
    yw_up = ((yy - 1) + (n1 - 0.5) * 7) % s
    band_up = np.digitize(yw_up, bounds[1:-1])
    top_edge = band != band_up
    v = np.where(top_edge, v + 0.9, v)
    yw_dn = ((yy + 1) + (n1 - 0.5) * 7) % s
    v = np.where(np.digitize(yw_dn, bounds[1:-1]) != band, v - 0.9, v)
    img = rgba(ramp(v, ['ink', 'navy', 'gray4', 'gray3'], 1.6, B4, iy, ix))
    rng = np.random.default_rng(seed + 2)
    # 세로 균열
    for _ in range(5):
        x0, y0, ln = int(rng.uniform(0, s)), int(rng.uniform(0, s)), int(rng.integers(2, 5))
        for k in range(ln):
            put(img, x0, y0 + k, 'ink', wrap=True)
            put(img, x0 + 1, y0 + k, 'gray4', wrap=True)
    # 희미한 수정 결
    for _ in range(3):
        x0, y0 = int(rng.uniform(0, s)), int(rng.uniform(0, s))
        put(img, x0, y0, 'blued', wrap=True)
        put(img, x0 + 1, y0 - 1, 'blued', wrap=True)
        put(img, x0 + 1, y0, 'blue', wrap=True)
    return img


def storm_floor_edge():
    return edge_floor({
        'ay': 3,
        'above':  [0, 1, 1, 0, 0, 0, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0],
        'thick':  [3, 3, 4, 3, 3, 4, 4, 3, 3, 3, 4, 3, 3, 3, 4, 3],
        'tip': 'gray3', 'tipbase': 'gray4',
        'top': ['gray2', 'gray2', 'gray1', 'gray2', 'gray3', 'gray2', 'gray1', 'gray2',
                'gray2', 'gray3', 'gray2', 'gray2', 'gray1', 'gray2', 'gray2', 'gray3'],
        'band': ['gray3', 'gray3', 'gray4'],
        'mix1': 0.6,
        'under': [('navy', 0.7, 'gray4'), ('navy', 0.4, 'gray4')],
        'fill': ('gray4', 0.6, 'navy'),
    })


def storm_ceil_edge():
    w, h, ay = 16, 12, 6
    img = new(w, h)
    t4 = thr((h, w), B4)
    for x in range(w):
        for y in range(ay):
            k = ay - 1 - y
            if k == 0:
                c = 'gray3'
            elif k == 1:
                c = 'navy'
            elif k == 2:
                c = 'gray4' if t4[y, x] < 0.5 else 'navy'
            else:
                c = 'gray4' if t4[y, x] < 0.7 else 'gray3'
            put(img, x, y, c)
    for x in range(w):
        put(img, x, ay, 'ink')
    # 종유석
    for cxs, ln, wd in [(2, 4, 3), (6, 1, 1), (9, 5, 3), (13, 2, 2)]:
        for k in range(ln):
            half = max(0, (wd - 1) // 2 - (k * wd) // (ln + 1))
            for dx in range(-half, half + 1):
                c = 'gray3' if dx < 0 else ('gray4' if dx == 0 else 'navy')
                if half == 0:
                    c = 'gray3' if k < ln - 1 else 'gray2'
                put(img, cxs + dx, ay + k, c)
            put(img, cxs + half + 1, ay + k, 'ink')
            put(img, cxs - half - 1, ay + k, 'ink') if k > 0 else None
        put(img, cxs, ay + ln, 'ink')
    alpha_fade_rows(img, {0: 0.3, 1: 0.6})
    return img


CRY = ['blued', 'cyan', 'white']
CRY_D = ['blued', 'blue', 'cyan']


def storm_decor():
    d = {}
    a = new(16, 16)
    m, rgb = sphere(16, 16, 8, 15, 6.5, 3.2, ['ink', 'navy', 'gray4', 'gray3'], 4)
    paint_rgb(a, m, rgb)
    shard(a, 10, 14, -1.05, 8, 3.4, CRY_D, edge_c='blued')
    shard(a, 5.5, 14, -2.2, 7, 3.2, CRY_D, edge_c='blued')
    shard(a, 8, 14.5, -1.62, 12.5, 4.4, CRY, edge_c='blued')
    outline(a, 'ink')
    glow(a, 'cyan', [60, 25])
    a[15, :, 3] = np.where(a[15, :, 3] > 0, 255, 0)
    d['decor_floor_a'] = (a, [8, 14])
    b = new(16, 24)
    trunk = [(8, 23), (8, 18), (7, 14), (7, 10)]
    for (x0, y0), (x1, y1) in zip(trunk[:-1], trunk[1:]):
        for x, y in line_pts(x0, y0, x1, y1):
            put(b, x - 1, y, 'gray2')
            put(b, x, y, 'gray3')
            put(b, x + 1, y, 'gray4')
    for br in [[(7, 14), (4, 11), (2, 10)], [(7, 11), (6, 7), (3, 4)], [(7, 10), (9, 6), (12, 4)],
               [(8, 17), (11, 14), (13, 14)], [(6, 7), (7, 4)], [(4, 11), (3, 13)]]:
        for (x0, y0), (x1, y1) in zip(br[:-1], br[1:]):
            draw_line(b, x0, y0, x1, y1, 'gray3')
    for x in range(5, 12):
        put(b, x, 23, 'gray4')
    outline(b, 'ink')
    d['decor_floor_b'] = (b, [8, 22])
    c = new(16, 16)
    m, rgb = sphere(16, 16, 6, 12, 5, 3.8, ['ink', 'navy', 'gray4', 'gray3', 'gray2'], 4)
    paint_rgb(c, m, rgb)
    m, rgb = sphere(16, 16, 11.5, 13, 3.6, 2.8, ['ink', 'navy', 'gray4', 'gray3', 'gray2'], 4)
    paint_rgb(c, m, rgb)
    shard(c, 9, 10, -1.3, 5, 2.4, CRY_D, edge_c='blued')
    outline(c, 'ink')
    glow(c, 'cyan', [45])
    c[15, :, 3] = np.where(c[15, :, 3] > 0, 255, 0)
    d['decor_floor_c'] = (c, [8, 14])
    e = new(16, 24)
    pts = [(2, 0), (14, 0), (11, 6), (10, 12), (9, 16), (7, 16), (6, 11), (4, 5)]
    m = poly_mask(16, 24, pts)
    xx, yy = grid(16, 24)
    v = 2.2 - (xx - 4) / 9 * 1.8
    paint_rgb(e, m, ramp(v, ['navy', 'gray4', 'gray3', 'gray2'], 3, B4))
    shard(e, 8, 15, 1.62, 8, 3.6, CRY, edge_c='blued')
    outline(e, 'ink')
    e[0, :, 3] = np.where(e[0, :, 3] > 0, 255, 0)
    glow(e, 'cyan', [50, 20])
    e[0, :, :] = np.where(e[0, :, 3:4] == 255, e[0], 0)
    d['decor_ceil_a'] = (e, [8, 1])
    f = new(16, 16)
    m, rgb = sphere(16, 16, 8, 0.5, 7, 3, ['ink', 'navy', 'gray4', 'gray3'], 4)
    paint_rgb(f, m, rgb)
    shard(f, 5, 2, 2.0, 7, 3, CRY_D, edge_c='blued')
    shard(f, 11, 2, 1.15, 8, 3.2, CRY_D, edge_c='blued')
    shard(f, 8, 2, 1.57, 11.5, 4.2, CRY, edge_c='blued')
    outline(f, 'ink')
    glow(f, 'cyan', [55, 22])
    f[0, :, :] = np.where(f[0, :, 3:4] == 255, f[0], 0)
    d['decor_ceil_b'] = (f, [8, 1])
    return d


def storm_particle():
    a = new(8, 8)
    for k, (x, y) in enumerate(line_pts(6, 0, 3, 7)):
        put(a, x, y, 'gray1' if k > 4 else 'gray2', 120 + 18 * k)
    put(a, 3, 7, 'white', 230)
    b = new(8, 8)
    for k, (x, y) in enumerate(line_pts(5, 1, 3, 6)):
        put(b, x, y, 'gray1' if k > 3 else 'gray2', 110 + 22 * k)
    return [a, b]


def crystal(seed, shards):
    S = 32
    img = new(S, S)
    for (bx, by, ang, ln, wd, bright) in shards:
        shard(img, bx, by, ang, ln, wd, CRY if bright else CRY_D, edge_c='blued')
    outline(img, 'teal')
    glow(img, 'cyan', [80, 34])
    return img


def stormorb(i):
    S, c = 32, 16.0
    img = new(S, S)
    rng = np.random.default_rng(6100 + i)
    xx, yy = grid(S, S)
    r = [10.4, 10.9, 10.1][i]
    m, rgb = sphere(S, S, c, c, r, r, ['blued', 'blue', 'cyan', 'white'], 3.0, bias=[0, 0.25, -0.1][i])
    paint_rgb(img, m, rgb)
    # 안쪽 소용돌이
    n = fbm(S, S, 3, 3, 2, 6200 + i)
    swirl = m & (np.abs(np.sin(np.arctan2(yy - c, xx - c) * 3 + np.hypot(xx - c, yy - c) * 0.7 + i * 2.1)) < 0.18)
    swirl &= np.hypot(xx - c, yy - c) < r - 2
    paint(img, swirl, 'white')
    outline(img, 'blued')
    # 전기 가지
    for k in range(3):
        a = k * 2 * np.pi / 3 + i * 0.75 + rng.uniform(-0.2, 0.2)
        pts = []
        steps = 5
        for j in range(steps + 1):
            t = j / steps
            rr = 7.5 + t * 6.3
            aa = a + t * 0.5 + (rng.uniform(-0.18, 0.18) if 0 < j < steps else 0)
            pts.append((c + math.cos(aa) * rr - 0.5, c + math.sin(aa) * rr - 0.5))
        polyline(img, pts, 'yellow')
        put(img, pts[-1][0], pts[-1][1], 'white')
        mid = pts[2]
        put(img, mid[0], mid[1], 'white')
    for x, y in [(11, 10), (12, 10), (11, 11)]:
        put(img, x, y, 'white')
    glow(img, 'cyan', [90, 40] if i != 1 else [120, 60])
    return img


def pylon(down):
    """천장용(down=False)은 위에 붙어 아래로, 바닥용은 아래에 붙어 위로 향한다."""
    S = 24
    img = new(S, S)

    def Y(y):
        return y if not down else S - 1 - y

    def hline(x0, x1, y, c):
        for x in range(x0, x1 + 1):
            put(img, x, Y(y), c)

    # 고정판
    for y in range(0, 3):
        hline(2, 21, y, 'gray3')
    hline(2, 21, 2 if not down else 0, 'gray4')
    hline(2, 21, 0 if not down else 2, 'gray2')
    for bx in (4, 19):
        put(img, bx, Y(1), 'gray1')
    # 목
    for y in range(3, 6):
        hline(9, 14, y, 'gray4')
        put(img, 9, Y(y), 'gray3')
    # 몸통
    for y in range(6, 15):
        for x in range(5, 19):
            t = (x - 5) / 13
            c = 'gray2' if t < 0.2 else ('gray3' if t < 0.7 else 'gray4')
            put(img, x, Y(y), c)
    for x in range(5, 19):
        put(img, x, Y(6), 'gray1' if not down else 'gray2')
        put(img, x, Y(14), 'gray4' if not down else 'gray3')
    # 경고 띠
    for y in range(9, 12):
        for x in range(5, 19):
            put(img, x, Y(y), 'gold' if ((x + y) // 2) % 2 == 0 else 'ink')
    # 코일
    for y in range(15, 20):
        for x in range(7, 17):
            c = ('clay' if x < 10 else ('rust' if x < 14 else 'brown')) if y % 2 else ('brownl' if x < 11 else 'brown')
            put(img, x, Y(y), c)
    # 방전 끝
    for y, x0, x1 in [(20, 9, 14), (21, 10, 13), (22, 11, 12), (23, 11, 12)]:
        for x in range(x0, x1 + 1):
            put(img, x, Y(y), 'cyan' if x < 12 else 'blue')
    put(img, 11, Y(22), 'white')
    put(img, 11, Y(23), 'white')
    put(img, 12, Y(23), 'cyan')
    outline(img, 'ink')
    # 고정면은 잘리지 않게 바깥 테두리를 지운다
    edge_row = 0 if not down else S - 1
    img[edge_row, :, :] = np.where(img[edge_row, :, 3:4] > 0, img[edge_row], 0)
    return img


def beam(i):
    W, Hh = 16, 32
    img = new(W, Hh)
    rng = np.random.default_rng(7100 + i)
    ys = np.arange(0, 33, 4)
    xs = 8 + rng.uniform(-2.6, 2.6, len(ys))
    xs[0] = xs[-1] = 8.0
    xx, yy = grid(W, Hh)
    d = np.full((Hh, W), 99.0)
    for oy in (-32, 0, 32):
        for k in range(len(ys) - 1):
            ax, ay, bx, by = xs[k], ys[k] + oy, xs[k + 1], ys[k + 1] + oy
            vx, vy = bx - ax, by - ay
            t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / (vx * vx + vy * vy), 0, 1)
            dd = np.hypot(xx - (ax + t * vx), yy - (ay + t * vy))
            d = np.minimum(d, dd)
    core = [1.1, 1.5, 0.8][i]
    inner = [2.4, 3.0, 1.9][i]
    outer = [4.2, 5.0, 3.4][i]
    halo = [6.0, 6.8, 5.0][i]
    paint(img, d < halo, 'blue', 70)
    paint(img, d < outer, 'cyan', 150)
    paint(img, d < inner, 'cyan')
    paint(img, d < core, 'white')
    # 잔가지
    for k in range(1, len(ys) - 1):
        if rng.random() < 0.5:
            sx = int(xs[k])
            sd = 1 if rng.random() < 0.5 else -1
            for j in range(1, 4):
                put(img, sx + sd * (j + 1), ys[k] + j * (1 if k % 2 else -1), 'cyan', 220)
            put(img, sx + sd * 5, ys[k] + 3 * (1 if k % 2 else -1), 'white', 230)
    return img


def beam_warn(i):
    W, Hh = 16, 32
    img = new(W, Hh)
    for y in range(Hh):
        if (y + i * 4) % 8 < 3:
            put(img, 7, y, 'white', 235)
            put(img, 8, y, 'cyan', 235)
            put(img, 6, y, 'cyan', 80)
            put(img, 9, y, 'cyan', 80)
    return img


def storm_obstacles():
    o = {}
    o['crystal_a'] = ([crystal(91, [(17, 18, -2.4, 11.5, 5, False), (15, 17, 0.25, 11, 5, False),
                                     (16, 19, 1.9, 9.5, 4.6, False), (15, 18, -1.15, 14.5, 6.4, True)])],
                      [16, 16], {'r': 12})
    o['crystal_b'] = ([crystal(92, [(16, 16, -0.5, 13.5, 5.6, False), (16, 16, 2.6, 13.2, 5.4, False),
                                     (16, 16, 1.25, 12.0, 5, False), (16, 16, -1.95, 13.6, 5.8, True),
                                     (16, 16, 0.55, 10.5, 4.6, True)])],
                      [16, 16], {'r': 12})
    o['stormorb'] = ([stormorb(0), stormorb(1), stormorb(2)], [16, 16], {'r': 11}, 12)
    o['pylonTop'] = ([pylon(False)], [12, 0], None)
    o['pylonBottom'] = ([pylon(True)], [12, 24], None)
    o['beam'] = ([beam(0), beam(1), beam(2)], [8, 16], {'x': -6, 'y': -16, 'w': 12, 'h': 32}, 20)
    o['beamWarn'] = ([beam_warn(0), beam_warn(1)], [8, 16], None, 8)
    return o


# ====================================================================== 아틀라스


def pack(items, maxw, pad=2):
    """items: [(name, frames, meta)] → (sheet, animations)"""
    x = y = rowh = 0
    placed = []
    usedw = 0
    for name, frames, meta in items:
        fh, fw = frames[0].shape[:2]
        tot = len(frames) * fw + (len(frames) - 1) * pad
        if x > 0 and x + tot > maxw:
            x = 0
            y += rowh + pad
            rowh = 0
        rects = []
        for fr in frames:
            rects.append([x, y, fw, fh])
            x += fw + pad
        usedw = max(usedw, x - pad)
        rowh = max(rowh, fh)
        placed.append((name, frames, rects, meta))
    sheet = new(usedw, y + rowh)
    anims = {}
    for name, frames, rects, meta in placed:
        for fr, (rx, ry, rw, rh) in zip(frames, rects):
            sheet[ry:ry + rh, rx:rx + rw] = fr
        a = {'frames': rects}
        a.update(meta)
        anims[name] = a
    return sheet, anims


def write_atlas(dirp, base, items, maxw):
    sheet, anims = pack(items, maxw)
    save(sheet, os.path.join(dirp, base + '.png'))
    with open(os.path.join(dirp, base + '.json'), 'w', encoding='utf-8') as fp:
        json.dump({'image': base + '.png', 'animations': anims}, fp, ensure_ascii=False, indent=2)
        fp.write('\n')
    return sheet, anims


# ====================================================================== 시험 장면


def top_fn(x):
    return 64 + 26 * math.sin(x * 0.0105 + 0.7) + 14 * math.sin(x * 0.027 + 2.1) + 6 * math.sin(x * 0.061)


def bot_fn(x):
    return 292 + 24 * math.sin(x * 0.0093 + 1.9) + 13 * math.sin(x * 0.031 + 0.3) + 5 * math.sin(x * 0.07 + 1)


def frame_of(T, name, k=0):
    """타일·장애물 이름으로 프레임 그림과 앵커를 꺼낸다."""
    for atlas in (T['tiles_anims'], T['obs_anims']):
        if name in atlas:
            a = atlas[name]
            sheet = T['tiles_sheet'] if atlas is T['tiles_anims'] else T['obs_sheet']
            x, y, w, h = a['frames'][k % len(a['frames'])]
            return sheet[y:y + h, x:x + w], a.get('anchor', [w // 2, h // 2])
    raise KeyError(name)


def render_scene(T, camx, blob=True, cast=None):
    out = T['sky'].copy()
    for layer, k in ((T['far'], 0.15), (T['mid'], 0.4)):
        off = int(round(camx * k)) % VW
        blit(out, np.roll(layer, -off, axis=1), 0, 0)
    fb, _ = frame_of(T, 'floorBody')
    cb, _ = frame_of(T, 'ceilBody')
    fe, fa = frame_of(T, 'floorEdge')
    ce, ca = frame_of(T, 'ceilEdge')
    cols = []
    x0 = camx - camx % 4
    for wx in range(x0, camx + VW + 4, 4):
        sx = wx - camx
        t, b = int(round(top_fn(wx))), int(round(bot_fn(wx)))
        cols.append((wx, sx, t, b))
        for k in range(4):
            px = sx + k
            if 0 <= px < VW:
                out[:t, px] = cb[np.arange(t) % 32, (wx + k) % 32]
                out[b:, px] = fb[np.arange(b, VH) % 32, (wx + k) % 32]
    for wx, sx, t, b in cols:
        s = wx % 16
        blit(out, fe[:, s:s + 4], sx, b - fa[1])
        blit(out, ce[:, s:s + 4], sx, t - ca[1])

    def tb(wx):
        w4 = wx - wx % 4
        return int(round(top_fn(w4))), int(round(bot_fn(w4)))

    for name, wx, where, yv, k in (cast or []):
        img, (ax, ay) = frame_of(T, name, k)
        t, b = tb(wx)
        if where == 'floor':
            y = b
        elif where == 'ceil':
            y = t
        elif where == 'floorbase':
            y = b - (img.shape[0] - ay) + 1
        else:
            y = yv
        blit(out, img, wx - camx - ax, y - ay)
        if name == 'pylonTop' and yv == 'beam':
            bimg, (bax, bay) = frame_of(T, 'beam', k)
            y0 = t + img.shape[0] - 2
            y1 = b - img.shape[0] + 2
            yy0 = y0
            while yy0 < y1:
                seg = bimg[:min(32, y1 - yy0)]
                blit(out, seg, wx - camx - bax, yy0)
                yy0 += 32
        if name == 'pylonTop' and yv == 'warn':
            bimg, (bax, bay) = frame_of(T, 'beamWarn', k)
            y0 = t + img.shape[0] - 1
            y1 = b - img.shape[0] + 1
            yy0 = y0
            while yy0 < y1:
                blit(out, bimg[:min(32, y1 - yy0)], wx - camx - bax, yy0)
                yy0 += 32
    if blob:
        t, b = tb(camx + 170)
        cy = (t + b) // 2
        bl = new(32, 32)
        m = ellipse_mask(32, 32, 16, 17, 10, 9)
        paint(bl, m, 'red')
        paint(bl, m & ellipse_mask(32, 32, 13, 14, 6, 5), 'salmon')
        put(bl, 20, 15, 'white')
        put(bl, 20, 16, 'ink')
        outline(bl, 'ink')
        blit(out, bl, 170 - 16, cy - 17)
    return out


def snap_palette(img, ref):
    cols = np.unique(ref[..., :3].reshape(-1, 3), axis=0).astype(np.int32)
    px = img[..., :3].reshape(-1, 3).astype(np.int32)
    best = np.zeros(len(px), np.int64)
    bd = np.full(len(px), 1 << 40, np.int64)
    for i, c in enumerate(cols):
        dd = ((px - c) ** 2).sum(1)
        better = dd < bd
        bd[better] = dd[better]
        best[better] = i
    out = img.copy()
    out[..., :3] = cols[best].reshape(img.shape[:2] + (3,)).astype(np.uint8)
    out[..., 3] = 255
    return out


# ====================================================================== 미리보기


def preview_tiles(T, theme):
    sheet = T['tiles_sheet']
    bg = {'cloud': SKY2, 'mushroom': 'purple', 'storm': NIGHT1}[theme]
    a = up(flat(sheet, bg), 4)
    fb, _ = frame_of(T, 'floorBody')
    cb, _ = frame_of(T, 'ceilBody')
    pat = np.concatenate([np.tile(cb, (3, 4, 1)), np.tile(fb, (3, 4, 1))], axis=1)
    p = up(pat, 3)
    W = max(a.shape[1], p.shape[1])
    out = new(W, a.shape[0] + p.shape[0] + 8)
    out[..., 3] = 255
    out[:a.shape[0], :a.shape[1]] = a
    out[a.shape[0] + 8:, :p.shape[1]] = p
    save(out, os.path.join(PREV, 'world_%s_tiles.png' % theme))


def preview_obstacles(T, theme):
    sheet, anims = T['obs_sheet'], T['obs_anims']
    bg = {'cloud': SKY2, 'mushroom': 'purple', 'storm': NIGHT1}[theme]
    base = flat(sheet, bg)
    over = base.copy()
    for name, a in anims.items():
        hit = a.get('hit')
        if not hit:
            continue
        ax, ay = a['anchor']
        for (x, y, w, h) in a['frames']:
            if 'r' in hit:
                xx, yy = grid(w, h)
                dd = np.hypot(xx - ax, yy - ay)
                ring = (dd > hit['r'] - 0.5) & (dd <= hit['r'] + 0.5)
                sub = over[y:y + h, x:x + w]
                sub[ring] = (255, 0, 68, 255)
            else:
                x0, y0 = ax + hit['x'], ay + hit['y']
                sub = over[y:y + h, x:x + w]
                for xq in range(max(0, x0), min(w, x0 + hit['w'])):
                    for yq in (y0, y0 + hit['h'] - 1):
                        if 0 <= yq < h:
                            sub[yq, xq] = (255, 0, 68, 255)
                for yq in range(max(0, y0), min(h, y0 + hit['h'])):
                    for xq in (x0, x0 + hit['w'] - 1):
                        if 0 <= xq < w:
                            sub[yq, xq] = (255, 0, 68, 255)
            sub = over[y:y + h, x:x + w]
            if 0 <= ay < h and 0 <= ax < w:
                sub[min(ay, h - 1), min(ax, w - 1)] = (255, 255, 0, 255)
    out = np.concatenate([up(base, 4), up(over, 4)], axis=0)
    save(out, os.path.join(PREV, 'world_%s_obstacles.png' % theme))


def preview_seams(T, theme):
    sky2 = np.concatenate([T['sky'], T['sky']], axis=1)
    lay = sky2.copy()
    blit(lay, np.concatenate([T['far'], T['far']], axis=1), 0, 0)
    blit(lay, np.concatenate([T['mid'], T['mid']], axis=1), 0, 0)
    crop = up(lay[:, 640 - 120:640 + 120], 3)
    top = lay
    W = max(top.shape[1], crop.shape[1])
    out = new(W, top.shape[0] + crop.shape[0] + 6)
    out[..., 3] = 255
    out[:top.shape[0], :top.shape[1]] = top
    out[top.shape[0] + 6:, :crop.shape[1]] = crop
    save(out, os.path.join(PREV, 'world_%s_seams.png' % theme))


CASTS = {
    'cloud': [
        ('decor_floor_a', 2632, 'floor', 0, 0), ('decor_floor_b', 2720, 'floor', 0, 0),
        ('decor_floor_c', 2852, 'floor', 0, 0), ('decor_floor_a', 3010, 'floor', 0, 0),
        ('decor_floor_b', 3150, 'floor', 0, 0), ('decor_ceil_a', 2700, 'ceil', 0, 0),
        ('decor_ceil_b', 2900, 'ceil', 0, 0), ('decor_ceil_a', 3100, 'ceil', 0, 0),
        ('rock_a', 2560, 'air', 168, 0), ('bigrock', 2800, 'air', 196, 0), ('balloon', 2960, 'air', 150, 0),
        ('rock_b', 3060, 'air', 230, 0), ('balloon', 3130, 'air', 200, 1), ('rock_c', 2680, 'air', 240, 0),
        ('particle', 2500, 'air', 140, 0), ('particle', 2760, 'air', 120, 1), ('particle', 2990, 'air', 250, 0),
    ],
    'mushroom': [
        ('decor_floor_a', 2600, 'floor', 0, 0), ('decor_floor_b', 2700, 'floor', 0, 0),
        ('decor_floor_c', 2830, 'floor', 0, 0), ('decor_floor_a', 3050, 'floor', 0, 0),
        ('decor_floor_c', 3130, 'floor', 0, 0), ('decor_ceil_a', 2660, 'ceil', 0, 0),
        ('decor_ceil_b', 2880, 'ceil', 0, 0), ('decor_ceil_a', 3070, 'ceil', 0, 0),
        ('mushroom', 2940, 'floorbase', 0, 0), ('mushroom', 2780, 'floorbase', 0, 1),
        ('thorn_a', 2600, 'air', 170, 0), ('thorn_b', 3040, 'air', 200, 0),
        ('spore', 2860, 'air', 150, 0), ('spore', 3150, 'air', 140, 1),
        ('particle', 2520, 'air', 150, 0), ('particle', 2720, 'air', 210, 1), ('particle', 2990, 'air', 120, 0),
        ('particle', 3100, 'air', 250, 1),
    ],
    'storm': [
        ('decor_floor_a', 2620, 'floor', 0, 0), ('decor_floor_b', 2716, 'floor', 0, 0),
        ('decor_floor_c', 2840, 'floor', 0, 0), ('decor_floor_a', 3060, 'floor', 0, 0),
        ('decor_ceil_a', 2650, 'ceil', 0, 0), ('decor_ceil_b', 2900, 'ceil', 0, 0),
        ('decor_ceil_a', 3110, 'ceil', 0, 0),
        ('crystal_a', 2580, 'air', 176, 0), ('crystal_b', 3020, 'air', 220, 0),
        ('stormorb', 2800, 'air', 150, 0), ('stormorb', 3140, 'air', 170, 1),
        ('pylonTop', 2900, 'ceil', 'beam', 0), ('pylonBottom', 2900, 'floor', 0, 0),
        ('pylonTop', 2700, 'ceil', 'warn', 0), ('pylonBottom', 2700, 'floor', 0, 0),
    ],
}


def rain_overlay(img, seed):
    rng = np.random.default_rng(seed)
    a = img.copy()
    return a


def make_scene(T, theme):
    scene = render_scene(T, 2496, blob=True, cast=CASTS[theme])
    if theme == 'storm':
        p, (ax, ay) = frame_of(T, 'particle', 0)
        rng = np.random.default_rng(9)
        for _ in range(70):
            blit(scene, p, int(rng.uniform(0, VW)), int(rng.uniform(0, VH)))
    save(up(scene, 2), os.path.join(PREV, 'world_%s_scene.png' % theme))
    # 로비 카드용 축소 장면
    full = render_scene(T, 2496, blob=False, cast=CASTS[theme])
    small = np.array(Image.fromarray(full, 'RGBA').reduce(4))
    pv = snap_palette(small, full)
    return pv


# ====================================================================== 검사


SPEC = {
    'cloud': {'rock_a': (32, 32, 1, {'r': 12}), 'rock_b': (32, 32, 1, {'r': 12}), 'rock_c': (32, 32, 1, {'r': 12}),
              'bigrock': (48, 48, 1, {'r': 18}), 'balloon': (32, 32, 2, {'r': 11})},
    'mushroom': {'mushroom': (48, 32, 2, {'x': -20, 'y': -6, 'w': 40, 'h': 16}),
                 'thorn_a': (32, 32, 1, {'r': 12}), 'thorn_b': (32, 32, 1, {'r': 12}),
                 'spore': (24, 24, 2, {'r': 9})},
    'storm': {'crystal_a': (32, 32, 1, {'r': 12}), 'crystal_b': (32, 32, 1, {'r': 12}),
              'stormorb': (32, 32, 3, {'r': 11}), 'pylonTop': (24, 24, 1, None),
              'pylonBottom': (24, 24, 1, None), 'beam': (16, 32, 3, 'any'), 'beamWarn': (16, 32, 2, None)},
}
TILE_SPEC = {'floorEdge': (16, 12), 'floorBody': (32, 32), 'ceilEdge': (16, 12), 'ceilBody': (32, 32)}


def validate():
    ok = True
    for theme in ('cloud', 'mushroom', 'storm'):
        dp = os.path.join(OUT, theme)
        for f in ('sky.png', 'far.png', 'mid.png'):
            im = Image.open(os.path.join(dp, f))
            if im.size != (640, 360) or im.mode != 'RGBA':
                print('  !', theme, f, im.size, im.mode)
                ok = False
        if Image.open(os.path.join(dp, 'preview.png')).size != (160, 90):
            print('  ! preview size', theme)
            ok = False
        for base, spec in (('tiles', None), ('obstacles', SPEC[theme])):
            js = json.load(open(os.path.join(dp, base + '.json'), encoding='utf-8'))
            im = Image.open(os.path.join(dp, js['image']))
            W, Hh = im.size
            for name, a in js['animations'].items():
                for (x, y, w, h) in a['frames']:
                    if x < 0 or y < 0 or x + w > W or y + h > Hh:
                        print('  ! rect outside', theme, base, name)
                        ok = False
                ax, ay = a.get('anchor', [0, 0])
                if not (0 <= ax <= a['frames'][0][2] and 0 <= ay <= a['frames'][0][3]):
                    print('  ! anchor outside', theme, name)
                    ok = False
            names = set(js['animations'])
            if base == 'tiles':
                need = set(TILE_SPEC) | {'decor_floor_a', 'decor_floor_b', 'decor_floor_c', 'decor_ceil_a',
                                         'decor_ceil_b', 'particle'}
                for n_, (w, h) in TILE_SPEC.items():
                    fr = js['animations'][n_]['frames'][0]
                    if (fr[2], fr[3]) != (w, h):
                        print('  ! size', theme, n_)
                        ok = False
                for n_ in ('decor_floor_a', 'decor_floor_b', 'decor_floor_c', 'decor_ceil_a', 'decor_ceil_b'):
                    fr = js['animations'][n_]['frames'][0]
                    if (fr[2], fr[3]) not in ((16, 16), (16, 24)):
                        print('  ! decor size', theme, n_)
                        ok = False
                pf = js['animations']['particle']['frames']
                if not (1 <= len(pf) <= 2 and all(f[2] <= 8 and f[3] <= 8 for f in pf)):
                    print('  ! particle', theme)
                    ok = False
                # 몸통 타일은 빈틈 없이 불투명해야 한다
                arr = np.array(im)
                for n_ in ('floorBody', 'ceilBody'):
                    x, y, w, h = js['animations'][n_]['frames'][0]
                    if (arr[y:y + h, x:x + w, 3] < 255).any():
                        print('  ! body not opaque', theme, n_)
                        ok = False
            else:
                need = set(spec)
                for n_, (w, h, nf, hit) in spec.items():
                    a = js['animations'].get(n_)
                    if a is None:
                        continue
                    if len(a['frames']) != nf or any((f[2], f[3]) != (w, h) for f in a['frames']):
                        print('  ! frames', theme, n_)
                        ok = False
                    if hit is None and 'hit' in a:
                        print('  ! unexpected hit', theme, n_)
                        ok = False
                    if isinstance(hit, dict) and a.get('hit') != hit:
                        print('  ! hit mismatch', theme, n_, a.get('hit'))
                        ok = False
            miss = need - names
            extra = names - need
            if miss:
                print('  ! missing', theme, base, sorted(miss))
                ok = False
            if extra:
                print('  ! extra', theme, base, sorted(extra))
                ok = False
    print('검사', '통과' if ok else '실패')
    return ok


def report_hits(T, theme):
    for name, a in T['obs_anims'].items():
        hit = a.get('hit')
        if not hit or 'r' not in hit:
            continue
        for k in range(len(a['frames'])):
            img, (ax, ay) = frame_of(T, name, k)
            mn, me, mx = radial_profile(img, ax, ay)
            print('   %-10s f%d  r=%-4g art min %.1f mean %.1f max %.1f' % (name, k, hit['r'], mn, me, mx))


# ====================================================================== 실행

THEMES = {
    'cloud': dict(sky=cloud_sky, far=cloud_far, mid=cloud_mid, fbody=cloud_floor_body, fedge=cloud_floor_edge,
                  cbody=cloud_ceil_body, cedge=cloud_ceil_edge, decor=cloud_decor, particle=cloud_particle,
                  obstacles=cloud_obstacles, fa=[0, 3], ca=[0, 7], pfps=3),
    'mushroom': dict(sky=mushroom_sky, far=mushroom_far, mid=mushroom_mid, fbody=mushroom_floor_body,
                     fedge=mushroom_floor_edge, cbody=mushroom_ceil_body, cedge=mushroom_ceil_edge,
                     decor=mushroom_decor, particle=mushroom_particle, obstacles=mushroom_obstacles,
                     fa=[0, 3], ca=[0, 6], pfps=4),
    'storm': dict(sky=storm_sky, far=storm_far, mid=storm_mid, fbody=lambda: storm_rock_body(501),
                  fedge=storm_floor_edge, cbody=lambda: storm_rock_body(511, dark=0.15), cedge=storm_ceil_edge,
                  decor=storm_decor, particle=storm_particle, obstacles=storm_obstacles,
                  fa=[0, 3], ca=[0, 6], pfps=8),
}


def build(theme):
    cfg = THEMES[theme]
    dp = os.path.join(OUT, theme)
    os.makedirs(dp, exist_ok=True)
    T = {'sky': cfg['sky'](), 'far': cfg['far'](), 'mid': cfg['mid']()}
    save(T['sky'], os.path.join(dp, 'sky.png'))
    save(T['far'], os.path.join(dp, 'far.png'))
    save(T['mid'], os.path.join(dp, 'mid.png'))
    decor = cfg['decor']()
    pfr = cfg['particle']()
    items = [
        ('floorEdge', [cfg['fedge']()], {'anchor': cfg['fa']}),
        ('ceilEdge', [cfg['cedge']()], {'anchor': cfg['ca']}),
        ('particle', pfr, {'fps': cfg['pfps'], 'anchor': [4, 4]}),
        ('floorBody', [cfg['fbody']()], {'anchor': [0, 0]}),
        ('ceilBody', [cfg['cbody']()], {'anchor': [0, 0]}),
    ]
    for n_ in ('decor_floor_a', 'decor_floor_b', 'decor_floor_c', 'decor_ceil_a', 'decor_ceil_b'):
        img, anc = decor[n_]
        items.append((n_, [img], {'anchor': anc}))
    T['tiles_sheet'], T['tiles_anims'] = write_atlas(dp, 'tiles', items, 96)
    obs = cfg['obstacles']()
    oitems = []
    for name, v in obs.items():
        frames, anchor, hit = v[0], v[1], v[2]
        fps = v[3] if len(v) > 3 else None
        meta = {}
        if fps:
            meta['fps'] = fps
        meta['anchor'] = anchor
        if hit:
            meta['hit'] = hit
        oitems.append((name, frames, meta))
    T['obs_sheet'], T['obs_anims'] = write_atlas(dp, 'obstacles', oitems, 160)
    pv = make_scene(T, theme)
    save(pv, os.path.join(dp, 'preview.png'))
    save(up(pv, 4), os.path.join(PREV, 'world_%s_preview.png' % theme))
    preview_tiles(T, theme)
    preview_obstacles(T, theme)
    preview_seams(T, theme)
    print(theme, '완료')
    report_hits(T, theme)
    return T


def main():
    os.makedirs(PREV, exist_ok=True)
    for theme in ('cloud', 'mushroom', 'storm'):
        build(theme)
    validate()


if __name__ == '__main__':
    main()
