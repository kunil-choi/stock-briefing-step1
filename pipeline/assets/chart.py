# pipeline/assets/chart.py
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
from datetime import datetime, timedelta
from typing import Optional
from .config import C, STOCK_CODES, normalize_stock_name


def _set_korean_font():
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/Library/Fonts/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            matplotlib.rcParams["font.family"] = prop.get_name()
            matplotlib.rcParams["axes.unicode_minus"] = False
            return
    matplotlib.rcParams["axes.unicode_minus"] = False

_set_korean_font()


def _fetch_ohlcv_pykrx(code: str, days: int) -> Optional[pd.DataFrame]:
    """pykrx(KRX data.krx.co.kr)로 OHLCV 조회. KRX_ID/KRX_PW 환경변수가 없으면
    최근 pykrx 버전은 예외 없이 빈 DataFrame을 반환하므로 empty 체크가 필수."""
    try:
        from pykrx import stock as krx
        end   = datetime.today().strftime("%Y%m%d")
        start = (datetime.today() - timedelta(days=days * 3)).strftime("%Y%m%d")
        df    = krx.get_market_ohlcv_by_date(start, end, code)
        if df is None or df.empty:
            return None
        df = df.tail(days)
        df.index = pd.to_datetime(df.index)
        col_map = {
            "시가": "Open", "고가": "High", "저가": "Low",
            "종가": "Close", "거래량": "Volume"
        }
        df = df.rename(columns=col_map)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                return None
        return df
    except Exception as e:
        print(f"  [chart] pykrx 실패: {e}")
        return None


def _fetch_ohlcv_naver(code: str, days: int) -> Optional[pd.DataFrame]:
    """네이버 금융 공개 시세 API로 OHLCV 조회 (로그인 불필요, pykrx의 대체 소스).
    KRX가 data.krx.co.kr 스크래핑에 로그인을 요구하면서 pykrx가 무인증 환경에서
    항상 빈 데이터를 반환하게 됐기 때문에, 이 소스를 1차 대체 경로로 사용한다."""
    import ast
    import requests
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days * 4)).strftime("%Y%m%d")
    url = "https://api.finance.naver.com/siseJson.naver"
    params = {
        "symbol": code, "requestType": "1",
        "startTime": start, "endTime": end, "timeframe": "day",
    }
    try:
        r = requests.get(url, params=params, timeout=10,
                          headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        rows = ast.literal_eval(r.text.strip())
        if not rows or len(rows) < 2:
            return None
        header, data_rows = rows[0], rows[1:]
        df = pd.DataFrame(data_rows, columns=header)
        df = df.rename(columns={
            "날짜": "Date", "시가": "Open", "고가": "High",
            "저가": "Low", "종가": "Close", "거래량": "Volume",
        })
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                return None
        df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d")
        df = df.set_index("Date").sort_index().tail(days)
        return df
    except Exception as e:
        print(f"  [chart] 네이버 금융(siseJson) 조회 실패: {e}")
        return None


def _fetch_ohlcv_naver_fchart(code: str, days: int) -> Optional[pd.DataFrame]:
    """네이버 금융 구버전 fchart XML API (siseJson과 별개 서버/포맷의 무인증 소스).
    siseJson이 차단되거나 포맷이 바뀌는 경우를 대비한 2차 대체 경로."""
    import xml.etree.ElementTree as ET
    import requests
    url = "https://fchart.stock.naver.com/sise.nhn"
    params = {"symbol": code, "timeframe": "day", "count": str(days * 4), "requestType": "0"}
    try:
        r = requests.get(url, params=params, timeout=10, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.naver.com/",
        })
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = []
        for item in root.iter("item"):
            parts = (item.attrib.get("data") or "").split("|")
            if len(parts) >= 6:
                rows.append(parts[:6])
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["Date", "Close"]).set_index("Date").sort_index().tail(days)
        return df
    except Exception as e:
        print(f"  [chart] 네이버 금융(fchart) 조회 실패: {e}")
        return None


def fetch_ohlcv(stock_name: str, days: int = 20) -> Optional[pd.DataFrame]:
    normalized = normalize_stock_name(stock_name)
    code = STOCK_CODES.get(normalized)
    if not code:
        print(f"  [chart] 종목코드 없음: {stock_name} (정규화: {normalized})")
        return None

    df = _fetch_ohlcv_pykrx(code, days)
    if df is not None and len(df) >= 3:
        print(f"  [chart] pykrx 데이터 사용: {stock_name}")
        return df

    print(f"  [chart] pykrx 데이터 없음({stock_name}) → 네이버 금융(siseJson)으로 재시도")
    df = _fetch_ohlcv_naver(code, days)
    if df is not None and len(df) >= 3:
        print(f"  [chart] 네이버 금융(siseJson) 데이터 사용: {stock_name}")
        return df

    print(f"  [chart] 네이버 금융(siseJson) 실패({stock_name}) → 네이버 금융(fchart)으로 재시도")
    df = _fetch_ohlcv_naver_fchart(code, days)
    if df is not None and len(df) >= 3:
        print(f"  [chart] 네이버 금융(fchart) 데이터 사용: {stock_name}")
        return df

    print(f"  [chart] 모든 소스에서 데이터 조회 실패: {stock_name}")
    return None


def draw_candle_chart(df: pd.DataFrame, stock_name: str, save_path: str) -> Optional[str]:
    try:
        bg     = tuple(v / 255 for v in C["chart_bg"])
        up_col = "#%02x%02x%02x" % C["chart_up"]
        dn_col = "#%02x%02x%02x" % C["chart_down"]
        grid_c = "#%02x%02x%02x" % C["chart_grid"]
        text_c = "#%02x%02x%02x" % C["chart_text"]
        gold_c = "#%02x%02x%02x" % C["gold"]

        # figsize를 (17.0, 8.0)으로 줄여서 좌측 y축 레이블 공간 확보
        fig, (ax_c, ax_v) = plt.subplots(
            2, 1,
            figsize=(17.0, 8.0),
            facecolor=bg,
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.06}
        )

        for ax in (ax_c, ax_v):
            ax.set_facecolor(bg)
            ax.tick_params(colors=text_c, labelsize=14)
            for spine in ax.spines.values():
                spine.set_color(grid_c)
            ax.yaxis.grid(True, color=grid_c, linewidth=0.8, linestyle="--")
            ax.set_axisbelow(True)

        # 캔들 몸통 + 심지
        for i, (_, row) in enumerate(df.iterrows()):
            is_up  = row["Close"] >= row["Open"]
            color  = up_col if is_up else dn_col
            body_b = min(row["Open"], row["Close"])
            body_h = abs(row["Close"] - row["Open"]) or (row["High"] * 0.001)
            ax_c.bar(i, body_h, bottom=body_b, color=color, width=0.6, zorder=3)
            ax_c.plot([i, i], [row["Low"], row["High"]],
                      color=color, linewidth=1.5, zorder=2)

        # 종가 추세선
        ax_c.plot(list(range(len(df))), df["Close"].tolist(),
                  color=gold_c, linewidth=1.2, alpha=0.5, zorder=1)

        # 거래량 바
        for i, (_, row) in enumerate(df.iterrows()):
            is_up = row["Close"] >= row["Open"]
            ax_v.bar(i, row["Volume"],
                     color=(up_col if is_up else dn_col),
                     width=0.6, alpha=0.75, zorder=3)

        # x축 날짜 레이블
        step   = max(1, len(df) // 7)
        ticks  = list(range(0, len(df), step))
        labels = [df.index[i].strftime("%m/%d") for i in ticks]
        ax_c.set_xticks([])
        ax_v.set_xticks(ticks)
        ax_v.set_xticklabels(labels, color=text_c, fontsize=14)

        # y축 설정 — labelsize 14, pad=10으로 잘림 방지
        ax_c.yaxis.set_visible(True)
        ax_c.yaxis.set_label_position("left")
        ax_c.yaxis.tick_left()
        ax_c.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
        )
        ax_c.tick_params(axis="y", colors=text_c, labelsize=14,
                         left=True, pad=10)
        ax_v.yaxis.set_visible(False)

        # 최고가·최저가 어노테이션
        hi_i     = df["High"].idxmax()
        lo_i     = df["Low"].idxmin()
        idx_list = df.index.tolist()
        hi_x     = idx_list.index(hi_i)
        lo_x     = idx_list.index(lo_i)

        ax_c.annotate(
            f"▲ {int(df.loc[hi_i, 'High']):,}",
            xy=(hi_x, df.loc[hi_i, "High"]),
            xytext=(hi_x + 0.6, df.loc[hi_i, "High"] * 1.012),
            fontsize=14, color=up_col,
            arrowprops=dict(arrowstyle="-", color=up_col, lw=1.0)
        )
        ax_c.annotate(
            f"▼ {int(df.loc[lo_i, 'Low']):,}",
            xy=(lo_x, df.loc[lo_i, "Low"]),
            xytext=(lo_x + 0.6, df.loc[lo_i, "Low"] * 0.988),
            fontsize=14, color=dn_col,
            arrowprops=dict(arrowstyle="-", color=dn_col, lw=1.0)
        )

        # 종목명 워터마크
        ax_c.text(0.01, 0.96, stock_name,
                  transform=ax_c.transAxes,
                  fontsize=18, color=gold_c,
                  fontweight="bold", va="top", alpha=0.9)

        ax_c.set_xlim(-0.8, len(df) - 0.2)
        ax_v.set_xlim(-0.8, len(df) - 0.2)

        # 좌측 여백 명시 확보 (y축 숫자 잘림 방지)
        plt.subplots_adjust(left=0.10, right=0.97, top=0.97, bottom=0.08)
        plt.savefig(save_path, dpi=100, bbox_inches="tight", facecolor=bg)
        plt.close(fig)
        print(f"  [chart] 저장 완료: {save_path}")
        return save_path

    except Exception as e:
        print(f"  [chart] 차트 생성 실패 ({stock_name}): {e}")
        plt.close("all")
        return None


def build_chart_insight(df: pd.DataFrame) -> Optional[str]:
    """2주간 OHLCV로 간단한 차트 분석법 기반 코멘트를 생성합니다.
    등락폭이 미미하고 이동평균·거래량에서도 뚜렷한 신호가 없으면 None을 반환해
    의미 없는 코멘트를 억지로 붙이지 않습니다."""
    if df is None or len(df) < 5:
        return None
    try:
        closes = df["Close"].astype(float)
        first_close, last_close = closes.iloc[0], closes.iloc[-1]
        if first_close <= 0:
            return None
        change_pct = (last_close - first_close) / first_close * 100

        ma_window = min(5, len(closes) - 1) or 1
        ma = closes.rolling(ma_window).mean().iloc[-1]
        above_ma = last_close >= ma

        vol = df["Volume"].astype(float)
        half = max(1, len(vol) // 2)
        prior_vol, recent_vol = vol.iloc[:half].mean(), vol.iloc[half:].mean()
        vol_up = prior_vol > 0 and recent_vol / prior_vol >= 1.3
        vol_down = prior_vol > 0 and recent_vol / prior_vol <= 0.7

        significant_move = abs(change_pct) >= 3.0
        if not significant_move and not vol_up and not vol_down:
            return None  # 의미 있는 신호 없음 → 코멘트 생략

        parts = []
        if significant_move:
            direction = "상승" if change_pct > 0 else "하락"
            parts.append(f"2주간 {change_pct:+.1f}% {direction}")
        parts.append(f"{ma_window}일 이동평균선 {'위' if above_ma else '아래'}에서 거래 중")
        if vol_up:
            parts.append("최근 거래량 증가 동반")
        elif vol_down:
            parts.append("최근 거래량 감소")
        return ", ".join(parts)
    except Exception as e:
        print(f"  [chart] 차트 분석 코멘트 생성 실패: {e}")
        return None


def build_chart_with_insight(stock_name: str, img_dir: str):
    """차트 이미지 경로와 (의미가 있을 때만) 차트 분석 코멘트를 함께 반환합니다.
    반환: (path_or_None, insight_text_or_None)"""
    normalized = normalize_stock_name(stock_name)
    save_path  = os.path.join(img_dir, f"chart_{normalized}.png")
    if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
        print(f"  [chart] 캐시 사용: {normalized}")
        return save_path, None
    df = fetch_ohlcv(normalized, days=14)
    if df is None or len(df) < 3:
        print(f"  [chart] 데이터 부족: {normalized}")
        return None, None
    path = draw_candle_chart(df, normalized, save_path)
    insight = build_chart_insight(df) if path else None
    return path, insight
