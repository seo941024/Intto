"""날 때 나오는 작은 파티클을 한 점씩 찍어 PNG로 만든다.

10픽셀 안팎의 작은 그림은 AI가 크기를 지키지 못해서, 캐릭터 그림에서 뽑은 색으로 직접 찍는다.
  characters/<id>/trail.png, trail.json   캐릭터마다 날갯짓에 떨어지는 부스러기
  fx/particles.png, particles.json        모든 캐릭터가 같이 쓰는 가속 바람줄
사용
  python tools/art/make_particles.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "public" / "assets"


def hexc(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


# 몽실 그림에서 뽑은 색. 날개에서 떨어지는 조각이라 그늘은 날개의 푸른색을 쓴다
MONGSIL = {
    "O": hexc("#1b1433"),  # 외곽선
    "W": hexc("#fdfcf0"),  # 털
    "S": hexc("#cad3ed"),  # 날개 그늘
    "L": hexc("#bbc4e5"),  # 날개 깊은 그늘
}

# 구름 부스러기가 흩어지는 4프레임. 하트로 보이지 않게 혹을 크고 작게 엇갈려 놓는다
CRUMB = [
    [
        "...OOOO.....",
        "..OWWWWO.OO.",
        ".OWWWWWWOWWO",
        "OWWWWWWWWWWO",
        "OWWWWWWWWWSO",
        "OSWWWWWWWSSO",
        ".OSSLWWSSLO.",
        "..OOOOOOOO..",
    ],
    [
        ".OOOO.....",
        "OWWWWO.OO.",
        "OWWWWSOWWO",
        "OSWWSSOSSO",
        ".OSSLO.OO.",
        "..OOO.....",
    ],
    [
        ".OOO......",
        "OWWWO.....",
        "OWSSO..OO.",
        ".OOO..OWSO",
        ".......OO.",
    ],
    [
        ".O......",
        "OWO.....",
        ".O...O..",
        "....OSO.",
        ".....O..",
        "..S.....",
    ],
]


def grid_to_px(rows, pal):
    h = len(rows)
    w = max(len(r) for r in rows)
    px = np.zeros((h, w, 4), dtype=np.uint8)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in pal:
                px[y, x] = pal[ch]
    return px


def center_in(px, cw, ch):
    out = np.zeros((ch, cw, 4), dtype=np.uint8)
    h, w = px.shape[:2]
    y0 = (ch - h) // 2
    x0 = (cw - w) // 2
    out[y0:y0 + h, x0:x0 + w] = px
    return out


# 가속 바람줄. 흰 선 아래에 푸른 그늘을 한 줄 깔아 밝은 하늘에서도 보이게 한다
STREAK = {
    "H": hexc("#ffffff"),
    "P": hexc("#cad3ed"),
    "D": hexc("#6a7196"),
}


def streak_line(img, y, x_end, length, dashes=None, bold=False):
    """오른쪽이 굵고 왼쪽으로 가늘어지는 선. dashes가 있으면 그 구간만 남긴다. bold면 오른쪽을 두 줄로"""
    x0 = x_end - length + 1
    for x in range(x0, x_end + 1):
        if dashes and not any(a <= x <= b for a, b in dashes):
            continue
        u = (x - x0) / max(1, length - 1)
        img[y, x] = STREAK["H"] if u > 0.35 else STREAK["P"]
        under = y + 1
        if bold and u > 0.6 and x < x_end:
            img[y + 1, x] = STREAK["H"]
            under = y + 2
        if u > 0.55 and x < x_end:
            img[under, x] = STREAK["D"] if not dashes else STREAK["P"]


def make_streak():
    W, H = 40, 12
    frames = []
    # 짧은 선
    f = np.zeros((H, W, 4), dtype=np.uint8)
    streak_line(f, 1, 37, 14)
    streak_line(f, 4, 39, 22, bold=True)
    streak_line(f, 9, 35, 10)
    frames.append(f)
    # 긴 선
    f = np.zeros((H, W, 4), dtype=np.uint8)
    streak_line(f, 1, 37, 25)
    streak_line(f, 4, 39, 37, bold=True)
    streak_line(f, 9, 35, 19)
    frames.append(f)
    # 끊어지며 사라지는 선
    f = np.zeros((H, W, 4), dtype=np.uint8)
    streak_line(f, 1, 33, 18, dashes=[(16, 22), (26, 31)])
    streak_line(f, 4, 36, 30, dashes=[(7, 12), (16, 26), (30, 35)], bold=True)
    streak_line(f, 9, 31, 14, dashes=[(18, 22), (26, 29)])
    frames.append(f)
    return frames


def save_atlas(frames, folder, name, anims, extra=None):
    folder.mkdir(parents=True, exist_ok=True)
    fw = frames[0].shape[1]
    fh = frames[0].shape[0]
    sheet = np.concatenate(frames, axis=1)
    Image.fromarray(sheet).save(folder / f"{name}.png")
    spec = {"image": f"{name}.png", "res": 960, "frameWidth": fw, "frameHeight": fh, "animations": anims}
    if extra:
        spec.update(extra)
    (folder / f"{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 {folder / name}.png  {len(frames)}프레임 {fw}×{fh}")
    return sheet


def link_trail(folder):
    """게임이 부스러기 파일을 찾도록 캐릭터 sprite.json에 이름을 적는다"""
    sp = folder / "sprite.json"
    spec = json.loads(sp.read_text(encoding="utf-8"))
    spec["trail"] = "trail.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    crumbs = [center_in(grid_to_px(r, MONGSIL), 12, 12) for r in CRUMB]
    save_atlas(crumbs, ASSETS / "characters" / "mongsil", "trail",
               {"trail": {"frames": [0, 1, 2, 3], "fps": 8, "anchor": [6, 6]}},
               # 날개를 가장 깊이 내려친 3번째 날갯짓 프레임에서, 몸 기준점보다 왼쪽 앞날개 아래 끝에서 떨어뜨린다
               {"emit": {"flyFrame": 2, "at": [-26, -7], "lifeMs": 900}})
    link_trail(ASSETS / "characters" / "mongsil")
    streak = make_streak()
    save_atlas(streak, ASSETS / "fx", "particles",
               {"streak": {"frames": [0, 1, 2], "fps": 14, "anchor": [39, 6]}})


if __name__ == "__main__":
    main()
