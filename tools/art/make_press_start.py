"""ChatGPT로 받은 PRESS START 글자 그림을 첫 화면에 넣는다.

  art_inbox/press_start_v1.png  마젠타 바탕 위 로고풍 PRESS START 한 줄
출력 public/assets/ui/press_start.png  마젠타를 지우고 글자만 남겨 높이 HEIGHT로 줄인 그림
화면에는 CSS로 높이 48px에 그린다. 두 배 크기로 담아 고해상도 화면에서도 줄여 그린다.
사용
  python tools/art/make_press_start.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_scene import unkey  # noqa: E402
from pack_concept import scaled  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art_inbox" / "press_start_v1.png"
OUT = ROOT / "public" / "assets" / "ui" / "press_start.png"
HEIGHT = 96


def main():
    a = unkey(np.asarray(Image.open(SRC).convert("RGB")))
    # 바탕 마젠타가 고르지 않아 흐릿하게 남는 점은 지우고, 글자가 있는 자리만 잘라 쓴다
    a[a[..., 3] < 40] = 0
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    img = img.crop(img.getbbox())
    out = scaled(img, HEIGHT / img.height)
    out.save(OUT)
    print(f"원본 글자 {img.width}×{img.height} → {out.width}×{out.height}, {OUT}")


if __name__ == "__main__":
    main()
