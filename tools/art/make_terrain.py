"""시안 그림체의 지형 그림 한 장에서 천장·바닥 타일을 만든다.

입력은 위쪽에 구름 천장 띠, 아래쪽에 풀밭 바닥 띠가 있고 가운데가 마젠타인 그림이다.
  ceilEdge   천장 띠 전체. 울퉁불퉁한 아래 끝의 중간 높이를 지형 경계선으로 둔다
  ceilBody   천장 띠 윗부분의 꽉 찬 구름을 위아래·좌우로 이어지게 만든 무늬
  floorEdge  바닥 띠 윗부분. 풀 윗면의 중간 높이를 지형 경계선으로 둔다
  floorBody  바닥 띠 아래 바위를 위아래·좌우로 이어지게 만든 무늬
  decor      띠에서 떼어 낸 키 큰 장식. 띠는 땅 높이를 따라 4픽셀 세로줄로 잘려 붙으므로
             꽃이나 버섯처럼 위아래로 튀어나온 것은 따로 떼어 그 자리 땅 높이에 통째로 세운다
카메라가 1.5배 당겨 보므로 res 1440으로 넣어 화면에서 1:1로 그려지게 한다.
작은 입자 그림 particle은 입력 그림에서 만들지 않는다. 덮어쓰기 전 public/assets/world/<theme>/tiles.json에 든
particle 프레임을 읽어 res 1440 크기로 맞춰 새 아틀라스에 그대로 옮겨 싣는다. 처음 만든 임시 도트 입자가 이렇게 이어져 왔다.
그래서 tiles.json이 없으면 멈추고, 거기에 particle이 없으면 입자 없이 만든다.
버섯숲처럼 천장 이끼 속에 버섯 갓이 반쯤 묻혀 있거나 띠 양 끝에 물체가 많은 그림은 인자로 맞춘다.
  --ceil-pct --floor-pct  경계선을 열마다 잰 높이의 중간값 대신 이 백분위로. 매달리거나 솟은 장식이 많으면 중간값이 땅에서 멀어진다
  --ceil-grow             천장 장식이 띠 속에 묻힌 부분까지 초록이 아닌 색을 따라 찾아 통째로 떼고, 빈자리는 속 무늬 색으로 메운다
  --ceil-body             천장 속 무늬로 쓸 원본 가로 범위. 묻힌 버섯 줄기처럼 무늬에 되풀이되면 안 되는 것을 피한다
  --seam cut              띠 양 끝을 섞지 않고 가장 비슷한 세로 경로에서 잘라 잇고, 장식이 없는 줄에서 띠를 시작한다
  --cut                   장식을 경계선에서 이만큼 떨어진 줄부터 뗀다. 장식끼리 땅 위에서 이어져 한 덩어리가 되면 키운다
  --ceil-tall             천장 장식만 따로 떼는 기준. 아주 크게 주면 천장에서는 떼지 않는다
  --ceil-solid            천장 속 무늬를 이 줄 위에서만 뜬다. 외곽선 있는 띠를 옮겨 붙여 꽉 찬 끝 근처에 외곽선이 섞일 때
사용
  python tools/art/compose_ceiling.py
  python tools/art/make_terrain.py art_inbox/cloud_terrain_v2.png --theme cloud --floor-pct 80 --tall 10 --cut 4 --ceil-tall 9999 --seam cut --ceil-solid 62
  python tools/art/make_terrain.py art_inbox/mushroom_terrain_v1.png --theme mushroom --ceil-pct 15 --floor-pct 85 --ceil-grow --ceil-body 510:1150 --seam cut
  python tools/art/make_terrain.py art_inbox/storm_terrain_v1.png --theme storm --floor-pct 85 --ceil-tall 9999 --cut 16 --seam cut
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import unkey, shrink, to_img, lum, dilate  # noqa: E402
from import_scene import seamless, seamless_cut  # noqa: E402
import paper_doll as pd  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
RES = 1440
ART_SCALE = 2 / 3  # 땅 그림 배율. 카메라가 1.5배 당겨 보므로 2/3이면 받은 그림이 화면에서 원래 비율 그대로 보인다. 지형 경계선은 그대로
K = 960 / 1672 * RES / 960 * ART_SCALE  # 시안 크기 → res 1440 그림 크기
OVERLAP = 160  # 좌우 이음 폭, 원본 픽셀
TALL = 24  # 경계선에서 이만큼 넘게 튀어나온 덩어리는 장식으로 뗀다, 원본 픽셀
CUT = 4  # 장식은 경계선에서 이만큼 떨어진 줄부터 뗀다. 그 아래 밑동은 띠에 남는다
OVER = 3  # 떼어 낸 장식이 띠 쪽으로 겹쳐 담기는 줄 수


def tile_vertical(arr, overlap):
    """아래 끝 overlap 줄을 위쪽 시작과 섞어 위아래로도 이어지게 한다"""
    a = arr.copy()
    n = a.shape[0]
    body = a[overlap:].copy()
    m = body.shape[0]
    t = np.linspace(0, 1, overlap)[:, None, None]
    body[m - overlap:] = body[m - overlap:] * (1 - t) + a[:overlap] * t
    return body


def fade(arr, rows, top):
    """띠 위나 아래 rows 줄을 서서히 투명하게. 무늬 위에 겹칠 때 경계선이 안 보이게"""
    a = arr.copy()
    ramp = np.linspace(0, 1, rows)
    if top:
        a[:rows, :, 3] *= ramp[:, None]
    else:
        a[-rows:, :, 3] *= ramp[::-1][:, None]
    return a


def object_color(edge):
    """이끼·풀처럼 초록 계열이 아닌 픽셀. 버섯 갓의 주황, 줄기·점의 크림색, 꽃의 흰색·노란색"""
    r, g, b = edge[..., 0], edge[..., 1], edge[..., 2]
    return (r - g > -12) & (lum(edge) > 70) & (edge[..., 3] > 20)


def grow_into_band(edge, seed, inside):
    """경계선 너머 덩어리에서 시작해, 띠 속 inside 줄에 묻힌 같은 물체를 색으로 이어 찾는다.
    초록이 아닌 픽셀을 따라 넓히고, 마지막에 둘레의 어두운 외곽선을 붙인다"""
    obj = object_color(edge) & inside
    grow = seed.copy()
    while True:
        nxt = dilate(grow) & (seed | obj)
        if (nxt == grow).all():
            break
        grow = nxt
    light = lum(edge)
    ring = grow.copy()
    for _ in range(3):
        ring = dilate(ring)
    dark = (light < 100) & (edge[..., 3] > 0) & inside
    return grow | (ring & dark & ~grow)


def roll_clear(edge, lip, up):
    """이은 띠는 좌우가 이어지므로 아무 데서나 시작해도 된다. 경계선 너머로 나온 것이 가장 적은 세로줄에서 시작하게 돌려,
    장식이 띠 양 끝에 걸려 반으로 갈리지 않게 한다"""
    a = edge[..., 3] > 100
    if up:
        score = a[:max(0, lip - 2)].sum(0)
    else:
        score = a[lip + 2:].sum(0)
    near = np.convolve(score, np.ones(9), mode="same")
    x = int(near.argmin())
    return np.roll(edge, -x, axis=1), x


def split_decor(edge, lip, up, tall=TALL, cut_gap=CUT, body=None):
    """띠에서 경계선 위로, 천장이면 아래로 크게 튀어나온 덩어리를 떼어 낸다.
    떼어 낸 자리는 비우고, 덩어리 그림과 띠 안에서의 가로 가운데·세로 끝을 돌려준다.
    body를 주면 덩어리가 띠 속에 묻힌 부분까지 색으로 이어 찾아 함께 떼고, 빈자리는 body 무늬로 메운다"""
    a = edge[..., 3] > 100
    h, w = a.shape
    cut = lip - cut_gap if up else lip + cut_gap
    region = np.zeros_like(a)
    if up:
        region[:cut] = a[:cut]
    else:
        region[cut + 1:] = a[cut + 1:]
    keep = np.zeros_like(a)
    if up:
        keep[:cut] = True
    else:
        keep[cut + 1:] = True
    out = []
    for m in pd.pieces_of(region):
        ys, xs = np.nonzero(m)
        big = (lip - ys.min() > tall) if up else (ys.max() - lip > tall)
        if not big or xs.min() == 0 or xs.max() == w - 1:
            continue
        grow = m.copy()
        for _ in range(2):
            grow = dilate(grow)
        grow &= keep & (edge[..., 3] > 0)
        if body is not None:
            grow = grow_into_band(edge, grow, ~keep)
            if grow[:, 0].any() or grow[:, -1].any():
                continue
        ys, xs = np.nonzero(grow)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        # 띠 쪽으로 OVER줄 더 겹쳐 담는다. 띠는 그 줄을 그대로 두어, 잘린 경계가 줄여질 때 생기는 밝은 줄을 장식이 덮는다
        sel = grow.copy()
        if up:
            y1o = min(h, y1 + OVER)
            sel[y1:y1o, x0:x1] = edge[y1:y1o, x0:x1, 3] > 0
            y1 = y1o
        else:
            y0o = max(0, y0 - OVER)
            sel[y0o:y0, x0:x1] = edge[y0o:y0, x0:x1, 3] > 0
            y0 = y0o
        sprite = np.zeros((y1 - y0, x1 - x0, 4))
        sub = sel[y0:y1, x0:x1]
        sprite[sub] = edge[y0:y1, x0:x1][sub]
        edge_alpha = edge[..., 3].copy()
        edge[grow] = 0
        if body is not None:
            # 띠 속에 묻혀 있던 자리는 속 무늬 색으로 메운다. 투명도는 원래대로 두어 띠 위쪽이 흐려지는 것을 지킨다.
            # 장식이 그 위를 덮고, 기울어진 땅에서 가장자리만 살짝 보인다
            fill = grow & ~keep
            fy, fx = np.nonzero(fill)
            alpha = edge_alpha[fy, fx]
            edge[fy, fx] = body[fy % body.shape[0], fx % body.shape[1]]
            edge[fy, fx, 3] = alpha
        out.append((sprite, (x0 + x1) / 2, y1 if up else y0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--theme", default="cloud")
    ap.add_argument("--tall", type=int, default=TALL, help="경계선에서 이만큼 넘게 튀어나온 덩어리를 장식으로 뗀다, 원본 픽셀")
    ap.add_argument("--cut", type=int, default=CUT, help="장식을 경계선에서 이만큼 떨어진 줄부터 뗀다, 원본 픽셀")
    ap.add_argument("--ceil-tall", type=int, help="천장만 따로 줄 때 --tall 대신")
    ap.add_argument("--ceil-pct", type=float, default=50, help="천장 경계선: 열마다 잰 천장 아래 끝 높이의 백분위. 50이면 중간값")
    ap.add_argument("--floor-pct", type=float, default=50, help="바닥 경계선: 열마다 잰 바닥 위 끝 높이의 백분위. 50이면 중간값")
    ap.add_argument("--ceil-grow", action="store_true", help="천장 장식이 띠 속에 묻힌 부분까지 색으로 찾아 통째로 뗀다")
    ap.add_argument("--ceil-solid", type=int, help="천장 속 무늬를 뜨는 아래 끝 줄. 주지 않으면 천장이 모든 열에서 꽉 찬 끝")
    ap.add_argument("--ceil-body", help="천장 속 무늬로 쓸 원본 가로 범위 X0:X1. 묻힌 버섯 줄기처럼 무늬에 되풀이되면 안 되는 것을 피한다")
    ap.add_argument("--seam", choices=["blend", "cut"], default="blend",
                    help="띠 양 끝 잇기: blend 섞기, cut 가장 비슷한 선에서 잘라 잇고 장식이 없는 줄에서 띠를 시작")
    args = ap.parse_args()

    rgb = np.array(Image.open(args.input).convert("RGB"))
    keyed = unkey(rgb)
    alpha = keyed[..., 3] > 128
    h, w = alpha.shape
    mid = h // 2
    # 천장: 열마다 맨 아래 불투명 행, 바닥: 열마다 맨 위 불투명 행
    ceil_bottom = np.array([np.nonzero(alpha[:mid, x])[0].max() if alpha[:mid, x].any() else 0 for x in range(w)])
    floor_top = np.array([np.nonzero(alpha[mid:, x])[0].min() + mid if alpha[mid:, x].any() else h for x in range(w)])
    c_solid = int(ceil_bottom.min())  # 이 줄 위로는 천장이 꽉 차 있다
    if args.ceil_solid is not None:
        assert args.ceil_solid <= c_solid, f"--ceil-solid는 꽉 찬 끝 {c_solid}보다 얕아야 한다"
        c_solid = args.ceil_solid
    c_line = int(np.percentile(ceil_bottom, args.ceil_pct))
    c_end = int(ceil_bottom.max()) + 4
    f_start = int(floor_top.min()) - 4
    f_line = int(np.percentile(floor_top, args.floor_pct))
    f_solid = int(floor_top.max())  # 이 줄 아래로는 바닥이 꽉 차 있다
    print(f"천장 꽉 찬 끝 {c_solid}, 경계선 {c_line}, 아래 끝 {c_end} / 바닥 위 끝 {f_start}, 경계선 {f_line}, 꽉 찬 시작 {f_solid}")

    # 테두리 띠와 속 무늬는 한 번에 좌우를 이어 같은 열에서 자른다. 게임은 속 무늬를 원본에서의 깊이에 맞춰 띠 뒤에 깔아,
    # 띠가 흐려지는 자리 뒤로 같은 그림이 이어진다. 따로 이으면 무늬가 어긋나 블록이 두 겹으로 겹쳐 보인다
    join = seamless_cut if args.seam == "cut" else seamless
    floor_cut = f_solid + 70
    ceil_all = join(keyed[0:c_end], OVERLAP)
    floor_all = join(keyed[f_start:h], OVERLAP)
    if args.seam == "cut":
        _, cx0 = roll_clear(ceil_all, c_line, up=False)
        _, fx0 = roll_clear(floor_all[:floor_cut - f_start], f_line - f_start, up=True)
        ceil_all = np.roll(ceil_all, -cx0, axis=1)
        floor_all = np.roll(floor_all, -fx0, axis=1)
        print(f"띠 시작 줄 천장 {cx0}, 바닥 {fx0}")
    ceil_edge = fade(ceil_all.copy(), 14, top=True)
    floor_edge = fade(floor_all[:floor_cut - f_start].copy(), 18, top=False)
    # 속 무늬: 띠가 꽉 찬 곳에서 조금 더 안쪽부터 잘라 위아래로 잇는다.
    # 천장은 c_body_end 줄 위, 바닥은 f_body_start 줄 아래. tile_vertical이 위 18줄을 떼므로 바닥 무늬 첫 줄은 그 18줄 아래다
    c_body_end = c_solid - 10
    f_body_start = f_solid + 30
    if args.ceil_body:
        # 원본의 다른 가로 범위에서 뜬 무늬라 띠와 열이 맞지 않는다. 띠가 흐려지는 맨 위에서만 보인다
        a, b = (int(v) for v in args.ceil_body.split(":"))
        ceil_body = tile_vertical(join(keyed[0:c_body_end, a:b], OVERLAP), 18)
    else:
        ceil_body = tile_vertical(ceil_all[0:c_body_end].copy(), 18)
    floor_body = tile_vertical(floor_all[f_body_start - f_start:].copy(), 18)
    ceil_body[..., 3] = 255
    floor_body[..., 3] = 255
    # 키 큰 장식을 떼어 낸다
    ceil_tall = args.tall if args.ceil_tall is None else args.ceil_tall
    floor_decor = split_decor(floor_edge, f_line - f_start, up=True, tall=args.tall, cut_gap=args.cut)
    ceil_decor = split_decor(ceil_edge, c_line, up=False, tall=ceil_tall, cut_gap=args.cut,
                             body=ceil_body if args.ceil_grow else None)
    print(f"장식 바닥 {len(floor_decor)}개, 천장 {len(ceil_decor)}개")

    imgs = {
        "ceilEdge": shrink(to_img(ceil_edge), K),
        "ceilBody": shrink(to_img(ceil_body), K),
        "floorEdge": shrink(to_img(floor_edge), K),
        "floorBody": shrink(to_img(floor_body), K),
    }
    anchors = {
        "ceilEdge": [0, round(c_line * K)],
        "floorEdge": [0, round((f_line - f_start) * K)],
    }
    # 장식: 바닥은 아래 가운데, 천장은 위 가운데가 기준점. dy는 경계선에서 장식 끝까지, res 픽셀
    decor = {"floor": [], "ceil": []}
    for kind, lst, lip in (("floor", floor_decor, f_line - f_start), ("ceil", ceil_decor, c_line)):
        for i, (spr, cx, yend) in enumerate(lst):
            name = f"decor_{kind}{i}"
            im = shrink(to_img(spr), K)
            imgs[name] = im
            anchors[name] = [im.width // 2, im.height if kind == "floor" else 0]
            dy = (lip - yend) if kind == "floor" else (yend - lip)
            decor[kind].append({"name": name, "x": round(cx * K, 1), "dy": round(dy * K, 1)})

    # 지금 아틀라스의 작은 입자 그림을 옮겨 싣는다. res가 1440이면 그대로, res가 없는 640 기준 임시 그림이면 2.25배
    folder = ROOT / "public" / "assets" / "world" / args.theme
    old_def = json.loads((folder / "tiles.json").read_text(encoding="utf-8"))
    old_img = Image.open(folder / old_def["image"]).convert("RGBA")
    old_k = RES / old_def["res"] if "res" in old_def else RES / 640
    part = old_def["animations"].get("particle")
    particle_frames = []
    if part:
        for fr in part["frames"]:
            x, y, fw, fh = fr
            crop = old_img.crop((x, y, x + fw, y + fh))
            particle_frames.append(crop.resize((round(fw * old_k), round(fh * old_k)), Image.Resampling.NEAREST))

    # 세로로 쌓아 한 장에
    order = ["ceilEdge", "ceilBody", "floorEdge", "floorBody"] + [d["name"] for k in ("floor", "ceil") for d in decor[k]]
    width = max(imgs[n].width for n in order)
    height = sum(imgs[n].height + 2 for n in order) + (max((p.height for p in particle_frames), default=0) + 2)
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    anims = {}
    y = 0
    for n in order:
        im = imgs[n]
        sheet.alpha_composite(im, (0, y))
        a = {"frames": [[0, y, im.width, im.height]]}
        if n in anchors:
            a["anchor"] = anchors[n]
        anims[n] = a
        y += im.height + 2
    if particle_frames:
        x = 0
        frames = []
        for p in particle_frames:
            sheet.alpha_composite(p, (x, y))
            frames.append([x, y, p.width, p.height])
            x += p.width + 2
        anims["particle"] = {"frames": frames, "fps": part.get("fps", 3), "anchor": [round(v * old_k) for v in part.get("anchor", [4, 4])]}

    sheet.save(folder / "tiles.png")
    # 속 무늬를 깔기 시작하는 깊이, res 픽셀. 무늬 첫 줄이 원본에서 놓였던 깊이 그대로라 띠와 같은 그림이 겹친다
    body_gap = {"floor": round((f_body_start + 18 - f_line) * K, 1), "ceil": round((c_line - c_body_end) * K, 1)}
    spec = {"image": "tiles.png", "res": RES, "animations": anims, "decor": decor, "bodyGap": body_gap}
    (folder / "tiles.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    for n in order:
        print(f"  {n}: {imgs[n].width}×{imgs[n].height} 기준점 {anchors.get(n)}")
    print(f"저장 {folder / 'tiles.png'} {sheet.width}×{sheet.height}")


if __name__ == "__main__":
    main()
