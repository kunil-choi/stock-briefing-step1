# tests/test_thumbnail_select.py
"""
thumbnail_select.py(발언형/뉴스형 썸네일 후보 선정) 검증 스크립트. pytest
미사용, 다른 tests/*.py와 동일하게 순수 assert 기반이며 네트워크가 필요 없다.
실행: python tests/test_thumbnail_select.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.thumbnail_select import (  # noqa: E402
    build_news_title, build_quote_title, clean_quote_for_display,
    select_news_candidate, select_quote_candidate,
)


def _sample_script():
    return {
        "sections": [
            {"id": "opening"},
            {
                "id": "stock_삼성전자", "change": "-2.1%", "change_positive": False,
                "summary": "반도체 업황 우려", "catalysts": ["HBM 수요 둔화 우려"],
            },
            {
                "id": "stock_LG전자", "change": "+0.8%", "change_positive": True,
                "summary": "가전 판매 호조", "catalysts": ["신모델 흥행"],
            },
        ],
        "raw_stock_quotes": {
            "삼성전자": [
                {
                    "speaker": "김철수 연구원", "channel": "삼프로TV", "channel_type": "유튜브",
                    "quote": "오늘 주가는 빠졌지만 저는 지금이 저가매수 기회라고 봅니다, 목표주가 10만원",
                    "sentiment": "긍정",
                },
                {
                    "speaker": "박영희 대표", "channel": "미래에셋증권", "channel_type": "증권사",
                    "quote": "무난한 실적이 예상됩니다",
                    "sentiment": "",
                },
            ],
            "LG전자": [
                {
                    "speaker": "이민수 대표", "channel": "이데일리TV", "channel_type": "경제방송",
                    "quote": "가전 실적이 견조합니다",
                    "sentiment": "긍정",
                },
            ],
        },
    }


def _sample_ranking():
    return [
        {"companies": "삼성전자", "rank": 1, "ranking_score": 0.82},
        {"companies": "LG전자", "rank": 2, "ranking_score": 0.55},
    ]


def test_select_quote_candidate_prefers_contrarian_and_specific_quote():
    cand = select_quote_candidate(_sample_script(), _sample_ranking())
    assert cand is not None
    # 삼성전자는 하락(-2.1%)인데 김철수 연구원 발언은 긍정(저가매수) — 역발상
    # 신호 + 목표주가 수치(구체성) + 유튜브 채널 보너스가 겹쳐 가장 높은 점수여야 함
    assert cand["stock_name"] == "삼성전자", cand
    assert cand["speaker"] == "김철수 연구원", cand
    assert "저가매수" in cand["quote"]
    print(f"✅ select_quote_candidate: 역발상+구체성 발언 우선 선택 확인 → {cand['speaker']}")


def test_select_news_candidate_uses_ranking_order_and_excludes_stock():
    top = select_news_candidate(_sample_script(), _sample_ranking())
    assert top["stock_name"] == "삼성전자", top

    second = select_news_candidate(_sample_script(), _sample_ranking(), exclude_stock="삼성전자")
    assert second["stock_name"] == "LG전자", second
    print("✅ select_news_candidate: 랭킹 순서 + exclude_stock 중복 방지 확인")


def test_select_news_candidate_falls_back_to_section_order_without_ranking():
    cand = select_news_candidate(_sample_script(), ranking_entries=[])
    assert cand is not None
    assert cand["stock_name"] in ("삼성전자", "LG전자")
    print("✅ select_news_candidate: ranking.json 없을 때 sections 순서로 폴백 확인")


def test_clean_quote_for_display_truncates_and_strips_ending():
    long_quote = "이 종목은 정말로 좋은 흐름을 보이고 있다고 생각합니다마치겠습니다"
    out = clean_quote_for_display(long_quote, max_len=10)
    assert len(out) <= 11, out  # 10자 + "…"
    assert out.endswith("…")
    print(f"✅ clean_quote_for_display: 길이 제한/말줄임 확인 → {out}")


def test_build_titles_format():
    quote_cand = {"speaker": "김철수 연구원", "quote_display": "저가매수 기회"}
    title = build_quote_title(quote_cand)
    # "연구원"은 받침(ㄴ)이 있으므로 "이" — pick_i_ga()
    assert title == '김철수 연구원이 "저가매수 기회"라고 말한 까닭은?', title

    # 2.1%는 급락 기준(3.0%) 미만이라 "하락"이어야 함(과장 방지)
    news_cand = {"stock_name": "삼성전자", "change": "-2.1%", "change_positive": False}
    news_title = build_news_title(news_cand)
    assert news_title == "삼성전자 -2.1% 하락, 무슨 일?", news_title

    surge_cand = {"stock_name": "삼성전자", "change": "-4.5%", "change_positive": False}
    surge_title = build_news_title(surge_cand)
    assert surge_title == "삼성전자 -4.5% 급락, 무슨 일?", surge_title
    print("✅ build_quote_title / build_news_title: 포맷 확인(등락폭별 표현 강도 차등 포함)")


if __name__ == "__main__":
    test_select_quote_candidate_prefers_contrarian_and_specific_quote()
    test_select_news_candidate_uses_ranking_order_and_excludes_stock()
    test_select_news_candidate_falls_back_to_section_order_without_ranking()
    test_clean_quote_for_display_truncates_and_strips_ending()
    test_build_titles_format()
    print("\n✅ thumbnail_select 테스트 전체 통과")
