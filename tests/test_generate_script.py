# tests/test_generate_script.py
"""
generate_script.py의 순수 로직(네트워크/OpenAI 호출 없음) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반.

- build_stock_market_data(): V3_1 원본 price/change_pct를 실제 화면 표기로 변환.
- build_synthetic_mentions()/build_stock_quotes(): source_type=="증권사"(증권사
  유튜브 채널 실시간 코멘트)가 더 이상 애널리스트 리포트로 착각돼 드롭되지
  않고 channel_type="증권사"로 보존되는지 확인.
- _is_unfilled_stock_section(): 프롬프트 예시 placeholder("000,000"/"한줄
  요약")가 실제 값인 것처럼 그대로 반환된 경우를 걸러내는지 확인
  (실제로 ₩000,000 / "현대차 한줄 요약"가 화면에 노출된 사고의 재발 방지).

실행: OPENAI_API_KEY=dummy python tests/test_generate_script.py
"""
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from generate_script import (  # noqa: E402
    build_stock_market_data, build_synthetic_mentions, build_stock_quotes,
    _is_unfilled_stock_section, _merge_quotes_by_speaker,
)


def _sample_briefing_data():
    return {
        "market_leaders": [
            {"name": "삼성전자", "code": "005930", "price": 279500, "change_pct": 0.0,
             "price_label": "전일종가",
             "channel_mentions": [
                 {"source_type": "경제방송", "source_name": "TomatoTV", "content": "반도체 강세"},
                 {"source_type": "증권사",   "source_name": "삼성증권", "content": "목표주가 상향"},
                 {"source_type": "뉴스",     "source_name": "매일경제", "content": "수출 호조"},
                 {"source_type": "유튜브",   "source_name": "815머니톡", "content": "실적 기대"},
             ]},
        ],
        "stocks": [
            {"name": "현대차", "code": "005380", "price": 434000, "change_pct": 1.23,
             "price_label": "전일종가", "channel_mentions": []},
        ],
        "hidden_picks": [],
    }


def test_build_stock_market_data_formats_real_values():
    data = _sample_briefing_data()
    result = build_stock_market_data(data)
    assert result["삼성전자"]["price"] == "279,500"
    assert result["삼성전자"]["change"] == "+0.00%"
    assert result["삼성전자"]["change_positive"] is True
    assert result["현대차"]["price"] == "434,000"
    assert result["현대차"]["change"] == "+1.23%"
    print("✅ build_stock_market_data: V3_1 원본 price/change_pct가 실제 표기로 변환됨")


def test_securities_channel_mentions_not_dropped():
    data = _sample_briefing_data()
    mentions = build_synthetic_mentions(data, "")
    source_types = [m["source_type"] for m in mentions if m["stock_name"] == "삼성전자"]
    assert "증권사" in source_types, (
        f"source_type=='증권사' 멘션이 build_synthetic_mentions()에서 드롭됨: {source_types}"
    )
    assert len(mentions) == 4, f"삼성전자 channel_mentions 4건이 모두 보존돼야 함: {len(mentions)}건"
    print("✅ build_synthetic_mentions: 증권사 유튜브 채널 멘션이 더 이상 드롭되지 않음")


def test_stock_quotes_channel_type_mapping():
    data = _sample_briefing_data()
    mentions = build_synthetic_mentions(data, "")
    quotes = build_stock_quotes(mentions, "")
    types_by_channel = {q["channel"]: q["channel_type"] for q in quotes["삼성전자"]}
    assert types_by_channel["삼성증권"] == "증권사", "증권사 유튜브 채널이 증권사 카테고리로 분류돼야 함"
    assert types_by_channel["매일경제"] == "경제방송", "뉴스 소스는 경제방송 카테고리로 합쳐져야 함"
    assert types_by_channel["TomatoTV"] == "경제방송"
    assert types_by_channel["815머니톡"] == "유튜브"
    print("✅ build_stock_quotes: source_type이 channel_type으로 정확히 매핑됨 "
          f"({types_by_channel})")


def test_merge_quotes_by_speaker_combines_same_speaker_fragments():
    items = [
        {"speaker": "김철수", "channel": "삼프로TV", "channel_type": "유튜브",
         "quote": "반도체 업황이 개선되고 있습니다", "timestamp_url": "", "sentiment": "긍정"},
        {"speaker": "김철수", "channel": "삼프로TV", "channel_type": "유튜브",
         "quote": "특히 HBM 수요가 견조합니다", "timestamp_url": "", "sentiment": ""},
        {"speaker": "이영희", "channel": "한국경제TV", "channel_type": "경제방송",
         "quote": "단기 조정 가능성도 있습니다", "timestamp_url": "", "sentiment": ""},
    ]
    merged = _merge_quotes_by_speaker(items)
    assert len(merged) == 2, "화자 2명(채널·화자 기준) → 2개 그룹으로 병합돼야 함"
    kim = next(m for m in merged if m["speaker"] == "김철수")
    assert kim["quote"] == ["반도체 업황이 개선되고 있습니다", "특히 HBM 수요가 견조합니다"], (
        "같은 화자의 발언 조각이 등장 순서대로 리스트로 묶여야 함")
    lee = next(m for m in merged if m["speaker"] == "이영희")
    assert lee["quote"] == ["단기 조정 가능성도 있습니다"]
    print("✅ _merge_quotes_by_speaker: 같은 화자 발언 조각 병합, 다른 화자는 분리 유지 확인")


def test_stock_quotes_merges_before_capping_at_nine():
    # 같은 화자가 조각을 여러 개 남겨도 슬롯을 독점하지 않고 병합되어 1개 그룹으로 유지됨
    mentions = [
        {"stock_name": "삼성전자", "channel": "삼프로TV", "speaker": "김철수",
         "quote": f"발언 조각 {i}", "source_type": "유튜브"}
        for i in range(12)
    ]
    quotes = build_stock_quotes(mentions, "")
    assert len(quotes["삼성전자"]) == 1, "같은 화자 조각 12개는 병합 후 1개 그룹이어야 함"
    assert len(quotes["삼성전자"][0]["quote"]) == 12, "병합된 그룹 안에 조각 12개가 모두 보존돼야 함"

    # 서로 다른 화자가 9명을 초과하면 화자·채널 단위로 9명까지만 유지됨
    mentions2 = [
        {"stock_name": "삼성전자", "channel": f"채널{i}", "speaker": f"화자{i}",
         "quote": "발언", "source_type": "유튜브"}
        for i in range(12)
    ]
    quotes2 = build_stock_quotes(mentions2, "")
    assert len(quotes2["삼성전자"]) == 9, "서로 다른 화자 12명은 화자 단위로 9명까지만 유지돼야 함"
    print("✅ build_stock_quotes: 같은 화자는 병합, 서로 다른 화자는 9명 캡으로 폭넓게 유지 확인")


def test_unfilled_stock_section_detected():
    assert _is_unfilled_stock_section(
        {"corner_summary": "현대차 한줄 요약", "summary": "한줄 요약"}, "현대차"
    ), "프롬프트 예시 placeholder 그대로인 경우를 감지하지 못함"
    assert _is_unfilled_stock_section({"corner_summary": "", "summary": ""}, "현대차")
    assert not _is_unfilled_stock_section(
        {"corner_summary": "외국인 매수세로 강세 지속", "summary": "실적 기대감 유효"}, "현대차"
    ), "실제 채워진 내용을 placeholder로 오탐함"
    print("✅ _is_unfilled_stock_section: placeholder 미채움 여부를 정확히 판별")


if __name__ == "__main__":
    test_build_stock_market_data_formats_real_values()
    test_securities_channel_mentions_not_dropped()
    test_stock_quotes_channel_type_mapping()
    test_merge_quotes_by_speaker_combines_same_speaker_fragments()
    test_stock_quotes_merges_before_capping_at_nine()
    test_unfilled_stock_section_detected()
    print("\n✅ generate_script 테스트 전체 통과")
