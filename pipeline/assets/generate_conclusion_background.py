# pipeline/assets/generate_conclusion_background.py
"""
assets/backgrounds/conclusion_market.jpg를 생성합니다.

builders.build_conclusion()("오늘의 한 줄 결론" 화면)이 배경으로 쓰는 정적
이미지입니다. 이 화면은 매일 문구만 바뀌는 고정 코너라 매번 외부 이미지
검색(연합뉴스/KBS API)에 의존할 이유가 없고, 검색이 실패하면 배경 없이
밋밋한 카드로 나오는 문제도 있었습니다 — generate_sector_fallback_images.py와
같은 방식(PIL로 그린 추상 그래픽, 실사 대체가 아닌 안정적인 브랜드 배경)으로
"한국 주식시장"을 상징하는 대표 이미지 한 장을 미리 만들어 고정으로 씁니다.

구성: 짙은 금융 테마 그라디언트 + 우상향 캔들스틱 차트 실루엣 + 거래소 건물
실루엣(창문 그리드) + 브랜드 도트 텍스처 + 하단 비네트(텍스트 판이 얹힐
영역 가독성 보강). 글자는 이 이미지에 굽지 않는다 — 실제 타이틀/헤드라인
텍스트는 builders.build_conclusion()이 text_plate()로 위에 얹는다(문구가
매일 바뀌므로 이미지에 고정 텍스트를 구우면 안 됨).

실행: python pipeline/assets/generate_conclusion_background.py
"""
import os
import random
from PIL import Image, ImageDraw, ImageFilter

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, "..", "..", "assets", "backgrounds")
OUT_PATH = os.path.join(OUT_DIR, "conclusion_market.jpg")

W, H = 1920, 1080

ACCENT = (14, 159, 142)   # PALETTE["accent"] (teal)
UP     = (224, 57, 62)    # PALETTE["up"] (red, 한국 증권가 관행상 상승)
DOWN   = (47, 111, 237)   # PALETTE["down"] (blue, 하락)


def _make_gradient(size, top, bottom):
    small = Image.new("RGB", (1, size[1]))
    for y in range(size[1]):
        t = y / max(size[1] - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        small.putpixel((0, y), (r, g, b))
    return small.resize(size, Image.BILINEAR)


def _draw_candlestick_chart(img: Image.Image) -> Image.Image:
    """화면 우측 하단에 우상향하는 캔들스틱 실루엣을 그린다 — '주가그래프' 요소."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    n = 22
    chart_left, chart_right = int(W * 0.46), int(W * 0.97)
    chart_bottom = int(H * 0.92)
    baseline_top = int(H * 0.55)
    candle_w = (chart_right - chart_left) / n * 0.55
    gap = (chart_right - chart_left) / n

    rng = random.Random(20260722)  # 고정 시드 — 매번 같은(재현 가능한) 그래픽
    trend_top = chart_bottom
    for i in range(n):
        # 우상향 추세 + 약간의 굴곡(완전 직선은 부자연스러움)
        progress = i / (n - 1)
        wobble = rng.uniform(-18, 18)
        top_y = chart_bottom - (chart_bottom - baseline_top) * (progress ** 0.85) + wobble
        top_y = max(baseline_top, min(chart_bottom - 20, top_y))
        body_h = rng.uniform(26, 60)
        bottom_y = min(chart_bottom, top_y + body_h)
        is_up = rng.random() < 0.68  # 우상향 추세이므로 양봉 비중을 높게
        color = UP if is_up else DOWN
        x0 = chart_left + i * gap
        x1 = x0 + candle_w
        cx = (x0 + x1) / 2
        # 몸통
        draw.rectangle([x0, top_y, x1, bottom_y], fill=(*color, 235))
        # 위/아래 꼬리
        wick_top = top_y - rng.uniform(8, 22)
        wick_bottom = bottom_y + rng.uniform(8, 22)
        draw.line([(cx, wick_top), (cx, top_y)], fill=(*color, 235), width=3)
        draw.line([(cx, bottom_y), (cx, wick_bottom)], fill=(*color, 235), width=3)

    layer = layer.filter(ImageFilter.GaussianBlur(0.6))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def _draw_exchange_building(img: Image.Image) -> Image.Image:
    """화면 좌측에 거래소/금융가 스카이라인 실루엣을 그린다 — '한국거래소' 요소.
    실사 로고/특정 건물 재현이 아니라 "금융가 빌딩" 느낌의 추상 실루엣이다."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    base_y = int(H * 0.94)
    buildings = [
        # (x0, width, height, has_spire)
        (int(W * 0.03), 130, 420, False),
        (int(W * 0.10), 90,  300, False),
        (int(W * 0.16), 150, 560, True),   # 중앙 랜드마크(거래소 타워 느낌)
        (int(W * 0.245), 100, 360, False),
        (int(W * 0.305), 120, 460, False),
        (int(W * 0.37), 80,  260, False),
    ]
    silhouette = (18, 26, 36, 255)
    window_lit = (255, 214, 102, 130)  # 창문 불빛 = 따뜻한 노랑(하이라이트 톤) — 어두운 실루엣과 대비

    rng = random.Random(720)
    for x0, bw, bh, spire in buildings:
        top = base_y - bh
        draw.rectangle([x0, top, x0 + bw, base_y], fill=silhouette)
        if spire:
            spire_h = 90
            cx = x0 + bw / 2
            draw.polygon(
                [(cx - 8, top), (cx + 8, top), (cx + 3, top - spire_h), (cx - 3, top - spire_h)],
                fill=silhouette,
            )
        # 창문 그리드(듬성듬성 불 켜진 것처럼)
        rows = max(3, bh // 34)
        cols = max(2, bw // 26)
        for r in range(rows):
            for c in range(cols):
                if rng.random() < 0.45:
                    wx = x0 + 10 + c * (bw - 20) / max(cols - 1, 1)
                    wy = top + 16 + r * (bh - 32) / max(rows - 1, 1)
                    draw.rectangle([wx, wy, wx + 6, wy + 9], fill=window_lit)

    layer = layer.filter(ImageFilter.GaussianBlur(0.4))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def render() -> str:
    img = _make_gradient((W, H), (16, 20, 28), (6, 7, 10)).convert("RGB")

    # 액센트 글로우(브랜드 포인트) — 우측 상단
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy, r = int(W * 0.80), int(H * 0.22), int(W * 0.30)
    glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    img = Image.blend(img, glow, alpha=0.28)

    # 도트 그리드 텍스처(브랜드 라이트 테마 .dot 패턴의 다크 버전)
    draw = ImageDraw.Draw(img, "RGBA")
    step = 48
    for gx in range(0, W, step):
        for gy in range(0, H, step):
            draw.ellipse([gx, gy, gx + 2, gy + 2], fill=(255, 255, 255, 14))

    img = _draw_exchange_building(img)
    img = _draw_candlestick_chart(img).convert("RGB")

    # 좌상단(텍스트 판이 얹힐 영역) 가독성 보강 비네트 — 왼쪽일수록/위쪽일수록 어둡게
    vgrad = Image.new("L", (W, 1))
    for x in range(W):
        t = max(0.0, 1.0 - x / (W * 0.65))
        vgrad.putpixel((x, 0), int(140 * t))
    vgrad = vgrad.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, vgrad)

    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(OUT_PATH, "JPEG", quality=90)
    return OUT_PATH


if __name__ == "__main__":
    path = render()
    print(f"✅ 완료: {path}")
