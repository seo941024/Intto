"""변환한 AI 프레임 시트로 게임용 캐릭터 폴더를 만든다.

입력은 import_ai.py --sheet 결과물이다. 프레임은 모두 같은 크기의 정사각형이고 가로 한 줄이다.
  --fly    날갯짓 시트, 보통 4프레임
  --extra  가속 2, 피격 1, 유령 2 순서의 시트, 없으면 날갯짓 프레임으로 대신한다

출력 public/assets/characters/<id>/sheet.png, sprite.json, portrait.png
사용
  python tools/art/build_character.py --id mongsil --fly art_inbox/out/mongsil_flap_v1.png
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def frames_of(path):
    img = np.array(Image.open(path).convert("RGBA"))
    h = img.shape[0]
    n = img.shape[1] // h
    return [img[:, i * h:(i + 1) * h] for i in range(n)]


def carve(px, ratio):
    """도트 그림을 ratio배로 줄인다. 이웃과 가장 비슷한 줄부터 빼서 외곽선과 눈 같은 경계를 지킨다.
    ChatGPT가 그림마다 가짜 픽셀 크기를 다르게 그려서, 시트끼리 캐릭터 크기를 맞출 때 쓴다."""
    a = px.copy()
    ys, xs = np.nonzero(a[..., 3] > 0)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    tw = max(1, round(a.shape[1] * ratio))
    th = max(1, round(a.shape[0] * ratio))

    def cost(m, axis):
        m = m.astype(int)
        d = np.abs(np.diff(m, axis=axis))
        d = d[..., :3].sum(-1) + d[..., 3] * 3
        return d.sum(0) if axis == 1 else d.sum(1)

    while a.shape[1] > tw:
        c = cost(a, 1)
        i = int(c.argmin())
        a = np.delete(a, i + 1, axis=1)
    while a.shape[0] > th:
        c = cost(a, 0)
        i = int(c.argmin())
        a = np.delete(a, i + 1, axis=0)
    out = np.zeros_like(px)
    h, w = a.shape[:2]
    x0 = (px.shape[1] - w) // 2
    y0 = px.shape[0] - h - 2
    out[y0:y0 + h, x0:x0 + w] = a
    return out


def align(ref, img):
    """두 프레임의 실루엣이 가장 많이 겹치도록 옮긴다"""
    ra = ref[..., 3] > 0
    best = (-1e9, 0, 0)
    for dy in range(-10, 11):
        for dx in range(-10, 11):
            m = np.roll(np.roll(img[..., 3] > 0, dy, 0), dx, 1)
            score = (m & ra).sum() - 0.5 * (m ^ ra).sum()
            if score > best[0]:
                best = (score, dx, dy)
    _, dx, dy = best
    return np.roll(np.roll(img, dy, 0), dx, 1)


def body_center(frame):
    a = frame[..., 3] > 0
    ys, xs = np.nonzero(a)
    # 날개 때문에 위쪽이 들쭉날쭉하므로 아래 60%의 가운데를 몸통 중심으로 본다
    cut = ys.min() + int((ys.max() - ys.min()) * 0.4)
    sel = ys >= cut
    return int(round(xs[sel].mean())), int(round((ys[sel].min() + ys.max()) / 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--fly", required=True)
    ap.add_argument("--extra", default=None)
    ap.add_argument("--hit-radius", type=int, default=12)
    ap.add_argument("--extra-scale", type=float, default=1.0, help="추가 시트 캐릭터를 날갯짓 크기에 맞추는 축소 비율")
    ap.add_argument("--boost-fly", action="store_true", help="가속 동작을 빠른 날갯짓으로 만든다")
    args = ap.parse_args()

    fly = frames_of(args.fly)
    size = fly[0].shape[0]
    frames = list(fly)
    anims = {"fly": {"frames": list(range(len(fly))), "fps": 10}}
    if args.extra:
        ex = frames_of(args.extra)
        if ex[0].shape[0] != size:
            # 프레임 크기가 다르면 날갯짓 크기 캔버스로 옮긴다
            fixed = []
            for f in ex:
                c = np.zeros((size, size, 4), dtype=np.uint8)
                ys, xs = np.nonzero(f[..., 3] > 0)
                part = f[ys.min():ys.max() + 1, xs.min():xs.max() + 1][:size, :size]
                h, w = part.shape[:2]
                c[size - h - 2:size - 2, (size - w) // 2:(size - w) // 2 + w] = part
                fixed.append(c)
            ex = fixed
        if args.extra_scale != 1:
            ex = [carve(f, args.extra_scale) for f in ex]
        ref = fly[min(1, len(fly) - 1)]
        ex = [align(ref, f) for f in ex]
        base = len(frames)
        frames += ex
        names = [("boost", 2, 14), ("hurt", 1, 1), ("ghost", 2, 4)]
        i = base
        for name, count, fps in names:
            got = list(range(i, min(i + count, len(frames))))
            if got:
                anims[name] = {"frames": got, "fps": fps}
            i += count
    if args.boost_fly:
        # 가속은 같은 날갯짓을 빠르게 돌려 몸 크기가 바뀌지 않게 한다
        anims["boost"] = {"frames": list(range(len(fly))), "fps": 18}
    # 없는 동작은 날갯짓 2번째 프레임으로 대신한다
    for name in ("boost", "hurt", "ghost"):
        anims.setdefault(name, {"frames": [min(1, len(fly) - 1)], "fps": 1})

    ax, ay = body_center(fly[min(1, len(fly) - 1)])
    for a in anims.values():
        a["anchor"] = [ax, ay]

    out = Path("public/assets/characters") / args.id
    out.mkdir(parents=True, exist_ok=True)
    sheet = np.concatenate(frames, axis=1)
    Image.fromarray(sheet).save(out / "sheet.png")
    spec = {
        "image": "sheet.png",
        "res": 960,
        "frameWidth": size,
        "frameHeight": size,
        "hitRadius": args.hit_radius,
        "animations": anims,
    }
    if (out / "trail.json").exists():
        # make_particles.py가 만든 날갯짓 부스러기를 계속 쓰도록 이름을 남긴다
        spec["trail"] = "trail.json"
    (out / "sprite.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    # 로비 카드용 초상: 몸통 중심 앞쪽 48×48
    f = fly[min(1, len(fly) - 1)]
    a = f[..., 3] > 0
    ys, xs = np.nonzero(a)
    cx = min(xs.max() - 22, max(xs.min() + 24, ax + 6))
    cy = min(ys.max() - 22, max(ys.min() + 24, (ys.min() + ys.max()) // 2))
    x0 = max(0, cx - 24)
    y0 = max(0, cy - 24)
    por = np.zeros((48, 48, 4), dtype=np.uint8)
    crop = f[y0:y0 + 48, x0:x0 + 48]
    por[: crop.shape[0], : crop.shape[1]] = crop
    Image.fromarray(por).save(out / "portrait.png")
    print(f"{args.id}: 프레임 {len(frames)}개 {size}×{size}, 몸통 중심 ({ax}, {ay}), 동작 {', '.join(anims)}")


if __name__ == "__main__":
    main()
