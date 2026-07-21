# pipeline/assets/generate_sector_fallback_images.py
"""
assets/sector_fallback/*.jpg를 생성합니다.

실제 뉴스 이미지 검색(연합뉴스/KBS 등)이 API 키 미설정 등으로 실패했을 때
media_pipeline.py/GeneratedAbstractConnector가 최종 안전망으로 쓰는 로컬
배경 이미지입니다. 지금까지 이 폴더가 비어 있어(.gitkeep만 존재) 검색 실패 시
어떤 배경도 나오지 않는 문제가 있었습니다 — 이 스크립트로 섹터별 추상
그래픽을 생성해 채웁니다.

실사 대체가 아니라 "이미지가 전혀 없는 것"보다 나은 임시 안전망입니다.
실제 사진 소스(KBS/연합뉴스 API 등)가 준비되면 검색이 우선 사용되고,
이 파일들은 검색 실패 시에만 쓰입니다.

실행: python pipeline/assets/generate_sector_fallback_images.py
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, "..", "..", "assets", "sector_fallback")

W, H = 1920, 1080

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]

# 브랜드 액센트 컬러 순환(html_theme.py PALETTE의 accent/up/down 계열과 어울리는
# 톤으로 섹터마다 다르게 배정 — 같은 씬 안에서 여러 섹터가 연달아 나와도
# 단조롭지 않도록).
_ACCENT_CYCLE = [
    (14, 159, 142),   # teal (accent)
    (242, 163, 65),   # amber
    (224, 57, 62),    # red (up)
    (160, 91, 214),   # violet
    (47, 111, 237),   # blue (down)
    (37, 180, 120),   # green
    (216, 119, 71),   # burnt orange
]

SECTORS_KO = [
    "2차전지", "건설", "금융", "기타", "바이오/제약", "반도체", "방산", "부품",
    "에너지", "엔터", "유통", "인터넷/게임", "자동차", "전력기기", "조선",
    "철강/소재", "항공", "화장품/뷰티",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size, index=0)
    return ImageFont.load_default()


def _make_gradient(size, top, bottom):
    """작은 캔버스에 선형 그라디언트를 그린 뒤 업스케일 — 픽셀 단위 루프보다 훨씬 빠름."""
    small = Image.new("RGB", (1, size[1]))
    for y in range(size[1]):
        t = y / max(size[1] - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        small.putpixel((0, y), (r, g, b))
    return small.resize(size, Image.BILINEAR)


def _render_one(label: str, accent: tuple, out_path: str) -> None:
    # 1) 다크 금융 테마 배경(짙은 차콜 → 거의 검정 그라디언트)
    img = _make_gradient((W, H), (24, 27, 34), (8, 9, 12)).convert("RGB")

    # 2) 액센트 컬러 글로우(오프센터 원형 블러) — 은은한 브랜드 포인트
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy, r = int(W * 0.78), int(H * 0.28), int(W * 0.32)
    glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    img = Image.blend(img, glow, alpha=0.35)

    # 3) 도트 그리드 텍스처(라이트 테마의 .dot 패턴과 톤을 맞춘 다크 버전)
    draw = ImageDraw.Draw(img, "RGBA")
    step = 48
    for gx in range(0, W, step):
        for gy in range(0, H, step):
            draw.ellipse([gx, gy, gx + 2, gy + 2], fill=(255, 255, 255, 18))

    # 4) 큰 섹터 라벨을 아주 옅게 텍스처로 얹음(가독 목적이 아니라 질감용)
    font = _load_font(340)
    label_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    label_draw = ImageDraw.Draw(label_layer)
    bbox = label_draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    label_draw.text((W - tw - 60 - bbox[0], H - th - 40 - bbox[1]), label,
                     font=font, fill=(255, 255, 255, 20))
    img = Image.alpha_composite(img.convert("RGBA"), label_layer).convert("RGB")

    # 5) 하단 비네트(텍스트 플레이트/티커가 얹힐 영역 가독성 보강)
    grad = Image.new("L", (1, H))
    for y in range(H):
        t = max(0.0, (y - H * 0.55) / (H * 0.45))
        grad.putpixel((0, y), int(120 * t))
    grad = grad.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, grad)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=88)


def run() -> None:
    for i, sector in enumerate(SECTORS_KO):
        accent = _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)]
        out_path = os.path.join(OUT_DIR, f"{sector}.jpg")
        _render_one(sector, accent, out_path)
        print(f"  ✅ {sector}.jpg")

    _render_one("KBS 머니올라", _ACCENT_CYCLE[0], os.path.join(OUT_DIR, "default.jpg"))
    print("  ✅ default.jpg")
    print(f"\n✅ 완료: {len(SECTORS_KO) + 1}개 → {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    run()
