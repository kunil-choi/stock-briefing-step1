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

import generate_script  # noqa: E402
from generate_script import (  # noqa: E402
    build_stock_market_data, build_synthetic_mentions, build_stock_quotes,
    _is_unfilled_stock_section, _merge_quotes_by_speaker, partition_major_stocks,
    select_stock_classification, load_persisted_stock_classification,
    persist_stock_classification,
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


def test_partition_major_stocks_downgrades_names_without_price():
    # "엔비디아"는 다른 종목(SK하이닉스)의 브리핑 원문에서 언급만 됐을 뿐 V3_1이
    # 자체 시세를 추적하는 종목이 아니므로 stock_market_data에 값이 없는 경우를
    # 재현한다(2026-07-27 실제 사고 재현: quality_gate가 stock_엔비디아.price=''
    # 를 잡아냈다).
    core = {
        "market_leaders": ["삼성전자", "엔비디아"],
        "top_stocks": ["현대차"],
    }
    stock_market_data = {
        "삼성전자": {"price": "279,500", "change": "+0.00%"},
        "현대차":   {"price": "434,000", "change": "+1.23%"},
        # "엔비디아": 항목 자체가 없음 (V3_1이 시세를 추적하지 않음)
    }
    major_stocks, tier_by_name, no_price_stocks = partition_major_stocks(core, stock_market_data)
    assert major_stocks == ["삼성전자", "현대차"], (
        f"시세가 없는 '엔비디아'는 개별 카드 목록에서 빠져야 함: {major_stocks}"
    )
    assert tier_by_name == {"삼성전자": "market_leader", "현대차": "top_stock"}
    assert no_price_stocks == ["엔비디아"], (
        f"시세 없는 종목은 no_price_stocks로 분리돼야 함: {no_price_stocks}"
    )
    print("✅ partition_major_stocks: 실시간 시세 없는 종목이 개별 카드에서 안전하게 제외됨")


def test_partition_major_stocks_keeps_all_when_price_present():
    core = {"market_leaders": ["삼성전자"], "top_stocks": ["현대차"]}
    stock_market_data = {
        "삼성전자": {"price": "279,500", "change": "+0.00%"},
        "현대차":   {"price": "434,000", "change": "+1.23%"},
    }
    major_stocks, tier_by_name, no_price_stocks = partition_major_stocks(core, stock_market_data)
    assert major_stocks == ["삼성전자", "현대차"]
    assert no_price_stocks == []
    print("✅ partition_major_stocks: 시세가 모두 있으면 아무것도 내려가지 않음")


def test_unfilled_stock_section_detected():
    assert _is_unfilled_stock_section(
        {"corner_summary": "현대차 한줄 요약", "summary": "한줄 요약"}, "현대차"
    ), "프롬프트 예시 placeholder 그대로인 경우를 감지하지 못함"
    assert _is_unfilled_stock_section({"corner_summary": "", "summary": ""}, "현대차")
    assert not _is_unfilled_stock_section(
        {"corner_summary": "외국인 매수세로 강세 지속", "summary": "실적 기대감 유효"}, "현대차"
    ), "실제 채워진 내용을 placeholder로 오탐함"
    print("✅ _is_unfilled_stock_section: placeholder 미채움 여부를 정확히 판별")


def _sample_briefing_data_with_signals():
    """실제 v3-1 응답 형태(2026-08-10 사례)를 그대로 옮긴 픽스처 — market_leaders
    2개 + stocks 8개, signal(긍정/중립/부정)/weighted_score 포함."""
    return {
        "market_leaders": [
            {"name": "삼성전자",   "signal": "중립"},
            {"name": "SK하이닉스", "signal": "긍정"},
        ],
        "stocks": [
            {"name": "엘앤에프",     "signal": "긍정", "weighted_score": 12.84},
            {"name": "현대차",       "signal": "중립", "weighted_score": 9.0},
            {"name": "카카오",       "signal": "중립", "weighted_score": 8.0},
            {"name": "LS증권",       "signal": "긍정", "weighted_score": 6.0},
            {"name": "두산에너빌리티", "signal": "중립", "weighted_score": 5.0},
            {"name": "LG전자",       "signal": "긍정", "weighted_score": 4.0},
            {"name": "OCI홀딩스",     "signal": "긍정", "weighted_score": 3.0},
            {"name": "SK이노베이션", "signal": "긍정", "weighted_score": 2.0},
        ],
    }


def test_select_stock_classification_prefers_positive_over_neutral_over_negative():
    data = _sample_briefing_data_with_signals()
    result = select_stock_classification(data, top_stocks_count=3)
    assert result["market_leaders"] == ["삼성전자", "SK하이닉스"]
    # 긍정 5개(엘앤에프/LS증권/LG전자/OCI홀딩스/SK이노베이션) 중 weighted_score
    # 상위 3개만 뽑혀야 하고, 중립 종목은 하나도 안 뽑혀야 함(긍정이 이미 충분하므로)
    assert result["top_stocks"] == ["엘앤에프", "LS증권", "LG전자"], result["top_stocks"]
    assert "현대차" in result["remaining_stocks"] and "카카오" in result["remaining_stocks"]
    print(f"✅ select_stock_classification: 긍정 우선 선정 확인 → {result['top_stocks']}")


def test_select_stock_classification_fills_with_neutral_when_positive_insufficient():
    data = _sample_briefing_data_with_signals()
    # 긍정은 엘앤에프 1개만 남기고, 나머지 긍정 종목은 부정으로 바꿔 "긍정이 모자라면
    # 중립으로 채우고, 그래도 모자라면 부정까지 채운다"를 검증
    for s in data["stocks"]:
        if s["name"] == "엘앤에프":
            continue
        if s["signal"] == "긍정":
            s["signal"] = "부정"
    # 이제 signal 구성: 긍정 1개(엘앤에프), 중립 3개(현대차/카카오/두산에너빌리티),
    # 부정 4개(LS증권/LG전자/OCI홀딩스/SK이노베이션)
    result = select_stock_classification(data, top_stocks_count=3)
    # 긍정 1개 + 중립 중 weighted_score 상위 2개(현대차 9.0, 카카오 8.0)로 채워져야
    # 하고, 부정 종목은 하나도 뽑히면 안 됨
    assert result["top_stocks"] == ["엘앤에프", "현대차", "카카오"], result["top_stocks"]
    print(f"✅ select_stock_classification: 긍정 부족 시 중립으로 채움 확인 → {result['top_stocks']}")


def test_select_stock_classification_fills_with_negative_when_positive_and_neutral_insufficient():
    data = _sample_briefing_data_with_signals()
    # 긍정/중립을 각각 1개만 남기고 나머지는 전부 부정으로 바꿔 "그마저도 모자라면
    # 부정까지 채운다"를 검증
    for s in data["stocks"]:
        if s["name"] in ("엘앤에프", "현대차"):
            continue
        s["signal"] = "부정"
    result = select_stock_classification(data, top_stocks_count=3)
    assert result["top_stocks"][0] == "엘앤에프"  # 긍정
    assert result["top_stocks"][1] == "현대차"    # 중립
    assert result["top_stocks"][2] not in ("엘앤에프", "현대차")  # 부정으로 채워짐
    print(f"✅ select_stock_classification: 긍정+중립도 부족하면 부정으로 채움 확인 → {result['top_stocks']}")


def test_select_stock_classification_is_deterministic():
    data = _sample_briefing_data_with_signals()
    r1 = select_stock_classification(data)
    r2 = select_stock_classification(data)
    assert r1 == r2, "동일 입력인데 결과가 다름 — 더 이상 LLM 샘플링에 의존하면 안 됨"
    print("✅ select_stock_classification: 동일 입력 → 동일 출력(결정적) 확인")


def test_persist_and_load_stock_classification_roundtrip():
    import tempfile
    original_path = generate_script._STOCK_SELECTION_LOG_PATH
    tmp_dir = tempfile.mkdtemp()
    try:
        generate_script._STOCK_SELECTION_LOG_PATH = os.path.join(tmp_dir, "stock_selection_log.json")
        fp1 = "fingerprint-v1"

        assert load_persisted_stock_classification("2026-08-10", fp1) is None

        classification = {
            "market_leaders": ["삼성전자", "SK하이닉스"],
            "top_stocks": ["엘앤에프", "LS증권", "LG전자"],
            "remaining_stocks": ["현대차", "카카오"],
        }
        persist_stock_classification("2026-08-10", classification, fp1)

        loaded = load_persisted_stock_classification("2026-08-10", fp1)
        assert loaded == classification, loaded

        # 다른 날짜는 영향 없어야 함
        assert load_persisted_stock_classification("2026-08-11", fp1) is None

        # 같은 날짜를 다른 값으로 다시 기록하면 최신 값으로 덮어써야 함(재실행 시나리오)
        persist_stock_classification("2026-08-10", {
            "market_leaders": ["삼성전자", "SK하이닉스"],
            "top_stocks": ["카카오", "현대차", "LG전자"],
            "remaining_stocks": ["엘앤에프", "LS증권"],
        }, fp1)
        loaded2 = load_persisted_stock_classification("2026-08-10", fp1)
        assert loaded2["top_stocks"] == ["카카오", "현대차", "LG전자"], loaded2
        print("✅ persist/load_stock_classification: 날짜별 저장·재사용·덮어쓰기 확인")
    finally:
        generate_script._STOCK_SELECTION_LOG_PATH = original_path
        import shutil
        shutil.rmtree(tmp_dir)


def test_persisted_stock_classification_invalidated_when_briefing_data_changes():
    """사용자 요구사항: "고정"은 V3-1 데이터가 재실행 때도 완전히 동일할 때만
    적용된다. 데이터가 바뀌었으면(예: admin 교정) fingerprint가 달라져 캐시를
    재사용하면 안 된다."""
    import tempfile
    original_path = generate_script._STOCK_SELECTION_LOG_PATH
    tmp_dir = tempfile.mkdtemp()
    try:
        generate_script._STOCK_SELECTION_LOG_PATH = os.path.join(tmp_dir, "stock_selection_log.json")

        data_v1 = _sample_briefing_data_with_signals()
        fp_v1 = generate_script._briefing_data_fingerprint(data_v1)
        classification = select_stock_classification(data_v1)
        persist_stock_classification("2026-08-10", classification, fp_v1)

        # 같은 데이터로 재실행 → 캐시 재사용
        assert load_persisted_stock_classification("2026-08-10", fp_v1) == classification

        # V3-1이 데이터를 정정(예: LG전자 signal이 부정으로 바뀜)
        data_v2 = _sample_briefing_data_with_signals()
        for s in data_v2["stocks"]:
            if s["name"] == "LG전자":
                s["signal"] = "부정"
        fp_v2 = generate_script._briefing_data_fingerprint(data_v2)
        assert fp_v2 != fp_v1, "데이터가 바뀌었는데 fingerprint가 그대로임"

        # 바뀐 fingerprint로는 이전 캐시를 재사용하면 안 됨
        assert load_persisted_stock_classification("2026-08-10", fp_v2) is None
        print("✅ 캐시 무효화: V3-1 데이터가 바뀌면(같은 날짜여도) 이전 종목 선정을 재사용하지 않음")
    finally:
        generate_script._STOCK_SELECTION_LOG_PATH = original_path
        import shutil
        shutil.rmtree(tmp_dir)


def test_parse_panelist_identity_matches_real_v3_1_examples():
    from assets.config import parse_panelist_identity

    cases = [
        ("오현진 팀장 루체인베스트", {"name": "오현진", "title": "팀장", "company": "루체인베스트"}),
        ("김민준 토마토투자자문", {"name": "김민준", "title": "패널", "company": "토마토투자자문"}),
        ("염승환 이사/LS증권", {"name": "염승환", "title": "이사", "company": "LS증권"}),
        ("정경민 IBK투자증권 분당지점 팀장",
         {"name": "정경민", "title": "팀장", "company": "IBK투자증권 분당지점"}),
    ]
    for raw, expected in cases:
        result = parse_panelist_identity(raw)
        assert result == expected, f"{raw!r} → {result} (기대: {expected})"
    print("✅ parse_panelist_identity: 실제 v3-1 speaker_name 4개 형식 모두 정확히 분리")


def test_build_panelist_intro_uses_company_name_title_order():
    from assets.config import build_panelist_intro

    cases = [
        ("815머니톡", "오현진 팀장 루체인베스트", "815머니톡에 출연한 루체인베스트 오현진 팀장은"),
        ("TomatoTV", "김민준 토마토투자자문", "TomatoTV에 출연한 토마토투자자문 김민준 패널은"),
        ("삼프로TV", "염승환 이사/LS증권", "삼프로TV에 출연한 LS증권 염승환 이사는"),
        ("이데일리TV", "정경민 IBK투자증권 분당지점 팀장",
         "이데일리TV에 출연한 IBK투자증권 분당지점 정경민 팀장은"),
    ]
    for channel, speaker, expected in cases:
        result = build_panelist_intro(channel, speaker)
        assert result == expected, f"{channel!r}/{speaker!r} → {result!r} (기대: {expected!r})"
    print("✅ build_panelist_intro: 채널명 원표기 유지 + 소속/이름/직책 순서 통일 확인"
          "(실제 발음 교정은 pronunciation_ko.yml이 TTS 직전에 처리)")


if __name__ == "__main__":
    test_build_stock_market_data_formats_real_values()
    test_securities_channel_mentions_not_dropped()
    test_stock_quotes_channel_type_mapping()
    test_merge_quotes_by_speaker_combines_same_speaker_fragments()
    test_stock_quotes_merges_before_capping_at_nine()
    test_partition_major_stocks_downgrades_names_without_price()
    test_partition_major_stocks_keeps_all_when_price_present()
    test_unfilled_stock_section_detected()
    test_select_stock_classification_prefers_positive_over_neutral_over_negative()
    test_select_stock_classification_fills_with_neutral_when_positive_insufficient()
    test_select_stock_classification_fills_with_negative_when_positive_and_neutral_insufficient()
    test_select_stock_classification_is_deterministic()
    test_persist_and_load_stock_classification_roundtrip()
    test_persisted_stock_classification_invalidated_when_briefing_data_changes()
    test_parse_panelist_identity_matches_real_v3_1_examples()
    test_build_panelist_intro_uses_company_name_title_order()
    print("\n✅ generate_script 테스트 전체 통과")
