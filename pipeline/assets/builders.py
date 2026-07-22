# pipeline/assets/builders.py
"""
KBS 머니올라 — 방송 비주얼 빌더 (HTML/CSS 슬라이드 + Playwright 렌더링)
"동영상"이 아니라 "PPT 슬라이드를 만들어서 화면으로 쓴다"는 관점으로 설계.
generate_assets.py가 기대하는 함수 시그니처/반환값/출력 파일명은 기존과 동일하게 유지한다.
"""
import os

from .config import BROKERAGE_FIRMS
from .render import render_html_to_png
from .html_theme import (
    esc, file_uri, shell, centered_shell, kbs_badge, stat_table,
    point_card, point_card_img, bullet_column, quote_bubble, page_dots,
    numbered_bullets_from_text, PALETTE, _ACCENT_CYCLE,
    headline_card, report_card, risk_card, sector_heatmap,
    autofit_text, text_plate,
)
from .chart import build_chart_with_insight, build_week_chart
from .image_fetch import fetch_news_image

_CONCLUSION_BG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "backgrounds",
    "conclusion_market.jpg",
)


def _find_section(sections, id_prefix):
    for s in sections:
        if s.get("id", "").startswith(id_prefix):
            return s
    return {}


# ── 오프닝 ─────────────────────────────────────────────────────────────────

def build_opening(data, out_dir):
    sec      = _find_section(data.get("sections", []), "opening")
    keywords = sec.get("keywords", [])[:4]
    date_str = data.get("date", "")

    kw_html = "".join(
        f'<span class="pill" style="background:{c}1a;color:{c};border:2px solid {c};'
        f'font-size:26px;">{esc(k)}</span>'
        for k, c in zip(keywords, _ACCENT_CYCLE)
    )
    date_html = (
        f'<div class="pill" style="background:{PALETTE["accent_soft"]};'
        f'color:{PALETTE["accent"]};font-size:26px;">{esc(date_str)}</div>'
        if date_str else ""
    )

    content = f"""
<div style="position:absolute;z-index:-1;width:900px;height:900px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-260px;left:50%;transform:translateX(-50%);"></div>
<div style="font-size:32px;font-weight:700;color:{PALETTE['accent']};letter-spacing:.01em;">돈이 몰리는 길목을 선점하라</div>
<div style="font-size:88px;font-weight:800;line-height:1.25;">KBS 머니올라<br>주도주 브리핑</div>
<div class="pill" style="background:{PALETTE['highlight']};color:{PALETTE['ink']};
  font-size:34px;font-weight:800;padding:14px 34px;">단 10분, 오늘 장 준비 끝!</div>
{date_html}
<div style="display:flex;gap:16px;margin-top:12px;">{kw_html}</div>
"""
    html = centered_shell(content)
    return render_html_to_png(html, os.path.join(out_dir, "00_opening.png"))


# ── 훅 (Phase E/짧은 하이라이트 포맷: 브랜드 인트로를 대체하는 15초 훅) ────────
#
# narrative_reorder._build_hook_section()이 만드는 합성 섹션(id="hook")을
# 화면 2장으로 나눠 렌더링한다:
#   1) 00_hook_1_title.png  — 시그니처 질문(hook_title) 한 줄만
#   2) 00_hook_2_points.png — 오늘의 핵심 이슈(hook_points) 최대 3개를 큰 글씨
#      3줄로. 두 화면 모두 같은 배경 이미지(있으면)를 재사용해 하나의 오프닝
#      시퀀스처럼 보이게 한다. media_map.json의 선택 이미지(visual)가 있으면
#      전체화면 배경 사진 + 반투명 다크 판(text_plate) 위에 흰 글자를 올리고,
#      없으면 기존 원형 그라디언트 폴백(회귀 없음)을 그대로 쓴다.
def _build_hook_title(sec, out_dir, visual, image_path):
    title = sec.get("hook_title") or sec.get("subtitle") or sec.get("narration", "")

    if image_path:
        headline_inner = (
            f'<div style="font-size:64px;font-weight:800;line-height:1.4;color:#fff;">'
            f'{esc(title)}</div>'
        )
        content = f"""
<div class="pill" style="background:{PALETTE['accent']};color:#fff;font-size:26px;padding:12px 30px;">KBS 머니올라</div>
{text_plate(headline_inner, extra_style="text-align:left;max-width:1560px;")}
"""
        html = centered_shell(content, background_image=image_path)
    else:
        content = f"""
<div style="position:absolute;z-index:-1;width:900px;height:900px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-260px;left:50%;transform:translateX(-50%);"></div>
{kbs_badge()}
<div style="font-size:60px;font-weight:800;line-height:1.45;color:{PALETTE['ink']};
  max-width:1560px;">{esc(title)}</div>
"""
        html = centered_shell(content)

    return render_html_to_png(html, os.path.join(out_dir, "00_hook_1_title.png"))


def _build_hook_points(sec, out_dir, visual, image_path):
    points = [p for p in (sec.get("hook_points") or []) if p]
    # 오늘의 핵심 이슈 칩(최대 3개) — 기존 키워드 pill 패턴 재사용.
    # reordered_script의 keywords가 없으면 scene_plan의 한국어 키워드로 보강.
    keywords = (sec.get("keywords") or visual.get("visualKeywordsKo") or [])[:3]

    if image_path:
        lines_html = "".join(
            f'<div style="display:flex;gap:16px;align-items:flex-start;margin-top:22px;">'
            f'<span style="font-size:44px;font-weight:800;color:{_ACCENT_CYCLE[i % len(_ACCENT_CYCLE)]};">●</span>'
            f'<span style="font-size:42px;font-weight:800;line-height:1.4;color:#fff;">{esc(p)}</span>'
            f'</div>'
            for i, p in enumerate(points)
        )
        content = f"""
<div class="pill" style="background:{PALETTE['accent']};color:#fff;font-size:26px;padding:12px 30px;">오늘의 핵심 이슈</div>
{text_plate(lines_html, extra_style="text-align:left;max-width:1620px;")}
"""
        html = centered_shell(content, background_image=image_path)
    else:
        lines_html = "".join(
            f'<div style="display:flex;gap:16px;align-items:flex-start;margin-top:22px;">'
            f'<span style="font-size:40px;font-weight:800;color:{_ACCENT_CYCLE[i % len(_ACCENT_CYCLE)]};">●</span>'
            f'<span style="font-size:38px;font-weight:800;line-height:1.4;color:{PALETTE["ink"]};'
            f'text-align:left;">{esc(p)}</span>'
            f'</div>'
            for i, p in enumerate(points)
        )
        kw_html = "".join(
            f'<span class="pill" style="background:{c}1a;color:{c};border:2px solid {c};'
            f'font-size:22px;font-weight:700;">{esc(k)}</span>'
            for k, c in zip(keywords, _ACCENT_CYCLE)
        )
        content = f"""
<div style="position:absolute;z-index:-1;width:900px;height:900px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-260px;left:50%;transform:translateX(-50%);"></div>
{kbs_badge()}
<div class="pill" style="background:{PALETTE['highlight']};color:{PALETTE['ink']};
  font-size:28px;font-weight:800;padding:12px 30px;">오늘의 핵심 이슈</div>
<div style="max-width:1560px;">{lines_html}</div>
<div style="display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-top:8px;">{kw_html}</div>
"""
        html = centered_shell(content)

    return render_html_to_png(html, os.path.join(out_dir, "00_hook_2_points.png"))


def build_hook(sec, out_dir, visual=None):
    visual = visual or {}
    image_path = visual.get("image_path")
    paths = [_build_hook_title(sec, out_dir, visual, image_path)]
    if sec.get("hook_points"):
        paths.append(_build_hook_points(sec, out_dir, visual, image_path))
    return paths


# ── 오늘의 한 줄 결론 ───────────────────────────────────────────────────────
#
# narrative_reorder._build_mention_intro_section()이 만드는 합성 섹션
# (id="conclusion")을 렌더링한다. 이전에는 흰 카드(headline_card) + 화면 하단
# 관심종목 티커 조합이었는데, 사용자 피드백에 따라: (1) 하단 티커 밴드를
# 빼고, (2) 매번 검색에 의존하지 않는 고정 "한국 주식시장" 대표 배경
# (거래소풍 스카이라인 + 캔들스틱 차트, generate_conclusion_background.py로
# 생성)을 깔고, (3) 그 위에 "유튜브에서 가장 많이 언급된 종목 분석" 타이틀과
# 기존 내레이션 문구를 text_plate로 얹는 방식으로 바꿨다. 내레이션 자체는
# 그대로 유지한다(문구 변경 없음, 화면 표현만 변경).
def build_conclusion(sec, out_dir):
    headline = sec.get("subtitle") or sec.get("narration", "")
    inner = (
        f'<div style="font-size:46px;font-weight:800;color:#fff;line-height:1.3;">'
        f'유튜브에서 가장 많이 언급된 종목 분석</div>'
        f'<div style="font-size:28px;font-weight:600;color:#e5e7eb;line-height:1.6;'
        f'margin-top:22px;">{esc(headline)}</div>'
    )
    content = text_plate(inner, extra_style="text-align:left;max-width:1500px;")
    bg = _CONCLUSION_BG if os.path.isfile(_CONCLUSION_BG) else None
    html = shell("오늘의 한 줄 결론", content, background_image=bg, suppress_ticker=True)
    return render_html_to_png(html, os.path.join(out_dir, "01_conclusion.png"))


# ── 시장 요약 ───────────────────────────────────────────────────────────────

def build_market_summary(data, out_dir, visual=None):
    visual = visual or {}
    sec = _find_section(data.get("sections", []), "market_summary")
    corner_summary = sec.get("corner_summary", "")
    points = sec.get("points", [])[:6]
    image_path = visual.get("image_path")
    screen_lines = [l for l in (visual.get("screenText") or []) if l]
    # headline_card()는 이미 불투명 흰 카드 안에 텍스트를 담으므로 배경 사진이
    # 있어도 별도 색상 처리 없이 그대로 안전하게 읽힌다.
    headline_text = "\n".join(screen_lines) if screen_lines else corner_summary

    rows = [
        ("코스피",    sec.get("kospi_value", ""),  sec.get("kospi_change", ""),  sec.get("kospi_change_positive", True)),
        ("코스닥",    sec.get("kosdaq_value", ""), sec.get("kosdaq_change", ""), sec.get("kosdaq_change_positive", True)),
        ("나스닥",    sec.get("nasdaq_value", ""), sec.get("nasdaq_change", ""), sec.get("nasdaq_positive", False)),
        ("S&P500",    sec.get("sp500_value", ""),  sec.get("sp500_change", ""),  sec.get("sp500_positive", False)),
        ("원달러환율", sec.get("usdkrw_value", ""), sec.get("usdkrw_change", ""), sec.get("usdkrw_positive", False)),
    ]

    corner_html = headline_card(headline_text) if headline_text else ""
    points_html = ""
    if points:
        cards = "".join(point_card(i + 1, p, _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)])
                         for i, p in enumerate(points))
        points_html = f"""
<div style="font-size:30px;font-weight:800;margin:28px 0 16px;color:{PALETTE['accent']};">오늘의 핵심 포인트</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">{cards}</div>"""

    content = f"""{corner_html}
<div style="display:flex;gap:32px;align-items:flex-start;">
  <div style="flex:1;">{stat_table(rows)}</div>
</div>
{points_html}"""

    html = shell("주요 지표", content, background_image=image_path)
    return [render_html_to_png(html, os.path.join(out_dir, "01_market_00.png"))]


# ── 업종 분석 ───────────────────────────────────────────────────────────────

def build_sector(data, out_dir, visual=None):
    visual = visual or {}
    sec = _find_section(data.get("sections", []), "sectors")
    corner_summary = sec.get("corner_summary", "")
    sector_list = sec.get("sector_list", sec.get("sectors", sec.get("list", [])))[:6]
    image_path = visual.get("image_path")
    screen_lines = [l for l in (visual.get("screenText") or []) if l]
    headline_text = "\n".join(screen_lines) if screen_lines else corner_summary

    if image_path and headline_text:
        headline_html = text_plate(
            f'<div style="font-size:32px;font-weight:800;color:#fff;white-space:pre-line;">'
            f'{esc(headline_text)}</div>'
        )
    else:
        headline_html = (
            f'<div class="corner-summary">{esc(headline_text)}</div>' if headline_text else ""
        )

    content = f"""{headline_html}
{sector_heatmap(sector_list)}"""

    html = shell("핵심 업종 분석", content, background_image=image_path)
    return render_html_to_png(html, os.path.join(out_dir, "02_sector.png"))


# ── 종목 요약 슬라이드 ──────────────────────────────────────────────────────

def _build_stock_summary(sec, out_path, img_dir, visual=None):
    visual         = visual or {}
    stock_name     = sec.get("id", "").replace("stock_", "").replace("hidden_", "")
    # 1차 작업의 needsDataReview 안전장치를 화면에 실제로 적용: 오염 의심
    # 종목명(예: "뉴스경제방송유튜브")은 실제 이름 대신 안전한 표시명으로 보여준다.
    display_name  = (visual.get("safeDisplayName") or stock_name) if visual.get("needsDataReview") else stock_name
    price          = sec.get("price", "")
    change         = sec.get("change", "")
    positive       = sec.get("change_positive", True)
    summary        = sec.get("summary", "")
    catalysts      = sec.get("catalysts", [])[:4]
    risks          = sec.get("risks", [])[:4]
    corner_summary = sec.get("corner_summary", "")
    is_hidden      = sec.get("id", "").startswith("hidden_")
    image_path     = visual.get("image_path")
    screen_lines   = [l for l in (visual.get("screenText") or []) if l]

    hidden_badge = (
        f'<span class="pill" style="background:{PALETTE["highlight"]};color:#5c4a00;'
        f'font-size:20px;padding:6px 18px;margin-bottom:10px;">숨은 종목</span><br>'
        if is_hidden else ""
    )

    # 사진 배경 위에서는 accent(민트)보다 흰색 숫자가 대비가 안정적이다.
    price_number_color = "#ffffff" if image_path else PALETTE["accent"]
    price_html = ""
    if price:
        color = PALETTE["up"] if positive else PALETTE["down"]
        arrow = "▲" if positive else "▼"
        change_html = (
            f'<span class="pill" style="background:{color}1a;color:{color};'
            f'font-size:28px;margin-left:16px;">{arrow} {esc(change)}</span>'
            if change else ""
        )
        price_html = (
            f'<div style="margin-top:14px;">'
            f'<span style="font-size:48px;font-weight:800;color:{price_number_color};">'
            f'₩ {esc(price)}</span>{change_html}</div>'
        )

    # 화면 헤드라인: scene_plan의 압축된 screenText(최대 2줄) 우선, 없으면
    # 기존처럼 corner_summary/summary 원문으로 폴백(회귀 없음).
    summary_text = "\n".join(screen_lines) if screen_lines else (corner_summary or summary)

    # FIX-DUP-LOWER-1: 예전에는 화면 하단에 lower_third(종목명/코드/등락률/섹터)를
    # 또 띄웠는데, 이 정보가 전부 화면 상단(종목명/가격/등락률)과 그대로 겹쳐
    # 의미 없는 중복이었다. 그 자리를 최근 1주일(5거래일) 소형 주가 차트로
    # 대체한다 — 데이터를 못 구하면(네트워크 등) 조용히 생략한다(회귀 없음).
    chart_path = None
    try:
        chart_path = build_week_chart(stock_name, img_dir)
    except Exception as e:
        print(f"  [chart] 주간 차트 조회 실패({stock_name}): {e}")

    chart_html = ""
    if chart_path:
        chart_html = (
            f'<div class="card" style="padding:14px 18px;flex:1;min-width:300px;">'
            f'<div style="font-size:19px;font-weight:700;color:{PALETTE["muted"]};'
            f'margin-bottom:8px;">📈 최근 1주일 주가 추이</div>'
            f'<img src="{file_uri(chart_path)}" style="width:100%;border-radius:8px;display:block;">'
            f'</div>'
        )

    lower_html = ""
    cols = ""
    if catalysts:
        cols += bullet_column("투자 포인트", catalysts, PALETTE["up"])
    if risks:
        cols += f'<div style="flex:1;">{risk_card(risks)}</div>'
    cols += chart_html
    if cols:
        lower_html = f'<div style="display:flex;gap:24px;margin-top:28px;align-items:stretch;">{cols}</div>'

    if image_path:
        # 배경 이미지가 있으면 150px 원형 로고 대신 전체화면 배경을 쓰고,
        # 이름/가격/헤드라인을 반투명 다크 판 안에 흰 글자로 담는다.
        title_block = (
            f'{hidden_badge}'
            f'<div style="font-size:72px;font-weight:800;color:#fff;">{esc(display_name)}</div>'
            f'{price_html}'
        )
        summary_html = (
            f'<div style="font-size:28px;font-weight:700;color:#fff;margin-top:18px;'
            f'line-height:1.5;white-space:pre-line;">{esc(summary_text)}</div>'
            if summary_text else ""
        )
        content = f"""
<div>
  {text_plate(title_block + summary_html, extra_style="display:block;max-width:1400px;")}
  {lower_html}
</div>
"""
        bar_label = f"숨은 종목 분석: {display_name}" if is_hidden else f"종목 분석: {display_name}"
        html = shell(bar_label, content, stock_tag=display_name, background_image=image_path,
                     suppress_ticker=True)
        return render_html_to_png(html, out_path)

    # ── 배경 이미지가 없을 때(기존 동작, 회귀 없음) ──────────────────────────
    # needsDataReview(오염 의심 종목명)면 그 이름으로 로고를 검색하는 것 자체가
    # 무의미하므로 건너뛴다(실패로 끝날 헛된 외부 요청을 만들지 않음).
    logo_path = None if visual.get("needsDataReview") else fetch_news_image(stock_name, img_dir, [])
    logo_html = (
        f'<img src="{file_uri(logo_path)}" style="width:150px;height:150px;'
        f'border-radius:50%;object-fit:cover;border:4px solid {PALETTE["accent"]};'
        f'position:absolute;top:0;right:0;">'
        if logo_path else ""
    )
    summary_html = (
        f'<div class="corner-summary" style="margin-top:24px;white-space:pre-line;">{esc(summary_text)}</div>'
        if summary_text else ""
    )
    content = f"""
<div>
  <div style="position:relative;">
    {logo_html}
    {hidden_badge}
    <div style="font-size:72px;font-weight:800;">{esc(display_name)}</div>
    {price_html}
  </div>
  {summary_html}
  {lower_html}
</div>
"""
    bar_label = f"숨은 종목 분석: {display_name}" if is_hidden else f"종목 분석: {display_name}"
    html = shell(bar_label, content, stock_tag=display_name, suppress_ticker=True)
    return render_html_to_png(html, out_path)


# ── 종목 차트 슬라이드 ──────────────────────────────────────────────────────

def _build_stock_chart(sec, out_path, img_dir):
    stock_name = sec.get("id", "").replace("stock_", "").replace("hidden_", "")

    briefing_chart = os.path.join(img_dir, f"briefing_chart_{stock_name}.png")
    insight = None
    if os.path.exists(briefing_chart):
        chart_path = briefing_chart
        print(f"  [chart] 브리핑 앱 차트 사용: {stock_name}")
    else:
        chart_path, insight = build_chart_with_insight(stock_name, img_dir)

    if chart_path:
        insight_html = (
            f'<div class="corner-summary" style="margin-top:18px;">📈 {esc(insight)}</div>'
            if insight else ""
        )
        body = (f'<div class="card" style="padding:20px;text-align:center;">'
                f'<img src="{file_uri(chart_path)}" style="width:100%;border-radius:12px;"></div>'
                f'{insight_html}')
    else:
        body = (f'<div class="card" style="height:600px;display:flex;align-items:center;'
                f'justify-content:center;font-size:34px;color:{PALETTE["muted"]};">'
                f'{esc(stock_name)} 차트 데이터 준비 중</div>')

    html = shell(f"2주간 주가 차트: {stock_name}", body, stock_tag=stock_name)
    return render_html_to_png(html, out_path)


# ── 언급(mention) 슬라이드 — 채널 카테고리별 종합 분석 ──────────────────────

_CHANNEL_TYPE_LABELS = {"유튜브": "유튜브 종합", "경제방송": "경제방송 종합", "증권사": "증권사 리포트 종합"}


def _build_mention_page(sec, out_path, page_idx):
    stock_name = sec.get("id", "").replace("stock_", "").replace("hidden_", "")
    summaries  = sec.get("channel_summaries", [])
    total_pages = max(1, len(summaries))
    cs = summaries[page_idx] if page_idx < len(summaries) else {}

    channel_type = cs.get("channel_type", "")
    sources      = [s for s in cs.get("sources", []) if s]
    content      = cs.get("subtitle", "")
    label        = _CHANNEL_TYPE_LABELS.get(channel_type, channel_type or "종합 분석")
    source_text  = ", ".join(sources)

    card = quote_bubble(source_text, "", content, _ACCENT_CYCLE[page_idx % len(_ACCENT_CYCLE)], label)

    body = (f'<div style="display:flex;flex-direction:column;gap:20px;">{card}</div>'
            + page_dots(total_pages, page_idx))

    html = shell(f"전문가·방송 언급: {stock_name}", body, stock_tag=stock_name)
    return render_html_to_png(html, out_path)


# ── 종목 카드 묶음 ─────────────────────────────────────────────────────────

def build_stock_cards(sec, out_dir, img_dir, prefix, visual=None):
    generated_paths = set()

    summary_path = os.path.join(out_dir, f"{prefix}_1_summary.png")

    paths = [
        _build_stock_summary(sec, summary_path, img_dir, visual=visual),
    ]
    generated_paths.add(summary_path)

    pages = len(sec.get("channel_summaries", []))

    for p in range(pages):
        mention_path = os.path.join(out_dir, f"{prefix}_3_mention_{p:02d}.png")
        if mention_path in generated_paths:
            print(f"  ⚠️ 중복 프레임 건너뜀: {os.path.basename(mention_path)}")
            continue
        generated_paths.add(mention_path)
        paths.append(_build_mention_page(sec, mention_path, p))

    return paths


# ── 집계형 종목 섹션 (추가 관심 종목 / 증권사 리포트) ────────────────────────
# summary+chart+mention 개별 카드가 아니라 단일 슬라이드 한 장으로 구성.

def _extract_broker_label(text: str) -> str:
    """items[].text에서 언급된 첫 증권사명을 찾아 report_card의 broker 라벨로
    사용한다. script.json의 집계 섹션 items에는 별도 broker 필드가 없어
    (Phase B가 도입한) BROKERAGE_FIRMS 사전으로 텍스트에서 역추출한다."""
    for firm in BROKERAGE_FIRMS:
        if firm in (text or ""):
            return firm
    return "증권사 리포트"


def _build_aggregate_stock_slide(sec, out_dir, filename, title, use_report_card=False,
                                  img_dir=None):
    corner_summary = sec.get("corner_summary", "")
    corner_html = (
        f'<div class="corner-summary">{esc(corner_summary)}</div>' if corner_summary else ""
    )

    items = sec.get("items", [])
    if items and use_report_card:
        cards = "".join(
            report_card(
                _extract_broker_label(it.get("text", "")),
                (it.get("name") or "").strip(),
                (it.get("text") or "").strip(),
                color=_ACCENT_CYCLE[i % len(_ACCENT_CYCLE)],
            )
            for i, it in enumerate(items) if isinstance(it, dict)
        )
        body_html = f'<div style="display:flex;flex-direction:column;gap:14px;">{cards}</div>'
    elif items:
        # FIX-WATCHLIST-CARD-1: 종목명+설명을 하나의 텍스트 줄로 뭉쳐 보여주던
        # point_card() 대신, 종목마다 썸네일을 곁들인 카드형 레이아웃
        # (point_card_img())으로 바꿔 화면과 자막이 겹쳐 보이던 문제(자막이
        # 화면 텍스트를 그대로 반복)를 시각적으로도 구분되게 했다.
        cards = ""
        for i, it in enumerate(items):
            if isinstance(it, dict):
                name = (it.get("name") or "").strip()
                text = (it.get("text") or "").strip()
            else:
                name, text = "", str(it)
            img_uri = ""
            if name and img_dir is not None:
                img_path = fetch_news_image(name, img_dir, [])
                if img_path:
                    img_uri = file_uri(img_path)
            cards += point_card_img(i + 1, name, text, _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)], img_uri)
        layout = "grid;grid-template-columns:1fr 1fr" if len(items) > 5 else "flex;flex-direction:column"
        # FIX-TICKER-OVERLAP-1: 하단 뉴스 티커(news_ticker, .content 하단에
        # absolute 도킹)가 카드 목록 마지막 항목과 겹쳐 가리던 문제 — 다른
        # 빌더들처럼 티커 높이만큼 하단 여백을 미리 확보한다.
        body_html = f'<div style="display:{layout};gap:14px;padding-bottom:64px;">{cards}</div>'
    else:
        # items가 없는 경우(레거시/누락 대비): 문장 단위로만 분할해 표시
        body_text = sec.get("subtitle", sec.get("narration", ""))
        bullets = numbered_bullets_from_text(body_text, max_items=8)
        cards = "".join(
            point_card(i + 1, b, _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)])
            for i, b in enumerate(bullets)
        )
        body_html = f'<div style="display:flex;flex-direction:column;gap:14px;padding-bottom:64px;">{cards}</div>'

    content = f"{corner_html}{body_html}"
    html = shell(title, content)
    return render_html_to_png(html, os.path.join(out_dir, filename))


def build_extra_watchlist(data, out_dir, img_dir=None):
    sec = _find_section(data.get("sections", []), "stock_추가관심종목")
    if not sec:
        return None
    return _build_aggregate_stock_slide(sec, out_dir, "90_extra_watchlist.png", "추가 관심 종목",
                                         img_dir=img_dir)


def build_brokerage_report(data, out_dir, img_dir=None):
    sec = _find_section(data.get("sections", []), "stock_증권사리포트")
    if not sec:
        return None
    return _build_aggregate_stock_slide(sec, out_dir, "92_brokerage_report.png", "증권사 리포트",
                                         use_report_card=True, img_dir=img_dir)


# ── AI 투자 전략 ────────────────────────────────────────────────────────────

def build_ai_strategy(data, out_dir):
    sec = _find_section(data.get("sections", []), "ai_strategy")
    corner_summary = sec.get("corner_summary", "")
    bullet_points  = sec.get("bullet_points", sec.get("strategies", sec.get("items", [])))[:6]

    header = f"""
<div class="card" style="display:flex;align-items:center;gap:20px;padding:22px 28px;margin-bottom:24px;
  border-left:8px solid {PALETTE['accent']};">
  <div class="pill" style="background:{PALETTE['accent']};color:#fff;font-size:26px;">AI</div>
  <div>
    <div style="font-size:32px;font-weight:800;">오늘의 투자 전략 제안</div>
    {f'<div style="font-size:22px;color:{PALETTE["muted"]};margin-top:4px;">{esc(corner_summary)}</div>' if corner_summary else ''}
  </div>
</div>"""

    cards = ""
    for i, bp in enumerate(bullet_points):
        text = bp if isinstance(bp, str) else bp.get("strategy", bp.get("content", str(bp)))
        color = _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)]
        if " — " in text:
            stock_part, strat_part = text.split(" — ", 1)
            body = (f'<div style="font-size:28px;font-weight:800;color:{color};">{esc(stock_part.strip())}</div>'
                    f'<div style="font-size:24px;margin-top:6px;line-height:1.5;">{esc(strat_part.strip())}</div>')
        else:
            body = f'<div style="font-size:26px;line-height:1.5;">{esc(text)}</div>'
        cards += (
            f'<div class="card" style="display:flex;gap:18px;padding:20px 24px;">'
            f'<div class="badge-num" style="background:{color}22;color:{color};'
            f'border:2px solid {color};">{i + 1}</div>'
            f'<div style="flex:1;">{body}</div></div>'
        )

    content = header + f'<div style="display:flex;flex-direction:column;gap:14px;">{cards}</div>'
    html = shell("AI 투자 전략", content)
    return render_html_to_png(html, os.path.join(out_dir, "98_ai_strategy.png"))


# ── 클로징 ─────────────────────────────────────────────────────────────────

def build_closing(data, out_dir):
    content = f"""
{kbs_badge()}
<div style="font-size:96px;font-weight:800;">감사합니다</div>
<div style="font-size:38px;font-weight:600;color:{PALETTE['accent']};">성공적인 투자 되시길 바랍니다</div>
<div class="card" style="border:2px solid {PALETTE['up']}55;background:#fff6f6;
  padding:28px 36px;max-width:1400px;margin-top:12px;">
  <div style="font-size:28px;font-weight:800;color:{PALETTE['up']};margin-bottom:14px;">투자 유의사항</div>
  <div style="font-size:22px;line-height:1.7;color:#5c3a3a;text-align:left;">
    본 브리핑은 AI가 공개 데이터를 분석한 참고용 정보입니다.<br>
    특정 종목의 매수·매도 권유가 아니며, 수익을 보장하지 않습니다.<br>
    주식 투자는 원금 손실 위험이 있으며, 최종 투자 결정과<br>
    모든 책임은 전적으로 투자자 본인에게 있습니다.
  </div>
</div>
"""
    html = centered_shell(content)
    return render_html_to_png(html, os.path.join(out_dir, "99_closing.png"))


# ── 썸네일 (YouTube 업로드용, pipeline/generate_metadata.py에서 호출) ──────

def build_thumbnail(data: dict, title: str, out_path: str) -> str:
    """script.json + generate_metadata.py가 만든 title로 1920x1080(16:9,
    YouTube 썸네일 권장 규격 이상) PNG 1장을 만든다. 기존 build_opening()과
    같은 렌더링 경로(render_html_to_png)를 재사용하되, 영상 오프닝과는 다른
    더 굵고 임팩트 있는 레이아웃을 쓴다."""
    sections     = data.get("sections", [])
    leader_sec   = next((s for s in sections if s.get("id", "").startswith("stock_")), {})
    leader_name  = leader_sec.get("id", "").replace("stock_", "").replace("hidden_", "")
    change_pct   = leader_sec.get("change", "")
    is_up        = leader_sec.get("change_positive", True)
    date_str     = data.get("date", "")

    badge_color = PALETTE["up"] if is_up else PALETTE["down"]
    stock_html = (
        f'<div class="pill" style="background:{badge_color}1a;color:{badge_color};'
        f'border:3px solid {badge_color};font-size:40px;font-weight:800;">'
        f'{esc(leader_name)} {esc(change_pct)}</div>'
        if leader_name else ""
    )

    content = f"""
<div style="position:absolute;z-index:-1;width:1100px;height:1100px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-320px;left:50%;transform:translateX(-50%);"></div>
{kbs_badge()}
<div style="font-size:104px;font-weight:800;line-height:1.2;max-width:1600px;">{esc(title)}</div>
<div class="pill" style="background:{PALETTE['accent_soft']};color:{PALETTE['accent']};
  font-size:30px;">{esc(date_str)}</div>
{stock_html}
"""
    html = centered_shell(content)
    return render_html_to_png(html, out_path)
