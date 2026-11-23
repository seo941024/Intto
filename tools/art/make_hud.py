"""ChatGPT로 받은 HUD 부품 그림 두 장으로 레이스 화면 HUD 아틀라스를 만든다.

  art_inbox/hud_parts_v1.png   하트 둘, 빈 체력바, 체력 채움, 타이머 판, 순위 판 넷, 기술칸 둘, 진행 막대
  art_inbox/hud_digits_v1.png  숫자 0~9, 쌍점, m
출력 public/assets/ui/hud.png, hud.json. 기술 아이콘은 pack_concept.py의 icon_images를 그대로 싣는다.

부품은 모두 같은 배율 PART_K로 줄여 외곽선 굵기를 맞춘다. 비율은 바꾸지 않는다.
체력 채움은 빈 체력바 안쪽 어두운 자리에 맞춰 넣고, 게임은 체력만큼 왼쪽부터 잘라 그린다.
숫자는 크기마다 원본에서 바로 줄인다. S 순위표, M 타이머, L 거리
사용
  python tools/art/make_hud.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_doll as pd  # noqa: E402
from import_scene import unkey  # noqa: E402
from pack_concept import Packer, write_atlas, icon_images, scaled  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
UI = ROOT / "public" / "assets" / "ui"
PART_K = 0.28
DIGIT_H = {"S": 14, "M": 30, "L": 36}  # 숫자 0의 높이, 게임 픽셀
FLAG_H = 40  # 골 깃발 높이, 게임 픽셀
PART_NAMES = ["heartFull", "heartEmpty", "hpFrame", "hpFillSrc", "timerPlate",
              "rankRow1", "rankRow2", "rankRow3", "rankRow4", "slotFrame", "slotActive", "miniBar"]
DIGIT_NAMES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "colon", "m"]


def boxes(keyed, count):
    """마젠타 위에 떨어져 있는 부품의 상자. 위에서 아래 줄, 줄 안에서는 왼쪽부터"""
    m = keyed[..., 3] > 128
    small = m[::2, ::2]
    found = []
    for p in pd.pieces_of(small):
        if p.sum() < 100:
            continue
        ys, xs = np.nonzero(p)
        found.append((xs.min() * 2, ys.min() * 2, (xs.max() + 1) * 2, (ys.max() + 1) * 2))
    if len(found) != count:
        sys.exit(f"부품 수가 다름: {len(found)}개, {count}개여야 함")
    # 줄: 위 끝이 가까운 것끼리
    found.sort(key=lambda b: b[1])
    rows, cur = [], [found[0]]
    for b in found[1:]:
        if b[1] - cur[0][1] < 120:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    rows.append(cur)
    return [b for r in rows for b in sorted(r, key=lambda b: b[0])]


def crop(keyed, b, pad=4):
    x0, y0, x1, y1 = b
    h, w = keyed.shape[:2]
    a = keyed[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    return img.crop(img.getbbox())


def outside(passable):
    """테두리에서 passable 픽셀만 밟고 닿는 자리"""
    out = np.zeros_like(passable)
    out[0, :] = passable[0, :]
    out[-1, :] = passable[-1, :]
    out[:, 0] = passable[:, 0]
    out[:, -1] = passable[:, -1]
    while True:
        nxt = pd.dilate(out) & passable
        if (nxt == out).all():
            return out
        out = nxt


def hp_parts(frame, fill):
    """빈 체력바 안쪽 어두운 자리와, 채움 그림의 외곽선 안쪽"""
    fa = np.array(frame).astype(float)
    op = fa[..., 3] > 128
    dark = pd.lum(fa) < 80
    inner = op & dark & ~outside(~op | dark)
    ya, xa = np.nonzero(inner)
    ibox = (xa.min(), ya.min(), xa.max() + 1, ya.max() + 1)

    la = np.array(fill).astype(float)
    lop = la[..., 3] > 128
    ldark = pd.lum(la) < 80
    linner = lop & ~outside(~lop | ldark)
    yb, xb = np.nonzero(linner)
    fbox = (xb.min(), yb.min(), xb.max() + 1, yb.max() + 1)
    body = np.array(fill).copy()
    body[~linner] = 0
    body = Image.fromarray(body, "RGBA").crop(fbox)
    mask = Image.fromarray((inner * 255).astype(np.uint8), "L").crop(ibox)
    return ibox, body, mask


def tint(img, dark, light):
    """밝기를 지키며 두 색 사이로 다시 칠한다"""
    a = np.array(img).astype(float)
    lum = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2])[..., None] / 255
    a[..., :3] = np.array(dark) + (np.array(light) - np.array(dark)) * lum
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def fit_fill(frame, fill):
    """채움 그림을 틀 안쪽 어두운 자리 크기로 맞추고, 그 모양 밖은 지운다. 자리와 그림을 돌려준다"""
    ibox, body, mask = hp_parts(frame, fill)
    fx, fy = round(ibox[0] * PART_K), round(ibox[1] * PART_K)
    fw, fh = round((ibox[2] - ibox[0]) * PART_K), round((ibox[3] - ibox[1]) * PART_K)
    out = body.convert("RGBa").resize((fw, fh), Image.Resampling.LANCZOS).convert("RGBA")
    m = np.array(mask.resize((fw, fh), Image.Resampling.LANCZOS)).astype(float) / 255
    fa = np.array(out).astype(float)
    fa[..., 3] *= m
    return [fx, fy, fw, fh], Image.fromarray(np.clip(fa, 0, 255).astype(np.uint8), "RGBA")


def red(img):
    a = np.array(img).astype(float)
    lum = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2])[..., None] / 255
    a[..., :3] = np.array([150, 30, 50]) + (np.array([255, 140, 140]) - np.array([150, 30, 50])) * lum
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def main():
    parts_k = unkey(np.array(Image.open(INBOX / "hud_parts_v1.png").convert("RGB")))
    digits_k = unkey(np.array(Image.open(INBOX / "hud_digits_v1.png").convert("RGB")))
    parts = {n: crop(parts_k, b) for n, b in zip(PART_NAMES, boxes(parts_k, len(PART_NAMES)))}
    digits = {n: crop(digits_k, b) for n, b in zip(DIGIT_NAMES, boxes(digits_k, len(DIGIT_NAMES)))}

    p = Packer(1024)
    anims = {}

    def put(key, img):
        anims[key] = {"frames": [p.add(img)]}
        return img

    for n in PART_NAMES:
        if n != "hpFillSrc":
            put(n, scaled(parts[n], PART_K))

    # 체력 채움: 빈 체력바 안쪽 자리 크기로 맞추고 그 모양 밖은 지운다
    hp_rect, fill = fit_fill(parts["hpFrame"], parts["hpFillSrc"])
    put("hpFill", fill)
    put("hpFillLow", red(fill))
    # 진행 막대 채움: 같은 채움 그림을 노랗게 칠해 진행 막대 안쪽에 맞춘다
    mini_rect, mfill = fit_fill(parts["miniBar"], parts["hpFillSrc"])
    put("miniFill", tint(mfill, (214, 120, 20), (255, 236, 120)))
    # 골 깃발: 받은 그림이 있으면 펄럭이는 프레임으로 싣는다
    flag_src = INBOX / "hud_goal_v1.png"
    if flag_src.exists():
        fk = unkey(np.array(Image.open(flag_src).convert("RGB")))
        from import_scene import pieces
        frames = [Image.fromarray(np.clip(p, 0, 255).astype(np.uint8), "RGBA") for p in pieces(fk, min_gap=20) if (p[..., 3] > 128).sum() > 500]
        fh = max(f.height for f in frames)
        fwid = max(f.width for f in frames)
        rects = []
        for f in frames[:4]:
            c = Image.new("RGBA", (fwid, fh), (0, 0, 0, 0))
            c.alpha_composite(f, (0, fh - f.height))
            rects.append(p.add(scaled(c, FLAG_H / fh)))
        anims["goalFlag"] = {"frames": rects, "fps": 8, "anchor": [0, rects[0][3]]}

    # 숫자 세 크기. 모두 0의 높이를 기준으로 같은 배율
    ref_h = digits["0"].height
    for size, h in DIGIT_H.items():
        k = h / ref_h
        for n, img in digits.items():
            put(f"digit{size}_{n}", scaled(img, k))

    icons = icon_images()
    for name, img in icons.items():
        put(f"icon_{name}", img)

    # 그리는 자리: 타이머 판의 글자 가운데, 순위 판의 구슬 가운데
    tp = parts["timerPlate"]
    rk = parts["rankRow1"]
    # 타이머 숫자 칸: 판 오른쪽의 밝은 안쪽 줄들의 가운데
    tp_s = np.array(scaled(tp, PART_K)).astype(float)
    lum = 0.3 * tp_s[..., 0] + 0.59 * tp_s[..., 1] + 0.11 * tp_s[..., 2]
    rows = np.nonzero(((tp_s[..., 3] > 128) & (lum > 190))[:, round(tp_s.shape[1] * 0.45):].any(1))[0]
    extra = {
        "hpFillRect": hp_rect,
        "miniFillRect": mini_rect,
        "timerTextY": round((rows.min() + rows.max() + 1) / 2 / tp_s.shape[0], 3),
        "timerTextX": round(0.665, 3),
        "rankBadge": [round(rk.height * 0.5 * PART_K), round(rk.height * 0.5 * PART_K)],
    }
    backup = ROOT / "art_inbox" / "out" / "placeholder_backup" / "ui"
    backup.mkdir(parents=True, exist_ok=True)
    for n in ("hud.png", "hud.json"):
        if not (backup / n).exists() and (UI / n).exists():
            (backup / n).write_bytes((UI / n).read_bytes())
    write_atlas(UI, "hud", p, anims, extra)
    for n in ["heartFull", "hpFrame", "timerPlate", "rankRow1", "slotFrame", "slotActive", "miniBar", "hpFill", "digitS_0", "digitM_0", "digitL_0"]:
        print(f"  {n}: {anims[n]['frames'][0][2]}×{anims[n]['frames'][0][3]}")
    print(f"  체력 채움 자리 {extra['hpFillRect']}, 타이머 판 원본 {tp.size}")


if __name__ == "__main__":
    main()
