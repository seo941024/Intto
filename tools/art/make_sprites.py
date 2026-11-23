"""인또 스프라이트 생성기 — 캐릭터·아이템·효과·HUD·로비 UI.

프로젝트 루트에서 `python tools/art/make_sprites.py`로 실행한다.
모든 그림은 이 파일 안의 문자열 격자로 손으로 찍었고, 프레임 변형만 코드로 만든다.
난수는 고정 시드라서 실행할 때마다 같은 결과가 나온다.
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets')
PREVIEW = os.path.join(HERE, '_preview')
FONT_BOLD = os.path.join(ROOT, 'node_modules', 'galmuri', 'dist', 'Galmuri11-Bold.ttf')

random.seed(20261113)

# ---------------------------------------------------------------------------
# 팔레트 — Endesga 32와 문자 이름
# ---------------------------------------------------------------------------
CM = {
    'K': '181425',  # 가장 어두운 남색 — 외곽선
    'N': '262b44',  # 짙은 남색
    'n': '3a4466',
    'g': '5a6988',
    's': '8b9bb4',
    'l': 'c0cbdc',
    'W': 'ffffff',
    'p': 'f6757a',  # 분홍
    'R': 'e43b44',  # 빨강
    'r': 'a22633',  # 짙은 빨강
    'M': 'ff0044',
    'D': '3e2731',  # 가장 어두운 갈색
    'B': '733e39',  # 짙은 갈색
    'b': 'b86f50',  # 갈색
    'f': 'c28569',
    'm': 'be4a2f',  # 녹슨 주황
    'o': 'd77643',  # 주황 갈색
    't': 'e4a672',  # 황갈
    'e': 'e8b796',  # 연한 살구
    'c': 'ead4aa',  # 크림
    'O': 'f77622',  # 주황
    'Y': 'feae34',  # 노랑 주황
    'y': 'fee761',  # 노랑
    'G': '63c74d',  # 초록
    'h': '3e8948',
    'H': '265c42',
    'T': '193c3e',
    'U': '124e89',  # 짙은 파랑
    'u': '0099db',  # 파랑
    'C': '2ce8f5',  # 하늘
    'P': '68386c',  # 보라
    'q': 'b55088',
    # 같은 계열 중간색 — 꼭 필요한 곳에만
    'w': 'fff6e0',  # 종이 밝은 크림
    'v': 'f3e6c4',  # 종이 크림
    'a': 'a8e4f5',  # 옅은 하늘
    'i': '6cc4e8',  # 중간 하늘
    'k': 'fff9c8',  # 아주 옅은 노랑 — 반짝임
}

# 안쪽 선을 그릴 때 한 단계 어두운 색
DARKER = {}
for ramp in ['Wlsgn NK'.replace(' ', ''), 'pRrD', 'yYOmBD', 'ctfbBD', 'eft', 'odmB', 'GhHT', 'CiuUN', 'aiuU',
             'qPD', 'wvctb', 'kyY']:
    for a, b in zip(ramp, ramp[1:]):
        DARKER.setdefault(a, b)
DARKER['o'] = 'm'
DARKER['m'] = 'B'
DARKER['K'] = 'K'
DARKER['D'] = 'K'
DARKER['T'] = 'K'


def rgba(c, a=255):
    if c is None:
        return (0, 0, 0, 0)
    if isinstance(c, tuple):
        return c if len(c) == 4 else c + (a,)
    h = CM.get(c, c)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


RGB2CH = {rgba(v)[:3]: k for k, v in CM.items()}


def grid(rows, cmap=None, alpha=None):
    """문자열 격자를 RGBA 그림으로 바꾼다. '.'과 ' '는 투명."""
    cmap = cmap or {}
    alpha = alpha or {}
    w = max(len(r) for r in rows)
    img = Image.new('RGBA', (w, len(rows)), (0, 0, 0, 0))
    px = img.load()
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in '. ':
                continue
            col = cmap.get(ch, ch)
            px[x, y] = rgba(col, alpha.get(ch, 255))
    return img


def blank(w, h):
    return Image.new('RGBA', (w, h), (0, 0, 0, 0))


def paste(dst, src, x, y):
    dst.alpha_composite(src, (int(x), int(y)))
    return dst


def opaque(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > 0 for x in range(w)] for y in range(h)]


def ring(mask, diag=False):
    h = len(mask)
    w = len(mask[0])
    out = [[False] * w for _ in range(h)]
    nb = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diag:
        nb += [(1, 1), (-1, 1), (1, -1), (-1, -1)]
    for y in range(h):
        for x in range(w):
            if mask[y][x]:
                continue
            for dx, dy in nb:
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and mask[yy][xx]:
                    out[y][x] = True
                    break
    return out


def darker(c):
    ch = RGB2CH.get(c[:3])
    if ch is None:
        r, g, b, a = c
        return (int(r * 0.7), int(g * 0.7), int(b * 0.75), a)
    return rgba(DARKER.get(ch, 'K'), c[3])


def compose(w, h, layers):
    """부위를 순서대로 겹친다.

    layers 항목은 (그림, x, y, 외곽선색) 또는 (그림, x, y). 외곽선색이 있으면 그 부위 둘레에
    선을 두르는데, 이미 그린 부위 위에 걸치는 선은 그 부위 색의 한 단계 어두운 색이 된다.
    그래서 겹친 부위 사이에는 검은 선 대신 부드러운 안쪽 선이 생긴다.
    """
    canvas = blank(w, h)
    for item in layers:
        img, x, y = item[0], item[1], item[2]
        ol = item[3] if len(item) > 3 else None
        inner = item[4] if len(item) > 4 else True
        layer = blank(w, h)
        paste(layer, img, x, y)
        if ol:
            m = opaque(layer)
            rg = ring(m)
            cp = canvas.load()
            for yy in range(h):
                for xx in range(w):
                    if rg[yy][xx]:
                        under = cp[xx, yy]
                        if under[3] > 0 and inner:
                            cp[xx, yy] = darker(under) if inner is True else rgba(inner)
                        elif under[3] == 0:
                            cp[xx, yy] = rgba(ol)
        canvas.alpha_composite(layer)
    return canvas


def outline(img, col='K', diag=False):
    w, h = img.size
    out = img.copy()
    rg = ring(opaque(img), diag)
    px = out.load()
    for y in range(h):
        for x in range(w):
            if rg[y][x]:
                px[x, y] = rgba(col)
    return out


def shift(img, dx, dy):
    out = blank(*img.size)
    out.alpha_composite(img, (dx, dy)) if dx >= 0 and dy >= 0 else out.paste(img, (dx, dy), img)
    return out


def shear(img, top_dx, pivot_y, step=4):
    """윗줄을 앞으로 미는 기울이기. pivot_y 줄은 그대로, step줄마다 1픽셀."""
    w, h = img.size
    out = blank(w, h)
    for y in range(h):
        d = int(math.floor((pivot_y - y) / step)) if y < pivot_y else -int(math.floor((y - pivot_y) / (step * 2)))
        d = max(min(d, top_dx), -top_dx)
        row = img.crop((0, y, w, y + 1))
        out.paste(row, (d, y), row)
    return out


def recolor(img, mapping):
    out = img.copy()
    px = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c[3] == 0:
                continue
            ch = RGB2CH.get(c[:3])
            if ch in mapping:
                px[x, y] = rgba(mapping[ch], c[3])
    return out


def up(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def flip(img):
    return img.transpose(Image.FLIP_LEFT_RIGHT)


def save(img, *parts):
    path = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path


def save_json(obj, *parts):
    path = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json_dump(obj))
        f.write('\n')
    return path


def json_dump(obj, indent=0):
    """사람이 읽기 쉬운 JSON. 숫자 배열은 한 줄에 쓴다."""
    pad = '  ' * indent
    if isinstance(obj, dict):
        if not obj:
            return '{}'
        items = []
        for k, v in obj.items():
            items.append('%s  %s: %s' % (pad, json.dumps(k, ensure_ascii=False), json_dump(v, indent + 1)))
        return '{\n' + ',\n'.join(items) + '\n' + pad + '}'
    if isinstance(obj, list):
        if all(isinstance(v, (int, float)) for v in obj):
            return '[' + ', '.join(json.dumps(v) for v in obj) + ']'
        if all(isinstance(v, list) and all(isinstance(t, (int, float)) for t in v) for v in obj):
            return '[' + ', '.join(json_dump(v) for v in obj) + ']'
        return '[\n' + ',\n'.join(pad + '  ' + json_dump(v, indent + 1) for v in obj) + '\n' + pad + ']'
    return json.dumps(obj, ensure_ascii=False)


# 미리보기 배경
SKY_DAY = (120, 200, 240, 255)
SKY_NIGHT = (24, 20, 37, 255)


def preview_strip(frames, k, bgs=(SKY_DAY, SKY_NIGHT), gap=2):
    """프레임 목록을 낮·밤 배경 두 줄로 늘어놓은 확대 미리보기."""
    fw = max(f.width for f in frames)
    fh = max(f.height for f in frames)
    W = len(frames) * (fw + gap) + gap
    H = len(bgs) * (fh + gap) + gap
    out = Image.new('RGBA', (W, H), (60, 60, 70, 255))
    for j, bg in enumerate(bgs):
        for i, f in enumerate(frames):
            x = gap + i * (fw + gap)
            y = gap + j * (fh + gap)
            tile = Image.new('RGBA', (fw, fh), bg)
            tile.alpha_composite(f, ((fw - f.width) // 2, (fh - f.height) // 2))
            out.paste(tile, (x, y))
    return up(out, k)


def save_preview(img, name):
    os.makedirs(PREVIEW, exist_ok=True)
    img.save(os.path.join(PREVIEW, name))


# ===========================================================================
# 1. 캐릭터
# ===========================================================================
# 부위는 외곽선 없이 찍고 compose()가 부위마다 선을 두른다.

# --- 몽실: 구름 양 -----------------------------------------------------------
# 몸은 양털 뭉치 여러 개를 겹친 구름. 아래 뭉치가 앞이라서 위 뭉치에 위로 볼록한 그늘 선이 생긴다.
MONG_WOOL = [
    '................................',  # 0
    '................................',  # 1
    '................................',  # 2
    '................................',  # 3
    '................................',  # 4
    '................................',  # 5
    '...........WWWW.................',  # 6
    '..........WWWWWl................',  # 7
    '.........lWWWWWWl...............',  # 8
    '.......WWWlWlllll...............',  # 9
    '.....WWWWWlWWWWWlss.............',  # 10
    '.....WWWWlWWWWWWWls.............',  # 11
    '.....WWWlWWWWWWWWll.............',  # 12
    '.....llsWWWWWWWWWll.............',  # 13
    '....WWWlWWWWWWWWWll.............',  # 14
    '...WWWlWWWWWWWWWWlls............',  # 15
    '...WWWlWWWWWWWWWWlls............',  # 16
    '...WWlslllWWWWWWllss............',  # 17
    '...WlWWWWlWlllWssss.............',  # 18
    '....WWWWWlsWWWlWllll............',  # 19
    '....WWWWWlWWWWlllllll...........',  # 20
    '....WWWWlWWWWlWWWlllls..........',  # 21
    '....WWWWlWWWWlWWWWlls...........',  # 22
    '.....lllsWWWWWsWWWlls...........',  # 23
    '..........WWllslllls............',  # 24
    '...........lss..................',  # 25
]
# 이마 위 양털 한 뭉치 — 얼굴 위에 덮는다
MONG_TUFT = [
    '...WW....',
    '..WWWls..',
    '.WWWlWWWl',
    '.WWWlWWWl',
    '.WWWlWWWl',
    '..WWsWWls',
    '...lssss.',
]
# 짙은 얼굴, 큰 눈 두 개, 볼 홍조
MONG_FACE = [
    '...ggggg...',
    '..gsgggggg.',
    '.sggggggggg',
    'sgKKgggKKKg',
    'sgWKgggWKKg',
    'ggKKgggKKKn',
    'gguKggguKKn',
    'ggggggggggn',
    '.gpggggppgn',
    '..nggKKggn.',
    '...nnnnnn..',
]
# 맞았을 때 질끈 감은 눈
MONG_FACE_HURT = [
    '...ggggg...',
    '..gsgggggg.',
    '.sggggggggg',
    'sKgggggggKg',
    'sgKKgggKKgg',
    'gKggggggKgn',
    'ggggggggggn',
    'ggggggKKggn',
    '.gpggKrrKpn',
    '..ngggKKgn.',
    '...nnnnnn..',
]
MONG_EAR = [
    '..sgg',
    'sggnn',
    'gnn..',
]
# 구름 조각 날개 — 하늘색. 뒷날개는 한 단계 어둡게 바꿔 쓴다.
MONG_WING_UP = [
    '..aa....',
    '.aWWa...',
    'aWWWa...',
    'aWWWaa..',
    'iaWWWWa.',
    'iaaWWWa.',
    '.iaWWWWa',
    '.iiaWWWa',
    '..iiaWWa',
    '...iiaai',
    '....iii.',
]
MONG_WING_MID = [
    '..aWa.......',
    '.aWWWaaWa...',
    'aWWWWWWWWa..',
    'iaWWWWWWWWa.',
    '.iiaaWWWWWaa',
    '...iiiaaWWai',
    '......iiaaai',
    '........iii.',
]
MONG_WING_DOWN = [
    '.......aWWWa.',
    '...aaWWWWWWWa',
    '.aWWWWWWWWaai',
    'aWWWWaaaaaii.',
    'iaaaiiiiii...',
    '.iiiu.iu.....',
    '..uu.........',
]
MONG_LEGS = [
    'sg....sg',
    'gn....gn',
    'gn....gn',
    'nn....nn',
]


# --- 캐릭터 공통 -------------------------------------------------------------
GHOST_ALPHA = 185


def speed_lines(img, phase, rows):
    """가속 프레임 뒤쪽 바람 줄. rows는 (y, 길이) 목록. 실루엣 왼쪽 끝 바로 뒤에서 시작한다."""
    out = img.copy()
    px = out.load()
    w, h = img.size
    for j, (y, ln) in enumerate(rows):
        xs = [x for x in range(w) if px[x, y][3] > 0]
        if not xs:
            continue
        x_end = min(xs) - 1 - ((j + phase) % 2) * 2
        ln = ln - ((j + phase) % 2) * 2
        for k in range(ln):
            x = x_end - k
            if 0 <= x < w and px[x, y][3] == 0:
                c = 'W' if k < ln * 0.5 else 'a'
                px[x, y] = rgba(c, 235 if k < ln * 0.7 else 140)
    return out


# 유령 물결 꼬리 두 가지 — 끝이 위로 튕긴 것과 아래로 처진 것. 번갈아 보이면 살랑인다.
GHOST_TAIL_A = [
    'WWWWWWWWWWWWWllls',
    '.WWWWWWWWWWWllss.',
    '..WWWWWWWWlllss..',
    '...lWWWWWllss....',
    '....lWWWllss.....',
    '.WW..lWlss.......',
    'WWl..lls.........',
    '.llsss...........',
]
GHOST_TAIL_B = [
    'WWWWWWWWWWWWWllls',
    '.WWWWWWWWWWWllss.',
    '..WWWWWWWWlllss..',
    '....WWWWWWlss....',
    '.....WWWWlss.....',
    '....WWWlss.......',
    '..WWlls..........',
    '.Wls.............',
    'Wl...............',
]


def ghost_tail(width, phase):
    """꼬리 격자를 몸 폭에 맞춰 가로로 줄인다. 오른쪽 위 끝을 기준으로 왼쪽을 잘라 낸다."""
    g = GHOST_TAIL_A if phase == 0 else GHOST_TAIL_B
    img = grid(g)
    if width < img.width:
        # 넓은 윗부분은 왼쪽 열을 빼서 줄이고, 아래 꼬리 끝은 그대로 둔다
        cut = img.width - width
        top = img.crop((cut, 0, img.width, 3))
        bottom = img.crop((0, 3, img.width, img.height))
        out = blank(img.width, img.height)
        paste(out, bottom, 0, 3)
        paste(out, top, cut, 0)
        img = out
    return img


GHOST_MAP = {
    'W': 'W', 'k': 'W', 'y': 'W', 'w': 'W', 'v': 'W', 'c': 'W', 'a': 'W', 'l': 'a', 'e': 'a', 'p': 'a',
    'C': 'a', 'Y': 'a', 'i': 'a', 's': 'i', 't': 'i', 'f': 'i', 'O': 'i', 'R': 'i', 'o': 'i', 'g': 'a',
    'u': 'i', 'b': 'i', 'm': 'i', 'n': 'i', 'r': 'u', 'B': 'u', 'U': 'u', 'N': 'U', 'K': 'U', 'D': 'U',
}


def ghostify(img, alpha=GHOST_ALPHA, extra=None):
    """옅은 하늘색 단계로 바꾸고 반투명하게 한다. 눈동자와 외곽선만 짙은 파랑으로 남긴다."""
    m = dict(GHOST_MAP)
    m.update(extra or {})
    out = img.copy()
    px = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            ch = RGB2CH.get((r, g, b))
            c = m.get(ch)
            if c is None:
                lum = (0.3 * r + 0.55 * g + 0.15 * b) / 255
                c = 'W' if lum > 0.8 else 'a' if lum > 0.6 else 'i' if lum > 0.4 else 'u' if lum > 0.2 else 'U'
            al = {'W': alpha, 'a': alpha, 'i': alpha + 10, 'u': alpha + 25, 'U': min(255, alpha + 45)}[c]
            px[x, y] = rgba(c, al)
    return out


def char_json():
    return {
        'image': 'sheet.png',
        'frameWidth': 32,
        'frameHeight': 32,
        'hitRadius': 8,
        'animations': {
            'fly': {'frames': [0, 1, 2, 3], 'fps': 10, 'anchor': [16, 17]},
            'boost': {'frames': [4, 5], 'fps': 14, 'anchor': [16, 17]},
            'hurt': {'frames': [6], 'anchor': [16, 17]},
            'ghost': {'frames': [7, 8], 'fps': 4, 'anchor': [16, 17]},
        },
    }


def write_character(cid, frames, portrait):
    assert len(frames) == 9
    sheet = blank(32 * 9, 32)
    for i, f in enumerate(frames):
        assert f.size == (32, 32), (cid, i, f.size)
        paste(sheet, f, i * 32, 0)
    save(sheet, 'characters', cid, 'sheet.png')
    save_json(char_json(), 'characters', cid, 'sprite.json')
    assert portrait.size == (48, 48)
    save(portrait, 'characters', cid, 'portrait.png')
    return sheet


# --- 몽실 프레임 ---------------------------------------------------------------
MONG_WINGS = {
    'up': (MONG_WING_UP, 5, -1),
    'mid': (MONG_WING_MID, 1, 3),
    'down': (MONG_WING_DOWN, 0, 8),
}


def mong_layers(wing, bob, face=None, legdx=0, legs=True, wing_dx=0):
    g, wx, wy = MONG_WINGS[wing]
    wx += wing_dx
    back = recolor(grid(g), {'W': 'a', 'a': 'i', 'i': 'u'})
    y0 = 1 + bob
    L = [(back, wx + 3, wy - 1 + y0, 'N')]
    if legs:
        L.append((grid(MONG_LEGS), 10 + legdx, 23 + y0, 'N'))
    L += [(grid(MONG_WOOL), 0, y0, 'N'),
          (grid(MONG_EAR), 14, 13 + y0, 'N'),
          (grid(face or MONG_FACE), 18, 11 + y0, 'N'),
          (grid(MONG_TUFT), 15, 6 + y0, 'N'),
          (grid(g), wx, wy + y0, 'N', 'g')]
    return L


def cut_below(img, y):
    out = img.copy()
    px = out.load()
    for yy in range(y, img.height):
        for x in range(img.width):
            px[x, yy] = (0, 0, 0, 0)
    return out


def make_ghost(body, cut, x1, width, ph, ol='N', extra=None):
    """몸을 cut 줄에서 자르고 꼬리를 붙인다. x1은 꼬리 윗단의 오른쪽 끝 x."""
    body = cut_below(body, cut)
    g = blank(32, 32)
    tail = ghost_tail(width, ph)
    paste(g, tail, x1 - tail.width + 1, cut - 1)
    g.alpha_composite(body)
    g = outline(cut_below(g, 32), ol)
    return ghostify(g, extra=extra)


def build_mongsil():
    F = []
    for wing, bob, legdx in [('up', 1, 0), ('mid', 0, 0), ('down', -1, 1), ('mid', 0, 0)]:
        F.append(compose(32, 32, mong_layers(wing, bob, legdx=legdx)))
    for ph in (0, 1):
        body = compose(32, 32, mong_layers('down' if ph else 'mid', 0, legdx=-2))
        body = shear(body, 2, 22, 5)
        F.append(speed_lines(body, ph, [(9, 7), (14, 9), (19, 10), (24, 6)]))
    L = mong_layers('up', -1, face=MONG_FACE_HURT, legdx=1)
    L.append((grid(['.a.', 'aWa', 'aaa', '.a.']), 27, 6, 'N'))
    F.append(shift(compose(32, 32, L), 0, 0))
    for ph in (0, 1):
        body = compose(32, 32, mong_layers('up' if ph == 0 else 'mid', ph, legs=False))
        F.append(make_ghost(body, 21 + ph, 21, 17, ph, extra={'g': 'i', 'n': 'u'}))
    return F


# --- 깡동: 깡통 로봇 ----------------------------------------------------------
# 원통은 왼쪽 위 빛을 받는 세로 띠 명암. 뚜껑 테, 리벳 이음매, 빨간 라벨, 렌즈 눈 두 개.
KANG_CAN = [
    '...llllllllll...',  # 0  뚜껑 먼 테
    '.llssssssssssll.',  # 1
    'lsslllllllllsssg',  # 2  뚜껑 안쪽
    'WWWWWWWlllllssgg',  # 3  가까운 테
    'lWWllllllsssssgn',  # 4
    'lWWllllllsssssgn',  # 5
    'lWWllllllsssssgn',  # 6
    'lWWllllllsssssgn',  # 7
    'lWWllllllsssssgn',  # 8
    'sWlWssWssWssWsgn',  # 9  리벳 이음매
    'RppRcRRRRRRRrrrD',  # 10 라벨
    'RpcccccRRRRRrrrD',  # 11
    'RppcccRRRRRRrrrD',  # 12
    'RppcRcRRRRRRrrrD',  # 13
    'rrrrrrrrrrrrrrDD',  # 14
    'sWlWssWssWssWsgn',  # 15 리벳 이음매
    'lWWllllllsssssgn',  # 16
    '.sllllllssssssg.',  # 17
    '...sssssgggggg..',  # 18 바닥 테
]
KANG_EYE = [
    '.nnnn.',
    'nWCuun',
    'nCKKun',
    'nuKKUn',
    'nuuUUn',
    '.nnnn.',
]
KANG_EYE_FAR = [
    '.nn.',
    'nWCn',
    'nKKn',
    'nKKn',
    'nuUn',
    '.nn.',
]
KANG_EYE_HURT = [
    '.....',
    'K...K',
    '.K.K.',
    '..K..',
    '.K.K.',
]
KANG_MOUTH = ['K.K', '.K.']
# 옆구리 집게 팔 — 프로펠러 박자에 맞춰 위아래로 흔든다
KANG_ARMS = {
    'up': (['Wl...', 'lsg..', '.lsg.', '..lsg', '...ls'], -4, -4),
    'mid': (['Wls..', 'llssg', '...ls'], -4, -1),
    'down': (['...ls', '..lsg', '.lsg.', 'lsg..', 'Wl...'], -4, 0),
}
KANG_PROP = [
    [  # 옆에서 본 긴 날개
        '..OYYYYYy..yYYYYYO..',
        '.OYYYYYyy..yyYYYYYO.',
        '..OOOOOO....OOOOOO..',
    ],
    [  # 비스듬히
        '....OYYYyy..........',
        '.....OOOYy..yyYYO...',
        '..........yYYYYYYO..',
        '...........OOOOOO...',
    ],
    [  # 앞뒤로 선 날개
        '........yYYy........',
        '........OYYO........',
        '.......yYYYYy.......',
        '.......OOOOOO.......',
    ],
    [
        '..........yyYYYO....',
        '...OYYyy..yYOOO.....',
        '..OYYYYYYy..........',
        '...OOOOOO...........',
    ],
]
KANG_HUB = ['.RR.', 'RppR', 'rRRr', '.ss.', '.sg.', '.sg.']
KANG_FEET = ['gn...gn', 'sg...sg', 'gn...gn']


def kang_layers(pf, bob, eye=None, mouth=False, feet_dy=0, arm='mid'):
    y0 = 7 + bob
    ag, ax, ay = KANG_ARMS[arm]
    L = [(grid(KANG_FEET), 13, y0 + 18 + feet_dy, 'N'),
         (grid(ag), 8 + ax, y0 + 11 + ay, 'N'),
         (grid(KANG_CAN), 8, y0, 'N')]
    L += [(grid(KANG_EYE_FAR), 20, y0 + 3, 'N'), (grid(eye or KANG_EYE), 14, y0 + 3, 'N')]
    if mouth:
        L.append((grid(KANG_MOUTH), 18, y0 + 10, None))
    L += [(grid(KANG_HUB), 14, y0 - 6, 'N'), (grid(KANG_PROP[pf]), 6, y0 - 7, 'N')]
    return L


# --- 도토: 날다람쥐 ------------------------------------------------------------
DOTO_HEAD = [
    '.......Bm...',  # 0  먼 귀
    '..mo..Bmo...',  # 1
    '.mppo.mpo...',  # 2  가까운 귀, 분홍 속
    '.mppoompo...',  # 3
    '..moottttoo.',  # 4
    '..ottttttoo.',  # 5
    '.otttttoooo.',  # 6
    '.ottttKKKoo.',  # 7  큰 눈
    'otttooKWKoop',  # 8  코
    'ottoooKKKcpp',  # 9
    'ootoooeKKccc',  # 10
    '.oooooccccce',  # 11
    '.mooocccceee',  # 12
    '..mmmceeee..',  # 13
]
DOTO_BODY = [
    '.....ttttoo....',  # 0
    '...ttttttooooo.',  # 1
    '..tttooooooooom',  # 2
    '.ttoooooooooomm',  # 3
    'tooooooooooommm',  # 4
    'ooooooooommmmmm',  # 5
    'mooooommmmmmmBB',  # 6
    '.mmmmmmmmmmBBB.',  # 7
    '...mmmmmBBBB...',  # 8
]
DOTO_TAIL = [
    '.....ott....',  # 0
    '...otttto...',  # 1
    '..otttttoo..',  # 2
    '.ottttooom..',  # 3
    '.otttoommm..',  # 4
    'ottoommm....',  # 5
    'otoomm......',  # 6
    'ttoomm......',  # 7
    'ctoommm.....',  # 8
    '.ctoooommm..',  # 9
    '..cctoooooom',  # 10
    '....ccttoomm',  # 11
]
# 가까운 쪽 비막 — 위, 가운데, 아래. 앞발과 뒷발이 양 끝 모서리.
DOTO_MEM = {
    'up': [
        'tt.................',
        'ottooooooooooooott.',
        '.mooooooooooooooooc',
        '..cmmmmmmmmmmmmmcc.',
        '...ccc.cccc.ccc....',
    ],
    'mid': [
        'tt.................',
        'otoooooooooooooo.tt',
        'mooooooooooooooooot',
        '.mmmooooooooooooomc',
        '..cmmmmmmmmmmmmmmc.',
        '...cc.cccc.cccc.c..',
    ],
    'down': [
        'tt.................',
        'otoooooooooooooo...',
        'mooooooooooooooo.tt',
        'mmoooooooooooooooot',
        '.mmmooooooooooooooc',
        '..mmmmmmmmmmmmmmmc.',
        '...cmmmmmmmmmmmmc..',
        '....cc.cccc.cccc...',
    ],
}
DOTO_FAR = {
    'up': ['..tttooooo..', '.ttoooooomm.', 'tmmmmmmmmB..'],
    'mid': ['.tooooooom..', 'tmmmmmmmB...'],
    'down': None,
}

def doto_layers(m, bob, tail_dy=0, head=None):
    y0 = bob
    L = []
    far = DOTO_FAR[m]
    if far:
        L.append((recolor(grid(far), {'t': 'o', 'o': 'm', 'm': 'B'}), 10, y0 + (8 if m == 'up' else 10), 'D'))
    L += [(grid(DOTO_TAIL), 0, y0 + 6 + tail_dy, 'D'),
          (grid(DOTO_BODY), 8, y0 + 11, 'D'),
          (grid(head or DOTO_HEAD), 17, y0 + 4, 'D')]
    mg = grid(DOTO_MEM[m])
    L.append((mg, 6, y0 + 16, 'D'))
    return L



DOTO_HEAD_HURT = [row for row in DOTO_HEAD]
DOTO_HEAD_HURT[7] = '.ottttKoooo.'
DOTO_HEAD_HURT[8] = 'otttoooKKoop'
DOTO_HEAD_HURT[9] = 'ottoooKoocpp'
DOTO_HEAD_HURT[10] = 'ootoooeoBccc'


# --- 팔랑: 살아 있는 종이비행기 ------------------------------------------------
# 납작한 종이라서 면마다 한 가지 밝기. 꼭짓점 좌표로 면을 찍고 접힘선을 파랑으로 긋는다.
def poly_fill(img, pts, col, alpha=255):
    px = img.load()
    w, h = img.size
    n = len(pts)
    for y in range(h):
        for x in range(w):
            cx, cy = x + 0.5, y + 0.5
            c = False
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 > cy) != (y2 > cy):
                    xi = x1 + (cy - y1) * (x2 - x1) / (y2 - y1)
                    if cx < xi:
                        c = not c
            if c:
                px[x, y] = rgba(col, alpha)
    return img


def line_px(img, x0, y0, x1, y1, col, alpha=255):
    px = img.load()
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        x = round(x0 + (x1 - x0) * i / n)
        y = round(y0 + (y1 - y0) * i / n)
        if 0 <= x < img.width and 0 <= y < img.height:
            px[x, y] = rgba(col, alpha)
    return img


PAL_KEEL = [(5, 13), (29.5, 15.5), (29.5, 17.5), (24, 21), (10, 21.5), (6, 19)]
PAL_FACE = [
    'K..K.',
    'KW.KW',
    '.....',
    'p..p.',
]
PAL_FACE_HURT = [
    'K.K..',
    '.K..K',
    'K.K.K',
    '.....',
]
# 날개 끝 위치 — 위, 가운데, 아래
PAL_TIPS = {'up': (6, 1), 'mid': (2, 8), 'down': (1, 21)}


def pal_frame(wing, bob, face=PAL_FACE, sweep=0):
    tx, ty = PAL_TIPS[wing]
    tx -= sweep
    far = blank(32, 32)
    poly_fill(far, [(26, 14 + bob), (9, 12.5 + bob), (tx + 4, ty - 2 + bob)], 'c')
    line_px(far, 22, 14 + bob, tx + 6, ty - 1 + bob, 't')
    keel = blank(32, 32)
    poly_fill(keel, [(x, y + bob) for x, y in PAL_KEEL], 'v')
    poly_fill(keel, [(6, 19 + bob), (10, 21.5 + bob), (24, 21 + bob), (27, 19 + bob), (12, 19.5 + bob)], 'c')
    line_px(keel, 7, 14 + bob, 28, 16 + bob, 'u')
    paste(keel, grid(face), 21, 16 + bob)
    near = blank(32, 32)
    poly_fill(near, [(25, 15.2 + bob), (6, 13.2 + bob), (tx, ty + bob)], 'w')
    # 앞전은 밝게, 가운데 접힘선은 파랑
    line_px(near, 23, 15 + bob, tx + 1, ty + bob + (1 if ty < 13 else -1), 'W')
    mx, my = (6 + tx) // 2 + 3, (13 + ty) // 2 + bob
    line_px(near, 20, 15 + bob, mx, my, 'i')
    return compose(32, 32, [(far, 0, 0, 'N'), (keel, 0, 0, 'N'), (near, 0, 0, 'N', 'u')])


# --- 캐릭터 프레임 조립 ---------------------------------------------------------
def boost_pair(make, lines, top_dx=2, pivot=22):
    out = []
    for ph in (0, 1):
        body = shear(make(ph), top_dx, pivot, 5)
        out.append(speed_lines(body, ph, lines))
    return out


def build_kkangdong():
    F = [compose(32, 32, kang_layers(pf, bob, arm=arm))
         for pf, bob, arm in [(0, 1, 'up'), (1, 0, 'mid'), (2, -1, 'down'), (3, 0, 'mid')]]
    F += boost_pair(lambda ph: compose(32, 32, kang_layers(ph * 2 + 1, 0, arm='down')),
                    [(10, 6), (15, 9), (20, 10), (25, 6)])
    F.append(compose(32, 32, kang_layers(0, -1, eye=['......', 'K....K', '.K..K.', '..KK..', '.K..K.', 'K....K'],
                                         arm='up')))
    for ph in (0, 1):
        body = compose(32, 32, kang_layers(ph * 2, ph, arm='mid'))
        F.append(make_ghost(body, 24 + ph, 24, 15, ph, extra={'R': 'a', 'r': 'i', 'p': 'W'}))
    return F


def build_doto():
    F = [compose(32, 32, doto_layers(m, bob, tdy))
         for m, bob, tdy in [('up', 1, -1), ('mid', 0, 0), ('down', -1, 1), ('mid', 0, 0)]]
    F += boost_pair(lambda ph: compose(32, 32, doto_layers('up', 0, ph)), [(8, 6), (13, 8), (18, 10), (22, 6)])
    F.append(compose(32, 32, doto_layers('down', -1, -1, head=DOTO_HEAD_HURT)))
    for ph in (0, 1):
        body = compose(32, 32, doto_layers('up' if ph else 'mid', ph, 0))
        F.append(make_ghost(body, 19 + ph, 24, 17, ph))
    return F


def build_palang():
    F = [pal_frame(w, b) for w, b in [('up', 1), ('mid', 0), ('down', -1), ('mid', 0)]]
    F += boost_pair(lambda ph: pal_frame('mid', 0, sweep=2 + ph), [(11, 6), (15, 9), (19, 10)])
    F.append(pal_frame('up', -1, face=PAL_FACE_HURT))
    for ph in (0, 1):
        F.append(make_ghost(pal_frame('up' if ph else 'mid', ph), 19 + ph, 26, 17, ph))
    return F


def portrait_from(frame, x, y):
    """첫 판 초상화: 날기 프레임에서 24×24 칸을 잘라 2배로 키운다."""
    return up(frame.crop((x, y, x + 24, y + 24)), 2)


PORTRAIT_CROP = {'mongsil': (6, 4), 'kkangdong': (4, 3), 'doto': (8, 2), 'palang': (6, 4)}


def random_portrait():
    """무작위 선택 칸 — 남색 실루엣에 큰 물음표."""
    img = blank(48, 48)
    sil = blank(48, 48)
    d = ImageDraw.Draw(sil)
    d.ellipse((8, 12, 40, 42), fill=rgba('n'))
    d.ellipse((10, 6, 20, 18), fill=rgba('n'))
    d.ellipse((28, 6, 38, 18), fill=rgba('n'))
    d.polygon([(4, 24), (10, 18), (12, 30)], fill=rgba('n'))
    d.polygon([(44, 24), (38, 18), (36, 30)], fill=rgba('n'))
    shade = blank(48, 48)
    ImageDraw.Draw(shade).ellipse((14, 18, 44, 46), fill=rgba('N'))
    px, sp = sil.load(), shade.load()
    for y in range(48):
        for x in range(48):
            if px[x, y][3] and sp[x, y][3]:
                px[x, y] = rgba('N')
    img.alpha_composite(outline(sil, 'K'))
    q = pixel_text('?', 3, 'y', 'Y', 'K')
    paste(img, q, (48 - q.width) // 2, 13)
    return img


# ===========================================================================
# 글자 — 갈무리 글꼴을 원래 크기로 안티앨리어싱 없이 찍고 정수배로 키운다
# ===========================================================================
def font_mask(text, font=FONT_BOLD, size=12):
    f = ImageFont.truetype(font, size)
    x0, y0, x1, y1 = f.getbbox(text)
    m = Image.new('L', (x1 - x0 + 2, y1 - y0 + 2), 0)
    d = ImageDraw.Draw(m)
    d.fontmode = '1'
    d.text((1 - x0, 1 - y0), text, font=f, fill=255)
    return m.crop(m.getbbox())


def pixel_text(text, scale, fill, shade, ol, font=FONT_BOLD, size=12, light=None, shadow=None, ol_w=1):
    """확대한 글자에 윗부분 밝은 띠, 아랫부분 그늘, 외곽선, 그림자를 더한다."""
    m = font_mask(text, font, size)
    m = m.resize((m.width * scale, m.height * scale), Image.NEAREST)
    pad = ol_w + 2
    w, h = m.width + pad * 2, m.height + pad * 2
    body = blank(w, h)
    bp = body.load()
    mp = m.load()
    for y in range(m.height):
        for x in range(m.width):
            if mp[x, y]:
                t = y / m.height
                c = shade if t > 0.62 else fill
                if light and t < 0.3:
                    c = light
                bp[x + pad, y + pad] = rgba(c)
    if light:
        for y in range(1, h):
            for x in range(w):
                if bp[x, y][3] and not bp[x, y - 1][3] and y < h * 0.7:
                    bp[x, y] = rgba('W')
    out = body
    for _ in range(ol_w):
        out = outline(out, ol, diag=True)
    if shadow:
        sh = out.copy()
        spx = sh.load()
        for y in range(h):
            for x in range(w):
                if spx[x, y][3]:
                    spx[x, y] = rgba(shadow)
        res = blank(w, h + 2)
        paste(res, sh, 0, 2)
        res.alpha_composite(out)
        out = res
    return out.crop(out.getbbox())


# ===========================================================================
# 아틀라스 꾸리기
# ===========================================================================
def pack(entries, width, gap=1):
    """entries: (이름, [프레임 그림], 추가 속성) 목록. 선반 방식으로 늘어놓는다."""
    x = y = shelf = 0
    blits = []
    anims = {}
    for name, imgs, extra in entries:
        rects = []
        for im in imgs:
            if x + im.width > width:
                x = 0
                y += shelf + gap
                shelf = 0
            rects.append([x, y, im.width, im.height])
            blits.append((im, x, y))
            x += im.width + gap
            shelf = max(shelf, im.height)
        a = {'frames': rects}
        a.update(extra or {})
        anims[name] = a
    atlas = blank(width, y + shelf)
    for im, bx, by in blits:
        paste(atlas, im, bx, by)
    return atlas, anims


def write_atlas(folder, base, entries, width):
    atlas, anims = pack(entries, width)
    save(atlas, folder, base + '.png')
    save_json({'image': base + '.png', 'animations': anims}, folder, base + '.json')
    return atlas, anims


def disc(img, cx, cy, r, col, alpha=255):
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                px[x, y] = rgba(col, alpha)
    return img


def ring_px(img, cx, cy, r0, r1, col, alpha=255):
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if r0 <= d <= r1:
                px[x, y] = rgba(col, alpha)
    return img


def shaded_disc(img, cx, cy, r, ramp, alpha=255):
    """왼쪽 위 빛을 받는 공. ramp는 밝은 색부터."""
    px = img.load()
    n = len(ramp)
    for y in range(img.height):
        for x in range(img.width):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            if dx * dx + dy * dy > r * r:
                continue
            d = math.hypot(dx + r * 0.4, dy + r * 0.4) / (r * 1.4)
            k = min(n - 1, int(d * n))
            px[x, y] = rgba(ramp[k], alpha)
    return img


def rotate_pts(pts, cx, cy, ang):
    c, s_ = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * c - (y - cy) * s_, cy + (x - cx) * s_ + (y - cy) * c) for x, y in pts]


def center_on(im, w, h, dx=0, dy=0):
    out = blank(w, h)
    paste(out, im, (w - im.width) // 2 + dx, (h - im.height) // 2 + dy)
    return out


# ===========================================================================
# 2. 아이템 16×16
# ===========================================================================
GEM_BLUE = [
    '....KKKKKK....',
    '...KCCaWauK...',
    '..KCaWWaauuK..',
    '.KiCCCaauuuUK.',
    'KKKKKKKKKKKKKK',
    'KCaWaCuuuuUUUK',
    '.KCaCuuuuuUUK.',
    '..KCauuuuUUK..',
    '...KCuuuUUK...',
    '....KCuuUK....',
    '.....KuUK.....',
    '......KK......',
]
GEM_RED = [
    '...KKKKKKKK...',
    '..KppWWpRRrK..',
    '.KpWWWppRRrrK.',
    'KpppRRRRRrrrrK',
    'KYYYYYYYYYYYYK',
    'KpWpRRRRRrrrDK',
    '.KpWpRRRRrrDK.',
    '..KppRRRrrDK..',
    '...KpRRrrDK...',
    '....KpRrDK....',
    '.....KRDK.....',
    '......KK......',
]
SPARKLE = ['..W..', '..W..', 'WWkWW', '..W..', '..W..']
SPARKLE_S = ['.W.', 'WkW', '.W.']
BUNGEO = [
    '....KKKKKK......',
    '..KKttYYttKK..KK',
    '.KtYYttYYtttKKtK',
    'KtYKYtYtYtttbttK',
    'KtYYYtYtYtttbbbK',
    'KttttttttttbbbK.',
    '.KbtttttttbbbbbK',
    '..KKbbbbbbbbKKbK',
    '....KKKKKKKK..K.',
]
FEATHER = [
    '........KK',
    '......KKWK',
    '.....KWWlK',
    '....KWWlK.',
    '...KWWlyK.',
    '..KWWlYK..',
    '.KWWlyK...',
    '.KWlYK....',
    'KWlyK.....',
    'KlYK......',
    'KYK.......',
    'YK........',
]


def item_frames():
    blue, red, food, feather = [], [], [], []
    sp_pos = [(1, 0), (10, 2), (11, 9), (2, 9)]
    for i in range(4):
        bob = 1 if i in (1, 2) else 0
        f = blank(16, 16)
        paste(f, grid(GEM_BLUE), 1, 2 + bob)
        paste(f, grid(SPARKLE if i % 2 == 0 else SPARKLE_S), *sp_pos[i])
        blue.append(f)
        f = blank(16, 16)
        paste(f, grid(GEM_RED), 1, 2 + bob)
        paste(f, grid(SPARKLE), *sp_pos[(i + 2) % 4])
        paste(f, grid(SPARKLE_S), sp_pos[i][0] + 1, sp_pos[i][1] + 1)
        red.append(f)
    for i in range(2):
        f = blank(16, 16)
        paste(f, grid(BUNGEO), 0, 3 + i)
        food.append(f)
    for i, sh in enumerate([0, 1, 0, -1]):
        f = blank(16, 16)
        g = grid(FEATHER)
        if sh > 0:
            g = shear(g, 1, 6, 4)
        elif sh < 0:
            g = flip(shear(flip(g), 1, 6, 4))
        paste(f, g, 3, 2 + (1 if i == 2 else 0))
        feather.append(f)
    return [('gemBlue', blue, {'fps': 8}), ('gemRed', red, {'fps': 8}), ('food', food, {'fps': 3}),
            ('feather', feather, {'fps': 6})]


# ===========================================================================
# 3. 효과·발사체
# ===========================================================================
ACORN = [
    '......KK......',
    '.....KbK......',
    '...KKKbKKK....',
    '..KbBbBbBbK...',
    '.KbBbBbBbBbK..',
    'KbBbBbBbBbBBK.',
    'KBBBBBBBBBBBK.',
    '.KtttoooooomK.',
    '.KttoooooommK.',
    '.KtooooooommK.',
    '..KoooooommK..',
    '...KooommmK...',
    '....KKmmKK....',
    '......KK......',
]


def fx_puff(i):
    f = blank(16, 16)
    blobs = [(7, 8, 4.6), (4.5, 9.5, 3.2), (10.5, 9.5, 3.4), (8.5, 5.5, 3.0)] if i == 0 else \
            [(8, 8, 4.4), (4.5, 8.5, 3.4), (11, 9, 3.0), (7, 5.5, 3.2)]
    for cx, cy, r in blobs:
        shaded_disc(f, cx, cy, r, 'WWls')
    return outline(f, 'n')


def fx_nut(i):
    f = blank(16, 16)
    px = f.load()
    ang = math.radians(15 * i)
    hexp = [(8 + 6.6 * math.cos(ang + k * math.pi / 3), 8 + 6.6 * math.sin(ang + k * math.pi / 3)) for k in range(6)]
    poly_fill(f, hexp, 'l')
    for y in range(16):
        for x in range(16):
            if not px[x, y][3]:
                continue
            a = math.atan2(y + 0.5 - 8, x + 0.5 - 8) - ang
            k = int(((a + math.pi / 6) % (2 * math.pi)) // (math.pi / 3))
            na = ang + k * math.pi / 3
            lit = -math.cos(na) * 0.7 - math.sin(na) * 0.7
            c = 'W' if lit > 0.6 else 'l' if lit > 0 else 's' if lit > -0.6 else 'g'
            r = math.hypot(x + 0.5 - 8, y + 0.5 - 8)
            if r < 4.2:
                c = 'l' if (x + y) < 15 else 's'
            if r < 2.6:
                c = None
            px[x, y] = rgba(c) if c else (0, 0, 0, 0)
    ring_px(f, 8, 8, 2.6, 3.2, 'g')
    return outline(f, 'K')


def fx_paper(i):
    f = blank(16, 16)
    ang = math.radians(22.5 * i)
    for k in range(4):
        a = ang + k * math.pi / 2
        tip = (8 + 7.2 * math.cos(a), 8 + 7.2 * math.sin(a))
        left = (8 + 2.6 * math.cos(a - math.pi / 4) * 1.2, 8 + 2.6 * math.sin(a - math.pi / 4) * 1.2)
        right = (8 + 2.6 * math.cos(a + math.pi / 4) * 1.2, 8 + 2.6 * math.sin(a + math.pi / 4) * 1.2)
        poly_fill(f, [(8, 8), left, tip], 'w')
        poly_fill(f, [(8, 8), tip, right], 'c')
    disc(f, 8, 8, 1.6, 'u')
    return outline(f, 'n')


def fx_acorn(i):
    f = blank(16, 16)
    g = grid(ACORN)
    paste(f, g, 1, 2)
    px = f.load()
    if i == 0:
        px[8, 1] = rgba('y')
        px[9, 0] = rgba('O')
    else:
        px[9, 1] = rgba('O')
        px[8, 0] = rgba('y')
        px[10, 0] = rgba('y')
    return f


def bolt_path(seed):
    rnd = random.Random(seed)
    pts = [(8, 0)]
    y = 0
    while y < 28:
        y += rnd.randint(4, 6)
        pts.append((8 + rnd.choice([-4, -3, -2, 2, 3, 4]), min(y, 28)))
    pts.append((8, 32))
    return pts


def fx_boltseg(i):
    f = blank(16, 32)
    pts = bolt_path(100 + i)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for dx in (-2, 2):
            line_px(f, x0 + dx, y0, x1 + dx, y1, 'Y', 150)
        for dx in (-1, 1):
            line_px(f, x0 + dx, y0, x1 + dx, y1, 'y')
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        line_px(f, x0, y0, x1, y1, 'W')
    return f


def burst(size, r_in, r_out, n, col, alpha=255, rot=0.0):
    f = blank(size, size)
    c = size / 2
    for k in range(n):
        a = rot + k * 2 * math.pi / n
        line_px(f, round(c + r_in * math.cos(a)), round(c + r_in * math.sin(a)),
                round(c + r_out * math.cos(a)), round(c + r_out * math.sin(a)), col, alpha)
    return f


def fx_bolthit(i):
    f = blank(32, 32)
    if i == 0:
        disc(f, 16, 22, 9, 'y', 200)
        disc(f, 16, 22, 6, 'W')
        f.alpha_composite(burst(32, 6, 15, 8, 'W', rot=0.2), (0, 6))
    elif i == 1:
        ring_px(f, 16, 22, 7, 9.5, 'y')
        ring_px(f, 16, 22, 9.5, 10.5, 'Y', 180)
        disc(f, 16, 22, 3, 'W')
        f.alpha_composite(burst(32, 11, 15, 6, 'y', rot=0.6), (0, 6))
    else:
        ring_px(f, 16, 22, 10, 11, 'Y', 150)
        for x, y in [(6, 18), (25, 16), (10, 10), (22, 9), (15, 13)]:
            disc(f, x, y, 1.2, 'y')
        disc(f, 16, 24, 3.5, 'l', 120)
    return f


def fx_warn(i):
    f = blank(24, 24)
    col = 'R' if i == 0 else 'y'
    ring_px(f, 12, 12, 8.2, 9.6, col)
    for a in range(4):
        ang = a * math.pi / 2
        line_px(f, round(12 + 6 * math.cos(ang)), round(12 + 6 * math.sin(ang)),
                round(12 + 11 * math.cos(ang)), round(12 + 11 * math.sin(ang)), col)
    ex = grid(['KK', 'yy', 'yy', 'yy', 'KK', 'yy'] if i == 0 else ['KK', 'RR', 'RR', 'RR', 'KK', 'RR'])
    paste(f, ex, 11, 9)
    return outline(f, 'K')


def fx_oil(i):
    f = blank(48, 16)
    blobs = [(10, 8, 5), (18, 6, 5.5), (27, 7, 6), (36, 8, 5), (22, 10, 5), (31, 10, 4.5)]
    for cx, cy, r in blobs:
        shaded_disc(f, cx, cy, r, 'PDKK', 235)
    drips = [(14, 12), (24, 13), (35, 12)] if i == 0 else [(15, 13), (25, 12), (34, 13)]
    for x, y in drips:
        disc(f, x, y + 1, 1.6, 'K', 235)
    for x0, x1, y in [(13, 18, 4), (24, 28, 3), (33, 35, 5)]:
        line_px(f, x0 + i, y, x1 + i, y, 'q')
    return outline(f, 'K')


def fx_hit(i):
    f = blank(32, 32)
    if i == 0:
        f.alpha_composite(burst(32, 2, 7, 8, 'W'))
        disc(f, 16, 16, 3, 'W')
    elif i == 1:
        f.alpha_composite(burst(32, 4, 12, 8, 'y', rot=math.pi / 8))
        f.alpha_composite(burst(32, 3, 9, 8, 'W'))
        disc(f, 16, 16, 4, 'W')
    elif i == 2:
        ring_px(f, 16, 16, 9, 11, 'Y')
        ring_px(f, 16, 16, 8, 9, 'y')
        f.alpha_composite(burst(32, 12, 15, 8, 'y', rot=math.pi / 8))
    else:
        for k in range(8):
            a = k * math.pi / 4 + math.pi / 8
            disc(f, 16 + 13 * math.cos(a), 16 + 13 * math.sin(a), 1.2, 'Y', 200)
        ring_px(f, 16, 16, 12, 13, 'O', 120)
    return f


def fx_shield(i):
    f = blank(32, 32)
    disc(f, 16, 16, 14.5, 'a', 60)
    ring_px(f, 16, 16, 13.2, 14.6, 'C', 210)
    ring_px(f, 16, 16, 12.2, 13.2, 'a', 110)
    arc = [(9, 8), (8, 9), (7, 10), (7, 11), (10, 7), (11, 6.5)] if i == 0 else [(9, 9), (8, 10), (8, 11), (10, 8), (12, 7)]
    for x, y in arc:
        disc(f, x, y, 0.9, 'W', 230)
    disc(f, 21 + i, 23 - i, 1.0, 'W', 180)
    return f


def fx_dash(i):
    f = blank(48, 24)
    rows = [(5, 30), (9, 40), (12, 44), (15, 40), (19, 28)]
    for k, (y, ln) in enumerate(rows):
        ln = ln - i * 6 - (k % 2) * 4
        x1 = 47 - (k % 2) * 3
        for j in range(ln):
            x = x1 - j
            a = int(220 * (1 - j / ln))
            if a > 20:
                f.load()[x, y] = rgba('W' if j < ln * 0.4 else 'a', a)
    return f


def fx_revive(i):
    f = blank(32, 32)
    for y in range(32):
        a = int(140 * (1 - abs(y - 16) / 16) * (0.6 + 0.4 * (i % 2)))
        for x in range(13, 19):
            f.load()[x, y] = rgba('k' if 14 <= x <= 17 else 'y', a)
    ring_px(f, 16, 26 - i * 2, 5 + i * 2, 6 + i * 2, 'y', 200 - i * 30)
    for k, (x, y) in enumerate([(7, 20), (24, 17), (10, 9), (21, 6), (16, 13)]):
        yy = (y - i * 3 - k) % 30 + 1
        paste(f, grid(SPARKLE_S if (k + i) % 2 else ['W']), x - 1, yy - 1)
    return f


def fx_pickup(i):
    f = blank(16, 16)
    if i == 0:
        paste(f, grid(SPARKLE_S), 6, 6)
    elif i == 1:
        paste(f, grid(SPARKLE), 5, 5)
        ring_px(f, 8, 8, 4, 5, 'y', 200)
    elif i == 2:
        f.alpha_composite(burst(16, 3, 7, 8, 'y'))
        paste(f, grid(SPARKLE_S), 6, 6)
    else:
        for k in range(8):
            a = k * math.pi / 4
            f.load()[int(8 + 7 * math.cos(a))
                     if int(8 + 7 * math.cos(a)) < 16 else 15, int(8 + 7 * math.sin(a)) if int(8 + 7 * math.sin(a)) < 16 else 15] = rgba('Y', 200)
    return f


def fx_whirl(i):
    f = blank(24, 24)
    for k in range(2):
        base = i * 2 * math.pi / 3 + k * math.pi
        for t in range(40):
            r = 2 + t * 0.22
            a = base + t * 0.18
            x, y = 12 + r * math.cos(a), 12 + r * math.sin(a) * 0.7
            c = 'W' if t < 22 else 'a'
            disc(f, x, y, 0.8, c, 230 if t < 30 else 150)
    return outline(f, 'u')


def fx_fog():
    f = blank(96, 48)
    rnd = random.Random(7)
    blobs = [(20, 26, 15), (40, 20, 18), (62, 22, 17), (78, 28, 14), (50, 32, 16), (30, 34, 12), (70, 36, 10)]
    for cx, cy, r in blobs:
        shaded_disc(f, cx, cy, r, 'sggn', 215)
    px = f.load()
    for _ in range(60):
        x, y = rnd.randrange(96), rnd.randrange(48)
        if px[x, y][3] and (x + y) % 2 == 0:
            px[x, y] = rgba('s', 215)
    return f


def fx_text(text, fill, shade, light):
    t = pixel_text(text, 2, fill, shade, 'K', light=light)
    return center_on(t, 64, 24)


def fx_entries():
    return [
        ('puff', [fx_puff(i) for i in range(2)], {'fps': 8}),
        ('nut', [fx_nut(i) for i in range(4)], {'fps': 12}),
        ('acorn', [fx_acorn(i) for i in range(2)], {'fps': 8}),
        ('paper', [fx_paper(i) for i in range(4)], {'fps': 12}),
        ('boltSeg', [fx_boltseg(i) for i in range(3)], {'fps': 18}),
        ('boltHit', [fx_bolthit(i) for i in range(3)], {'fps': 12, 'loop': False}),
        ('warn', [fx_warn(i) for i in range(2)], {'fps': 6}),
        ('oil', [fx_oil(i) for i in range(2)], {'fps': 3}),
        ('hit', [fx_hit(i) for i in range(4)], {'fps': 16, 'loop': False}),
        ('shield', [fx_shield(i) for i in range(2)], {'fps': 4}),
        ('dash', [fx_dash(i) for i in range(3)], {'fps': 14}),
        ('revive', [fx_revive(i) for i in range(4)], {'fps': 8}),
        ('pickup', [fx_pickup(i) for i in range(4)], {'fps': 16, 'loop': False}),
        ('whirl', [fx_whirl(i) for i in range(3)], {'fps': 10}),
        ('fog', [fx_fog()], {}),
        ('nice', [fx_text('NICE', 'y', 'Y', 'k')], {}),
        ('kill', [fx_text('KILL', 'R', 'r', 'p')], {}),
    ]


# ===========================================================================
# 4. HUD
# ===========================================================================
HEART_FULL = [
    '.KKK...KKK...',
    'KpWRK.KRRrK..',
    'KWRRRKRRRrrK.',
    'KpRRRRRRRrrK.',
    'KRRRRRRRRrrK.',
    '.KRRRRRRrrK..',
    '..KRRRRrrK...',
    '...KRRrrK....',
    '....KRrK.....',
    '.....KK......',
]
HEART_EMPTY = [
    '.KKK...KKK...',
    'KnnnK.KnnNK..',
    'KnNNNKNNNNNK.',
    'KnNNNNNNNNNK.',
    'KNNNNNNNNNNK.',
    '.KNNNNNNNNK..',
    '..KNNNNNNK...',
    '...KNNNNK....',
    '....KNNK.....',
    '.....KK......',
]


def rounded_box(w, h, rings, fill, corner=1):
    """바깥부터 안쪽으로 고리 색을 차례로 두른 상자. rings 항목은 한 색 또는 (위왼쪽, 아래오른쪽) 두 색."""
    img = blank(w, h)
    px = img.load()
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            if corner and ((x < corner or x >= w - corner) and (y < corner or y >= h - corner)):
                continue
            if d < len(rings):
                r = rings[d]
                if isinstance(r, tuple):
                    tl = (y == d or x == d) and not (y == h - 1 - d or x == w - 1 - d)
                    c = r[0] if tl else r[1]
                else:
                    c = r
            else:
                c = fill
            if c:
                px[x, y] = rgba(c)
    # 둥근 모서리 안쪽 한 칸은 외곽선 색으로 메운다
    if corner:
        for (x, y) in [(corner, corner), (w - 1 - corner, corner), (corner, h - 1 - corner), (w - 1 - corner, h - 1 - corner)]:
            px[x, y] = rgba(rings[0] if not isinstance(rings[0], tuple) else rings[0][0])
    return img


def hp_frame():
    img = rounded_box(106, 12, ['K', ('g', 'N'), 'K'], None)
    px = img.load()
    for y in range(3, 9):
        for x in range(3, 103):
            px[x, y] = rgba('K' if y == 3 else 'N')
    return img


def slot_frame():
    return rounded_box(26, 26, ['K', ('s', 'n'), ('n', 'N'), 'K'], 'N')


def slot_active(i):
    img = rounded_box(30, 30, ['K', 'Y' if i == 0 else 'y', 'y' if i == 0 else 'k', 'K'], None, corner=2)
    return img


def icon_canvas():
    return blank(18, 18)


def icon_puff():
    f = icon_canvas()
    for cx, cy, r in [(8, 10, 5), (4.5, 11, 3.4), (12, 11, 3.6), (9, 6, 3.6)]:
        shaded_disc(f, cx, cy, r, 'WWls')
    f = outline(f, 'n')
    for y, x0, x1 in [(4, 14, 16), (8, 15, 17), (13, 15, 16)]:
        line_px(f, x0, y, x1, y, 'a')
    return f


def icon_dash():
    f = icon_canvas()
    for ox in (2, 8):
        poly_fill(f, [(ox, 3), (ox + 4, 3), (ox + 9, 9), (ox + 4, 15), (ox, 15), (ox + 5, 9)], 'Y')
        poly_fill(f, [(ox, 3), (ox + 4, 3), (ox + 9, 9), (ox + 5, 9)], 'y')
    return outline(f, 'K')


def icon_cloud():
    f = icon_canvas()
    for cx, cy, r in [(9, 8, 5), (5, 9, 3.5), (13, 9, 3.6), (8, 5.5, 3.5)]:
        shaded_disc(f, cx, cy, r, 'sgnN')
    f = outline(f, 'K')
    for x, y in [(5, 14), (9, 15), (13, 14)]:
        paste(f, grid(['C', 'u', 'U']), x, y)
    return f


def icon_bolt():
    f = icon_canvas()
    poly_fill(f, [(10, 1), (4, 10), (8, 10), (6, 17), (14, 7), (10, 7), (12, 1)], 'Y')
    poly_fill(f, [(10, 1), (4, 10), (8, 10), (9, 7), (12, 1)], 'y')
    return outline(f, 'K')


def icon_shield():
    f = icon_canvas()
    disc(f, 9, 9, 7.5, 'i')
    disc(f, 9, 9, 6.0, 'a')
    shaded_disc(f, 9, 9, 6.0, 'aaai')
    ring_px(f, 9, 9, 6.0, 7.5, 'C')
    for x, y in [(5, 5), (6, 4), (4, 6), (4, 7)]:
        f.load()[x, y] = rgba('W')
    return outline(f, 'U')


def icon_nut():
    f = blank(18, 18)
    g = fx_nut(1).crop((0, 0, 16, 16))
    paste(f, g, 1, 1)
    return f


ICON_WRENCH = [
    '.........KKK....',
    '........KlWsK...',
    '.......KlWsK....',
    '.......KlsK..KK.',
    '.......KlsKKKlK.',
    '......KllssslsK.',
    '.....KllsssssK..',
    '....KlssgKKKK...',
    '...KlssgK.......',
    '..KlssgK........',
    '.KlssgK.........',
    'KlssgK..........',
    'KssgK...........',
    '.KKK............',
]


def icon_repair():
    return center_on(grid(ICON_WRENCH), 18, 18)


def icon_oil():
    f = icon_canvas()
    poly_fill(f, [(9, 1), (4, 10), (14, 10)], 'P')
    shaded_disc(f, 9, 11, 5.2, 'qPDK')
    poly_fill(f, [(9, 2), (6, 8), (9, 7)], 'q')
    f.load()[6, 10] = rgba('W')
    f.load()[6, 11] = rgba('q')
    return outline(f, 'K')


def icon_acorn():
    return center_on(grid(ACORN), 18, 18)


def icon_glide():
    f = icon_canvas()
    poly_fill(f, [(2, 6), (16, 6), (15, 13), (9, 11), (3, 13)], 'o')
    poly_fill(f, [(2, 6), (16, 6), (15, 8), (3, 8)], 't')
    poly_fill(f, [(3, 11), (9, 10), (15, 11), (15, 13), (9, 11), (3, 13)], 'm')
    disc(f, 9, 5, 3, 'o')
    disc(f, 8.5, 4.5, 1.6, 't')
    f.load()[10, 4] = rgba('K')
    for x, y in [(2, 5), (16, 5), (3, 13), (15, 13)]:
        f.load()[x, y] = rgba('c')
    return outline(f, 'D')


def icon_whirl():
    f = icon_canvas()
    for k, (cy, rx) in enumerate([(3, 7.5), (6, 6.2), (9, 5), (12, 3.6), (15, 2.2)]):
        cx = 9 + (k % 2) - 0.5 * k
        for x in range(18):
            for y in range(18):
                if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / 1.6) ** 2 <= 1:
                    f.load()[x, y] = rgba('W' if x < cx - rx * 0.3 else 'a' if x < cx + rx * 0.5 else 'i')
    return outline(f, 'U')


def icon_paper():
    f = blank(18, 18)
    paste(f, fx_paper(1), 1, 1)
    return f


def icon_fold():
    f = icon_canvas()
    poly_fill(f, [(5, 5), (13, 5), (13, 13), (5, 13)], 'w')
    poly_fill(f, [(9, 5), (13, 5), (13, 9)], 'c')
    line_px(f, 9, 5, 13, 9, 'u')
    line_px(f, 5, 9, 13, 9, 'i')
    f = outline(f, 'n')
    for pts in [[(0, 0), (3, 3)], [(17, 0), (14, 3)], [(0, 17), (3, 14)], [(17, 17), (14, 14)]]:
        (x0, y0), (x1, y1) = pts
        line_px(f, x0, y0, x1, y1, 'Y')
    for x, y in [(3, 2), (2, 3), (14, 2), (15, 3), (2, 14), (3, 15), (15, 14), (14, 15)]:
        f.load()[x, y] = rgba('Y')
    return f


def icon_pinwheel():
    f = icon_canvas()
    line_px(f, 9, 9, 9, 17, 'b')
    line_px(f, 10, 10, 10, 17, 'B')
    cols = ['R', 'y', 'u', 'G']
    for k in range(4):
        a = k * math.pi / 2 - math.pi / 4
        tip = (9 + 7.5 * math.cos(a), 8 + 7.5 * math.sin(a))
        side = (9 + 6 * math.cos(a + math.pi / 2.6), 8 + 6 * math.sin(a + math.pi / 2.6))
        poly_fill(f, [(9, 8), tip, side], cols[k])
    disc(f, 9, 8, 1.4, 'W')
    return outline(f, 'K')


SMALL = {
    'crown': [
        '.K..K..K...',
        'KyK.KyK.KyK',
        'KYKKYYKKYK.',
        'KYYYYYYYYK.',
        'KYyYRYyYYK.',
        'KYYYYYYYOK.',
        'KOOOOOOOOK.',
        '.KKKKKKKK..',
    ],
    'check': [
        '........KK',
        '.......KGK',
        '......KGhK',
        'KK...KGhK.',
        'KGK.KGhK..',
        'KhGKGhK...',
        '.KhGhK....',
        '..KhK.....',
        '...K......',
    ],
    'ghostIcon': [
        '..KKKKK..',
        '.KWWWaaK.',
        'KWWWWWaiK',
        'KWUWWUaiK',
        'KWUWWUaiK',
        'KWWWWWaiK',
        'KWWaWWaiK',
        'KaWiaWiiK',
        '.KiKiKiK.',
        '..K.K.K..',
    ],
    'skull': [
        '..KKKKK..',
        '.KWWWWlK.',
        'KWWWWWWlK',
        'KWKKWKKlK',
        'KWKKWKKlK',
        'KWWWKWWlK',
        '.KlWWWlK.',
        '.KlKlKlK.',
        '..KKKKK..',
    ],
    'featherIcon': [
        '......KK.',
        '.....KWK.',
        '....KWlK.',
        '...KWlyK.',
        '..KWlYK..',
        '.KWlYK...',
        '.KlYK....',
        'KYKK.....',
        'YK.......',
    ],
}
STATUS = {
    'debuff_blind': [
        '...KKKKKK...',
        '.KKWWWWWWKK.',
        'KWWWWKKWWWWK',
        'KWWWKnnKWWWK',
        'KnnnnnnnnnnK',
        'KnnnnnnnnnnK',
        'KWWWKnnKWWWK',
        '.KKWWKKWWKK.',
        '...KKKKKK...',
    ],
    'debuff_heavy': [
        '....KKKK....',
        '...KsKKgK...',
        '...KK..KK...',
        '..KKKKKKKK..',
        '.KlssssssgK.',
        'KlsssssssgnK',
        'KssWWsWWsgnK',
        'KssWssWssgnK',
        'KssWWsWssgnK',
        'KsgggggggnnK',
        '.KKKKKKKKKK.',
    ],
    'debuff_shake': [
        'K.K......K.K',
        '.K..KKKK..K.',
        '...KyyyyK...',
        '..KyKKKKyK..',
        '..KyKyyKyK..',
        '..KyKyKKyK..',
        '..KyKKKyK...',
        '...KyyyK....',
        '.K..KKK...K.',
        'K.K......K.K',
    ],
    'debuff_slow': [
        'KKKKKKKKKK',
        'KcttttttcK',
        '.KcYYYYcK.',
        '..KcYYcK..',
        '...KYYK...',
        '...KccK...',
        '..KccYcK..',
        '.KccYYYcK.',
        'KcYYYYYYcK',
        'KKKKKKKKKK',
    ],
    'buff_glide': [
        '.........KK.',
        '.......KKWK.',
        '.....KKWWlK.',
        '...KKWWWlK..',
        '.KKWWWWllK..',
        'KWWWWWllK...',
        'KaWWWllK....',
        '.KaaalK.....',
        '..KaiK......',
        '...KK.......',
    ],
    'buff_shrink': [
        'KK.......KK.',
        'KGK.....KGK.',
        '.KGK...KGK..',
        '..KGKKKGK...',
        '...KKyKK....',
        '...KyyyK....',
        '...KKyKK....',
        '..KGKKKGK...',
        '.KGK...KGK..',
        'KGK.....KGK.',
        'KK.......KK.',
    ],
}


def team_badge(letter, base, light, dark):
    g = [
        '.KKKKKKKKKKKK.',
        'KllllllllllllK',
        'KlBBBBBBBBBBdK',
        'KlBBBBBBBBBBdK',
        'KlBBBBBBBBBBdK',
        'KlBBBBBBBBBBdK',
        'KlBBBBBBBBBBdK',
        'KlBBBBBBBBBBdK',
        '.KlBBBBBBBBdK.',
        '.KlBBBBBBBBdK.',
        '..KlBBBBBBdK..',
        '...KlBBBBdK...',
        '....KKddKK....',
        '......KK......',
    ]
    img = grid(g, {'l': light, 'B': base, 'd': dark})
    m = font_mask(letter, os.path.join(ROOT, 'node_modules', 'galmuri', 'dist', 'Galmuri7.ttf'), 8)
    px = img.load()
    mp = m.load()
    ox, oy = (14 - m.width) // 2, 3
    for y in range(m.height):
        for x in range(m.width):
            if mp[x, y]:
                px[ox + x, oy + y] = rgba('W')
                if px[ox + x + 1, oy + y + 1] != rgba('W'):
                    px[ox + x + 1, oy + y + 1] = rgba('K')
    return img


def marker(col, light, dark):
    g = [
        '.KKKKK.',
        'KlcccdK',
        'KcccccK',
        'KcccddK',
        '.KccdK.',
        '..KdK..',
        '...K...',
        '.......',
    ]
    return grid(g, {'l': light, 'c': col, 'd': dark})


def marker_self():
    g = [
        '.KKKKKKK.',
        'KWWWWWWWK',
        'KWkyyyYWK',
        'KWyyyYYWK',
        'KWyyYYYWK',
        '.KWYYYWK.',
        '..KWYWK..',
        '...KWK...',
        '....K....',
        '.........',
    ]
    return grid(g)


def rank_row(selfrow):
    if selfrow:
        img = rounded_box(150, 18, ['K', 'Y', ('y', 'O')], 'n')
        cell = 'Y'
    else:
        img = rounded_box(150, 18, ['K', ('n', 'N'), 'N'], 'N')
        cell = 'n'
    px = img.load()
    for y in range(3, 15):
        for x in range(3, 18):
            px[x, y] = rgba(cell)
        px[18, y] = rgba('K')
    return img


def mini_bar():
    img = rounded_box(240, 12, ['K', ('n', 'N'), 'K'], 'N')
    px = img.load()
    for x in range(3, 237):
        px[x, 3] = rgba('n')
    for k in range(0, 11):
        x = 3 + round(k * 233 / 10)
        h = 4 if k % 5 else 6
        for y in range(9 - h, 9):
            px[min(x, 236), y] = rgba('y' if k == 5 else 'g')
    return img


def timer_plate():
    img = rounded_box(64, 20, ['K', 'Y', ('O', 'm'), 'K'], 'N', corner=2)
    px = img.load()
    for x in range(4, 60):
        px[x, 4] = rgba('n')
    for x, y in [(5, 5), (58, 5), (5, 14), (58, 14)]:
        px[x, y] = rgba('c')
    return img


def countdown(text, fill, shade, light, scale=4):
    t = pixel_text(text, scale, fill, shade, 'K', light=light, shadow='N')
    assert t.width <= 64 and t.height <= 48, (text, t.size)
    return t


PIP_FULL = [
    '.KKKKK.',
    'KkyyyYK',
    'KyyYYYK',
    'KyYYYOK',
    'KYYYOOK',
    'KYOOOmK',
    '.KKKKK.',
]
PIP_EMPTY = [
    '.KKKKK.',
    'KKKKKKK',
    'KKNNNnK',
    'KKNNNnK',
    'KKNNNnK',
    'KnnnnnK',
    '.KKKKK.',
]


def pip_half():
    full = grid(PIP_FULL)
    img = grid(PIP_EMPTY)
    img.paste(full.crop((0, 0, 4, 7)), (0, 0))
    return img


def keycap(w, h=14, symbol=None, face='l', top='W', side='s', bottom='g'):
    img = blank(w, h)
    px = img.load()
    for y in range(h):
        for x in range(w):
            edge = x == 0 or y == 0 or x == w - 1 or y == h - 1
            corner = (x in (0, w - 1)) and (y in (0, h - 1))
            if corner:
                continue
            if edge:
                c = 'K'
            elif y >= h - 4:
                c = side if y < h - 2 else bottom
            elif y == 1:
                c = top
            elif x == 1:
                c = top
            elif x == w - 2:
                c = 's'
            else:
                c = face
            px[x, y] = rgba(c)
    px[1, h - 2] = rgba('K')
    px[w - 2, h - 2] = rgba('K')
    if symbol is not None:
        paste(img, symbol, (w - symbol.width) // 2, (h - 3 - symbol.height) // 2)
    return img


def key_letter(ch):
    m = font_mask(ch, os.path.join(ROOT, 'node_modules', 'galmuri', 'dist', 'Galmuri7.ttf'), 8)
    img = blank(m.width, m.height)
    px, mp = img.load(), m.load()
    for y in range(m.height):
        for x in range(m.width):
            if mp[x, y]:
                px[x, y] = rgba('N')
    return img


ARROW_UP = ['..N..', '.NNN.', 'NNNNN', '..N..', '..N..', '..N..']
ENTER = ['....N', '....N', '.N..N', 'NNNNN', '.N...']


def key_mouse(left):
    g = [
        '...KKKKKKK....',
        '..KLLLKRRRK...',
        '.KLLLLKRRRRK..',
        '.KLLLLKRRRRK..',
        '.KLLLLKRRRRK..',
        '.KKKKKKKKKKK..',
        '.KlllllllllK..',
        '.KWlllllllsK..',
        '.KWlllllllsK..',
        '.KlllllllssK..',
        '..KlllllssK...',
        '...KsssssK....',
        '....KKKKK.....',
        '..............',
    ]
    on = {'L': 'Y', 'R': 's'} if left else {'L': 's', 'R': 'Y'}
    img = grid(g, on)
    px = img.load()
    hx = 3 if left else 8
    px[hx, 2] = rgba('k' if True else 'W')
    return img


def hud_entries():
    E = [
        ('heartFull', [grid(HEART_FULL)], {}),
        ('heartEmpty', [grid(HEART_EMPTY)], {}),
        ('hpFrame', [hp_frame()], {}),
        ('hpFill', [grid(['G', 'G', 'G', 'G', 'h', 'H'])], {}),
        ('hpFillLow', [grid(['p', 'R', 'R', 'R', 'r', 'r'])], {}),
        ('slotFrame', [slot_frame()], {}),
        ('slotActive', [slot_active(0), slot_active(1)], {'fps': 3}),
    ]
    icons = {'puff': icon_puff, 'dash': icon_dash, 'cloud': icon_cloud, 'bolt': icon_bolt, 'shield': icon_shield,
             'nut': icon_nut, 'repair': icon_repair, 'oil': icon_oil, 'acorn': icon_acorn, 'glide': icon_glide,
             'whirl': icon_whirl, 'paper': icon_paper, 'fold': icon_fold, 'pinwheel': icon_pinwheel}
    for k, fn in icons.items():
        im = fn()
        assert im.size == (18, 18), (k, im.size)
        E.append(('icon_' + k, [im], {}))
    E += [
        ('rankRow', [rank_row(False)], {}),
        ('rankRowSelf', [rank_row(True)], {}),
        ('miniBar', [mini_bar()], {}),
        ('miniMarker0', [marker('R', 'p', 'r')], {}),
        ('miniMarker1', [marker('u', 'C', 'U')], {}),
        ('miniMarker2', [marker('G', 'y', 'h')], {}),
        ('miniMarker3', [marker('Y', 'y', 'O')], {}),
        ('miniMarkerSelf', [marker_self()], {}),
        ('timerPlate', [timer_plate()], {}),
    ]
    for k, g in SMALL.items():
        E.append((k, [grid(g)], {}))
    for k, g in STATUS.items():
        E.append((k, [center_on(grid(g), 12, 12)], {}))
    E += [
        ('teamA', [team_badge('A', 'R', 'p', 'r')], {}),
        ('teamB', [team_badge('B', 'u', 'C', 'U')], {}),
        ('num3', [countdown('3', 'R', 'r', 'p')], {}),
        ('num2', [countdown('2', 'Y', 'O', 'y')], {}),
        ('num1', [countdown('1', 'G', 'h', 'y')], {}),
        ('go', [countdown('GO', 'y', 'Y', 'k')], {}),
        ('pipFull', [grid(PIP_FULL)], {}),
        ('pipHalf', [pip_half()], {}),
        ('pipEmpty', [grid(PIP_EMPTY)], {}),
        ('keyMouseL', [key_mouse(True)], {}),
        ('keyMouseR', [key_mouse(False)], {}),
        ('keySpace', [keycap(40, 14, key_letter('SPACE'))], {}),
        ('keyUp', [keycap(14, 14, grid(ARROW_UP))], {}),
        ('keyRight', [keycap(14, 14, grid(ARROW_UP).rotate(-90, expand=True))], {}),
        ('keyEnter', [keycap(14, 14, grid(ENTER))], {}),
        ('keyW', [keycap(14, 14, key_letter('W'))], {}),
        ('keyD', [keycap(14, 14, key_letter('D'))], {}),
        ('keyM', [keycap(14, 14, key_letter('M'))], {}),
    ]
    return E


# ===========================================================================
# 5. 로비 화면 — 9-slice 판, 버튼, 입력칸, 카드, 로고, 배경
# ===========================================================================
DOT_TILE = ['N' * 8] * 8


def tile_pattern(base, dot):
    """8×8 안에서 끊김 없이 반복되는 잔점 무늬."""
    rows = []
    for y in range(8):
        r = ''
        for x in range(8):
            r += dot if (x, y) in ((1, 1), (5, 5)) else base
        rows.append(r)
    return grid(rows)


def framed(size, border, rings, center_base, center_dot=None, corner=2):
    img = rounded_box(size, size, rings + [center_base] * (border - len(rings)), center_base, corner=corner)
    if center_dot:
        t = tile_pattern(center_base, center_dot)
        img.paste(t, (border, border))
    return img


def button_img(face, light, dark, depth, pressed=False, accent=None):
    w = h = 24
    img = blank(w, h)
    px = img.load()
    for y in range(h):
        for x in range(w):
            cd = min(x, w - 1 - x) + min(y, h - 1 - y)
            if cd < 2:
                continue
            edge = x == 0 or y == 0 or x == w - 1 or y == h - 1 or cd == 2
            if edge:
                c = 'K'
            elif pressed:
                c = 'K' if y == 1 else dark if y == 2 else face
                if x == 1 and y > 2:
                    c = dark
            else:
                if y >= h - 1 - depth:
                    c = dark if y < h - 2 or True else dark
                    c = depth_col = dark
                elif y == 1 or x == 1:
                    c = light
                elif x == w - 2:
                    c = dark
                else:
                    c = face
                if y == h - 2 - depth and not (x == 1 or x == w - 2):
                    c = face
            px[x, y] = rgba(c)
    if not pressed:
        for x in range(2, w - 2):
            px[x, h - 2] = rgba('K' if depth else dark)
    if accent:
        for x in range(3, w - 3):
            px[x, 2] = rgba(accent)
    # 둥근 모서리 안쪽 점
    for (x, y) in [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)]:
        px[x, y] = rgba('K')
    return img


def input_img():
    return framed(24, 6, ['K', ('K', 'g'), ('N', 'n')], 'N')


def logo_img():
    scale = 8
    m = font_mask('인또')
    m = m.resize((m.width * scale, m.height * scale), Image.NEAREST)
    pad = 10
    W, H = m.width + pad * 2, m.height + pad * 2
    body = blank(W, H)
    bp, mp = body.load(), m.load()
    for y in range(m.height):
        for x in range(m.width):
            if not mp[x, y]:
                continue
            t = y / m.height
            c = 'k' if t < 0.2 else 'y' if t < 0.48 else 'Y' if t < 0.78 else 'O'
            # 획 아래쪽 두 줄 그늘, 위쪽 두 줄 반짝임
            below = y + 2 < m.height and mp[x, y + 2]
            above = y - 2 >= 0 and mp[x, y - 2]
            if not below:
                c = 'm'
            elif not above:
                c = 'W' if t < 0.6 else 'y'
            bp[x + pad, y + pad] = rgba(c)
    out = outline(body, 'B', diag=True)
    out = outline(out, 'B', diag=True)
    out = outline(out, 'K', diag=True)
    out = outline(out, 'K', diag=True)
    sh = out.copy()
    spx = sh.load()
    for y in range(H):
        for x in range(W):
            if spx[x, y][3]:
                spx[x, y] = rgba('N')
    res = blank(W + 4, H + 6)
    paste(res, sh, 2, 6)
    res.alpha_composite(out, (0, 0))
    wing = grid(LOGO_WING)
    wing = outline(wing, 'K')
    res2 = blank(res.width + 14, res.height + 6)
    paste(res2, flip(wing), 0, 0)
    paste(res2, res, 8, 6)
    paste(res2, wing, res2.width - wing.width, 0)
    return res2.crop(res2.getbbox())


LOGO_WING = [
    '.........WWWW..',
    '......WWWWWWWa.',
    '....WWWWWWWaa..',
    '...WWWWWWaa....',
    '..WWWWWaaWWWW..',
    '.WWWWaaaaaaa...',
    '.WWWaaWWWWWW...',
    'WWWaaaaaaaa....',
    'WWaaiiii.......',
    'Waii...........',
]


def lobby_bg():
    S = 128
    img = Image.new('RGBA', (S, S), rgba('N'))
    px = img.load()
    rnd = random.Random(42)
    # 아주 옅은 대각선 띠 — 점 무늬로만
    for y in range(S):
        for x in range(S):
            band = ((x + y) % 64) < 20
            if band and (x % 4 == 0 and y % 4 == 0):
                px[x, y] = rgba('n')
    # 작은 별과 구름 조각
    for _ in range(14):
        cx, cy = rnd.randrange(S), rnd.randrange(S)
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            px[(cx + dx) % S, (cy + dy) % S] = rgba('n' if (dx or dy) else 'g')
    for _ in range(20):
        cx, cy = rnd.randrange(S), rnd.randrange(S)
        px[cx, cy] = rgba('n')
    for _ in range(4):
        cx, cy = rnd.randrange(S), rnd.randrange(S)
        for dx in range(-5, 6):
            for dy in range(-2, 3):
                inside = (dx / 5.5) ** 2 + (dy / 2.5) ** 2 <= 1 or ((dx + 2) / 3) ** 2 + ((dy + 2) / 2) ** 2 <= 1
                if inside and (dx + dy) % 2 == 0:
                    px[(cx + dx) % S, (cy + dy) % S] = rgba('n')
    return img


def map_random():
    W, H = 160, 90
    img = Image.new('RGBA', (W, H), rgba('N'))
    px = img.load()
    themes = [('a', 'C', 'W'), ('q', 'P', 'p'), ('N', 'U', 'u')]
    for y in range(H):
        for x in range(W):
            band = min(2, max(0, int((x + y * 0.6) / 72)))
            a, b, c = themes[band]
            v = (y / H)
            col = a if v < 0.5 else b
            if (x + y) % 2 == 0 and 0.4 < v < 0.6:
                col = b if v < 0.5 else a
            if (x * 7 + y * 13) % 53 == 0:
                col = c
            px[x, y] = rgba(col)
    # 띠 사이 경계선
    for y in range(H):
        for k in (72, 144):
            x = int(k - y * 0.6)
            for d in (0, 1):
                if 0 <= x + d < W:
                    px[x + d, y] = rgba('K')
    q = pixel_text('?', 5, 'y', 'Y', 'K', light='k', shadow='N', ol_w=2)
    paste(img, q, (W - q.width) // 2, (H - q.height) // 2)
    return img


def ui_files():
    rings_panel = ['K', ('g', 'N'), 'n', 'n', ('Y', 'O'), 'K']
    rings_card = ['K', ('s', 'g'), 'g', ('n', 'N'), 'K']
    rings_card_sel = ['K', 'y', 'Y', ('O', 'm'), 'K']
    return {
        'panel.png': framed(24, 8, rings_panel, 'N', 'n'),
        'button.png': button_img('n', 'g', 'N', 2),
        'button_hover.png': button_img('g', 's', 'n', 2),
        'button_down.png': button_img('n', 'g', 'N', 0, pressed=True),
        'button_primary.png': button_img('Y', 'y', 'O', 2),
        'button_primary_hover.png': button_img('y', 'k', 'Y', 2),
        'input.png': input_img(),
        'card.png': framed(24, 8, rings_card, 'N', 'n'),
        'card_selected.png': framed(24, 8, rings_card_sel, 'n', 'g'),
        'logo.png': logo_img(),
        'lobby_bg.png': lobby_bg(),
        'map_random.png': map_random(),
    }


def nine_slice(img, b, w, h):
    """미리보기용 9-slice 그리기 — 테두리와 가운데를 반복으로 채운다."""
    W0, H0 = img.size
    out = blank(w, h)
    for (sx, sw, dx, dw) in [(0, b, 0, b), (b, W0 - 2 * b, b, w - 2 * b), (W0 - b, b, w - b, b)]:
        for (sy, sh, dy, dh) in [(0, b, 0, b), (b, H0 - 2 * b, b, h - 2 * b), (H0 - b, b, h - b, b)]:
            piece = img.crop((sx, sy, sx + sw, sy + sh))
            for yy in range(dy, dy + dh, sh):
                for xx in range(dx, dx + dw, sw):
                    cw, ch = min(sw, dx + dw - xx), min(sh, dy + dh - yy)
                    out.paste(piece.crop((0, 0, cw, ch)), (xx, yy))
    return out


# ===========================================================================
# 미리보기·검사
# ===========================================================================
def board(items, cols, bg, cell_pad=4, label_h=0):
    """(그림) 목록을 격자로 늘어놓은 판."""
    cw = max(i.width for i in items) + cell_pad * 2
    ch = max(i.height for i in items) + cell_pad * 2
    rows = (len(items) + cols - 1) // cols
    out = Image.new('RGBA', (cols * cw, rows * ch), bg)
    for k, im in enumerate(items):
        x = (k % cols) * cw + (cw - im.width) // 2
        y = (k // cols) * ch + (ch - im.height) // 2
        out.alpha_composite(im, (x, y))
    return out


def stack(images, gap=6, bg=(60, 60, 70, 255), horizontal=False):
    if horizontal:
        W = sum(i.width for i in images) + gap * (len(images) + 1)
        H = max(i.height for i in images) + gap * 2
    else:
        W = max(i.width for i in images) + gap * 2
        H = sum(i.height for i in images) + gap * (len(images) + 1)
    out = Image.new('RGBA', (W, H), bg)
    p = gap
    for im in images:
        if horizontal:
            out.alpha_composite(im, (p, gap))
            p += im.width + gap
        else:
            out.alpha_composite(im, (gap, p))
            p += im.height + gap
    return out


SPEC_FX = ['puff', 'nut', 'acorn', 'paper', 'boltSeg', 'boltHit', 'warn', 'oil', 'hit', 'shield', 'dash', 'revive',
           'pickup', 'whirl', 'fog', 'nice', 'kill']
SPEC_FX_SIZE = {'puff': (16, 16, 2), 'nut': (16, 16, 4), 'acorn': (16, 16, 2), 'paper': (16, 16, 4),
                'boltSeg': (16, 32, 3), 'boltHit': (32, 32, 3), 'warn': (24, 24, 2), 'oil': (48, 16, 2),
                'hit': (32, 32, 4), 'shield': (32, 32, 2), 'dash': (48, 24, 3), 'revive': (32, 32, 4),
                'pickup': (16, 16, 4), 'whirl': (24, 24, 3), 'fog': (96, 48, 1), 'nice': (64, 24, 1),
                'kill': (64, 24, 1)}
SPEC_ITEMS = {'gemBlue': 4, 'gemRed': 4, 'food': 2, 'feather': 4}
SPEC_UI = (['heartFull', 'heartEmpty', 'hpFrame', 'hpFill', 'hpFillLow', 'slotFrame', 'slotActive']
           + ['icon_' + k for k in ['puff', 'dash', 'cloud', 'bolt', 'shield', 'nut', 'repair', 'oil', 'acorn',
                                    'glide', 'whirl', 'paper', 'fold', 'pinwheel']]
           + ['rankRow', 'rankRowSelf', 'miniBar', 'miniMarker0', 'miniMarker1', 'miniMarker2', 'miniMarker3',
              'miniMarkerSelf', 'timerPlate', 'crown', 'check', 'ghostIcon', 'skull', 'featherIcon',
              'debuff_blind', 'debuff_heavy', 'debuff_shake', 'debuff_slow', 'buff_glide', 'buff_shrink',
              'teamA', 'teamB', 'num3', 'num2', 'num1', 'go',
              'pipFull', 'pipHalf', 'pipEmpty', 'keyMouseL', 'keyMouseR', 'keySpace', 'keyUp', 'keyRight',
              'keyEnter', 'keyW', 'keyD', 'keyM'])
SPEC_UI_SIZE = {'heartFull': (13, 12), 'heartEmpty': (13, 12), 'hpFrame': (106, 12), 'hpFill': (1, 6),
                'hpFillLow': (1, 6), 'slotFrame': (26, 26), 'slotActive': (30, 30), 'rankRow': (150, 18),
                'rankRowSelf': (150, 18), 'miniBar': (240, 12), 'miniMarker0': (7, 8), 'miniMarker1': (7, 8),
                'miniMarker2': (7, 8), 'miniMarker3': (7, 8), 'miniMarkerSelf': (9, 10), 'timerPlate': (64, 20),
                'teamA': (14, 14), 'teamB': (14, 14), 'pipFull': (7, 7), 'pipHalf': (7, 7), 'pipEmpty': (7, 7)}
CHARS = ['mongsil', 'kkangdong', 'doto', 'palang']
LOBBY_FILES = ['panel.png', 'button.png', 'button_hover.png', 'button_down.png', 'button_primary.png',
               'button_primary_hover.png', 'input.png', 'card.png', 'card_selected.png', 'logo.png', 'lobby_bg.png',
               'map_random.png']


def validate():
    problems = []

    def check_json(path, names=None):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        img_path = os.path.join(os.path.dirname(path), data['image'])
        if not os.path.exists(img_path):
            problems.append('%s: 그림 없음 %s' % (path, img_path))
            return data, None
        im = Image.open(img_path)
        W, H = im.size
        fw, fh = data.get('frameWidth'), data.get('frameHeight')
        for name, a in data['animations'].items():
            for fr in a['frames']:
                if isinstance(fr, list):
                    x, y, w, h = fr
                else:
                    cols = W // fw
                    x, y, w, h = (fr % cols) * fw, (fr // cols) * fh, fw, fh
                if x < 0 or y < 0 or x + w > W or y + h > H:
                    problems.append('%s: %s 프레임 %s가 그림 밖' % (path, name, fr))
        for n in names or []:
            if n not in data['animations']:
                problems.append('%s: 이름 없음 %s' % (path, n))
        return data, im

    for c in CHARS:
        d, im = check_json(os.path.join(OUT, 'characters', c, 'sprite.json'), ['fly', 'boost', 'hurt', 'ghost'])
        if im is not None and im.size != (288, 32):
            problems.append('%s 시트 크기 %s' % (c, im.size))
        if d.get('hitRadius') != 8:
            problems.append('%s hitRadius' % c)
        p = Image.open(os.path.join(OUT, 'characters', c, 'portrait.png'))
        if p.size != (48, 48):
            problems.append('%s 초상 크기 %s' % (c, p.size))
    if Image.open(os.path.join(OUT, 'characters', 'random', 'portrait.png')).size != (48, 48):
        problems.append('random 초상 크기')
    d, _ = check_json(os.path.join(OUT, 'items', 'items.json'), list(SPEC_ITEMS))
    for n, cnt in SPEC_ITEMS.items():
        fr = d['animations'][n]['frames']
        if len(fr) != cnt or any(f[2:] != [16, 16] for f in fr):
            problems.append('items %s 프레임 수·크기' % n)
    d, _ = check_json(os.path.join(OUT, 'fx', 'fx.json'), SPEC_FX)
    for n, (w, h, cnt) in SPEC_FX_SIZE.items():
        fr = d['animations'][n]['frames']
        if len(fr) != cnt or any(f[2:] != [w, h] for f in fr):
            problems.append('fx %s 프레임 수·크기 %s' % (n, [f[2:] for f in fr]))
    d, _ = check_json(os.path.join(OUT, 'ui', 'ui.json'), SPEC_UI)
    for n, (w, h) in SPEC_UI_SIZE.items():
        if any(f[2:] != [w, h] for f in d['animations'][n]['frames']):
            problems.append('ui %s 크기 %s' % (n, d['animations'][n]['frames']))
    for n in ['icon_' + k for k in ['puff', 'dash', 'cloud', 'bolt', 'shield', 'nut', 'repair', 'oil', 'acorn',
                                    'glide', 'whirl', 'paper', 'fold', 'pinwheel']]:
        if d['animations'][n]['frames'][0][2:] != [18, 18]:
            problems.append('ui %s 크기' % n)
    for n in ['crown', 'check', 'ghostIcon', 'skull', 'featherIcon']:
        w, h = d['animations'][n]['frames'][0][2:]
        if w > 11 or h > 10:
            problems.append('ui %s 크기 %dx%d' % (n, w, h))
    for n in ['debuff_blind', 'debuff_heavy', 'debuff_shake', 'debuff_slow', 'buff_glide', 'buff_shrink']:
        if d['animations'][n]['frames'][0][2:] != [12, 12]:
            problems.append('ui %s 크기' % n)
    for n in ['num3', 'num2', 'num1', 'go']:
        w, h = d['animations'][n]['frames'][0][2:]
        if w > 64 or h > 48:
            problems.append('ui %s 크기' % n)
    if len(d['animations']['slotActive']['frames']) != 2:
        problems.append('slotActive 프레임 수')
    sizes = {'logo.png': None, 'lobby_bg.png': (128, 128), 'map_random.png': (160, 90)}
    for f in LOBBY_FILES:
        p = os.path.join(OUT, 'ui', f)
        if not os.path.exists(p):
            problems.append('없음 ' + f)
            continue
        s = Image.open(p).size
        if f in sizes and sizes[f] and s != sizes[f]:
            problems.append('%s 크기 %s' % (f, s))
        if f not in sizes and s != (24, 24):
            problems.append('%s 크기 %s' % (f, s))
    return problems


def main():
    # 1. 캐릭터
    sheets = {}
    builders = {'mongsil': build_mongsil, 'kkangdong': build_kkangdong, 'doto': build_doto, 'palang': build_palang}
    portraits = {}
    for cid, fn in builders.items():
        frames = fn()
        px_, py_ = PORTRAIT_CROP[cid]
        portraits[cid] = portrait_from(frames[1], px_, py_)
        sheets[cid] = (frames, write_character(cid, frames, portraits[cid]))
    portraits['random'] = random_portrait()
    save(portraits['random'], 'characters', 'random', 'portrait.png')

    # 2. 아이템, 3. 효과
    item_e = item_frames()
    items_atlas, _ = write_atlas('items', 'items', item_e, 64)
    fx_e = fx_entries()
    fx_atlas, _ = write_atlas('fx', 'fx', fx_e, 256)

    # 4. HUD
    hud_e = hud_entries()
    ui_atlas, _ = write_atlas('ui', 'ui', hud_e, 256)

    # 5. 로비
    lobby = ui_files()
    for name, im in lobby.items():
        save(im, 'ui', name)

    # 미리보기
    rows = []
    for cid in CHARS:
        frames = sheets[cid][0]
        rows.append(preview_strip(frames + [center_on(portraits[cid], 48, 48)], 1))
    rows.append(preview_strip([portraits['random']], 1))
    save_preview(up(stack(rows), 4), 'sprites_characters.png')

    fx_boards = []
    for bg in (SKY_DAY, SKY_NIGHT):
        fx_boards.append(board([f for _, fs, _ in item_e for f in fs], 16, bg))
        fx_boards.append(board([f for _, fs, _ in fx_e for f in fs if f.width <= 32], 14, bg))
        fx_boards.append(board([f for _, fs, _ in fx_e for f in fs if f.width > 32], 8, bg))
    save_preview(up(stack(fx_boards), 4), 'sprites_items_fx.png')

    hud_items = [f for _, fs, _ in hud_e for f in fs]
    small = [f for f in hud_items if f.width <= 64]
    wide = [f for f in hud_items if f.width > 64]
    navy = rgba('N')
    sample = Image.new('RGBA', (300, 70), SKY_DAY)
    hp = blank(106, 12)
    hp.alpha_composite(hp_frame())
    fill = grid(['G', 'G', 'G', 'G', 'h', 'H']).resize((70, 6), Image.NEAREST)
    hp.alpha_composite(fill, (3, 3))
    sample.alpha_composite(hp, (4, 4))
    for k in range(2):
        sample.alpha_composite(grid(HEART_FULL), (114 + k * 14, 4))
    sample.alpha_composite(grid(HEART_EMPTY), (142, 4))
    icons = [f for n, fs, _ in hud_e if n.startswith('icon_') for f in fs]
    for k in range(5):
        sl = slot_frame()
        sl.alpha_composite(icons[k], (4, 4))
        sample.alpha_composite(sl, (6 + k * 30, 22))
    sample.alpha_composite(slot_active(0), (4, 20))
    sample.alpha_composite(timer_plate(), (170, 22))
    hud_prev = stack([board(small, 12, navy), board(small, 12, SKY_DAY), board(wide, 2, navy), sample])
    save_preview(up(hud_prev, 3), 'sprites_hud.png')

    pieces = []
    for name in ['panel.png', 'card.png', 'card_selected.png']:
        pieces.append(nine_slice(lobby[name], 8, 72, 48))
    for name in ['button.png', 'button_hover.png', 'button_down.png', 'button_primary.png',
                 'button_primary_hover.png', 'input.png']:
        pieces.append(nine_slice(lobby[name], 6, 64, 22))
    raw = [lobby[n] for n in LOBBY_FILES if lobby[n].size == (24, 24)]
    tiled_bg = Image.new('RGBA', (256, 128))
    for x in (0, 128):
        tiled_bg.paste(lobby['lobby_bg.png'], (x, 0))
    lob = stack([board(raw, 9, (60, 60, 70, 255)), board(pieces, 3, (60, 60, 70, 255)),
                 board([lobby['logo.png']], 1, rgba('N')), board([lobby['logo.png']], 1, SKY_DAY),
                 stack([tiled_bg, lobby['map_random.png'], portraits['random']], horizontal=True)])
    save_preview(up(lob, 3), 'sprites_lobby.png')

    problems = validate()
    if problems:
        print('검사 실패:')
        for p in problems:
            print(' -', p)
        raise SystemExit(1)
    print('완료: 캐릭터 %d, 아이템 %d, 효과 %d, HUD %d, 로비 %d' % (
        len(CHARS), len(item_e), len(fx_e), len(hud_e), len(lobby)))


if __name__ == '__main__':
    main()
