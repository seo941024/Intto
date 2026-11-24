"""다른 그림에서 받은 천장 띠를 지형 원본에 옮겨 붙여, make_terrain에 넣을 새 지형 원본을 만든다.

구름섬 천장에 외곽선을 두른 띠는 랜덤 그림 시트 art_inbox/random_sheet_v1.png 가운데에 따로 그려져 왔다.
그 띠는 위쪽이 평평한 남색 줄로 막혀 있어 그대로 쓰면 천장 속에 가로줄이 생긴다.
  1. 받은 띠에서 위쪽 남색 줄 아래부터 아래 끝까지만 쓴다
  2. 지형 원본 맨 위의 꽉 찬 구름 줄을 그대로 두고, 그 아래에 띠를 몇 줄 섞어 이어 붙인다
  3. 바닥 띠와 그림 크기는 원본 그대로라 바닥 타일은 바뀌지 않는다
천장 속 무늬는 원본 구름 줄에서만 뜨도록 make_terrain에 --ceil-solid로 이어 붙인 줄을 넘긴다.
사용
  python tools/art/compose_ceiling.py
  python tools/art/make_terrain.py art_inbox/cloud_terrain_v2.png --theme cloud --floor-pct 80 --tall 10 --cut 4 --ceil-tall 9999 --seam cut --ceil-solid 62
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import MAGENTA  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
BASE = INBOX / "cloud_terrain_v1.webp"
STRIP = INBOX / "random_sheet_v1.png"
OUT = INBOX / "cloud_terrain_v2.png"
STRIP_ROWS = (568, 665)  # 받은 띠에서 쓰는 줄: 위쪽 남색 줄 바로 아래부터 구름 아래 끝 밑까지
KEEP = 75  # 원본 맨 위에서 그대로 두는 꽉 찬 구름 줄 수
JOIN = 62  # 띠를 붙이기 시작하는 줄. KEEP까지는 원본과 섞는다
CLEAR = 170  # 원본 천장 띠를 지우는 줄 수. 원본 천장 아래 끝보다 깊고 바닥보다 얕다


def main():
    base = np.asarray(Image.open(BASE).convert("RGB")).astype(float)
    strip = np.asarray(Image.open(STRIP).convert("RGB")).astype(float)
    assert base.shape[1] == strip.shape[1], "두 그림 폭이 같아야 한다"
    out = base.copy()
    out[KEEP:CLEAR] = MAGENTA
    band = strip[STRIP_ROWS[0]:STRIP_ROWS[1]]
    y1 = JOIN + band.shape[0]
    assert y1 <= CLEAR
    n = KEEP - JOIN
    t = np.linspace(0, 1, n)[:, None, None]
    out[JOIN:KEEP] = base[JOIN:KEEP] * (1 - t) + band[:n] * t
    out[KEEP:y1] = band[n:]
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(OUT)
    print(f"원본 {KEEP}줄 + 띠 {band.shape[0]}줄, {JOIN}줄부터 {n}줄 섞음 → {OUT}")


if __name__ == "__main__":
    main()
