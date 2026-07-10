# pipeline/assets/ranking.py
"""
"주도주 랭킹형" 플롯 — companies/themes/volume_score/news_score/report_score를
종합해 ranking_score를 계산하고 오늘의 주도주 TOP5를 선정한다.

script.json에는 거래대금/뉴스언급/증권사언급을 직접 나타내는 숫자 필드가
없으므로, 이미 존재하는 데이터에서 다음과 같이 근사한다:
  - volume_score: chart.py의 fetch_ohlcv()(pykrx→네이버 폴백, 이미 검증된 소스)로
    가져온 최근 OHLCV의 거래량 추세(최근 절반 vs 이전 절반)
  - news_score:   해당 종목 섹션의 channel_summaries 중 유튜브/경제방송 카테고리
    개수 + 출처 수
  - report_score: channel_summaries 중 증권사 카테고리의 출처(증권사) 수

각 점수는 0~1로 정규화하고, ranking_score는 compute_ranking_score()라는
별도 함수로 분리해 가중치를 쉽게 조정/테스트할 수 있게 한다.
"""
from typing import Callable, Optional

DEFAULT_WEIGHTS = (0.4, 0.3, 0.3)  # (volume, news, report)

_AGGREGATE_STOCK_IDS = {"stock_추가관심종목", "stock_오늘의픽", "stock_증권사리포트"}


def is_stock_candidate(section_id: str) -> bool:
    if section_id in _AGGREGATE_STOCK_IDS:
        return False
    return section_id.startswith("stock_") or section_id.startswith("hidden_")


def compute_volume_score(df) -> float:
    """최근 OHLCV DataFrame(Volume 컬럼 포함)에서 최근 절반 대비 이전 절반의
    평균 거래량 비율을 0~1 점수로 정규화한다. 데이터가 없거나 너무 적으면
    중립값 0.5를 반환한다(거래량 정보 없음 ≠ 관심 없음으로 단정하지 않음)."""
    if df is None or len(df) < 4:
        return 0.5
    vol = df["Volume"].astype(float)
    half = max(1, len(vol) // 2)
    prior_vol = vol.iloc[:half].mean()
    recent_vol = vol.iloc[half:].mean()
    if prior_vol <= 0:
        return 0.5
    ratio = recent_vol / prior_vol
    # ratio 1.0(변화 없음) → 0.5, ratio 2.0(거래량 2배) → 1.0, ratio 0.0 → 0.0
    score = 0.5 + (ratio - 1.0) * 0.5
    return max(0.0, min(1.0, score))


_NEWS_CHANNEL_TYPES = {"유튜브", "경제방송"}


def compute_news_score(section: dict) -> float:
    """channel_summaries 중 유튜브/경제방송 카테고리 등장 개수 + 출처 수를
    0~1로 정규화한다."""
    summaries = section.get("channel_summaries") or []
    hit = 0
    total_sources = 0
    for cs in summaries:
        if cs.get("channel_type") in _NEWS_CHANNEL_TYPES:
            hit += 1
            total_sources += len(cs.get("sources") or [])
    if hit == 0:
        return 0.0
    score = 0.3 * hit + 0.1 * min(total_sources, 4)
    return max(0.0, min(1.0, score))


def compute_report_score(section: dict) -> float:
    """channel_summaries 중 증권사 카테고리의 출처(증권사) 수를 0~1로 정규화한다."""
    summaries = section.get("channel_summaries") or []
    for cs in summaries:
        if cs.get("channel_type") == "증권사":
            n = len(cs.get("sources") or [])
            return max(0.0, min(1.0, 0.4 + 0.2 * n))
    return 0.0


def compute_ranking_score(volume_score: float, news_score: float, report_score: float,
                           weights: tuple = DEFAULT_WEIGHTS) -> float:
    """volume/news/report 세 점수를 가중합해 ranking_score를 계산한다.
    가중치 산식을 이 함수 하나로 분리해 향후 조정/테스트가 쉽도록 했다."""
    wv, wn, wr = weights
    return round(wv * volume_score + wn * news_score + wr * report_score, 4)


def build_ranking(script_data: dict, top_n: int = 5,
                   fetch_ohlcv_fn: Optional[Callable] = None,
                   weights: tuple = DEFAULT_WEIGHTS) -> dict:
    """script.json 전체에서 종목 후보를 뽑아 ranking_score 상위 top_n개를
    선정한다. fetch_ohlcv_fn을 주입하면(테스트용) 실제 네트워크 호출 없이
    합성 OHLCV로 검증할 수 있다(기본값은 chart.fetch_ohlcv, pykrx→네이버 폴백)."""
    from .config import normalize_stock_name, STOCK_CODES, get_stock_sector

    if fetch_ohlcv_fn is None:
        from .chart import fetch_ohlcv as fetch_ohlcv_fn

    sections = script_data.get("sections") or []
    candidates = []
    for sec in sections:
        sid = sec.get("id", "")
        if not is_stock_candidate(sid):
            continue
        name = sid.replace("stock_", "").replace("hidden_", "")
        normalized = normalize_stock_name(name)

        df = fetch_ohlcv_fn(normalized)
        volume_score = compute_volume_score(df)
        news_score = compute_news_score(sec)
        report_score = compute_report_score(sec)
        ranking_score = compute_ranking_score(volume_score, news_score, report_score, weights)

        candidates.append({
            "rank": 0,  # 정렬 후 채움
            "id": sid,
            "companies": normalized,
            "code": STOCK_CODES.get(normalized, ""),
            "themes": get_stock_sector(normalized),
            "price": sec.get("price", ""),
            "change": sec.get("change", ""),
            "change_positive": sec.get("change_positive", True),
            "volume_score": round(volume_score, 3),
            "news_score": round(news_score, 3),
            "report_score": round(report_score, 3),
            "ranking_score": ranking_score,
        })

    candidates.sort(key=lambda c: c["ranking_score"], reverse=True)
    top = candidates[:top_n]
    for i, c in enumerate(top, 1):
        c["rank"] = i

    return {
        "title": script_data.get("title", ""),
        "date": script_data.get("date", ""),
        "ranking": top,
    }
