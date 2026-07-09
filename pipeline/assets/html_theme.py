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


def sector_card(idx: int, name: str, desc: str, momentum: str, color: str) -> str:
    mom_colors = {"상승": PALETTE["up"], "하락": PALETTE["down"], "보합": "#f2a341"}
    mcolor = mom_colors.get(momentum, PALETTE["muted"])
    mom_html = (
        f'<span class="pill" style="background:{mcolor}1a;color:{mcolor};'
        f'font-size:20px;padding:6px 16px;margin-left:auto;">{esc(momentum)}</span>'
        if momentum else ""
    )
    return f"""
<div class="card" style="padding:24px 26px;">
  <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;">
    <div class="badge-num" style="background:{color}22;color:{color};border:2px solid {color};">{idx}</div>
    <div style="font-size:32px;font-weight:800;">{esc(name)}</div>
    {mom_html}
  </div>
  <div style="font-size:23px;color:{PALETTE['muted']};line-height:1.55;">{esc(desc)}</div>
</div>"""


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
