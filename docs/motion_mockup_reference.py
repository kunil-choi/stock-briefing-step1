# -*- coding: utf-8 -*-
"""
개선안(Phase 0~2) 적용 시 나오는 프레임 예시를 실제로 렌더링한다.
레포의 PALETTE / 폰트 / shell 레이아웃을 그대로 사용.
애니메이션 중간 시점(t)의 상태를 파이썬에서 계산해 정적 HTML로 굽는다.
"""
import os, base64, math, subprocess
from playwright.sync_api import sync_playwright

REPO = "/home/claude/repo"
FONT_DIR = os.path.join(REPO, "assets", "fonts")
OUT = "/mnt/user-data/outputs"
os.makedirs(OUT, exist_ok=True)

W, H = 1920, 1080
SUBTITLE_BAR_H = 180

PALETTE = {
    "bg": "#faf9f6", "dot": "#e6e4dc", "ink": "#16181d", "muted": "#6b7280",
    "accent": "#0e9f8e", "accent_soft": "#e3f7f3", "highlight": "#ffe066",
    "up": "#e0393e", "down": "#2f6fed", "card": "#ffffff", "border": "#e8e6df",
    "shadow": "rgba(20,20,20,.08)",
}


def b64font(name):
    p = os.path.join(FONT_DIR, name)
    with open(p, "rb") as f:
        return "data:font/ttf;base64," + base64.b64encode(f.read()).decode()


NOTO = b64font("NotoSansKR-Bold.ttf")
BHS = b64font("BlackHanSans-Regular.ttf")

BASE_CSS = f"""
@font-face{{font-family:'Noto Sans KR';src:url('{NOTO}') format('truetype');font-weight:100 900;font-display:block;}}
@font-face{{font-family:'Black Han Sans';src:url('{BHS}') format('truetype');font-weight:400;font-display:block;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;}}
body{{
  font-family:'Noto Sans KR',sans-serif; word-break:keep-all; color:{PALETTE['ink']};
  background: radial-gradient(circle, {PALETTE['dot']} 1.6px, transparent 1.6px) 0 0/30px 30px, {PALETTE['bg']};
  position:relative;
}}
.stage{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;}}
.topbar{{position:absolute;left:0;top:0;width:{W}px;height:96px;display:flex;align-items:center;
  padding:0 56px;background:{PALETTE['card']};border-bottom:1px solid {PALETTE['border']};}}
.topbar .brand{{font-weight:800;font-size:26px;color:{PALETTE['accent']};margin-right:28px;}}
.topbar .brand-sub{{font-weight:600;font-size:18px;color:{PALETTE['muted']};margin-right:28px;}}
.topbar .divider{{width:2px;height:40px;background:{PALETTE['border']};margin-right:28px;}}
.topbar .label{{font-weight:800;font-size:36px;flex:1;}}
.topbar .date{{font-weight:600;font-size:24px;color:{PALETTE['muted']};}}
.subtitle-zone{{position:absolute;left:0;bottom:0;width:{W}px;height:{SUBTITLE_BAR_H}px;
  background:linear-gradient(180deg,rgba(22,24,29,0) 0%,rgba(22,24,29,.55) 45%,rgba(22,24,29,.55) 100%);}}
.subtitle-zone .tag{{position:absolute;top:14px;right:40px;font-size:18px;font-weight:700;color:#fff;opacity:.85;}}
.subtitle-zone .sub{{position:absolute;left:0;right:0;bottom:44px;text-align:center;color:#fff;
  font-size:42px;font-weight:700;text-shadow:0 3px 10px rgba(0,0,0,.6);}}
.subtitle-zone .sub em{{font-style:normal;color:{PALETTE['highlight']};}}
.content{{position:absolute;left:56px;right:56px;top:120px;bottom:{SUBTITLE_BAR_H + 24}px;}}
.card{{background:{PALETTE['card']};border:1px solid {PALETTE['border']};border-radius:20px;
  box-shadow:0 10px 28px {PALETTE['shadow']};}}
.mockmark{{position:absolute;left:24px;top:{H - SUBTITLE_BAR_H - 46}px;z-index:99;
  font-family:monospace;font-size:20px;font-weight:700;color:#ff2d95;
  background:rgba(255,255,255,.92);border:2px solid #ff2d95;border-radius:8px;padding:4px 12px;}}
"""


def shell(label, content, tag="", sub="", mark=""):
    tag_html = f'<div class="tag">#{tag}</div>' if tag else ""
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    mark_html = f'<div class="mockmark">{mark}</div>' if mark else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}</style></head>
<body><div class="stage">
  <div class="topbar"><div class="brand">KBS</div><div class="brand-sub">머니올라</div>
    <div class="divider"></div><div class="label">{label}</div><div class="date">2026.08.21</div></div>
  <div class="content">{content}</div>
  {mark_html}
  <div class="subtitle-zone">{tag_html}{sub_html}</div>
</div></body></html>"""


def ease(t):
    """easeOutCubic — 방송 그래픽에서 가장 흔한 감속 커브"""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ── 씬 1: 시장 지표 카운트업 ────────────────────────────────────────────────
IDX = [
    ("코스피", 3152.47, 1.24, True),
    ("코스닥", 812.30, 0.85, True),
    ("원/달러", 1382.50, -0.42, False),
]


def scene_market(t, animated=True):
    """t: 장면 시작 후 경과 초"""
    cards = []
    for i, (name, val, chg, up) in enumerate(IDX):
        delay = i * 0.18
        p = ease((t - delay) / 0.9) if animated else 1.0
        shown = val * p
        col = PALETTE["up"] if up else PALETTE["down"]
        arrow = "▲" if up else "▼"
        # 등장 모션: 아래에서 살짝 올라오며 페이드인
        ty = (1 - p) * 26
        op = min(1.0, p * 1.6)
        # 등락률 배지는 숫자가 다 굴러간 뒤(p>0.85)에 팝
        bp = ease((t - delay - 0.75) / 0.35) if animated else 1.0
        bscale = 0.6 + 0.4 * bp if bp > 0 else 0
        bar_w = 100 * ease((t - delay - 0.2) / 0.8) if animated else 100
        cards.append(f"""
<div class="card" style="flex:1;padding:34px 38px;transform:translateY({ty:.1f}px);opacity:{op:.2f};">
  <div style="font-size:28px;font-weight:700;color:{PALETTE['muted']};">{name}</div>
  <div style="font-size:88px;font-weight:800;letter-spacing:-.02em;line-height:1.1;
       font-variant-numeric:tabular-nums;">{shown:,.2f}</div>
  <div style="height:8px;background:{PALETTE['border']};border-radius:99px;margin:14px 0 18px;">
    <div style="height:8px;width:{bar_w:.1f}%;background:{col};border-radius:99px;"></div></div>
  <div style="display:inline-flex;align-items:center;gap:10px;background:{col};color:#fff;
       border-radius:99px;padding:8px 22px;font-size:30px;font-weight:800;
       transform:scale({bscale:.2f});opacity:{min(1,bp*2):.2f};">{arrow} {abs(chg):.2f}%</div>
</div>""")
    # 투자자별 순매수 (하단 스트립)
    flows = [("외국인", 4820, True), ("기관", 1240, True), ("개인", -6060, False)]
    fmax = 6500
    frows = []
    for i, (who, amt, up) in enumerate(flows):
        d = 1.05 + i * 0.14
        fp = ease((t - d) / 0.7) if animated else 1.0
        col = PALETTE["up"] if up else PALETTE["down"]
        frows.append(f"""
<div style="display:flex;align-items:center;gap:22px;margin-bottom:16px;opacity:{min(1,fp*2):.2f};">
  <div style="width:120px;font-size:30px;font-weight:800;color:{PALETTE['muted']};">{who}</div>
  <div style="flex:1;height:38px;background:#f2f1ec;border-radius:10px;overflow:hidden;">
    <div style="height:38px;width:{abs(amt)/fmax*100*fp:.1f}%;
         background:linear-gradient(90deg,{col}bb,{col});border-radius:10px;"></div></div>
  <div style="width:230px;text-align:right;font-size:34px;font-weight:800;color:{col};
       font-variant-numeric:tabular-nums;">{amt*fp:+,.0f}억</div>
</div>""")
    hp = ease((t - 1.85) / 0.5) if animated else 0
    headline = f"""
<div style="margin-top:26px;font-size:44px;font-weight:800;opacity:{hp:.2f};
     transform:translateY({(1-hp)*18:.1f}px);">
  외국인 <span style="background:linear-gradient(transparent 58%, {PALETTE['highlight']} 58%);">
  8거래일 연속 순매수</span></div>"""
    strip = f"""<div class="card" style="margin-top:30px;padding:30px 40px 18px;">
  <div style="font-size:26px;font-weight:700;color:{PALETTE['muted']};margin-bottom:20px;">
    투자자별 순매수</div>{''.join(frows)}</div>"""
    return f'<div style="display:flex;gap:28px;">{"".join(cards)}</div>{strip}{headline}'


# ── 씬 2: 섹터 랭킹 바 성장 ────────────────────────────────────────────────
SECTORS = [("반도체", 3.82), ("2차전지", 2.41), ("방산", 1.95), ("조선", 1.12), ("금융", -0.64)]


def scene_sector(t, animated=True):
    mx = 4.2
    rows = []
    for i, (name, v) in enumerate(SECTORS):
        delay = i * 0.12
        p = ease((t - delay) / 0.85) if animated else 1.0
        col = PALETTE["up"] if v > 0 else PALETTE["down"]
        w = abs(v) / mx * 100 * p
        num = v * p
        rows.append(f"""
<div style="display:flex;align-items:center;gap:26px;margin-bottom:22px;opacity:{min(1,p*2):.2f};">
  <div style="width:64px;height:64px;border-radius:50%;background:{PALETTE['accent_soft']};
       color:{PALETTE['accent']};font-size:30px;font-weight:800;display:flex;
       align-items:center;justify-content:center;flex-shrink:0;">{i+1}</div>
  <div style="width:200px;font-size:36px;font-weight:800;">{name}</div>
  <div style="flex:1;height:56px;background:#f2f1ec;border-radius:12px;overflow:hidden;">
    <div style="height:56px;width:{w:.1f}%;background:linear-gradient(90deg,{col}cc,{col});
         border-radius:12px;"></div></div>
  <div style="width:170px;text-align:right;font-size:44px;font-weight:800;color:{col};
       font-variant-numeric:tabular-nums;">{num:+.2f}%</div>
</div>""")
    return f"""<div class="card" style="padding:38px 44px;">
  <div style="font-size:30px;font-weight:700;color:{PALETTE['muted']};margin-bottom:26px;">
    업종별 등락률 TOP 5</div>{''.join(rows)}</div>"""


# ── 씬 3: 차트 드로잉 + 나레이션 싱크 강조 ─────────────────────────────────
PRICES = [71200, 70800, 72400, 73100, 72600, 74300, 75900, 75200, 76800, 78400,
          79100, 78600, 80200, 81500, 80900, 82700, 84100, 83600, 85300, 86900]


def scene_stock(t, animated=True, pop=False):
    cw, ch = 1000, 420
    lo, hi = min(PRICES) * 0.99, max(PRICES) * 1.01
    pts = []
    for i, v in enumerate(PRICES):
        x = i / (len(PRICES) - 1) * cw
        y = ch - (v - lo) / (hi - lo) * ch
        pts.append((x, y))
    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    p = ease(t / 1.6) if animated else 1.0
    dash = "" if not animated else f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{length*(1-p):.0f}"'
    # 진행 중인 선 끝의 광점
    idx = min(len(pts) - 1, int(p * (len(pts) - 1)))
    ex, ey = pts[idx]
    area = f"M 0,{ch} L " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L {cw},{ch} Z"

    up = PALETTE["up"]
    chart = f"""
<svg viewBox="0 0 {cw} {ch}" width="{cw}" height="{ch}" style="overflow:visible;">
  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{up}" stop-opacity=".28"/>
    <stop offset="100%" stop-color="{up}" stop-opacity="0"/></linearGradient>
    <clipPath id="c"><rect x="0" y="-40" width="{cw*p:.1f}" height="{ch+80}"/></clipPath></defs>
  <g clip-path="url(#c)"><path d="{area}" fill="url(#g)"/></g>
  <path d="{path}" fill="none" stroke="{up}" stroke-width="7" stroke-linecap="round"
        stroke-linejoin="round" {dash}/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="16" fill="{up}" opacity=".22"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="{up}" stroke="#fff" stroke-width="4"/>
</svg>"""

    pop_scale = 1.18 if pop else 1.0
    pop_bg = PALETTE["highlight"] if pop else "transparent"
    pop_shadow = f"0 6px 22px rgba(224,57,62,.35)" if pop else "none"
    rp = ease((t - 1.15) / 0.5) if animated else 1.0
    right = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:26px;
     opacity:{rp:.2f};transform:translateX({(1-rp)*30:.1f}px);">
  <div style="font-size:30px;font-weight:700;color:{PALETTE['muted']};">2분기 영업이익</div>
  <div style="display:inline-block;font-size:96px;font-weight:800;color:{PALETTE['up']};
       transform:scale({pop_scale});transform-origin:left center;
       background:{pop_bg};border-radius:14px;padding:2px 16px;box-shadow:{pop_shadow};
       font-variant-numeric:tabular-nums;">12조원</div>
  <div style="font-size:34px;font-weight:700;color:{PALETTE['muted']};">
    전년 대비 <span style="color:{PALETTE['up']};font-weight:800;">+214%</span></div>
</div>"""
    return f"""<div class="card" style="padding:36px 44px;display:flex;gap:44px;align-items:center;height:100%;">
  <div><div style="font-size:34px;font-weight:800;margin-bottom:10px;">삼성전자
    <span style="font-size:26px;color:{PALETTE['muted']};font-weight:600;">005930</span></div>
    {chart}</div>{right}</div>"""


# ── AS-IS(현재 방식) 비교용 ────────────────────────────────────────────────
def scene_asis():
    rows = "".join(
        f'<tr style="border-top:1px solid {PALETTE["border"]};">'
        f'<td style="padding:16px 28px;font-weight:700;color:{PALETTE["muted"]};">{n}</td>'
        f'<td style="padding:16px 28px;text-align:right;font-weight:800;font-size:30px;">{v:,.2f}</td>'
        f'<td style="padding:16px 28px;text-align:right;font-weight:700;font-size:24px;'
        f'color:{PALETTE["up"] if u else PALETTE["down"]};">{"▲" if u else "▼"} {abs(c):.2f}%</td></tr>'
        for n, v, c, u in IDX)
    return f"""<table class="card" style="width:100%;border-collapse:collapse;font-size:26px;">
<tr style="background:{PALETTE['accent_soft']};">
  <th style="text-align:left;padding:18px 28px;">지수</th>
  <th style="text-align:right;padding:18px 28px;">현재가</th>
  <th style="text-align:right;padding:18px 28px;">등락률</th></tr>{rows}</table>
<div style="margin-top:28px;font-size:28px;line-height:1.6;color:{PALETTE['ink']};">
  외국인이 8거래일 연속 순매수를 이어가며 지수 상승을 이끌었습니다.</div>"""


FRAMES = [
    ("00_AS-IS_현재방식_정지슬라이드",
     shell("오늘의 시장", scene_asis(), tag="시장요약",
           sub="외국인이 <em>8거래일 연속</em> 순매수를 이어가며",
           mark="AS-IS · 0.0s ~ 22.0s 내내 동일 (완전 정지)")),
    ("01_카운트업_t0.10s",
     shell("오늘의 시장", scene_market(0.10), tag="시장요약",
           sub="코스피는 오늘",
           mark="AFTER · t=0.10s · 카드 등장 + 숫자 카운트업 시작")),
    ("02_카운트업_t0.55s",
     shell("오늘의 시장", scene_market(0.55), tag="시장요약",
           sub="코스피는 오늘 3,152포인트로",
           mark="AFTER · t=0.55s · 숫자 굴러가는 중 + 게이지 성장")),
    ("03_카운트업_t2.60s_완료",
     shell("오늘의 시장", scene_market(2.60), tag="시장요약",
           sub="외국인이 <em>8거래일 연속</em> 순매수를 이어가며",
           mark="AFTER · t=2.60s · 착지 + 나레이션 싱크 하이라이트")),
    ("04_섹터랭킹바_t0.75s",
     shell("업종별 흐름", scene_sector(0.75), tag="섹터",
           sub="반도체가 <em>3.8% 급등</em>하며 시장을 이끌었고",
           mark="AFTER · t=0.75s · 바가 순차적으로 자라는 중")),
    ("05_차트드로잉_t0.80s",
     shell("주도주 체크", scene_stock(0.80), tag="삼성전자",
           sub="최근 한 달 주가는 꾸준히 우상향했습니다",
           mark="AFTER · t=0.80s · 차트 라인이 그려지는 중")),
    ("06_나레이션싱크_팝_t3.20s",
     shell("주도주 체크", scene_stock(2.0, pop=True), tag="삼성전자",
           sub="2분기 영업이익은 <em>12조원</em>을 기록했습니다",
           mark="AFTER · t=3.20s · '12조원' 발화 순간 숫자 팝 (Phase 2)")),
]


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for name, html in FRAMES:
            page.set_content(html, wait_until="load")
            page.evaluate("() => document.fonts.ready")
            path = os.path.join(OUT, f"{name}.png")
            page.screenshot(path=path)
            print("✅", path)
        b.close()


if __name__ == "__main__":
    main()
