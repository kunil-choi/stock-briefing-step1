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
          date_str: str = "") -> str:
    date_str = date_str or _BRIEFING_DATE_STR or date.today().strftime("%Y.%m.%d")
    tag_html = f'<div class="tag">#{esc(stock_tag)}</div>' if stock_tag else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}</style></head>
<body><div class="stage">
  <div class="topbar">
    <div class="brand">KBS</div>
    <div class="brand-sub">머니올라</div>
    <div class="divider"></div>
    <div class="label">{esc(strip_emoji(topbar_label))}</div>
    <div class="date">{esc(date_str)}</div>
  </div>
  <div class="content">{content_html}</div>
  <div class="subtitle-zone">{tag_html}</div>
</div></body></html>"""


def centered_shell(content_html: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}
.center-wrap{{
  position:absolute; left:0; top:0; width:{W}px; height:{H - SUBTITLE_BAR_H}px;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  text-align:center; gap:22px;
}}
</style></head>
<body><div class="stage">
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


def quote_bubble(channel: str, speaker: str, text: str, color: str,
                  channel_type: str = "") -> str:
    type_html = (
        f'<span class="pill" style="background:{PALETTE["ink"]};color:#fff;'
        f'font-size:18px;padding:4px 14px;margin-right:10px;">{esc(channel_type)}</span>'
        if channel_type else ""
    )
    channel_html = (
        f'<span class="pill" style="background:{color}1a;color:{color};'
        f'font-size:22px;padding:6px 18px;">{esc(channel)}</span>'
        if channel else ""
    )
    speaker_html = (
        f'<span style="font-size:28px;font-weight:800;color:{PALETTE["ink"]};margin-left:14px;">'
        f'{esc(speaker)}</span>'
        if speaker else ""
    )
    header_html = (
        f'<div style="display:flex;align-items:center;margin-bottom:16px;">'
        f'{type_html}{channel_html}{speaker_html}</div>'
        if (channel_type or channel or speaker) else ""
    )
    return f"""
<div class="card" style="border-left:8px solid {color};padding:26px 30px;position:relative;">
  <div style="position:absolute;top:14px;right:26px;font-size:52px;color:{color}33;font-weight:800;">&rdquo;</div>
  {header_html}
  <div style="font-size:27px;line-height:1.55;font-weight:600;">{esc(text)}</div>
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
