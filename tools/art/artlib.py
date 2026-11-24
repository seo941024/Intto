"""그림 도구가 함께 쓰는 작은 함수.

  unkey     마젠타 배경을 투명으로 바꾼다
  key_crop  마젠타 바탕 그림 파일을 열어 정한 자리를 잘라 배경을 걷고, 그림이 있는 자리만 남긴다
  crop_box  마젠타를 걷은 배열에서 상자 자리를 여유를 두고 잘라, 그림이 있는 자리만 남긴다
  shrink    알파를 곱한 상태로 LANCZOS로 줄인다
  to_img    실수 배열을 RGBA 그림으로
  lum       밝기
  dilate    참·거짓 판을 둘레로 넓힌다
직접 돌리지 않고 다른 도구가 가져다 쓴다.
"""
import numpy as np
from PIL import Image

MAGENTA = np.array([255, 0, 255], dtype=float)


def unkey(rgb):
    """마젠타 배경을 투명으로. 경계의 반투명 픽셀은 마젠타 섞인 만큼 색을 되돌린다"""
    a = rgb.astype(float)
    dist = np.abs(a - MAGENTA).sum(-1)
    alpha = np.clip((dist - 70) / 150, 0, 1)
    safe = np.maximum(alpha, 1e-3)[..., None]
    col = (a - (1 - alpha[..., None]) * MAGENTA) / safe
    out = np.zeros(rgb.shape[:2] + (4,), dtype=float)
    out[..., :3] = np.clip(col, 0, 255)
    out[..., 3] = alpha * 255
    return out


def to_img(a):
    """실수 배열을 0~255로 잘라 RGBA 그림으로 만든다"""
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def crop_box(keyed, box, pad=0):
    """마젠타를 걷은 배열에서 box에 pad만큼 여유를 두고 잘라, 그림이 있는 자리만 남긴다. box는 x0, y0, x1, y1"""
    x0, y0, x1, y1 = box
    img = to_img(keyed[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad])
    return img.crop(img.getbbox())


def key_crop(path, box=None):
    """마젠타 바탕 그림 파일을 열어 box 자리만 잘라 배경을 걷고, 그림이 있는 자리만 남긴다. box는 x0, y0, x1, y1"""
    img = Image.open(path).convert("RGB")
    if box:
        img = img.crop(box)
    out = to_img(unkey(np.asarray(img)))
    return out.crop(out.getbbox())


def shrink(img, k):
    """알파를 곱한 상태로 줄여 가장자리에 배경색이 번지지 않게 한다. 폭과 높이는 1픽셀 밑으로 내려가지 않는다"""
    w = max(1, round(img.width * k))
    h = max(1, round(img.height * k))
    return img.convert("RGBa").resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")


def lum(px):
    """밝기. 초록에 가장 무게를 둔다"""
    return 0.3 * px[..., 0] + 0.59 * px[..., 1] + 0.11 * px[..., 2]


def dilate(m, r=1):
    """참인 칸을 가로세로 대각선으로 r칸 넓힌다. 판 끝은 반대쪽 끝과 이어진다"""
    g = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            g |= np.roll(np.roll(m, dy, 0), dx, 1)
    return g
