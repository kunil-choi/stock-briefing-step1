# pipeline/assets/html_theme.py
"""
'PPT 슬라이드'를 만든다는 관점의 HTML/CSS 디자인 시스템.
NotebookLM 스타일 참고: 밝은 배경 + 점그리드, 민트/틸 액센트 + 노란 하이라이트,
큰 볼드 타이포, 말풍선형 인용 카드, 심플한 표. 한국 증권가 관행(상승=빨강/하락=파랑)은 유지.
"""
import os
import re
import base64
import mimetypes
import html as _he
from datetime import date
from .config import SUBTITLE_ZONE_TOP

W, H = 1920, 1080
SUBTITLE_BAR_H = H - SUBTITLE_ZONE_TOP  # 화면 하단 자막 전용 고정 여백(px). 슬라이드 콘텐츠는 이 영역을 절대 침범하지 않음.

# 각 슬라이드 상단바에 표시할 날짜. generate_assets.py가 script.json의 실제 브리핑
# 날짜로 최초 1회 설정한다 — 설정하지 않으면 렌더링 시점의 시스템 날짜로 폴백하는데,
# 워크플로우가 브리핑 생성 완료 전에 캐시된 이전 데이터로 실행되면 날짜가 실제
# 브리핑 내용과 어긋나는 문제가 있었다.
_BRIEFING_DATE_STR = ""


def set_briefing_date(date_str: str) -> None:
    global _BRIEFING_DATE_STR
    _BRIEFING_DATE_STR = date_str or ""


# 3차 작업: 하단 뉴스 티커. set_briefing_date()와 동일한 패턴(전역 상태 1회
# 설정 → shell()이 매 호출마다 자동 소비)으로, 모든 shell() 기반 빌더 호출부를
# 일일이 고치지 않고 generate_assets.py가 한 번만 설정하면 된다.
_TICKER_TEXT = ""
_TICKER_TONE = "neutral"


def set_ticker_text(text: str, tone: str = "neutral") -> None:
    global _TICKER_TEXT, _TICKER_TONE
    _TICKER_TEXT = text or ""
    _TICKER_TONE = tone

PALETTE = {
    "bg":           "#faf9f6",
    "dot":          "#e6e4dc",
    "ink":          "#16181d",
    "muted":        "#6b7280",
    "accent":       "#0e9f8e",
    "accent_soft":  "#e3f7f3",
    "highlight":    "#ffe066",
    "up":           "#e0393e",
    "down":         "#2f6fed",
    "card":         "#ffffff",
    "border":       "#e8e6df",
    "shadow":       "rgba(20,20,20,.08)",
}

_ACCENT_CYCLE = [PALETTE["accent"], "#f2a341", PALETTE["down"], "#a05bd6", PALETTE["up"]]


def esc(s) -> str:
    return _he.escape(str(s or ""))


def strip_emoji(s: str) -> str:
    return re.sub(
        r'[\U00010000-\U0010ffff\U0001F300-\U0001F9FF☀-⛿✀-➿]',
        '', s or ''
    ).strip()


def file_uri(path: str) -> str:
    """로컬 이미지를 base64 data URI로 인라인합니다.

    render_html_to_png()는 page.set_content()로 HTML을 로드하는데, 이 경우 문서
    오리진이 about:blank가 되어 <img src="file://...">가 Chromium 보안 정책에 의해
    조용히 차단됩니다(에러 없이 그냥 표시만 안 됨). 이 때문에 차트/로고 이미지가
    데이터는 정상 생성되고도 화면에는 전혀 보이지 않는 문제가 있었습니다.
    data: URI는 문서 오리진과 무관하게 항상 로드되므로 이 방식을 사용합니다.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        mime, _ = mimetypes.guess_type(path)
        mime = mime or "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return "file://" + os.path.abspath(path)


# ── 3차 작업: 배경 이미지 / 사진 위 텍스트 판 / 하단 뉴스 티커 ──────────────
#
# 이 파일의 기존 카드/텍스트는 전부 인라인 style(색상 등)로 작성돼 있어(CSS
# 클래스로 일괄 오버라이드하기 어려움), 사진 위에서도 항상 읽히도록 만드는
# 방법으로 "글자 색을 바꾸는" 대신 "반투명 다크 판(text_plate) 위에 흰 글자를
# 올리는" 접근을 쓴다 — 어떤 사진이 오더라도(밝든 어둡든) 대비가 보장된다.

def background_layer(image_path, darkness: float = 0.72, credit: str = "") -> str:
    """전체화면 배경 이미지 + 아래로 갈수록 어두워지는 그라디언트 오버레이.
    image_path가 없거나 파일이 실제로 없으면 빈 문자열을 반환해 기존 레이아웃을
    그대로 유지한다(호출부에서 이 반환값을 content 앞에 붙이기만 하면 됨 —
    z-index가 음수라 뒤에 깔리므로 DOM 삽입 위치는 중요하지 않다).

    credit이 있으면(예: "사진: 연합뉴스") 화면 우측 하단에 작은 출처 텍스트를
    워터마크로 얹는다 — 뉴스 사진을 실제로 다운로드해 쓰는 만큼 출처를
    표시해야 한다는 요구사항(FIX-CREDIT-1)."""
    if not image_path or not os.path.isfile(image_path):
        return ""
    uri = file_uri(image_path)
    # 화면 우측, 자막 번인 영역(subtitle-zone) 바로 위 — .tag(종목 해시태그,
    # subtitle-zone 안쪽 top:14px)와 실제로 타 붙는 캡션 텍스트(자막존 하단)
    # 둘 다와 겹치지 않는 유일한 안전지대.
    credit_html = (
        f'<div style="position:absolute;right:24px;bottom:{SUBTITLE_BAR_H + 14}px;z-index:-1;'
        f'font-size:16px;color:rgba(255,255,255,.75);font-weight:600;'
        f'text-shadow:0 1px 3px rgba(0,0,0,.8);">{esc(credit)}</div>'
        if credit else ""
    )
    return f"""
<div style="position:absolute;inset:0;z-index:-3;background-image:url('{uri}');
  background-size:cover;background-position:center;"></div>
<div style="position:absolute;inset:0;z-index:-2;
  background:linear-gradient(180deg, rgba(5,7,13,.30) 0%, rgba(5,7,13,.55) 45%,
  rgba(5,7,13,{darkness}) 100%);"></div>
{credit_html}"""


def text_plate(inner_html: str, extra_style: str = "") -> str:
    """사진 배경 위에 얹는 반투명 다크 판. 카드 없이 배경에 직접 나오는
    헤드라인/타이틀류 텍스트를 감쌀 때 사용한다(사진의 밝기와 무관하게 항상
    대비를 보장하기 위함 — 글자색만 흰색으로 바꾸는 것보다 안전하다)."""
    return (
        f'<div style="display:inline-block;background:rgba(5,7,13,.55);'
        f'border-radius:18px;padding:22px 30px;{extra_style}">{inner_html}</div>'
    )


def news_ticker(text: str, tone: str = "neutral") -> str:
    """화면 하단(.content 영역 안쪽, 자막 번인 영역과는 분리된 위치)에 고정
    표시되는 얇은 뉴스 티커. 이 파이프라인은 DOM을 정지 스크린샷으로 뜨는
    방식이라(video가 아니라 PNG 1장) CSS marquee 애니메이션은 캡처 시점의
    임의의 프레임만 찍혀 의미가 없다 — 그래서 스크롤 대신 고정 텍스트로
    표시한다."""
    if not text:
        return ""
    colors = {"bullish": PALETTE["up"], "bearish": PALETTE["down"], "neutral": PALETTE["accent"]}
    color = colors.get(tone, PALETTE["accent"])
    return f"""
<div style="position:absolute;left:0;right:0;bottom:0;height:48px;
  display:flex;align-items:center;background:{PALETTE['ink']}f0;
  border-left:6px solid {color};border-radius:10px;padding:0 22px;overflow:hidden;">
  <span style="font-size:21px;font-weight:700;color:#fff;white-space:nowrap;">{esc(text)}</span>
</div>"""


BASE_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;}}
body{{
  font-family:'Noto Sans KR','NanumGothic','Malgun Gothic',sans-serif;
  color:{PALETTE['ink']};
  background:
    radial-gradient(circle, {PALETTE['dot']} 1.6px, transparent 1.6px) 0 0/30px 30px,
    {PALETTE['bg']};
  position:relative;
}}
.stage{{position:absolute; left:0; top:0; width:{W}px; height:{H}px;}}
.topbar{{
  position:absolute; left:0; top:0; width:{W}px; height:96px;
  display:flex; align-items:center; padding:0 56px;
  background:{PALETTE['card']}; border-bottom:1px solid {PALETTE['border']};
}}
.topbar .brand{{
  font-weight:800; font-size:26px; color:{PALETTE['accent']};
  letter-spacing:.01em; margin-right:28px;
}}
.topbar .brand-sub{{font-weight:600; font-size:18px; color:{PALETTE['muted']}; margin-right:28px;}}
.topbar .divider{{width:2px; height:40px; background:{PALETTE['border']}; margin-right:28px;}}
.topbar .label{{font-weight:800; font-size:36px; color:{PALETTE['ink']}; flex:1;}}
.topbar .date{{font-weight:600; font-size:24px; color:{PALETTE['muted']};}}
.subtitle-zone{{
  position:absolute; left:0; bottom:0; width:{W}px; height:{SUBTITLE_BAR_H}px;
  background:linear-gradient(180deg, rgba(22,24,29,0) 0%, rgba(22,24,29,.55) 45%, rgba(22,24,29,.55) 100%);
}}
.subtitle-zone .tag{{
  position:absolute; top:14px; right:40px; font-size:18px; font-weight:700; color:#fff; opacity:.85;
}}
.content{{position:absolute; left:56px; right:56px; top:120px; bottom:{SUBTITLE_BAR_H + 24}px;}}
.card{{
  background:{PALETTE['card']}; border:1px solid {PALETTE['border']};
  border-radius:20px; box-shadow:0 10px 28px {PALETTE['shadow']};
}}
.pill{{
  display:inline-flex; align-items:center; gap:8px;
  border-radius:999px; padding:8px 20px; font-weight:700; font-size:22px;
}}
.corner-summary{{
  display:flex; align-items:center; gap:14px;
  background:{PALETTE['accent_soft']}; border-left:6px solid {PALETTE['accent']};
  border-radius:12px; padding:18px 24px; font-size:26px; font-weight:600;
  color:{PALETTE['ink']}; margin-bottom:28px;
}}
.badge-num{{
  display:flex; align-items:center; justify-content:center;
  width:52px; height:52px; border-radius:50%; font-weight:800; font-size:24px;
  flex-shrink:0;
}}
"""


def shell(topbar_label: str, content_html: str, stock_tag: str = "",
          date_str: str = "", background_image=None, suppress_ticker: bool = False,
          credit: str = "") -> str:
    date_str = date_str or _BRIEFING_DATE_STR or date.today().strftime("%Y.%m.%d")
    tag_html = f'<div class="tag">#{esc(stock_tag)}</div>' if stock_tag else ""
    has_bg = bool(background_image and os.path.isfile(background_image))
    bg_html = background_layer(background_image, credit=credit)
    # 티커는 set_ticker_text()로 한 번 설정한 전역값을 모든 shell() 호출이
    # 자동으로 소비한다(set_briefing_date()와 동일한 패턴) — 빌더 함수 시그니처를
    # 일일이 바꾸지 않아도 된다. suppress_ticker=True는 lower_third()처럼
    # .content 하단을 이미 차지하는 콘텐츠와 겹치지 않도록 개별 호출부가 끈다.
    ticker_html = "" if suppress_ticker else news_ticker(_TICKER_TEXT, _TICKER_TONE)
    # 배경 사진이 있으면 흰 상단바가 사진과 따로 노는 느낌이 들어, 반투명
    # 다크 톤 + 흰 글자로 바꿔 사진과 한 화면처럼 어울리게 한다.
    topbar_style = ' style="background:rgba(5,7,13,.55);border-bottom:none;"' if has_bg else ""
    label_style = ' style="color:#fff;"' if has_bg else ""
    date_style = ' style="color:#e5e7eb;"' if has_bg else ""
    sub_style = ' style="color:#cbd5e1;"' if has_bg else ""
    divider_style = ' style="background:rgba(255,255,255,.35);"' if has_bg else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}</style></head>
<body><div class="stage">
  {bg_html}
  <div class="topbar"{topbar_style}>
    <div class="brand">KBS</div>
    <div class="brand-sub"{sub_style}>머니올라</div>
    <div class="divider"{divider_style}></div>
    <div class="label"{label_style}>{esc(strip_emoji(topbar_label))}</div>
    <div class="date"{date_style}>{esc(date_str)}</div>
  </div>
  <div class="content">{content_html}{ticker_html}</div>
  <div class="subtitle-zone">{tag_html}</div>
</div></body></html>"""


def centered_shell(content_html: str, background_image=None, credit: str = "") -> str:
    # background_layer()는 .stage 전체(화면 전체 높이)를 덮어야 자막존 경계에서
    # 이미지가 끊기지 않으므로, .center-wrap 안이 아니라 .stage의 형제로 둔다.
    bg_html = background_layer(background_image, credit=credit)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}
.center-wrap{{
  position:absolute; left:0; top:0; width:{W}px; height:{H - SUBTITLE_BAR_H}px;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  text-align:center; gap:22px;
}}
</style></head>
<body><div class="stage">
  {bg_html}
  <div class="center-wrap">{content_html}</div>
  <div class="subtitle-zone"></div>
</div></body></html>"""


def kbs_badge() -> str:
    return (f'<div class="pill" style="background:{PALETTE["accent"]};color:#fff;'
            f'font-size:26px;padding:12px 30px;">KBS 머니올라</div>')


def stat_table(rows: list) -> str:
    """rows: [(label, value, change_str, positive_bool), ...]"""
    header = (
        f'<tr style="background:{PALETTE["accent_soft"]};">'
        f'<th style="text-align:left;padding:18px 28px;border-radius:20px 0 0 0;">지수</th>'
        f'<th style="text-align:right;padding:18px 28px;">현재가</th>'
        f'<th style="text-align:right;padding:18px 28px;border-radius:0 20px 0 0;">등락률</th>'
        f'</tr>'
    )
    body = "".join(
        f'<tr style="border-top:1px solid {PALETTE["border"]};">'
        f'<td style="padding:16px 28px;font-weight:700;color:{PALETTE["muted"]};">{esc(l)}</td>'
        f'<td style="padding:16px 28px;text-align:right;font-weight:800;font-size:30px;">{esc(v)}</td>'
        f'<td style="padding:16px 28px;text-align:right;font-weight:700;font-size:24px;'
        f'color:{PALETTE["up"] if p else PALETTE["down"]};">{"▲" if p else "▼"} {esc(c)}</td>'
        f'</tr>'
        for l, v, c, p in rows if v
    )
    return (
        f'<table class="card" style="width:100%;border-collapse:collapse;'
        f'font-size:26px;">{header}{body}</table>'
    )


def point_card(num: int, text: str, color: str) -> str:
    return (
        f'<div class="card" style="display:flex;align-items:flex-start;gap:16px;'
        f'padding:22px 24px;">'
        f'<div class="badge-num" style="background:{color}22;color:{color};'
        f'border:2px solid {color};">{num}</div>'
        f'<div style="font-size:25px;line-height:1.5;font-weight:600;padding-top:4px;">'
        f'{esc(text)}</div>'
        f'</div>'
    )


def point_card_img(num: int, name: str, text: str, color: str, image_uri: str = "") -> str:
    """point_card()의 이미지 포함 변형. "추가 관심 종목"처럼 종목이 여러 개
    나열되는 집계 슬라이드에서, 텍스트뿐이던 카드에 종목 썸네일을 곁들여
    한눈에 구분되는 카드형 레이아웃으로 보여준다. image_uri가 없으면(검색
    실패 등) 썸네일 없이 기존 point_card()와 동일한 레이아웃으로 폴백한다."""
    img_html = (
        f'<img src="{image_uri}" style="width:64px;height:64px;border-radius:12px;'
        f'object-fit:cover;flex-shrink:0;border:2px solid {color}55;">'
        if image_uri else ""
    )
    name_html = (
        f'<div style="font-size:22px;font-weight:800;color:{color};margin-bottom:4px;">{esc(name)}</div>'
        if name else ""
    )
    return (
        f'<div class="card" style="display:flex;align-items:center;gap:16px;'
        f'padding:18px 24px;">'
        f'<div class="badge-num" style="background:{color}22;color:{color};'
        f'border:2px solid {color};flex-shrink:0;">{num}</div>'
        f'{img_html}'
        f'<div style="flex:1;">{name_html}'
        f'<div style="font-size:23px;line-height:1.5;font-weight:600;">{esc(text)}</div>'
        f'</div>'
        f'</div>'
    )


def bullet_column(title: str, items: list, color: str) -> str:
    lis = "".join(
        f'<li style="margin-bottom:14px;line-height:1.5;">{esc(it)}</li>'
        for it in items
    )
    return f"""
<div class="card" style="padding:26px 30px;flex:1;">
  <div class="pill" style="background:{color};color:#fff;font-size:24px;margin-bottom:18px;">{esc(title)}</div>
  <ul style="list-style:none;font-size:25px;color:{PALETTE['ink']};">{lis}</ul>
</div>"""


def chat_bubble(avatar_uri: str, sender: str, channel_type: str, text: str, color: str) -> str:
    """카카오톡 대화창처럼 왼쪽 원형 아바타 + 꼬리 달린 말풍선으로 발언을
    보여준다(builders._build_mention_page 전용). avatar_uri는 실제 인물
    사진이 아니라 panel_avatars.get_avatar_path()가 고른 일반화된 일러스트
    아바타다 — 실제 발언자와의 닮음 여부는 고려 대상이 아니다."""
    type_html = (
        f'<span class="pill" style="background:{PALETTE["ink"]};color:#fff;'
        f'font-size:16px;padding:3px 12px;margin-right:8px;">{esc(channel_type)}</span>'
        if channel_type else ""
    )
    sender_html = (
        f'<div style="display:flex;align-items:center;margin-bottom:10px;">'
        f'{type_html}<span style="font-size:22px;font-weight:800;color:{PALETTE["ink"]};">'
        f'{esc(sender)}</span></div>'
        if sender else ""
    )
    avatar_html = (
        f'<img src="{avatar_uri}" style="width:120px;height:120px;border-radius:50%;'
        f'border:4px solid {color};flex-shrink:0;box-shadow:0 8px 20px rgba(0,0,0,.28);">'
        if avatar_uri else ""
    )
    return f"""
<div style="display:flex;align-items:flex-start;gap:22px;">
  {avatar_html}
  <div style="position:relative;flex:1;">
    <div style="position:absolute;left:-15px;top:38px;width:0;height:0;
      border-top:15px solid transparent;border-bottom:15px solid transparent;
      border-right:17px solid #fff;"></div>
    <div class="card" style="padding:26px 30px;">
      {sender_html}
      <div style="font-size:27px;line-height:1.55;font-weight:600;">{esc(text)}</div>
    </div>
  </div>
</div>"""


def page_dots(total: int, current: int) -> str:
    if total <= 1:
        return ""
    dots = "".join(
        f'<div style="width:12px;height:12px;border-radius:50%;'
        f'background:{PALETTE["accent"] if i == current else PALETTE["border"]};"></div>'
        for i in range(total)
    )
    return (f'<div style="display:flex;gap:10px;justify-content:center;'
            f'margin-top:18px;">{dots}</div>')


# ── Phase D: 방송형 컴포넌트 (lower-third / headline / report / risk / heatmap) ──

def autofit_text(text: str, base_font_size: int, max_lines: int = 2,
                  min_font_size: int = 16, extra_style: str = "") -> str:
    """`data-autofit` 마커가 달린 <div>를 반환합니다. render.py의
    render_html_to_png()가 스크린샷 직전에 실제 렌더링 높이를 측정해 이 폰트
    크기를 max_lines줄에 맞을 때까지 자동으로 줄입니다. -webkit-line-clamp을
    안전망으로 함께 걸어, 자동 축소가 min_font_size에 막혀 완전히 맞지 않더라도
    화면 밖으로 흘러넘치지 않고 말줄임표로 잘리도록 합니다."""
    return (
        f'<div data-autofit="true" data-max-lines="{max_lines}" data-min-font="{min_font_size}" '
        f'style="font-size:{base_font_size}px;line-height:1.35;display:-webkit-box;'
        f'-webkit-box-orient:vertical;-webkit-line-clamp:{max_lines};overflow:hidden;'
        f'{extra_style}">{esc(text)}</div>'
    )


def lower_third(name: str, code: str, change_pct: str, positive: bool,
                 sector: str = "") -> str:
    """종목명/코드/등락률/섹터를 표시하는 방송형 하단 자막바(lower-third).
    한국 증권가 관행대로 상승은 빨강(up), 하락은 파랑(down)을 사용합니다.
    부모 요소가 position:relative(또는 absolute)여야 하단에 도킹됩니다."""
    color = PALETTE["up"] if positive else PALETTE["down"]
    arrow = "▲" if positive else "▼"
    code_html = (
        f'<span style="font-size:22px;color:#cfd3da;font-weight:600;margin-left:14px;">'
        f'{esc(code)}</span>' if code else ""
    )
    sector_html = (
        f'<span class="pill" style="background:{PALETTE["accent_soft"]};color:{PALETTE["accent"]};'
        f'font-size:20px;margin-left:16px;">{esc(sector)}</span>' if sector else ""
    )
    change_html = (
        f'<span class="pill" style="background:{color}1a;color:{color};font-size:24px;'
        f'font-weight:800;margin-left:16px;">{arrow} {esc(change_pct)}</span>' if change_pct else ""
    )
    return f"""
<div style="position:absolute;left:0;bottom:0;width:100%;display:flex;align-items:center;
  background:linear-gradient(90deg,{PALETTE['ink']}ee 0%,{PALETTE['ink']}cc 75%,transparent 100%);
  padding:18px 32px;border-left:8px solid {color};box-sizing:border-box;">
  <span style="font-size:32px;font-weight:800;color:#fff;">{esc(name)}</span>
  {code_html}{sector_html}{change_html}
</div>"""


def headline_card(headline: str, subtext: str = "", color: str = None) -> str:
    """한 줄 핵심 결론을 강조하는 헤드라인 카드. 기존 corner-summary보다 임팩트
    있게 보이도록 큰 텍스트 + 왼쪽 액센트 바를 사용합니다."""
    color = color or PALETTE["accent"]
    sub_html = (
        f'<div style="font-size:24px;color:{PALETTE["muted"]};margin-top:10px;font-weight:600;">'
        f'{esc(subtext)}</div>' if subtext else ""
    )
    headline_html = autofit_text(
        headline, base_font_size=40, max_lines=2, min_font_size=22,
        extra_style=f"font-weight:800;color:{PALETTE['ink']};",
    )
    return f"""
<div class="card" style="border-left:10px solid {color};padding:26px 32px;margin-bottom:24px;">
  {headline_html}
  {sub_html}
</div>"""


def report_card(broker: str, stock_name: str, text: str, opinion: str = "",
                 target_price: str = "", color: str = None) -> str:
    """증권사 리포트 카드. opinion/target_price는 값이 있을 때만 표시됩니다
    (현재 script.json 스키마의 집계 섹션 items는 name/text만 갖고 있어 선택적
    필드로 설계했습니다 — 스키마가 opinion/target_price를 채우면 자동 표시됩니다)."""
    color = color or PALETTE["accent"]
    opinion_html = (
        f'<span class="pill" style="background:{color}1a;color:{color};font-size:20px;'
        f'margin-left:12px;">{esc(opinion)}</span>' if opinion else ""
    )
    target_html = (
        f'<span style="font-size:22px;color:{PALETTE["muted"]};font-weight:700;margin-left:12px;">'
        f'목표주가 {esc(target_price)}</span>' if target_price else ""
    )
    text_html = autofit_text(
        text, base_font_size=25, max_lines=2, min_font_size=18,
        extra_style="line-height:1.5;font-weight:600;margin-top:10px;",
    )
    return f"""
<div class="card" style="border-left:8px solid {color};padding:22px 28px;">
  <div style="display:flex;align-items:center;flex-wrap:wrap;">
    <span class="pill" style="background:{PALETTE['ink']};color:#fff;font-size:20px;">{esc(broker)}</span>
    <span style="font-size:28px;font-weight:800;margin-left:14px;">{esc(stock_name)}</span>
    {opinion_html}{target_html}
  </div>
  {text_html}
</div>"""


def risk_card(risks: list, title: str = "리스크 요인") -> str:
    """리스크 요인을 강조 스타일로 보여주는 카드. bullet_column의 리스크 전용
    변형이며, 하락=파랑 규칙에 맞춰 down 색상을 사용합니다."""
    color = PALETTE["down"]
    lis = "".join(
        f'<li style="margin-bottom:12px;line-height:1.5;">{esc(r)}</li>'
        for r in risks
    )
    return f"""
<div class="card" style="border:2px solid {color}55;background:#f4f8ff;padding:24px 28px;">
  <div class="pill" style="background:{color};color:#fff;font-size:22px;margin-bottom:14px;">
    ⚠ {esc(title)}
  </div>
  <ul style="list-style:none;font-size:24px;color:{PALETTE['ink']};">{lis}</ul>
</div>"""


def sector_heatmap(sector_list: list) -> str:
    """섹터 리스트를 히트맵 타일 그리드로 표시합니다. script.json의 sector_list는
    숫자 등락폭이 아니라 momentum 문자열(상승/하락/보합)만 갖고 있는 경우가
    많아, 타일 색은 momentum 3단계로 근사합니다. 상승=빨강/하락=파랑 한국
    증권가 관행을 그대로 따릅니다."""
    mom_colors = {"상승": PALETTE["up"], "하락": PALETTE["down"], "보합": "#f2a341"}
    mom_arrows = {"상승": "▲", "하락": "▼", "보합": "―"}
    tiles = ""
    for sector in sector_list:
        if isinstance(sector, dict):
            name     = sector.get("name", "")
            desc     = sector.get("desc", sector.get("description", ""))
            momentum = sector.get("momentum", "")
        else:
            name, desc, momentum = str(sector), "", ""
        color = mom_colors.get(momentum, PALETTE["muted"])
        arrow = mom_arrows.get(momentum, "")
        desc_html = autofit_text(
            desc, base_font_size=20, max_lines=2, min_font_size=14,
            extra_style="color:#fff;opacity:.92;margin-top:8px;line-height:1.4;",
        )
        tiles += f"""
<div style="background:{color};border-radius:16px;padding:22px 24px;min-height:170px;
  display:flex;flex-direction:column;justify-content:space-between;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-size:28px;font-weight:800;color:#fff;">{esc(name)}</span>
    <span style="font-size:26px;font-weight:800;color:#fff;">{arrow}</span>
  </div>
  {desc_html}
</div>"""
    return f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;">{tiles}</div>'


# ── Phase F: 주도주 랭킹 카드 ─────────────────────────────────────────────────

def _score_bar(label: str, value: float, bar_color: str) -> str:
    pct = max(0, min(100, round(value * 100)))
    return f"""
<div style="margin-top:8px;">
  <div style="display:flex;justify-content:space-between;font-size:16px;color:{PALETTE['muted']};">
    <span>{esc(label)}</span><span>{pct}</span>
  </div>
  <div style="background:{PALETTE['border']};border-radius:6px;height:10px;overflow:hidden;">
    <div style="width:{pct}%;background:{bar_color};height:100%;"></div>
  </div>
</div>"""


def ranking_card(rank: int, name: str, code: str, themes: str, ranking_score: float,
                  volume_score: float, news_score: float, report_score: float,
                  change_pct: str = "", positive: bool = True) -> str:
    """주도주 랭킹 카드. 순위 배지 + 종목명/코드/테마(섹터) + 종합 점수 +
    거래량/뉴스·방송/증권사 점수 breakdown 바를 표시합니다."""
    color = PALETTE["up"] if positive else PALETTE["down"]
    arrow = "▲" if positive else "▼"
    change_html = (
        f'<span class="pill" style="background:{color}1a;color:{color};font-size:22px;'
        f'margin-left:12px;">{arrow} {esc(change_pct)}</span>' if change_pct else ""
    )
    theme_html = (
        f'<span class="pill" style="background:{PALETTE["accent_soft"]};color:{PALETTE["accent"]};'
        f'font-size:18px;margin-left:10px;">{esc(themes)}</span>' if themes else ""
    )
    bars = (
        _score_bar("거래량", volume_score, PALETTE["accent"])
        + _score_bar("뉴스/방송", news_score, "#f2a341")
        + _score_bar("증권사", report_score, "#a05bd6")
    )
    code_html = (
        f'<span style="font-size:20px;color:{PALETTE["muted"]};font-weight:600;">{esc(code)}</span>'
        if code else ""
    )
    return f"""
<div class="card" style="padding:24px 26px;">
  <div style="display:flex;align-items:center;gap:14px;">
    <div class="badge-num" style="width:64px;height:64px;font-size:30px;
      background:{color}22;color:{color};border:3px solid {color};">{rank}</div>
    <div>
      <div style="font-size:32px;font-weight:800;">{esc(name)} {code_html}</div>
      <div style="margin-top:4px;">{theme_html}{change_html}</div>
    </div>
    <div style="margin-left:auto;text-align:right;">
      <div style="font-size:18px;color:{PALETTE['muted']};">종합 점수</div>
      <div style="font-size:34px;font-weight:800;color:{PALETTE['accent']};">{ranking_score:.2f}</div>
    </div>
  </div>
  {bars}
</div>"""


def numbered_bullets_from_text(text: str, max_items: int = 6) -> list:
    """긴 문단 텍스트를 문장 단위로 쪼개 불릿 리스트처럼 보여주기 위한 헬퍼."""
    if not text:
        return []
    sentences = re.split(r'(?<=[.다요]\.)\s+|(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return [text.strip()]
    if len(sentences) <= max_items:
        return sentences
    chunk = max(1, -(-len(sentences) // max_items))
    return [" ".join(sentences[i:i + chunk]) for i in range(0, len(sentences), chunk)][:max_items]
