# pipeline/assets/html_theme.py
"""
'PPT 슬라이드'를 만든다는 관점의 HTML/CSS 디자인 시스템.
NotebookLM 스타일 참고: 밝은 배경 + 점그리드, 민트/틸 액센트 + 노란 하이라이트,
큰 볼드 타이포, 말풍선형 인용 카드, 심플한 표. 한국 증권가 관행(상승=빨강/하락=파랑)은 유지.
"""
import os
import re
import math
import base64
import mimetypes
import itertools
import html as _he
from datetime import date
from .config import SUBTITLE_ZONE_TOP

W, H = 1920, 1080

_HERE = os.path.dirname(os.path.abspath(__file__))
_HEADLINE_FONT_PATH = os.path.join(_HERE, "..", "..", "assets", "fonts", "BlackHanSans-Regular.ttf")
HEADLINE_FONT_FAMILY = "Black Han Sans"
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


def nl2br(s) -> str:
    """esc()와 동일하되, 문자열 안의 개행(\\n)을 <br>로 바꿔 사람이 직접
    지정한 줄바꿈을 그대로 살린다(발언/뉴스 썸네일 제목처럼 문구·줄바꿈을
    사람이 다듬는 경우에 사용 — esc()만 쓰면 HTML이 개행을 공백으로
    뭉개버려 지정한 줄바꿈이 무시된다)."""
    return esc(s).replace("\n", "<br>")


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
    # 그라디언트 3단계(0%/45%/100%)는 기본값 darkness=0.72 기준으로 잡은
    # 비율(.30/.55/.72)을 유지한 채 darkness에 맞춰 함께 스케일한다. 이전엔
    # 100% 지점만 darkness를 따르고 0%/45%는 .30/.55로 고정돼 있어서, 호출부가
    # darkness를 0.1처럼 낮게 줘도(build_conclusion() — 자체 완성된 오프닝
    # 타이틀 이미지 위라 어두운 오버레이가 불필요) 화면 상단~중단(마침 타이틀
    # 텍스트가 있는 위치)은 여전히 최대 55% 검은 오버레이가 깔려 텍스트가
    # 칙칙하게 죽어 보였다(사용자 보고 버그: 실제 영상 결과물의 타이틀 글씨가
    # 저장된 원본 이미지보다 흐리게 나옴).
    top    = darkness * (0.30 / 0.72)
    mid    = darkness * (0.55 / 0.72)
    return f"""
<div style="position:absolute;inset:0;z-index:-3;background-image:url('{uri}');
  background-size:cover;background-position:center;"></div>
<div style="position:absolute;inset:0;z-index:-2;
  background:linear-gradient(180deg, rgba(5,7,13,{top}) 0%, rgba(5,7,13,{mid}) 45%,
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


def _headline_font_face_css() -> str:
    """썸네일 제목처럼 임팩트가 필요한 헤드라인 전용 서체(Black Han Sans,
    SIL OFL 라이선스 — assets/fonts/BlackHanSans-OFL.txt)를 base64로 인라인
    임베드한다. file_uri()와 같은 이유(Chromium이 about:blank 오리진에서
    file://을 막음)로 로컬 경로 대신 data URI를 쓴다. 본문 서체(Noto Sans
    KR)는 그대로 두고, 이 서체는 필요한 곳에서만 font-family로 opt-in한다."""
    if not os.path.isfile(_HEADLINE_FONT_PATH):
        return ""
    uri = file_uri(_HEADLINE_FONT_PATH)
    return f"""@font-face {{
  font-family:'{HEADLINE_FONT_FAMILY}'; src:url('{uri}') format('truetype');
  font-weight:400; font-style:normal; font-display:block;
}}"""


BASE_CSS = f"""
{_headline_font_face_css()}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;}}
body{{
  font-family:'Noto Sans KR','NanumGothic','Malgun Gothic',sans-serif;
  word-break:keep-all; overflow-wrap:break-word;
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
/* 숫자 카운트업 도중 자릿수가 바뀌어도 글자폭이 흔들리지 않게 고정폭 숫자를
   강제한다(영상 모션그래픽 업그레이드 P1-2 — MOTION_JS의 data-anim="count"). */
[data-anim="count"]{{font-variant-numeric:tabular-nums;}}
"""

# ── 영상 모션그래픽 업그레이드(Phase 1) — 프레임 시퀀스 애니메이션 런타임 ────
#
# render.py의 render_html_to_frames()가 한 페이지를 한 번만 로드한 뒤
# window.__setT(t)를 여러 번 호출해 상태만 바꿔가며 스크린샷을 찍는다(매
# 프레임 set_content()를 다시 부르면 HTML 파싱/폰트 로딩이 반복돼 수십 배
# 느려짐 — 문서 P1-1 참고). __setT(t)는 반드시 순수 함수여야 한다: 같은 t를
# 두 번 넣으면 항상 같은 화면이 나와야 하고(프레임 캡처를 임의 순서/여러 번
# 다시 호출해도 안전), 내부에 setInterval/requestAnimationFrame 같은 자체
# 타이머를 두지 않는다 — 상태는 오직 인자로 받은 t와 DOM의 data-* 속성만으로
# 결정한다.
#
# docs/motion_mockup_reference.py의 ease()(easeOutCubic)를 JS로 그대로
# 옮겼다 — 파이썬 목업과 실제 렌더링이 같은 커브를 쓰게 하기 위함.
MOTION_JS = r"""
(function () {
  function ease(t) {
    t = Math.max(0, Math.min(1, t));
    return 1 - Math.pow(1 - t, 3);
  }

  function fmtNum(v, decimals, suffix) {
    var sign = v < 0 ? '-' : '';
    var s = Math.abs(v).toFixed(decimals);
    var parts = s.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return sign + parts.join('.') + (suffix || '');
  }

  function progressFor(el, t) {
    var delay = parseFloat(el.dataset.delay || '0');
    var dur = parseFloat(el.dataset.dur || '0.6');
    if (dur <= 0) dur = 0.001;
    return ease((t - delay) / dur);
  }

  window.__setT = function (t) {
    document.querySelectorAll('[data-anim]').forEach(function (el) {
      var type = el.dataset.anim;
      var p = progressFor(el, t);

      if (type === 'count') {
        var to = parseFloat(el.dataset.to || '0');
        var decimals = parseInt(el.dataset.decimals || '0', 10);
        var suffix = el.dataset.suffix || '';
        el.textContent = fmtNum(to * p, decimals, suffix);
      } else if (type === 'grow') {
        var toPct = parseFloat(el.dataset.to || '100');
        el.style.width = (toPct * p) + '%';
      } else if (type === 'fadeup') {
        el.style.opacity = Math.min(1, p * 1.6);
        el.style.transform = 'translateY(' + ((1 - p) * 26) + 'px)';
      } else if (type === 'pop') {
        el.style.opacity = Math.min(1, p * 2);
        el.style.transform = 'scale(' + (0.6 + 0.4 * p) + ')';
      } else if (type === 'draw') {
        var path = el.tagName.toLowerCase() === 'path' ? el : el.querySelector('path');
        if (path) {
          var len = path.getTotalLength();
          path.style.strokeDasharray = String(len);
          path.style.strokeDashoffset = String(len * (1 - p));
        }
      } else if (type === 'dot') {
        // svg_line_chart()의 광점(선 끝을 따라가는 원) 전용 — data-points에
        // "x1,y1;x2,y2;..."로 인코딩된 좌표 목록 중 진행률에 해당하는 점으로
        // cx/cy를 옮긴다. 목업(scene_stock())의
        // "idx = min(len(pts)-1, int(p*(len(pts)-1)))"과 동일하게 정점 사이를
        // 매끄럽게 보간하지 않고 그대로 건너뛴다(라인 자체가 이미 매끄럽게
        // 그려지므로 점은 방금 그려진 지점만 가리키면 충분).
        var raw = el.dataset.points || '';
        if (raw) {
          var pts = raw.split(';').map(function (pair) {
            var xy = pair.split(',');
            return [parseFloat(xy[0]), parseFloat(xy[1])];
          });
          if (pts.length) {
            var idx = Math.min(pts.length - 1, Math.floor(p * (pts.length - 1)));
            el.setAttribute('cx', pts[idx][0]);
            el.setAttribute('cy', pts[idx][1]);
          }
        }
      }
    });
  };
})();
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
</div><script>{MOTION_JS}</script></body></html>"""


def centered_shell(content_html: str, background_image=None, credit: str = "",
                    darkness: float = 0.72) -> str:
    # background_layer()는 .stage 전체(화면 전체 높이)를 덮어야 자막존 경계에서
    # 이미지가 끊기지 않으므로, .center-wrap 안이 아니라 .stage의 형제로 둔다.
    # darkness 기본값(0.72)은 사진 위에 텍스트를 얹을 때 가독성을 위한 어두운
    # 그라디언트다 — 오프닝 타이틀 이미지처럼 이미 자체적으로 읽기 쉬운 완성된
    # 디자인 위에는 이 그라디언트가 불필요하게 화면을 어둡게 만든다(사용자
    # 보고 버그: "화면이 너무 어둡다"). build_conclusion()이 낮은 값을 넘겨
    # 이 오버레이를 사실상 끈다.
    bg_html = background_layer(background_image, darkness=darkness, credit=credit)
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
</div><script>{MOTION_JS}</script></body></html>"""


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


# ── 영상 모션그래픽 업그레이드 P1-3(a): 시장 지표 카운트업 ────────────────────

def market_index_cards(rows: list) -> str:
    """rows: [(label, value, change_str, positive_bool), ...]. stat_table()
    (표 형태)의 카운트업 카드 버전 — 목업(scene_market())의 3분할 카드를
    그대로 따르되, 이 화면은 기존처럼 지수 5개(코스피/코스닥/나스닥/S&P500/
    원달러)를 유지한다(사용자 확인 — 목업은 3개만 예시로 보여줌). 카드마다
    0.18초씩 늦게 등장(fadeup)하고, 숫자가 0→실제값으로 굴러가며(count),
    진행 게이지 바가 차오르고(grow, 값 크기와 무관하게 항상 100%까지 —
    "로딩 중" 느낌의 장식용 리빌), 등락률 배지가 숫자가 다 굴러간 뒤 팝
    (pop)으로 등장한다.

    value가 숫자로 못 읽히면(빈 문자열 등 — 데이터 누락) 카운트업 없이
    정적 텍스트로 폴백한다(회귀 없음). stat_table()은 지우지 않는다(다른
    빌더가 표 형태 그대로 쓸 수 있으므로 남겨둠)."""
    cards = ""
    idx = 0
    for label, value, change_str, positive in rows:
        if not value:
            continue
        color = PALETTE["up"] if positive else PALETTE["down"]
        arrow = "▲" if positive else "▼"
        delay = idx * 0.18
        idx += 1

        numeric = re.sub(r"[^\d.\-]", "", value)
        try:
            target = float(numeric)
            decimals = len(numeric.split(".")[-1]) if "." in numeric else 0
            number_html = (
                f'<div data-anim="count" data-to="{target}" data-decimals="{decimals}" '
                f'data-delay="{delay:.2f}" data-dur="0.9" style="font-size:52px;font-weight:800;'
                f'letter-spacing:-.02em;line-height:1.1;">0</div>'
            )
        except ValueError:
            number_html = (
                f'<div style="font-size:52px;font-weight:800;letter-spacing:-.02em;'
                f'line-height:1.1;">{esc(value)}</div>'
            )
        change_html = (
            f'<div data-anim="pop" data-delay="{delay + 0.75:.2f}" data-dur="0.35" '
            f'style="display:inline-flex;align-items:center;gap:8px;background:{color};color:#fff;'
            f'border-radius:99px;padding:6px 18px;font-size:22px;font-weight:800;opacity:0;">'
            f'{arrow} {esc(change_str)}</div>' if change_str else ""
        )
        cards += f"""
<div class="card" data-anim="fadeup" data-delay="{delay:.2f}" data-dur="0.55"
     style="flex:1;padding:26px 22px;opacity:0;min-width:0;">
  <div style="font-size:22px;font-weight:700;color:{PALETTE['muted']};">{esc(label)}</div>
  {number_html}
  <div style="height:6px;background:{PALETTE['border']};border-radius:99px;margin:12px 0 14px;">
    <div data-anim="grow" data-to="100" data-delay="{delay + 0.1:.2f}" data-dur="0.8"
         style="height:6px;width:0%;background:{color};border-radius:99px;"></div>
  </div>
  {change_html}
</div>"""
    return f'<div style="display:flex;gap:14px;">{cards}</div>'


def point_card(num: int, text: str, color: str, font_size: int = 25) -> str:
    return (
        f'<div class="card" style="display:flex;align-items:flex-start;gap:16px;'
        f'padding:22px 24px;">'
        f'<div class="badge-num" style="background:{color}22;color:{color};'
        f'border:2px solid {color};">{num}</div>'
        f'<div style="font-size:{font_size}px;line-height:1.5;font-weight:600;padding-top:4px;">'
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
    아바타다 — 실제 발언자와의 닮음 여부는 고려 대상이 아니다.

    한 화면에 카드 1개만 보여주는 구성(전문가 1명당 1페이지)으로 바뀌면서
    화면에 여유 공간이 많아져, 여러 카드를 동시에 쌓던 이전 크기보다 아바타·
    글자를 크게 키웠다(사용자 요청 — 잘 보이고 화면에 적절한 비율로 채워지도록)."""
    type_html = (
        f'<span class="pill" style="background:{PALETTE["ink"]};color:#fff;'
        f'font-size:20px;padding:4px 16px;margin-right:10px;">{esc(channel_type)}</span>'
        if channel_type else ""
    )
    sender_html = (
        f'<div style="display:flex;align-items:center;margin-bottom:18px;">'
        f'{type_html}<span style="font-size:34px;font-weight:800;color:{PALETTE["ink"]};">'
        f'{esc(sender)}</span></div>'
        if sender else ""
    )
    avatar_html = (
        f'<img src="{avatar_uri}" style="width:200px;height:200px;border-radius:50%;'
        f'border:5px solid {color};flex-shrink:0;box-shadow:0 10px 26px rgba(0,0,0,.3);">'
        if avatar_uri else ""
    )
    return f"""
<div style="display:flex;align-items:flex-start;gap:36px;">
  {avatar_html}
  <div style="position:relative;flex:1;">
    <div style="position:absolute;left:-18px;top:52px;width:0;height:0;
      border-top:18px solid transparent;border-bottom:18px solid transparent;
      border-right:20px solid #fff;"></div>
    <div class="card" style="padding:44px 52px;">
      {sender_html}
      <div style="font-size:44px;line-height:1.6;font-weight:600;">{esc(text)}</div>
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


# ── 영상 모션그래픽 업그레이드 P1-3(b): 섹터 랭킹 바 성장 ─────────────────────

def sector_rank_bars(sector_list: list) -> str:
    """섹터 리스트를 순위 배지 + 성장 막대 리스트로 표시합니다(목업 04번
    프레임 참고 — docs/motion_mockup_reference.py의 scene_sector()). 각 막대에
    data-anim="grow"를 걸어 순번마다 0.12초씩 늦게 순차적으로 자라나게 한다.

    sector_heatmap()(타일 그리드)과 같은 이유로 momentum 문자열(상승/하락/
    보합)만 근거로 막대 길이를 3단계로 근사한다 — script.json의 sector_list엔
    숫자 등락폭이 없다(narration이 LLM 생성이라 정밀한 수치를 붙이면 없는
    데이터를 지어내는 셈이 되므로 일부러 안 붙임). 그래서 목업처럼 "+3.81%"
    같은 정밀 수치 대신 momentum 라벨(상승/하락/보합)을 그대로 보여준다.
    desc(섹터 설명)는 sector_heatmap()엔 있었는데 막대 1줄짜리 레이아웃엔
    자리가 없어, 막대 아래 작은 보조 텍스트로 남겨 정보 손실을 막는다."""
    mom_colors = {"상승": PALETTE["up"], "하락": PALETTE["down"], "보합": "#f2a341"}
    mom_bar_pct = {"상승": 78, "하락": 45, "보합": 30}
    mom_arrows = {"상승": "▲", "하락": "▼", "보합": "―"}
    rows = ""
    for i, sector in enumerate(sector_list):
        if isinstance(sector, dict):
            name     = sector.get("name", "")
            desc     = sector.get("desc", sector.get("description", ""))
            momentum = sector.get("momentum", "")
        else:
            name, desc, momentum = str(sector), "", ""
        color = mom_colors.get(momentum, PALETTE["muted"])
        pct = mom_bar_pct.get(momentum, 20)
        arrow = mom_arrows.get(momentum, "")
        delay = i * 0.12
        desc_html = (
            f'<div style="margin:6px 0 0 90px;font-size:19px;color:{PALETTE["muted"]};'
            f'font-weight:600;line-height:1.4;">{esc(desc)}</div>' if desc else ""
        )
        rows += f"""
<div style="margin-bottom:22px;">
  <div style="display:flex;align-items:center;gap:26px;">
    <div class="badge-num" style="width:64px;height:64px;font-size:30px;
      background:{PALETTE['accent_soft']};color:{PALETTE['accent']};flex-shrink:0;">{i + 1}</div>
    <div style="width:200px;font-size:36px;font-weight:800;flex-shrink:0;">{esc(name)}</div>
    <div style="flex:1;height:56px;background:#f2f1ec;border-radius:12px;overflow:hidden;">
      <div data-anim="grow" data-to="{pct}" data-delay="{delay:.2f}" data-dur="0.85"
           style="height:56px;width:0%;background:linear-gradient(90deg,{color}cc,{color});
           border-radius:12px;"></div>
    </div>
    <div style="width:130px;text-align:right;font-size:32px;font-weight:800;color:{color};
      flex-shrink:0;">{arrow} {esc(momentum)}</div>
  </div>
  {desc_html}
</div>"""
    return f"""<div class="card" style="padding:38px 44px;">
  <div style="font-size:30px;font-weight:700;color:{PALETTE['muted']};margin-bottom:26px;">
    업종별 등락 흐름</div>{rows}</div>"""


# ── 영상 모션그래픽 업그레이드 P1-3(c): 차트 드로잉 ────────────────────────────

_chart_id_seq = itertools.count()


def svg_line_chart(prices: list, width: int = 1000, height: int = 420,
                    color: str = None) -> str:
    """종가 시계열을 "그려지는"(draw) SVG 라인 차트로 만듭니다(목업 05번
    프레임 참고 — docs/motion_mockup_reference.py의 scene_stock() 중 차트
    부분). chart.py의 draw_candle_chart()(matplotlib PNG, 캔들 차트)를
    대체하지 않고 병행 제공하는 라인 차트 버전이다 — 호출부가 chart.py의
    fetch_ohlcv()로 받은 df["Close"] 시계열을 그대로 넘기면 된다.

    data-anim="draw"로 path의 stroke-dashoffset을 선 전체 길이→0으로 진행시켜
    선이 그려지는 효과를 낸다. 영역 그라디언트는 clipPath 안 <rect>의 CSS
    width를 0%→100%로 키워(data-anim="grow") 선을 따라 차오르게 한다 — SVG
    rect에 CSS 퍼센트 width가 실제로 클리핑에 반영되는지 Chromium에서 직접
    확인함(픽셀 샘플링으로 60% 클립이 정확히 60% 지점에서 잘리는 것을 검증).
    두 애니메이션 모두 같은 dur(1.6초)를 써서 "선이 그려지는 만큼 아래
    영역도 함께 차오르는" 것처럼 보이게 한다.

    prices가 2개 미만이면(차트를 그릴 수 없음) 빈 문자열을 반환한다 —
    호출부가 기존처럼 "차트 없음" 폴백을 그대로 쓸 수 있다(회귀 없음)."""
    if not prices or len(prices) < 2:
        return ""
    color = color or PALETTE["up"]
    cid = next(_chart_id_seq)
    grad_id, clip_id = f"chartGrad{cid}", f"chartClip{cid}"

    lo, hi = min(prices) * 0.99, max(prices) * 1.01
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(prices):
        x = i / (len(prices) - 1) * width
        y = height - (v - lo) / span * height
        pts.append((x, y))
    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M 0,{height} L " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L {width},{height} Z"
    ex, ey = pts[-1]
    points_attr = ";".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    return f"""
<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="overflow:visible;">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity=".28"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="{clip_id}">
      <rect data-anim="grow" data-to="100" data-delay="0" data-dur="1.6"
            x="0" y="-40" width="0%" height="{height + 80}"/>
    </clipPath>
  </defs>
  <g clip-path="url(#{clip_id})"><path d="{area}" fill="url(#{grad_id})"/></g>
  <path data-anim="draw" data-delay="0" data-dur="1.6" d="{path}" fill="none"
        stroke="{color}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
  <circle data-anim="dot" data-points="{points_attr}" data-delay="0" data-dur="1.6"
          cx="{ex:.1f}" cy="{ey:.1f}" r="16" fill="{color}" opacity=".22"/>
  <circle data-anim="dot" data-points="{points_attr}" data-delay="0" data-dur="1.6"
          cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="{color}" stroke="#fff" stroke-width="4"/>
</svg>"""


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
