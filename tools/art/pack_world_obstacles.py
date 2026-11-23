"""버섯숲·폭풍협곡 장애물 그림을 ChatGPT 시트에서 오려 게임 아틀라스로 묶는다. 구름섬은 pack_concept.py가 묶는다.

시트는 마젠타 위에 물체가 흩어진 그림 한 장이다. 물체마다 따로 오려, 부딪힘 크기는 shared/mapgen.js의 OBSTACLE_GEOM에
맞추고 그림은 pack_concept.py와 같이 res 1440에 ART_SCALE만큼 키워 넣는다. 그림 모양은 바꾸지 않고 크기와 기준점만 정한다.

  mushroom  튕김 버섯 mushroom, 가시덤불 thorn_a·thorn_b, 포자 spore
  storm     수정 crystal_a·crystal_b, 전기 구슬 stormorb, 번개 기둥 머리 pylonTop·pylonBottom, 번개 줄기 beam·beamWarn

크기를 정하는 기준은 키우기 전 크기, 맵 단위로 적는다
  둥근 장애물   구름섬 바위처럼 그림 폭이 부딪힘 지름의 1.4배쯤
  튕김 버섯     갓 폭이 OBSTACLE_GEOM.mushroom.capW. 키운 그림의 갓 높이를 출력하니, ART_SCALE을 바꾸면 OBSTACLE_GEOM의 capTop·capBottom과 이 파일의 CAP_TOP·CAP_BOTTOM에 옮겨 적는다
  번개 줄기     기둥 머리 사이가 가장 먼 284 맵 단위여도 줄기 한 장이 다 덮는 길이
사용
  python tools/art/pack_world_obstacles.py --theme mushroom
  python tools/art/pack_world_obstacles.py --theme storm
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_scene import unkey  # noqa: E402
import paper_doll as pd  # noqa: E402
from pack_concept import Packer, write_atlas, scaled, ASSETS, ROOT, WORLD_RES, ART_SCALE  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PX = WORLD_RES / 960  # 맵 1단위가 아틀라스 몇 픽셀인지. res 1440이면 1.5
CAP_W = 60  # OBSTACLE_GEOM.mushroom.capW
CAP_TOP = 55  # OBSTACLE_GEOM.mushroom.capTop
CAP_BOTTOM = 34  # OBSTACLE_GEOM.mushroom.capBottom
PYLON_W = 30  # 번개 기둥 머리 돌 테두리 폭. 가장 좁은 110 간격에서도 위아래 머리가 닿지 않는 크기
BEAM_K = 0.35  # 번개 줄기: 원본 1픽셀이 키우기 전 몇 맵 단위인지. 줄기 길이가 가장 먼 기둥 사이를 덮도록 정했다


def objects(keyed, cell=4, reach=3, small=1500, attach=80):
    """마젠타를 걷은 시트에서 물체를 하나씩 찾는다. 가까운 반짝이·물방울 같은 작은 조각은 가장 가까운 물체에 붙인다"""
    a = keyed[..., 3] > 24
    h, w = a.shape
    g = a[: h // cell * cell, : w // cell * cell].reshape(h // cell, cell, w // cell, cell).any((1, 3))
    for _ in range(reach):
        g = pd.dilate(g)
    found = []
    for m in pd.pieces_of(g):
        full = np.kron(m, np.ones((cell, cell), bool))
        full = np.pad(full, ((0, h - full.shape[0]), (0, w - full.shape[1])))
        mask = full & (keyed[..., 3] > 8)
        if mask.any():
            found.append({"mask": mask, "area": int(((keyed[..., 3] > 128) & mask).sum())})
    for o in found:
        ys, xs = np.nonzero(o["mask"])
        o["box"] = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    big = [o for o in found if o["area"] >= small]
    for o in found:
        if o["area"] >= small:
            continue
        x0, y0, x1, y1 = o["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        best, bd = None, attach
        for b in big:
            bx0, by0, bx1, by1 = b["box"]
            d = np.hypot(max(bx0 - cx, 0, cx - bx1), max(by0 - cy, 0, cy - by1))
            if d <= bd:
                best, bd = b, d
        if best is not None:
            best["mask"] |= o["mask"]
            b = best["box"]
            best["box"] = (min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1))
    for o in big:
        o["cx"] = (o["box"][0] + o["box"][2]) / 2
        o["cy"] = (o["box"][1] + o["box"][3]) / 2
    return big


def crop(keyed, o):
    x0, y0, x1, y1 = o["box"]
    arr = np.zeros((y1 - y0, x1 - x0, 4))
    sub = o["mask"][y0:y1, x0:x1]
    arr[sub] = keyed[y0:y1, x0:x1][sub]
    return arr


def to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def centroid(arr, alpha=128):
    ys, xs = np.nonzero(arr[..., 3] > alpha)
    return xs.mean(), ys.mean()


def row_widths(arr, alpha=128):
    """줄마다 불투명 픽셀의 왼쪽·오른쪽 끝과 폭"""
    out = []
    for row in arr[..., 3] > alpha:
        xs = np.nonzero(row)[0]
        out.append((xs.min(), xs.max(), xs.max() - xs.min() + 1) if len(xs) else (0, 0, 0))
    return out


def largest_piece(mask):
    """8방향으로 이어진 조각 가운데 가장 큰 것. 4배 줄여 찾고 원래 크기로 되돌린다"""
    h, w = mask.shape
    c = 2
    g = mask[: h // c * c, : w // c * c].reshape(h // c, c, w // c, c).any((1, 3))
    best = max(pd.pieces_of(g), key=lambda m: m.sum())
    full = np.kron(best, np.ones((c, c), bool))
    full = np.pad(full, ((0, h - full.shape[0]), (0, w - full.shape[1])))
    return full & mask


class Sheet:
    def __init__(self):
        self.packer = Packer(1024)
        self.anims = {}

    def add(self, name, arr, k, anchor, hit=None):
        """원본 1픽셀이 키우기 전 k 맵 단위가 되게 줄인다. anchor는 원본 픽셀 좌표"""
        s = k * ART_SCALE * PX
        img = scaled(to_img(arr), s)
        rect = self.packer.add(img)
        a = {"frames": [rect], "anchor": [round(anchor[0] * s), round(anchor[1] * s)]}
        if hit:
            a["hit"] = hit
        self.anims[name] = a
        print(f"  {name}: 원본 {arr.shape[1]}×{arr.shape[0]} → {img.width}×{img.height}, 맵에서 {img.width / PX:.0f}×{img.height / PX:.0f}")
        return img


def strip_stray(arr, max_h=12, max_area=1500):
    """외곽선 밖으로 삐져나온 가는 밝은 줄을 지운다. 원본 그림의 버섯 갓 왼쪽 흰 줄 같은 것.
    바깥에서 어두운 외곽선을 넘지 않고 닿는 밝은 픽셀 덩어리 중 얇고 작은 것만 지운다"""
    import paper_doll as pd
    a = arr.copy()
    op = a[..., 3] > 60
    dark = op & (pd.lum(a) < 90)
    passable = ~dark
    out = np.zeros_like(passable)
    out[0, :], out[-1, :], out[:, 0], out[:, -1] = passable[0, :], passable[-1, :], passable[:, 0], passable[:, -1]
    while True:
        nxt = pd.dilate(out) & passable
        if (nxt == out).all():
            break
        out = nxt
    n = 0
    for m in pd.pieces_of(op & out & (pd.lum(a) > 110)):
        ys, _ = np.nonzero(m)
        if ys.max() - ys.min() + 1 <= max_h and m.sum() <= max_area:
            a[m] = 0
            n += 1
    return a, n


def pack_mushroom(keyed, sheet):
    objs = objects(keyed)
    assert len(objs) == 4, f"물체 {len(objs)}개, 4개여야 한다"
    spore = min(objs, key=lambda o: o["cy"])
    rest = sorted([o for o in objs if o is not spore], key=lambda o: o["cx"])
    mush, thorn_a, thorn_b = rest

    # 튕김 버섯: 갓 폭을 capW에. 기준점은 아래 가운데, drawBottom으로 그린다
    arr, n = strip_stray(crop(keyed, mush))
    print(f"  버섯 외곽선 밖 가는 줄 {n}개 지움")
    rw = row_widths(arr)
    cap_w = max(w for _, _, w in rw)
    k = CAP_W / cap_w
    h = arr.shape[0]
    widest = max(range(h), key=lambda y: rw[y][2])
    # 갓 아랫단: 가장 넓은 줄에서 내려가며 폭이 처음으로 갓 폭의 60% 밑으로 줄어드는 곳. 그 아래 밑동 잎은 갓이 아니다
    rim = next(y for y in range(widest, h) if rw[y][2] < cap_w * 0.6) - 1
    d = k * ART_SCALE
    # 키운 그림 위에서 갓 폭이 capW 이상인 가장 윗줄과 갓 아랫단의 높이. 부딪힘 높이와 비교해 출력만 한다
    top30 = min(y for y in range(h) if rw[y][2] * d >= CAP_W)
    cap_top = (h - top30) * d
    cap_bottom = (h - rim) * d
    stem = [rw[y][2] * d for y in range(rim + 10, rim + 60)]
    sheet.add("mushroom", arr, k, (arr.shape[1] / 2, h), hit={"x": -CAP_W // 2, "y": -CAP_TOP, "w": CAP_W, "h": CAP_TOP - CAP_BOTTOM})
    print(f"  → 키운 그림: 갓 폭 {cap_w * d:.1f}, 폭 {CAP_W} 넘는 갓 윗줄 높이 {cap_top:.1f}, 갓 아랫단 높이 {cap_bottom:.1f}, "
          f"줄기 폭 {min(stem):.1f}~{max(stem):.1f}, 전체 높이 {h * d:.1f} / 부딪힘 갓 {CAP_BOTTOM}~{CAP_TOP}")

    # 가시덤불: 그림 폭 50·52, 기준점은 불투명 픽셀 무게중심
    for name, o, width in (("thorn_a", thorn_a, 50), ("thorn_b", thorn_b, 52)):
        arr = crop(keyed, o)
        sheet.add(name, arr, width / arr.shape[1], centroid(arr), hit={"r": 18})

    # 포자: 가운데 솜뭉치 지름을 32에. 물방울은 그대로 둘레에 남는다
    arr = crop(keyed, spore)
    body = largest_piece(arr[..., 3] > 128)
    ys, xs = np.nonzero(body)
    bw = xs.max() - xs.min() + 1
    sheet.add("spore", arr, 32 / bw, ((xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2), hit={"r": 14})


def pack_storm(keyed, sheet):
    objs = objects(keyed)
    assert len(objs) == 7, f"물체 {len(objs)}개, 7개여야 한다"
    beams = sorted([o for o in objs if (o["box"][3] - o["box"][1]) > 2.5 * (o["box"][2] - o["box"][0])], key=lambda o: o["cx"])
    assert len(beams) == 2, "세로로 긴 번개 줄기가 둘이어야 한다"
    rest = sorted([o for o in objs if all(o is not b for b in beams)], key=lambda o: o["cx"])
    left = sorted(rest[0:2], key=lambda o: o["cy"])
    mid = sorted(rest[2:4], key=lambda o: o["cy"])
    pylon_top, pylon_bottom = left
    orb, crystal_a = mid
    crystal_b = rest[4]

    # 수정: 넓은 것은 폭 50, 길쭉한 것은 높이 50
    arr = crop(keyed, crystal_a)
    sheet.add("crystal_a", arr, 50 / arr.shape[1], centroid(arr), hit={"r": 18})
    arr = crop(keyed, crystal_b)
    sheet.add("crystal_b", arr, 50 / arr.shape[0], centroid(arr), hit={"r": 18})

    # 전기 구슬: 구슬 지름을 35에, 기준점은 구슬 가운데. 둘레의 돌 조각은 떨어져 있고 전기 줄은 가늘어서
    # 가장 큰 불투명 덩어리의 무게중심과 넓이로 구슬을 잰다
    arr = crop(keyed, orb)
    ball = largest_piece(arr[..., 3] > 200)
    ys, xs = np.nonzero(ball)
    dia = 2 * np.sqrt(ball.sum() / np.pi)
    sheet.add("stormorb", arr, 35 / dia, (xs.mean(), ys.mean()), hit={"r": 16})

    # 기둥 머리: 돌 테두리 폭을 PYLON_W에. 위 머리는 테두리 윗변, 아래 머리는 테두리 아랫변이 땅에 살짝 묻히게
    tips = {}
    for name, o, top in (("pylonTop", pylon_top, True), ("pylonBottom", pylon_bottom, False)):
        arr = crop(keyed, o)
        rw = row_widths(arr, 200)
        h = arr.shape[0]
        rows = range(0, int(h * 0.35)) if top else range(int(h * 0.65), h)
        ring_w = max(rw[y][2] for y in rows)
        ring = [y for y in rows if rw[y][2] >= ring_w * 0.85]
        y0, y1 = min(ring), max(ring)
        cx = (rw[y0][0] + rw[y0][1]) / 2
        k = PYLON_W / ring_w
        sink = (y1 - y0) * 0.15
        ay = (min(y for y in range(h) if rw[y][2]) + sink) if top else (max(y for y in range(h) if rw[y][2]) - sink)
        # 수정 끝: 가운데 세로줄에서 어두운 외곽선이 있는 마지막 줄. 그 너머 밝은 전기 줄은 빼고 잰다
        band = arr[:, int(cx) - 6:int(cx) + 7]
        lum = 0.3 * band[..., 0] + 0.59 * band[..., 1] + 0.11 * band[..., 2]
        col = ((band[..., 3] > 200) & (lum < 110)).any(1)
        ys = np.nonzero(col)[0]
        tip = (ys.max() - ay) if top else (ay - ys.min())
        tips[name] = tip * k * ART_SCALE
        sheet.add(name, arr, k, (cx, ay))
    print(f"  → 기둥 머리 끝까지 맵에서 위 {tips['pylonTop']:.1f}, 아래 {tips['pylonBottom']:.1f}")

    # 번개 줄기: 한 장을 기둥 머리 사이 가운데에 놓고 양 끝은 머리와 땅에 가린다
    for name, o in (("beam", beams[0]), ("beamWarn", beams[1])):
        arr = crop(keyed, o)
        h, w = arr.shape[:2]
        hit = {"x": -9, "y": -round(h * BEAM_K * ART_SCALE / 2), "w": 18, "h": round(h * BEAM_K * ART_SCALE)} if name == "beam" else None
        sheet.add(name, arr, BEAM_K, (w / 2, h / 2), hit=hit)
    print(f"  → 번개 줄기 길이 맵에서 {beams[0]['box'][3] - beams[0]['box'][1]:.0f}px × {BEAM_K * ART_SCALE:.3f} = "
          f"{(beams[0]['box'][3] - beams[0]['box'][1]) * BEAM_K * ART_SCALE:.0f}, 가장 먼 기둥 머리 끝 사이 {284 - tips['pylonTop'] - tips['pylonBottom']:.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True, choices=["mushroom", "storm"])
    ap.add_argument("--input", help="기본 art_inbox/<theme>_obstacles_v1.png")
    args = ap.parse_args()
    src = Path(args.input) if args.input else ROOT / "art_inbox" / f"{args.theme}_obstacles_v1.png"
    keyed = unkey(np.array(Image.open(src).convert("RGB")))
    print(f"{src.name} → {args.theme}, ART_SCALE {ART_SCALE}")
    sheet = Sheet()
    if args.theme == "mushroom":
        pack_mushroom(keyed, sheet)
    else:
        pack_storm(keyed, sheet)
    write_atlas(ASSETS / "world" / args.theme, "obstacles", sheet.packer, sheet.anims, res=WORLD_RES)


if __name__ == "__main__":
    main()
