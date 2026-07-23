# pipeline/assets/generate_conclusion_background.py
"""
assets/backgrounds/conclusion_market.jpg를 생성합니다.

builders.build_conclusion()("오늘의 한 줄 결론" 화면)이 배경으로 쓰는 정적
이미지입니다. 이 화면은 매일 문구만 바뀌는 고정 코너라 매번 외부 이미지
검색(연합뉴스/KBS API)에 의존할 이유가 없고, 검색이 실패하면 배경 없이
밋밋한 카드로 나오는 문제도 있었습니다 — generate_sector_fallback_images.py와
같은 방식(PIL로 그린 추상 그래픽, 실사 대체가 아닌 안정적인 브랜드 배경)으로
"증권거래소 전광판" 느낌의 이미지를 미리 만들어 고정으로 씁니다.

구성: 어두운 전광판 배경 위에 상승/하락 색상의 시세 셀(칸) 그리드를 채우고
(실제 종목 코드나 사명이 아닌 무작위 숫자 — 특정 종목을 지칭하지 않음),
사진처럼 보이도록 전체에 강한 가우시안 블러를 적용해 아웃포커스된 전광판
사진 느낌을 낸다. 글자는 이 이미지에 굽지 않는다 — 실제 타이틀/헤드라인
텍스트는 builders.build_conclusion()이 text_plate()로 위에 얹는다(문구가
매일 바뀌므로 이미지에 고정 텍스트를 구우면 안 됨).

실행: python pipeline/assets/generate_conclusion_background.py
"""
import os
import random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, "..", "..", "assets", "backgrounds")
OUT_PATH = os.path.join(OUT_DIR, "conclusion_market.jpg")

W, H = 1920, 1080

UP   = (224, 57, 62)    # PALETTE["up"] (red, 한국 증권가 관행상 상승)
DOWN = (47, 111, 237)   # PALETTE["down"] (blue, 하락)
FLAT = (90, 96, 110)    # 보합


def _load_font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_ticker_board(rng: random.Random) -> Image.Image:
    """전광판처럼 촘촘한 시세 셀 그리드를 그린다. 특정 종목을 지칭하지 않는
    무작위 숫자/등락률만 채운다."""
    img = Image.new("RGB", (W, H), (8, 9, 13))
    draw = ImageDraw.Draw(img)

    cell_w, cell_h = 96, 58
    gap = 6
    cols = W // (cell_w + gap) + 1
    rows = H // (cell_h + gap) + 1
    font_price = _load_font(20)
    font_chg = _load_font(15)

    for r in range(rows):
        for c in range(cols):
            x0 = c * (cell_w + gap)
            y0 = r * (cell_h + gap)
            x1, y1 = x0 + cell_w, y0 + cell_h
            roll = rng.random()
            color = UP if roll < 0.42 else (DOWN if roll < 0.80 else FLAT)
            cell_bg = (color[0] // 6, color[1] // 6, color[2] // 6)
            draw.rectangle([x0, y0, x1, y1], fill=cell_bg, outline=(30, 32, 38))
            price = rng.randint(1000, 99000)
            pct = rng.uniform(0.1, 9.9)
            arrow = "▲" if color is UP else ("▼" if color is DOWN else "-")
            draw.text((x0 + 8, y0 + 8), f"{price:,}", font=font_price, fill=(*color, 255))
            draw.text((x0 + 8, y0 + 32), f"{arrow} {pct:.2f}%", font=font_chg, fill=(*color, 220))

    return img


def render() -> str:
    rng = random.Random(20260722)  # 고정 시드 — 매번 같은(재현 가능한) 그래픽
    img = _draw_ticker_board(rng)

    # 전광판을 실제로 카메라 아웃포커스로 찍은 사진처럼 강하게 블러 처리한다
    # ("흐릿하게 처리" 요구사항) — 위에 얹히는 텍스트 판의 가독성도 함께 높인다.
    img = img.filter(ImageFilter.GaussianBlur(9))

    # 좌상단(텍스트 판이 얹힐 영역) 가독성 보강 비네트 — 왼쪽일수록/위쪽일수록 어둡게
    vgrad = Image.new("L", (W, 1))
    for x in range(W):
        t = max(0.0, 1.0 - x / (W * 0.7))
        vgrad.putpixel((x, 0), int(160 * t))
    vgrad = vgrad.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, vgrad)

    # 전체적으로 살짝 어둡게 눌러 텍스트 대비를 한 번 더 보강
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, dark, alpha=0.18)

    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(OUT_PATH, "JPEG", quality=90)
    return OUT_PATH


if __name__ == "__main__":
    path = render()
    print(f"✅ 완료: {path}")
