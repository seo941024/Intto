"""대기실 초상 다섯 개를 흰 테두리 얼굴 그림으로 만든다.

  art_inbox/hud_faces_flag_v1.png  흰 테두리 얼굴 넷. 진행 막대 얼굴과 같은 그림. make_hud.faces_and_flags로 떼어 낸다
  art_inbox/random_sheet_v1.png    흰 테두리를 두른 물음표 솜뭉치. RANDOM_BOX 자리
출력 public/assets/characters/<id>/portrait.png  캐릭터 고르기 칸, 참가자 칸, 결과표에 쓰는 96×96
네 얼굴은 한 장에 같은 크기로 그려져 왔으므로 모두 같은 배율로 줄여 그림 속 크기 차이를 그대로 둔다.
가장 넓은 얼굴이 칸에 꼭 맞는 배율이다. 랜덤은 다른 그림이라 얼굴들의 평균 높이에 맞춘다.
그림은 자르지 않고 비율을 지켜 칸 가운데에 놓는다.
사용
  python tools/art/make_portraits.py
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib import key_crop, shrink  # noqa: E402
from make_hud import faces_and_flags  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "art_inbox"
RANDOM_SRC = INBOX / "random_sheet_v1.png"
RANDOM_BOX = (128, 84, 608, 484)  # 물음표 솜뭉치가 놓인 자리: 원본 좌표 x0, y0, x1, y1
SIZE = 96
PAD = 2


def place(img, k):
    small = shrink(img, k)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.alpha_composite(small, ((SIZE - small.width) // 2, (SIZE - small.height) // 2))
    return out, small.size


def main():
    faces, _ = faces_and_flags()
    room = SIZE - 2 * PAD
    k = min(min(room / f.width, room / f.height) for f in faces.values())
    for cid, f in faces.items():
        por, size = place(f, k)
        por.save(ROOT / "public" / "assets" / "characters" / cid / "portrait.png")
        print(f"{cid}: 원본 {f.width}×{f.height} → {size[0]}×{size[1]}")

    rnd = key_crop(RANDOM_SRC, RANDOM_BOX)
    avg_h = sum(f.height for f in faces.values()) / len(faces) * k
    kr = min(avg_h / rnd.height, room / rnd.width, room / rnd.height)
    por, size = place(rnd, kr)
    por.save(ROOT / "public" / "assets" / "characters" / "random" / "portrait.png")
    print(f"random: 원본 {rnd.width}×{rnd.height} → {size[0]}×{size[1]}")


if __name__ == "__main__":
    main()
