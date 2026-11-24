"""ChatGPT로 받은 랜덤 맵 그림을 대기실 맵 고르기에 넣는다.

  art_inbox/random_sheet_v2.png  세 맵을 비스듬히 나눠 담고 가운데 물음표를 단 카드
출력 public/assets/ui/map_random.png  원본 비율 그대로, 폭 640
그림은 자르지 않고 마젠타 배경만 지운 뒤 비율을 지켜 줄인다. 랜덤 캐릭터 초상은 make_portraits.py가 만든다.
사용
  python tools/art/make_random.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import key_crop, shrink  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
MAP_SHEET = INBOX / "random_sheet_v2.png"
MAP_BOX = (700, 108, 1596, 576)  # 카드가 놓인 자리: 원본 좌표 x0, y0, x1, y1
MAP_W = 640


def main():
    card = key_crop(MAP_SHEET, MAP_BOX)
    m = shrink(card, MAP_W / card.width)
    out = ROOT / "public" / "assets" / "ui" / "map_random.png"
    m.save(out)
    print(f"랜덤 맵 {card.width}×{card.height} → {m.width}×{m.height}, {out}")


if __name__ == "__main__":
    main()
