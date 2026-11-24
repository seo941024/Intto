"""구름섬 시안 한 장에서 물체 조각을 오려 낸다.

시안 그림은 굵은 외곽선이 있어서, 그 선을 벽으로 두고 바깥에서부터 배경을 채워 지우면 물체만 남는다.
결과는 시안 크기 그대로 art_inbox/out/cut/ 에 둔다. pack_concept.py가 그중 보석 gem_blue_a·gem_red, 고기 meat,
깃털 feather, 바위 rock, 풍선 balloon_a 여섯 장을 읽는다. git에는 이 여섯 장만 올린다.
시안의 HUD 판·숫자 조각과 게임 크기로 줄인 art_inbox/out/cut960/ 도 함께 만들지만 지금은 쓰는 곳이 없다.
HUD는 make_hud.py가 따로 받은 그림으로 만든다.
사용
  python tools/art/cut_concept.py
  python tools/art/pack_concept.py
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import shrink, lum, dilate  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art_inbox" / "concept_cloud_v1.webp"
OUT = ROOT / "art_inbox" / "out" / "cut"
OUT960 = ROOT / "art_inbox" / "out" / "cut960"
GAME_K = 960 / 1672

# 이름: (왼, 위, 오른, 아래), 외곽선 밝기 기준, 틈 메우기
PIECES = {
    "balloon_a": ((585, 175, 735, 355), 110, 1),
    "balloon_b": ((665, 515, 815, 690), 110, 1),
    "balloon_c": ((1500, 285, 1655, 465), 110, 1),
    "rock": ((915, 120, 1170, 360), 120, 1),
    "gem_blue_a": ((515, 365, 610, 445), 110, 1),
    "gem_blue_b": ((478, 535, 570, 612), 110, 1),
    "gem_blue_c": ((1058, 605, 1148, 682), 110, 1),
    "gem_red": ((915, 410, 1010, 495), 110, 1),
    "meat": ((1130, 480, 1260, 580), 110, 1),
    "feather": ((1430, 515, 1545, 615), 110, 1),
    "island_a": ((850, 290, 955, 395), 120, 1),
    "island_b": ((850, 540, 1005, 695), 120, 1),
    "island_c": ((1215, 585, 1420, 800), 120, 1),
    "heart": ((35, 22, 108, 82), 110, 1),
    "hp_bar": ((185, 25, 435, 80), 110, 1),
    "timer": ((643, 12, 1028, 102), 110, 1),
    "rank_1": ((1395, 26, 1648, 88), 110, 1),
    "rank_2": ((1395, 86, 1648, 147), 110, 1),
    "rank_3": ((1395, 146, 1648, 207), 110, 1),
    "rank_4": ((1395, 206, 1648, 266), 110, 1),
    "slot": ((25, 810, 121, 914), 110, 1),
    "slot_on": ((232, 806, 336, 918), 110, 1),
    "progress": ((600, 848, 1248, 902), 110, 1),
    "distance": ((38, 88, 372, 190), 110, 1),
}

# 판 안의 글자·그림을 지울 상자. 시안 좌표, 좌우 바로 바깥 세로줄 색을 이어 채운다
ERASE = {
    "timer": [(736, 30, 1006, 88)],
    "rank_1": [(1456, 30, 1633, 85)],
    "rank_2": [(1456, 89, 1633, 144)],
    "rank_3": [(1456, 149, 1633, 204)],
    "rank_4": [(1456, 209, 1633, 263)],
    "slot": [(43, 826, 104, 898)],
    "slot_on": [(250, 826, 318, 898)],
}


def outline_cut(a, thr, grow):
    """어두운 외곽선을 벽으로 두고 바깥에서 배경을 채워 지운다. 남은 부분이 물체다"""
    dark = lum(a) < thr
    wall = dilate(dark, grow) if grow else dark
    h, w = wall.shape
    bg = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not wall[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not wall[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx] and not wall[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    obj = ~bg
    if grow:
        # 틈을 메우려고 키운 벽 두께만큼 바깥 테두리를 다시 깎되, 원래 어두운 외곽선은 남긴다
        edge = obj & dilate(bg, grow)
        obj &= ~(edge & ~dark)
    return obj


def erase_rows(a, box, origin, vertical=False):
    """box 안을 바로 바깥 색으로 이어 채운다. 기본은 좌우로, vertical이면 위아래도 섞는다"""
    x0, y0, x1, y1 = box
    ox, oy = origin
    lx, rx = x0 - ox - 1, x1 - ox
    ty, by = y0 - oy - 1, y1 - oy
    src = a.astype(float)
    for y in range(ty + 1, by):
        for x in range(lx + 1, rx):
            tx = (x - lx) / (rx - lx)
            h = src[y, lx] * (1 - tx) + src[y, rx] * tx
            if vertical:
                t = (y - ty) / (by - ty)
                v = src[ty, x] * (1 - t) + src[by, x] * t
                h = (h + v) / 2
            a[y, x] = h


def save(name, rgba):
    img = Image.fromarray(rgba)
    img.save(OUT / f"{name}.png")
    shrink(img, GAME_K).save(OUT960 / f"{name}.png")


def hp_parts(src):
    """HP 막대에서 빈 틀과 채움 한 줄을 나눈다. 바깥 외곽선 상자를 재서 둥근 사각형으로 오린다"""
    cx0, cy0, cx1, cy1 = 176, 24, 438, 79
    a = src[cy0:cy1, cx0:cx1].astype(float)
    h, w = a.shape[:2]
    mask = rounded_mask(h, w, (180 - cx0, 28 - cy0, 433 - cx0, 74 - cy0), 12)
    green = (a[..., 1] > a[..., 0] + 40) & (a[..., 1] > a[..., 2] + 20)
    green[:, 400 - cx0:] = False
    green[:, :12] = False
    cols = np.nonzero(green.any(0))[0]
    rows = np.nonzero(green[:, 290 - cx0])[0]
    empty_col = a[:, 408 - cx0].copy()
    fill_col = a[:, 290 - cx0].copy()
    frame = a.copy()
    for c in range(cols.min(), cols.max() + 1):
        frame[:, c] = np.where(green[:, c][:, None] | (np.arange(h) >= rows.min())[:, None] & (np.arange(h) <= rows.max())[:, None], empty_col, frame[:, c])
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(frame, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(mask, 255, 0)
    save("hp_frame", out)
    fill = np.zeros((rows.max() - rows.min() + 1, 4, 4), dtype=np.uint8)
    fill[..., :3] = np.clip(fill_col[rows.min():rows.max() + 1, None, :], 0, 255).astype(np.uint8)
    fill[..., 3] = 255
    save("hp_fill", fill)
    # 게임에서 채움을 그릴 안쪽 자리. 시안 크기 기준
    meta = {"fillX": int(cols.min()), "fillY": int(rows.min()), "fillW": int(empty_until(green, a, cx0) - cols.min()), "fillH": int(len(rows))}
    print(f"  hp_frame, hp_fill 채움 자리 {meta}")
    return meta


def empty_until(green, a, cx0):
    """초록 채움이 끝나고 빈 칸이 이어지는 오른쪽 끝, 안쪽 외곽선 바로 앞"""
    row = lum(a[:, :, :3])[a.shape[0] // 2]
    x = 420 - cx0
    while x < len(row) - 1 and row[x] > 40:
        x += 1
    return x


def progress_parts(src):
    x0, y0, x1, y1 = PIECES["progress"][0]
    a = src[y0:y1, x0:x1].copy()
    obj = outline_cut(a, 110, 1)
    empty_col = a[:, 1000 - x0].copy()
    fill_col = a[:, 700 - x0].copy()
    frame = a.copy()
    # 왼쪽 끝 둥근 마개 뒤부터 깃발 앞까지를 빈 칸 색으로
    for c in range(618 - x0, 1190 - x0):
        frame[:, c] = empty_col
    yellow = (a[:, 700 - x0, 0] > 180) & (a[:, 700 - x0, 2] < 120)
    rows = np.nonzero(yellow)[0]
    fill = np.zeros((rows.max() - rows.min() + 1, 4, 4), dtype=np.uint8)
    fill[..., :3] = fill_col[rows.min():rows.max() + 1, None, :3]
    fill[..., 3] = 255
    out = np.zeros(a.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = frame[..., :3]
    # 양 사이 마커가 외곽선 밖으로 튀어나온 부분은 막대 높이로 잘라 낸다
    obj[:, 618 - x0:1190 - x0] = obj[:, 1000 - x0][:, None]
    out[..., 3] = np.where(obj, 255, 0)
    grass = (frame[..., 1] > frame[..., 2] + 10) & (frame[..., 1] > frame[..., 0] + 10)
    out[..., 3][grass] = 0
    # 인또는 결승선 없이 시간으로 끝나므로, 오른쪽 깃발 대신 왼쪽 둥근 마개를 뒤집어 붙인다
    cap = out[:, :618 - x0]
    body_end = 1190 - x0
    out = np.concatenate([out[:, :body_end], cap[:, ::-1]], axis=1)
    save("progress_frame", out)
    save("progress_fill", fill)
    print(f"  progress_frame, progress_fill 채움 높이 {len(rows)}px")
    return {"fillX": 618 - x0, "fillY": int(rows.min()), "fillW": 1190 - 618, "fillH": int(len(rows))}


def digits(src, box, bright, name):
    """판 위 숫자를 밝은 부분과 그 둘레 외곽선으로 오려 글자마다 나눈다.
    글자 사이 틈은 밝은 부분끼리만 보고 나눈 뒤, 글자마다 외곽선 두께만큼 넓힌다"""
    x0, y0, x1, y1 = box
    a = src[y0:y1, x0:x1]
    core = lum(a) > bright
    cols = core.any(0)
    out = []
    x = 0
    w = len(cols)
    while x < w:
        if not cols[x]:
            x += 1
            continue
        s = x
        while x < w and cols[x]:
            x += 1
        gs, ge = max(0, s - 3), min(w, x + 3)
        part = np.zeros_like(core)
        part[:, s:x] = core[:, s:x]
        m = dilate(part, 2)[:, gs:ge]
        g = np.zeros((y1 - y0, ge - gs, 4), dtype=np.uint8)
        g[..., :3] = a[:, gs:ge]
        g[..., 3] = np.where(m, 255, 0)
        out.append(g)
    print(f"  {name}: 글자 {len(out)}개")
    return out


def rounded_mask(h, w, box, r):
    """box=(x0, y0, x1, y1) 안쪽 둥근 사각형"""
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        corner = ((xx < x0 + r) if cx == x0 + r else (xx > x1 - r)) & ((yy < y0 + r) if cy == y0 + r else (yy > y1 - r))
        inside &= ~(corner & ((xx - cx) ** 2 + (yy - cy) ** 2 > r * r))
    return inside


# 기술칸 다섯 개. 시안 좌표로 자르는 왼쪽 위, 1번 칸 기준 간격은 외곽선으로 맞춘 값
SLOT_CROP_W, SLOT_CROP_H, SLOT_Y = 112, 117, 805
SLOT_X = [18, 123, 228, 333, 438]  # 3번째가 고른 칸
SLOT_BOX = (7, 9, 104, 107)  # 자른 칸 안에서 바깥 외곽선 상자
SLOT_INSET = 16  # 테두리와 안쪽 외곽선 두께, 이 안쪽이 아이콘 자리


def slot_stack(src):
    return np.stack([src[SLOT_Y:SLOT_Y + SLOT_CROP_H, x:x + SLOT_CROP_W].astype(float) for i, x in enumerate(SLOT_X) if i != 2])


def slot_shape(stack):
    """네 칸에서 셋 이상이 어두운 자리를 칸 외곽선으로 보고, 줄마다 그 사이를 칸 모양으로 채운다.
    칸마다 뒤 배경이 달라서, 여러 칸이 함께 어두운 곳만 외곽선이다"""
    dark = (lum(stack) < 75).sum(0) >= 3
    h, w = dark.shape
    mask = np.zeros((h, w), dtype=bool)
    for y in range(h):
        xs = np.nonzero(dark[y])[0]
        if len(xs) >= 2 and xs.max() - xs.min() > 20:
            mask[y, xs.min():xs.max() + 1] = True
    return mask


def empty_slot(src):
    """아이콘 자리는 칸 안쪽 가장자리 색으로 채운다. 네 칸 가장자리 색의 중앙값을 써서 아이콘이 걸려도 흔들리지 않는다"""
    stack = slot_stack(src)
    med = np.median(stack, 0)
    x0, y0, x1, y1 = SLOT_BOX
    ix0, iy0, ix1, iy1 = x0 + SLOT_INSET, y0 + SLOT_INSET, x1 - SLOT_INSET, y1 - SLOT_INSET
    inner = rounded_mask(SLOT_CROP_H, SLOT_CROP_W, (ix0, iy0, ix1, iy1), 8)
    base = med.copy()
    for y in range(iy0, iy1 + 1):
        xs = np.nonzero(inner[y])[0]
        if not len(xs):
            continue
        # 채울 자리 바로 바깥 색. 안쪽 판의 둥근 모서리와 외곽선은 네 칸 중앙값 그대로 남는다
        left = med[y, xs.min() - 1]
        right = med[y, xs.max() + 1]
        for x in range(ix0, ix1 + 1):
            if inner[y, x]:
                t = (x - xs.min() + 1) / max(1, xs.max() - xs.min() + 2)
                base[y, x] = left * (1 - t) + right * t
    return base, inner, slot_shape(stack)


def make_slots(src):
    base, inner, mask = empty_slot(src)
    out = np.zeros((SLOT_CROP_H, SLOT_CROP_W, 4), dtype=np.uint8)
    out[..., :3] = np.clip(base, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(mask, 255, 0)
    save("slot", out)
    # 고른 칸: 시안의 금색 테두리를 그대로 쓰고 안쪽만 빈 칸으로 바꾼 뒤 바깥에 빛을 두른다
    x = SLOT_X[2]
    gold = src[SLOT_Y:SLOT_Y + SLOT_CROP_H, x:x + SLOT_CROP_W].astype(float)
    gold[inner] = base[inner]
    gmask = dilate(mask, 2)
    pad = 6
    H, W = SLOT_CROP_H + pad * 2, SLOT_CROP_W + pad * 2
    big = np.zeros((H, W, 4), dtype=np.uint8)
    am = np.zeros((H, W), dtype=bool)
    am[pad:pad + SLOT_CROP_H, pad:pad + SLOT_CROP_W] = gmask
    prev = am
    for alpha in (170, 110, 60, 25):
        grown = prev.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            grown |= np.roll(np.roll(prev, dy, 0), dx, 1)
        ring = grown & ~prev
        big[ring] = (255, 190, 60, alpha)
        prev = grown
    inner_big = big[pad:pad + SLOT_CROP_H, pad:pad + SLOT_CROP_W]
    inner_big[gmask, :3] = np.clip(gold[gmask], 0, 255).astype(np.uint8)
    inner_big[gmask, 3] = 255
    save("slot_on", big)
    print("  slot, slot_on")


def recolor_like(glyph, ref):
    """노란 글자를 흰 글자 색으로 바꾼다. 밝기 순서대로 흰 글자의 색을 맞춘다"""
    g = glyph.copy()
    m = g[..., 3] > 0
    rm = ref[..., 3] > 0
    rc = ref[..., :3][rm].astype(float)
    rl = lum(rc)
    order = np.argsort(rl)
    rl, rc = rl[order], rc[order]
    gl = lum(g[..., :3][m].astype(float))
    # 밝기 분위가 같은 흰 글자 색을 고른다
    q = np.searchsorted(np.sort(gl), gl) / max(1, len(gl) - 1)
    pick = rc[np.clip((q * (len(rc) - 1)).astype(int), 0, len(rc) - 1)]
    g[..., :3][m] = pick.astype(np.uint8)
    return g


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    OUT960.mkdir(parents=True, exist_ok=True)
    src = np.array(Image.open(SRC).convert("RGB")).astype(np.uint8)
    for name, (box, thr, grow) in PIECES.items():
        if name in ("hp_bar", "progress", "slot", "slot_on"):
            continue
        x0, y0, x1, y1 = box
        a = src[y0:y1, x0:x1].copy()
        obj = outline_cut(a, thr, grow)
        for eb in ERASE.get(name, []):
            erase_rows(a, eb, (x0, y0), vertical=name.startswith("slot"))
        if name.startswith("rank_"):
            # 초상 귀가 판 위아래로 튀어나온 부분은 판 밖이므로 지운다
            ex0 = ERASE[name][0][0] - x0
            ex1 = ERASE[name][0][2] - x0
            # 판 오른쪽 끝 세로줄에서 판의 위아래 끝을 재고, 그 바깥은 지운다
            rows = np.nonzero(obj[:, ex1 + 4])[0]
            obj[:rows.min(), ex0:ex1] = False
            obj[rows.max() + 1:, ex0:ex1] = False
        if name == "slot_on":
            continue
        rgba = np.zeros(a.shape[:2] + (4,), dtype=np.uint8)
        rgba[..., :3] = a
        rgba[..., 3] = np.where(obj, 255, 0)
        save(name, rgba)
        print(f"  {name}: {x1 - x0}×{y1 - y0}, 남김 {obj.mean() * 100:.0f}%")
    hp_meta = hp_parts(src)
    make_slots(src)
    prog_meta = progress_parts(src)
    import json
    meta = {"scale": GAME_K, "hp": hp_meta, "progress": prog_meta}
    (OUT / "hud_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # 순위표 숫자: 2~4위 흰 글자에 0~9가 다 들어 있다. 1389, 1357, 1320
    for i, (row, text) in enumerate([((1538, 96, 1630, 140), "1389"), ((1538, 156, 1630, 200), "1357"), ((1538, 216, 1630, 260), "1320")]):
        gl = digits(src, row, 170, f"순위 숫자 {text}")
        for g, ch in zip(gl, text):
            p = OUT / f"digit_small_{ch}.png"
            if not p.exists() or i == 0:
                Image.fromarray(g).save(p)
                shrink(Image.fromarray(g), GAME_K).save(OUT960 / f"digit_small_{ch}.png")
    # 4와 6은 흰 글자에 없어서 1위 노란 숫자 1436에서 가져와 흰 글자 색으로 바꾼다
    yellow = digits(src, (1538, 36, 1630, 80), 150, "순위 숫자 1436")
    ref = np.array(Image.open(OUT / "digit_small_3.png").convert("RGBA"))
    for g, ch in zip(yellow, "1436"):
        if ch in "46":
            w = recolor_like(g, ref)
            Image.fromarray(w).save(OUT / f"digit_small_{ch}.png")
            shrink(Image.fromarray(w), GAME_K).save(OUT960 / f"digit_small_{ch}.png")
    # 쌍점은 타이머 글자 00:37.25의 세 번째 글자에서 가져와 흰 숫자 색으로 맞춘다
    tg = digits(src, (736, 30, 1006, 88), 170, "타이머 00:37.25")
    if len(tg) >= 3:
        ref = np.array(Image.open(OUT / "digit_small_3.png").convert("RGBA"))
        colon = recolor_like(tg[2], ref)
        Image.fromarray(colon).save(OUT / "digit_small_colon.png")
    print(f"저장 {OUT}, {OUT960}")


if __name__ == "__main__":
    main()
