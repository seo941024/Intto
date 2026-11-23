"""시안 그림체로 다시 그린 캐릭터 한 장에서 게임용 캐릭터 폴더를 만든다.

입력은 마젠타 배경 위에 나는 자세, 맞은 자세, 유령 자세 세 개가 가로로 놓인 그림이다.
  날갯짓   나는 자세의 몸은 고정하고 날개 조각만 뿌리를 축으로 돌려 4프레임을 만든다
           몸은 날갯짓에 맞춰 위아래로 살짝 오르내리고, 다리는 한 박자 늦게 따라온다
  날개가 없는 캐릭터는 --mode bob 으로 몸 전체만 오르내린다
  --strip-left 를 주면 나는 자세 왼쪽의 속도선·연기처럼 외곽선 밖에 떠 있는 효과를 지운다
  --src-scale 을 주면 원본 그림 1픽셀을 그만큼으로 줄인다. 캐릭터끼리 픽셀 굵기를 맞출 때 쓴다
  --fly-frames 로 나는 모습 4프레임이 가로로 놓인 그림을 주면 나는 프레임은 그 그림을 쓴다
           크기는 첫 그림의 나는 자세 폭에 맞추고, 아래쪽 몸이 겹치도록 위치만 맞춘다. 맞은 모습과 유령은 첫 그림 그대로
카메라가 1.5배 당겨 보므로 res 1440으로 넣어 화면에서 1:1로 그려지게 한다.
출력 public/assets/characters/<id>/sheet.png, sprite.json. 대기실 초상은 make_portraits.py
사용
  python tools/art/build_hd_character.py art_inbox/mongsil_v2.webp --id mongsil --mode wings \
      --back-box 0.49,0.37
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_doll as pd  # noqa: E402
from import_scene import unkey, pieces  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
RES = 1440
# 날개는 ChatGPT 그림 원래 크기에서 돌린 뒤 줄인다. 외곽선이 또렷해야 날개 조각이 깔끔하게 떨어진다


def to_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def resize(img, k):
    return img.convert("RGBa").resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS).convert("RGBA")


def binarize(a):
    a = a.copy()
    a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
    a[a[..., 3] == 0] = 0
    return a


def strip_left(a):
    """줄마다 맨 왼쪽 어두운 외곽선보다 왼쪽에 있는 픽셀을 지운다. 몸 뒤에 떠 있는 속도선과 연기가 빠진다"""
    a = a.copy()
    dark = (a[..., 3] > 128) & (pd.lum(a) < 90)
    for y in range(a.shape[0]):
        xs = np.nonzero(dark[y])[0]
        if len(xs):
            a[y, :xs[0]] = 0
        else:
            a[y] = 0
    ys = np.nonzero((a[..., 3] > 8).any(1))[0]
    xs = np.nonzero((a[..., 3] > 8).any(0))[0]
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def pad(a, p):
    out = np.zeros((a.shape[0] + 2 * p, a.shape[1] + 2 * p, 4), dtype=np.uint8)
    out[p:-p, p:-p] = a
    return out


def wing_masks(f, back_box):
    """앞날개: 왼쪽 위의 가장 큰 외곽선 조각. 뒷날개: 몸과 붙어 있으면 back_box 안의 털 부분을 잘라 쓴다"""
    comps, outline, _ = pd.components(f)
    a = f[..., 3] > 0
    ys, xs = np.nonzero(a)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    W, H = x1 - x0 + 1, y1 - y0 + 1
    cands = []
    for pts in comps:
        py, px = pts[:, 0], pts[:, 1]
        if len(pts) < 50:
            continue
        if px.mean() - x0 < W * 0.35 and py.min() - y0 < H * 0.5:
            cands.append(pts)
    cands.sort(key=len, reverse=True)
    front = np.zeros(a.shape, dtype=bool)
    if cands:
        front[cands[0][:, 0], cands[0][:, 1]] = True
    back = np.zeros(a.shape, dtype=bool)
    if back_box:
        bx, by = back_box
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        inner = a & ~outline & ~front
        c = f[..., :3].astype(int)
        orange = (c[..., 0] - c[..., 2]) > 40  # 뿔처럼 주황빛은 날개가 아니다
        back = inner & ~orange & (xx < x0 + W * bx) & (yy < y0 + H * by)
    grow = lambda m: (pd.dilate(m) & outline) | m
    return grow(front), grow(back)


def rotate_piece(f, mask, root, angle, outline_color, ring_px):
    """날개 속살을 뿌리 기준으로 돌리고, 원본 외곽선 두께만큼 새 외곽선을 두른다"""
    a = f[..., 3] > 0
    inner = mask & a & (pd.lum(f.astype(float)) >= 90)
    src = np.zeros_like(f)
    src[inner] = f[inner]
    rot = np.array(Image.fromarray(src).rotate(angle, resample=Image.Resampling.NEAREST, center=(root[0] + 0.5, root[1] + 0.5)))
    rin = rot[..., 3] > 0
    # 돌리며 생긴 바늘구멍 메우기
    n = sum(np.roll(np.roll(rin, dy, 0), dx, 1).astype(int) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    holes = ~rin & (n >= 5)
    for y, x in zip(*np.nonzero(holes)):
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if rin[y + dy, x + dx]:
                rot[y, x] = rot[y + dy, x + dx]
                break
    rin = rot[..., 3] > 0
    grown = rin.copy()
    for _ in range(ring_px):
        grown = pd.dilate(grown)
    out = rot.copy()
    out[grown & ~rin] = outline_color
    return out


def clean_orphans(f, reach=2):
    """주변에 속살이 하나도 없는 어두운 외곽선 픽셀을 지운다. 날개가 떠난 자리에 남는 선"""
    a = f[..., 3] > 0
    dark = a & (pd.lum(f.astype(float)) < 90)
    inner = a & ~dark
    near = inner.copy()
    for _ in range(reach):
        near = pd.dilate(near)
    out = f.copy()
    out[dark & ~near] = 0
    return out


def layer_dist(src, valid, maxd):
    """src에서 출발해 valid 픽셀만 따라 한 칸씩 넓혀 간 거리. maxd 넘으면 큰 값"""
    d = np.full(src.shape, 10**6, dtype=np.int32)
    cur = src.copy()
    d[cur] = 0
    for i in range(1, maxd + 1):
        nxt = pd.dilate(cur) & valid & (d == 10**6)
        if not nxt.any():
            break
        d[nxt] = i
        cur |= nxt
    return d


def split_outline(f, front, back, ring_px):
    """외곽선 픽셀을 가장 가까운 덩어리 몫으로 나눈다. 앞날개와 붙은 외곽선은 앞날개가 가져간다"""
    a = f[..., 3] > 0
    dark = a & (pd.lum(f.astype(float)) < 90)
    fi = front & a & ~dark
    bi = back & a & ~dark
    body_i = a & ~dark & ~fi & ~bi
    reach = dark | fi | bi | body_i
    df = layer_dist(fi, dark, ring_px)
    db = layer_dist(bi, dark, ring_px)
    dy = layer_dist(body_i, dark, ring_px)
    bias = max(1, ring_px // 2)
    f_dark = dark & (df <= ring_px) & (df <= np.minimum(db, dy) + bias)
    b_dark = dark & ~f_dark & (db <= ring_px) & (db <= dy)
    return fi | f_dark, bi | b_dark


def wing_piece(f, keep):
    out = np.zeros_like(f)
    out[keep] = f[keep]
    return out


def rotate_smooth(piece, root, angle):
    """알파를 곱한 상태로 부드럽게 돌린다. 원래 외곽선이 그대로 따라 돌아 새로 그린 티가 나지 않는다"""
    img = Image.fromarray(piece, "RGBA").convert("RGBa")
    rot = img.rotate(angle, resample=Image.Resampling.BICUBIC, center=(root[0] + 0.5, root[1] + 0.5))
    return rot.convert("RGBA")


def flap_frames(f, front, back, angles, back_amp, bob, legs_px, front_margin=8, reach=8, ring_px=6):
    a = f[..., 3] > 0
    fpart, bpart = split_outline(f, front, back, ring_px)
    # 몸에서 날개와 날개 몫 외곽선을 뺀다. 몸 속살에 더 가까운 외곽선은 몸에 남는다
    body = f.copy()
    body[fpart | bpart] = 0
    body = clean_orphans(body, reach)
    legs = pd.leg_inner(body, None) if legs_px else np.zeros(a.shape, dtype=bool)
    pieces_ = []
    for keep, mask, amp in ((bpart, back, back_amp), (fpart, front, 1.0)):
        if not mask.any():
            continue
        ys, xs = np.nonzero(mask)
        k = np.argmax(xs + ys)
        pieces_.append((wing_piece(f, keep), (xs[k], ys[k]), amp))
    rx = None
    if front.any():
        ys, xs = np.nonzero(front)
        rx = xs[np.argmax(xs + ys)] - front_margin
    out = []
    for i, ang in enumerate(angles):
        # 몸이 가장 높이 뜬 프레임에서 다리가 한 박자 늦게 따라오며 늘어난다
        fb = pd.dangle(body, legs, legs_px if bob[i] > 0 else 0)
        canvas = Image.fromarray(fb, "RGBA")
        for piece, root, amp in pieces_:
            canvas.alpha_composite(rotate_smooth(piece, root, ang * amp))
        if rx is not None:
            # 날개 뿌리보다 오른쪽의 뿔과 머리는 날개 앞에 오도록 몸을 다시 덮는다
            front_part = fb.copy()
            front_part[:, : rx + 1] = 0
            canvas.alpha_composite(Image.fromarray(front_part, "RGBA"))
        out.append(pd.shift_y(np.array(canvas), -bob[i]))
    return out


def body_center(frame):
    a = frame[..., 3] > 0
    ys, xs = np.nonzero(a)
    cut = ys.min() + int((ys.max() - ys.min()) * 0.4)
    sel = ys >= cut
    return int(round(xs[sel].mean())), int(round((ys[sel].min() + ys.max()) / 2))


def align_to(ref, img):
    """아래쪽 몸통 실루엣이 가장 많이 겹치도록 옮긴다"""
    ra = ref[..., 3] > 0
    ia = img[..., 3] > 0
    h = ra.shape[0]
    cut = int(h * 0.45)
    best = (-1e9, 0, 0)
    for dy in range(-14, 15):
        for dx in range(-14, 15):
            m = np.roll(np.roll(ia, dy, 0), dx, 1)
            s = (m[cut:] & ra[cut:]).sum() - 0.5 * (m[cut:] ^ ra[cut:]).sum()
            if s > best[0]:
                best = (s, dx, dy)
    _, dx, dy = best
    return np.roll(np.roll(img, dy, 0), dx, 1)


def center_in(img, fw, fh):
    """프레임 가운데에 놓는다"""
    c = np.zeros((fh, fw, 4), dtype=np.uint8)
    h, w = img.shape[:2]
    x0, y0 = (fw - w) // 2, (fh - h) // 2
    c[max(0, y0):max(0, y0) + min(h, fh), max(0, x0):max(0, x0) + min(w, fw)] = img[:min(h, fh), :min(w, fw)]
    return c


def place(a, fw, fh, cx, cy):
    """그림의 몸통 중심 cx, cy가 프레임 가운데 아래쪽에 오도록 놓는다"""
    out = np.zeros((fh, fw, 4), dtype=np.uint8)
    ox, oy = fw // 2 - cx, round(fh * 0.6) - cy
    h, w = a.shape[:2]
    sx0, sy0 = max(0, -ox), max(0, -oy)
    dx0, dy0 = max(0, ox), max(0, oy)
    ww = min(w - sx0, fw - dx0)
    hh = min(h - sy0, fh - dy0)
    out[dy0:dy0 + hh, dx0:dx0 + ww] = a[sy0:sy0 + hh, sx0:sx0 + ww]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--id", required=True)
    ap.add_argument("--mode", choices=["wings", "bob"], default="wings")
    ap.add_argument("--width", type=int, default=78, help="나는 자세 폭, res 1440 그림 픽셀. 화면에서 이만큼 보인다")
    ap.add_argument("--back-box", default=None, help="뒷날개를 몸에서 잘라 낼 범위, 그림 폭·높이 비율 x,y")
    ap.add_argument("--rotate", default="-26,-9,14,-9")
    ap.add_argument("--back-amp", type=float, default=0.7)
    ap.add_argument("--bob", default="-1,0,1,0", help="프레임마다 몸이 뜨는 픽셀, 최종 크기 기준")
    ap.add_argument("--legs", type=int, default=1)
    ap.add_argument("--hit-radius", type=int, default=12)
    ap.add_argument("--frame", default="112x96")
    ap.add_argument("--strip-left", action="store_true")
    ap.add_argument("--src-scale", type=float, default=None, help="원본 1픽셀을 이만큼으로 줄인다. 주면 --width 대신 쓴다")
    ap.add_argument("--fly-frames", default=None, help="나는 모습 4프레임 그림. 주면 나는 프레임을 이 그림으로 만든다")
    args = ap.parse_args()

    keyed = unkey(np.array(Image.open(args.input).convert("RGB")))
    poses = pieces(keyed, min_gap=20)
    if len(poses) < 3:
        sys.exit(f"자세 3개를 찾지 못함: {len(poses)}개")
    poses = poses[:3]
    if args.strip_left:
        poses[0] = strip_left(poses[0])
    poses = [to_img(p) for p in poses]
    k = args.src_scale or args.width / poses[0].width
    fw, fh = (int(v) for v in args.frame.lower().split("x"))
    bob = [int(v) for v in args.bob.split(",")]
    angles = [float(v) for v in args.rotate.split(",")]

    # 나는 자세: 원래 크기에서 날개를 돌린 뒤 최종 크기로 줄인다
    work_k = 1 / k  # 최종 1픽셀이 원본에서 차지하는 픽셀
    work = pad(binarize(np.array(poses[0])), 80)
    wbob = [round(b * work_k) for b in bob]
    if args.mode == "wings":
        bb = tuple(float(v) for v in args.back_box.split(",")) if args.back_box else None
        front, back = wing_masks(work, bb)
        print(f"앞날개 {int(front.sum())}픽셀, 뒷날개 {int(back.sum())}픽셀, 원본 배율 {work_k:.2f}")
        # 원본 외곽선 두께가 최종 1.5픽셀쯤이라, 그 두 배 안에 속살이 없는 외곽선만 떠다니는 선으로 본다
        fly_work = flap_frames(work, front, back, angles, args.back_amp, wbob, round(work_k) if args.legs else 0,
                               front_margin=round(work_k * 2), reach=round(work_k * 3), ring_px=round(work_k * 1.4))
    else:
        fly_work = [pd.shift_y(work, -b) for b in wbob]
    fly = [np.array(resize(to_img(f), k)) for f in fly_work]
    if args.fly_frames:
        seq = pieces(unkey(np.array(Image.open(args.fly_frames).convert("RGB"))), min_gap=20)
        seq = [s for s in seq if (s[..., 3] > 128).sum() > 500]  # 가장자리 티끌은 빼고
        if len(seq) < 4:
            sys.exit(f"나는 프레임 4개를 찾지 못함: {len(seq)}개")
        seq = [to_img(s) for s in seq[:4]]
        kf = k * poses[0].width / float(np.median([s.width for s in seq]))
        fly = [np.array(resize(to_img(binarize(np.array(s))), kf)) for s in seq]
        print(f"나는 프레임 그림 배율 {kf / k:.3f}")

    hurt = np.array(resize(poses[1], k))
    ghost = np.array(resize(poses[2], k))
    # 몸통 중심은 날개를 펴지 않은 2번째 프레임 기준
    ref = fly[1]
    cx, cy = body_center(ref)
    if args.fly_frames:
        # 따로 그린 프레임은 2번째 프레임에 아래쪽 몸을 맞춘 뒤 몸을 살짝 오르내린다
        ref_placed = place(ref, fw, fh, cx, cy)
        frames = [ref_placed if i == 1 else align_to(ref_placed, center_in(f, fw, fh)) for i, f in enumerate(fly)]
        frames = [pd.shift_y(f, -b) for f, b in zip(frames, bob)]
    else:
        frames = [place(f, fw, fh, cx, cy) for f in fly]
    ref_placed = frames[1]

    def placed_like(img):
        return align_to(ref_placed, center_in(img, fw, fh))

    hurt_f = placed_like(hurt)
    ghost_f = placed_like(ghost)
    ghost_f2 = np.roll(ghost_f, -1, 0)  # 유령은 1픽셀 위아래로 둥실
    frames += [hurt_f, ghost_f, ghost_f2]

    ax, ay = fw // 2, round(fh * 0.6)
    anims = {
        "fly": {"frames": [0, 1, 2, 3], "fps": 10, "anchor": [ax, ay]},
        "boost": {"frames": [0, 1, 2, 3], "fps": 18, "anchor": [ax, ay]},
        "hurt": {"frames": [4], "fps": 1, "anchor": [ax, ay]},
        "ghost": {"frames": [5, 6], "fps": 4, "anchor": [ax, ay]},
    }
    out = ROOT / "public" / "assets" / "characters" / args.id
    out.mkdir(parents=True, exist_ok=True)
    backup = ROOT / "art_inbox" / "out" / "placeholder_backup" / "characters" / args.id
    if not backup.exists():
        backup.mkdir(parents=True)
        for n in ("sheet.png", "sprite.json", "portrait.png"):
            if (out / n).exists():
                (backup / n).write_bytes((out / n).read_bytes())
    sheet = np.concatenate(frames, axis=1)
    Image.fromarray(sheet).save(out / "sheet.png")
    spec = {"image": "sheet.png", "res": RES, "frameWidth": fw, "frameHeight": fh, "hitRadius": args.hit_radius, "animations": anims}
    if (out / "trail.json").exists():
        spec["trail"] = "trail.json"
    (out / "sprite.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    # 대기실 초상은 make_portraits.py가 흰 테두리 얼굴로 따로 만든다
    print(f"{args.id}: 프레임 {len(frames)}개 {fw}×{fh}, 기준점 ({ax}, {ay}), 나는 자세 폭 {fly[1].shape[1]}")


if __name__ == "__main__":
    main()
