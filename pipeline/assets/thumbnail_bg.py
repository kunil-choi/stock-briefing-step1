# pipeline/assets/thumbnail_bg.py
"""
썸네일 전용 배경 이미지 생성.

assets.chart.draw_candle_chart()는 종목 분석 슬라이드용(축·범례·어노테이션이
있는 정보 전달 목적, 밝은 배경)이라 그 위에 큰 제목 글자를 얹는 썸네일
배경으로 쓰면 정보가 과하고 대비도 약하다. 이 모듈은 대신 어두운 분위기
배경 위에:
  1) 실제 종목의 2주 캔들차트(assets.chart.fetch_ohlcv() 재사용)를 축·눈금
     없이 큼직하고 반투명하게,
  2) "일반적인 거래소" 느낌을 내는 장식 요소(격자, 흩뿌린 종목코드·등락률
     텍스트, 방향성 워터마크 화살표)를
함께 합성해 상징적인 한 장을 만든다.

시세 조회가 실패해도(네트워크 등) 장식 요소만으로 완성된 배경을 반환한다
— 실제 데이터 없이 캔들 모양을 지어내지 않는다(가짜 시세로 오해될 수 있는
요소는 만들지 않는다는 이 파이프라인의 기존 원칙과 동일).
"""
import os
import random
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

from .chart import fetch_ohlcv
from .config import normalize_stock_name

W, H = 1920, 1080

_UP_COLOR = "#e0393e"    # 상승(한국 증권가 관행)
_DOWN_COLOR = "#2f6fed"  # 하락

# 장식용 티커 텍스트에만 쓰는 종목코드 목록(실제 시세와 무관 — 순수 배경 질감).
_TICKER_CODES = [
    "KOSPI", "KOSDAQ", "005930", "000660", "035420", "051910", "006400",
    "207940", "005380", "035720", "068270", "323410", "032830", "003550",
]


def _mood_colors(is_bullish: bool):
    """상승 기조면 어두운 청록, 하락/경고 기조면 어두운 적색 계열로 전체
    분위기를 잡는다(builders.py가 배지 색으로 쓰는 PALETTE up/down과 동일
    축을 배경 톤에도 그대로 적용해 일관성을 유지)."""
    if is_bullish:
        return "#081418", "#0e6b5c"
    return "#140808", "#7a1620"


def _draw_grid(ax, alpha: float = 0.08):
    for x in np.linspace(0, 1, 13):
        ax.axvline(x, color="#ffffff", alpha=alpha, linewidth=0.8, zorder=1)
    for y in np.linspace(0, 1, 8):
        ax.axhline(y, color="#ffffff", alpha=alpha, linewidth=0.8, zorder=1)


def _draw_ticker_noise(ax, seed_key: str):
    """일반적인 거래소 시세판을 연상시키는 순수 장식 텍스트(실제 시세 아님).
    같은 종목·방향이면 항상 같은 배치가 나오도록 시드를 고정해 재실행해도
    배경이 흔들리지 않게 한다."""
    rng = random.Random(seed_key)
    for _ in range(24):
        code = rng.choice(_TICKER_CODES)
        pct = rng.uniform(-4.0, 4.0)
        sign = "+" if pct >= 0 else ""
        color = _UP_COLOR if pct >= 0 else _DOWN_COLOR
        ax.text(
            rng.uniform(0.0, 1.0), rng.uniform(0.62, 1.0), f"{code} {sign}{pct:.2f}%",
            fontsize=rng.uniform(12, 17), color=color, alpha=rng.uniform(0.12, 0.24),
            family="monospace", ha="left", va="center", zorder=2,
        )


def _draw_candles(ax, df) -> None:
    """실제 OHLCV를 배경 하단부(화면 높이 8~52% 구간)에 축·눈금 없이 크고
    반투명하게 그린다. 정보 전달용이 아니라 '분위기' 전달용이라
    draw_candle_chart()와 달리 어노테이션을 전부 뺐다."""
    opens = df["Open"].astype(float)
    closes = df["Close"].astype(float)
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    n = len(df)

    lo, hi = lows.min(), highs.max()
    span = (hi - lo) or 1.0

    def norm(v):
        return 0.08 + (v - lo) / span * 0.44

    x0, x1 = 0.05, 0.95
    step = (x1 - x0) / max(n, 1)
    width = step * 0.55

    for i in range(n):
        o, c, h, l = opens.iloc[i], closes.iloc[i], highs.iloc[i], lows.iloc[i]
        color = _UP_COLOR if c >= o else _DOWN_COLOR
        cx = x0 + step * i + step / 2
        body_lo, body_hi = norm(min(o, c)), norm(max(o, c))
        if body_hi - body_lo < 0.004:
            body_hi = body_lo + 0.004
        ax.add_patch(Rectangle(
            (cx - width / 2, body_lo), width, body_hi - body_lo,
            facecolor=color, edgecolor="none", alpha=0.6, zorder=3,
        ))
        ax.plot([cx, cx], [norm(l), norm(h)], color=color, linewidth=1.8,
                alpha=0.6, zorder=3, solid_capstyle="round")


def _draw_direction_watermark(ax, is_bullish: bool):
    """텍스트가 놓이는 좌측을 비우고, 우측에 큼직한 방향 화살표를 아주
    옅게 얹어(사진 대신 상징적 '히어로 비주얼' 역할) 발언/뉴스 톤을
    한눈에 전달한다."""
    glyph = "▲" if is_bullish else "▼"
    color = _UP_COLOR if is_bullish else _DOWN_COLOR
    ax.text(0.82, 0.56, glyph, fontsize=520, color=color, alpha=0.16,
            ha="center", va="center", zorder=1, fontweight="bold")


def build_thumbnail_background(stock_name: str, img_dir: str, is_bullish: bool = True) -> Optional[str]:
    """썸네일 배경 PNG(1920x1080)를 만들어 경로를 반환한다. img_dir 안에
    캐시하며(종목·방향 조합별로 별도 캐시), assets.chart.build_chart_with_insight()의
    캐시 파일명(chart_*.png)과 겹치지 않게 thumb_bg_* 접두어를 쓴다."""
    normalized = normalize_stock_name(stock_name)
    tag = "up" if is_bullish else "down"
    save_path = os.path.join(img_dir, f"thumb_bg_{normalized}_{tag}.png")
    if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
        return save_path

    dark, glow = _mood_colors(is_bullish)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 중앙 상단에서 옅게 퍼지는 스포트라이트형 방사 그라디언트(사진 없이도
    # 시선을 모으는 초점을 만들기 위함).
    grid_res = 240
    xx, yy = np.meshgrid(np.linspace(0, 1, grid_res), np.linspace(0, 1, grid_res))
    dist = np.sqrt((xx - 0.5) ** 2 + ((yy - 0.62) * 1.4) ** 2)
    dist = dist / dist.max()
    cmap = LinearSegmentedColormap.from_list("mood", [glow, dark])
    ax.imshow(dist, extent=[0, 1, 0, 1], origin="lower", cmap=cmap,
              aspect="auto", zorder=0)

    _draw_grid(ax)
    _draw_ticker_noise(ax, f"{normalized}_{tag}")
    _draw_direction_watermark(ax, is_bullish)

    df = fetch_ohlcv(normalized, days=14)
    if df is not None and len(df) >= 3:
        _draw_candles(ax, df)
    else:
        print(f"  [thumb_bg] 시세 데이터 없음({normalized}) → 격자·티커 장식만으로 배경 구성")

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    try:
        fig.savefig(save_path, dpi=100, facecolor=dark)
    finally:
        plt.close(fig)
    return save_path
