# pipeline/assets/generate_panel_avatars.py
"""
assets/character/avatar_01.png ~ avatar_10.png를 생성합니다.

builders._build_mention_page()("전문가·방송 언급" 화면)이 쓰는 일러스트
아바타입니다. 영상 속 실제 발언자의 얼굴을 추출해 캐리커처로 재구성하는
방식은 (1) 이 파이프라인에 영상 다운로드/프레임 추출 기능이 없어 별도의
큰 작업이 필요하고, (2) 실제 인물의 얼굴을(스타일화하더라도) 본인 동의 없이
재사용하면 초상권 문제가 생길 수 있어, 대신 "실제 인물과의 일치 여부는
고려하지 않는" 일반화된 일러스트 아바타 10종을 채널 유형/발언자 이름
해시로 결정적으로 배정한다(panel_avatars.get_avatar_path 참고) — 같은
발언자는 항상 같은 아바타를 쓰지만, 실존 인물을 지칭하지는 않는다.

스타일: 단순한 평면(flat) 벡터풍 반신 일러스트 원형 배지. 브랜드 액센트
컬러(_ACCENT_CYCLE)를 배경으로 순환시켜 화면에 여러 명이 연달아 나와도
단조롭지 않게 한다.

실행: python pipeline/assets/generate_panel_avatars.py
"""
import os
from PIL import Image, ImageDraw

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, "..", "..", "assets", "character")

W, H = 480, 480
CX, CY = W // 2, H // 2
R = W // 2

_ACCENT_CYCLE = [
    (14, 159, 142),   # teal
    (242, 163, 65),   # amber
    (224, 57, 62),    # red
    (160, 91, 214),   # violet
    (47, 111, 237),   # blue
    (37, 180, 120),   # green
    (216, 119, 71),   # burnt orange
    (14, 159, 142),
    (242, 163, 65),
    (224, 57, 62),
]

_SKIN_TONES = [(255, 219, 172), (240, 184, 135), (198, 134, 66)]

# (skin_idx, hair_style, hair_color, glasses, headset, blazer_color)
_AVATARS = [
    (0, "short",  (40, 32, 26),   False, False, (34, 45, 66)),
    (1, "long",   (90, 60, 40),   True,  False, (58, 42, 74)),
    (2, "bald",   None,           False, False, (70, 30, 32)),
    (0, "short_gray", (150, 150, 150), True, False, (46, 38, 70)),
    (1, "bun",    (30, 26, 22),   False, False, (24, 60, 92)),
    (2, "short",  (60, 42, 30),   False, True,  (24, 80, 60)),
    (0, "long_gray", (190, 190, 190), True, False, (88, 52, 30)),
    (1, "short",  (25, 22, 20),   False, True,  (24, 45, 66)),
    (2, "curly",  (35, 28, 24),   True,  False, (70, 50, 20)),
    (0, "short_red", (110, 55, 40), False, False, (30, 55, 90)),
]


def _draw_hair(draw, skin_color, style, color):
    if style == "bald":
        return
    if style in ("short", "short_gray", "short_red"):
        draw.pieslice([CX - 95, CY - 175, CX + 95, CY + 15], 180, 360, fill=color)
    elif style in ("long", "long_gray"):
        draw.pieslice([CX - 100, CY - 175, CX + 100, CY + 20], 180, 360, fill=color)
        draw.rectangle([CX - 100, CY - 60, CX - 80, CY + 60], fill=color)
        draw.rectangle([CX + 80, CY - 60, CX + 100, CY + 60], fill=color)
    elif style == "bun":
        draw.pieslice([CX - 95, CY - 172, CX + 95, CY + 10], 180, 360, fill=color)
        draw.ellipse([CX - 28, CY - 205, CX + 28, CY - 155], fill=color)
    elif style == "curly":
        for dx, dy, rr in [(-70, -140, 34), (-30, -165, 36), (10, -170, 36),
                            (50, -150, 34), (75, -110, 30), (-85, -100, 28)]:
            draw.ellipse([CX + dx - rr, CY + dy - rr, CX + dx + rr, CY + dy + rr], fill=color)


def _draw_avatar(bg_color, skin_color, hair_style, hair_color, glasses, headset, blazer_color) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 원형 배지 배경
    draw.ellipse([0, 0, W, H], fill=(*bg_color, 255))

    # 블레이저/어깨
    draw.pieslice([CX - 150, CY + 40, CX + 150, CY + 340], 180, 360, fill=(*blazer_color, 255))
    # 셔츠 깃(살짝 밝은 톤으로 대비)
    draw.polygon([(CX - 26, CY + 70), (CX, CY + 100), (CX + 26, CY + 70),
                  (CX + 14, CY + 130), (CX - 14, CY + 130)], fill=(235, 235, 235, 255))

    # 목
    draw.rectangle([CX - 22, CY + 45, CX + 22, CY + 90], fill=(*skin_color, 255))

    # 얼굴
    draw.ellipse([CX - 78, CY - 95, CX + 78, CY + 65], fill=(*skin_color, 255))

    # 머리(얼굴보다 먼저/나중 순서 신경 — 뒷머리는 이미 그렸으니 여기서는 없음)
    _draw_hair(draw, skin_color, hair_style, hair_color)

    # 눈
    draw.ellipse([CX - 40, CY - 15, CX - 24, CY - 1], fill=(40, 32, 28, 255))
    draw.ellipse([CX + 24, CY - 15, CX + 40, CY - 1], fill=(40, 32, 28, 255))

    # 눈썹
    draw.line([(CX - 42, CY - 26), (CX - 20, CY - 30)], fill=(60, 45, 38, 255), width=4)
    draw.line([(CX + 20, CY - 30), (CX + 42, CY - 26)], fill=(60, 45, 38, 255), width=4)

    # 코
    draw.line([(CX, CY - 5), (CX - 6, CY + 18)], fill=(190, 150, 120, 255), width=3)

    # 입(살짝 미소)
    draw.arc([CX - 26, CY + 20, CX + 26, CY + 46], 20, 160, fill=(120, 60, 55, 255), width=4)

    # 안경(선택)
    if glasses:
        lens_color = (30, 30, 34, 230)
        for sign in (-1, 1):
            lx = CX + sign * 32
            draw.ellipse([lx - 26, CY - 20, lx + 26, CY + 12], outline=lens_color, width=5)
        draw.line([(CX - 6, CY - 8), (CX + 6, CY - 8)], fill=lens_color, width=5)

    # 앞머리(짧은/처진 스타일은 이마 위에 살짝 덮어줘야 자연스러움)
    if hair_style in ("short", "short_gray", "short_red", "curly"):
        draw.pieslice([CX - 78, CY - 95, CX + 78, CY - 20], 180, 360, fill=(*hair_color, 255))

    # 헤드셋 마이크(방송 출연자 느낌, 선택) — 머리 위에 얹히므로 앞머리보다 나중에 그려야
    # 가려지지 않는다.
    if headset:
        mic_color = (25, 25, 28, 255)
        draw.arc([CX - 82, CY - 100, CX + 82, CY + 10], 200, 340, fill=mic_color, width=7)
        draw.line([(CX + 60, CY - 30), (CX + 20, CY + 30)], fill=mic_color, width=5)
        draw.ellipse([CX + 12, CY + 24, CX + 28, CY + 40], fill=mic_color)

    return img


def render() -> list:
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = []
    for i, (skin_idx, hair_style, hair_color, glasses, headset, blazer_color) in enumerate(_AVATARS, start=1):
        bg_color = _ACCENT_CYCLE[(i - 1) % len(_ACCENT_CYCLE)]
        skin_color = _SKIN_TONES[skin_idx]
        img = _draw_avatar(bg_color, skin_color, hair_style, hair_color or (0, 0, 0),
                            glasses, headset, blazer_color)
        out_path = os.path.join(OUT_DIR, f"avatar_{i:02d}.png")
        img.save(out_path, "PNG")
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    paths = render()
    print(f"✅ 완료: {len(paths)}개 아바타 → {OUT_DIR}")
