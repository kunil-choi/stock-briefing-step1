# tests/test_mention_briefing.py
"""
narrative_reorder.build_mention_briefing()("종목 언급 중심" 플롯) 검증
스크립트. pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반.
네트워크 불필요.
실행: python tests/test_mention_briefing.py
"""
import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.narrative_reorder import (  # noqa: E402
    build_mention_briefing,
    MENTION_INTRO_LINE,
    _LEADER_TRANSITION,
    _WATCHLIST_TRANSITION,
    _HIDDEN_PICK_TRANSITION,
)


def _stock(name, tier):
    # 실제 script.json 스키마와 동일하게 "narration_summary"/"subtitle_summary"만
    # 갖는다("narration"/"subtitle" 키는 없음) — generate_voice.py의
    # _build_jobs()가 개별 종목 섹션은 narration_summary를 TTS 원문으로 읽고
    # narration은 아예 보지 않으므로, 테스트 픽스처도 이를 정확히 반영해야
    # 접두어 버그(narration에만 붙어 실제 음성엔 반영 안 되는)를 잡아낼 수 있다.
    return {
        "id": f"stock_{name}",
        "label": f"종목 분석 - {name}",
        "stock_tier": tier,
        "corner_summary": f"{name} 관련 요약",
        "narration_summary": f"{name} 분석입니다.",
        "subtitle_summary": f"{name} 분석입니다.",
        "price": "10,000", "change": "+1.0%", "change_positive": True,
        "catalysts": ["호재1"], "risks": ["리스크1"],
        "channel_summaries": [
            {"channel_type": "유튜브", "narration": f"{name} 유튜브 언급", "subtitle": f"{name} 유튜브 언급"},
        ],
    }


def _base_script(include_market_data=True, include_hidden=True):
    market_summary = {
        "id": "market_summary", "corner_summary": "오늘 시장은 상승세를 이어가고 있습니다.",
        "narration": "코스피가 상승세를 보이고 있습니다.", "subtitle": "코스피가 상승세를 보이고 있습니다.",
        "points": ["포인트1", "포인트2"],
    }
    if include_market_data:
        market_summary.update({
            "kospi_value": "2,650.32", "kospi_change": "+0.82%", "kospi_change_positive": True,
            "kosdaq_value": "850.11", "kosdaq_change": "-0.15%", "kosdaq_change_positive": False,
            "nasdaq_value": "18,500.00", "nasdaq_change": "+1.20%", "nasdaq_positive": True,
            "sp500_value": "5,800.00", "sp500_change": "+0.90%", "sp500_positive": True,
            "usdkrw_value": "1,380.50", "usdkrw_change": "+0.30%", "usdkrw_positive": True,
        })

    sections = [
        {"id": "opening", "narration": "오프닝", "subtitle": "오프닝", "keywords": []},
        market_summary,
        {"id": "sectors", "corner_summary": "반도체 강세", "narration": "반도체 업종 강세",
         "subtitle": "반도체 업종 강세", "sector_list": []},
        _stock("대형주1", "market_leader"),
        _stock("대형주2", "market_leader"),
        _stock("관심종목1", "top_stock"),
        _stock("관심종목2", "top_stock"),
        {"id": "stock_추가관심종목", "label": "추가 관심 종목",
         "narration": "추가 관심 종목입니다.", "subtitle": "추가 관심 종목입니다.",
         "items": [{"name": "추가종목1", "text": "설명"}]},
        {"id": "ai_strategy", "corner_summary": "전략", "narration": "전략 안내",
         "subtitle": "전략 안내", "bullet_points": ["포인트1"]},
        {"id": "closing", "narration": "마무리", "subtitle": "마무리", "disclaimer": "투자 유의사항"},
    ]
    if include_hidden:
        sections.insert(-1, {
            "id": "stock_오늘의픽", "label": "오늘의 픽",
            "narration": "오늘의 픽입니다.", "subtitle": "오늘의 픽입니다.",
            "items": [{"name": "히든픽1", "text": "설명"}],
        })
    return {"title": "테스트", "date": "2026년 07월 16일", "sections": sections}


def test_order_and_excluded_sections():
    script_data = _base_script()
    reordered = build_mention_briefing(script_data)
    ids = [s["id"] for s in reordered["sections"]]

    assert ids[0] == "hook"
    assert ids[1] == "conclusion"
    assert ids[2] == "market_summary"
    assert ids[-1] == "closing"
    assert "sectors" not in ids, "sectors는 이 구성에서 제외되어야 함"
    assert "ai_strategy" not in ids, "ai_strategy는 이 구성에서 제외되어야 함"
    assert "risks" not in ids and "checklist" not in ids
    assert "stock_대형주1" in ids and "stock_대형주2" in ids
    assert "stock_관심종목1" in ids and "stock_관심종목2" in ids
    assert "stock_추가관심종목" in ids
    assert "stock_오늘의픽" in ids
    print(f"✅ 섹션 구성/제외 확인: {ids}")


def test_conclusion_is_fixed_mention_intro():
    reordered = build_mention_briefing(_base_script())
    conclusion = next(s for s in reordered["sections"] if s["id"] == "conclusion")
    assert conclusion["narration"] == MENTION_INTRO_LINE
    assert conclusion["subtitle"] == MENTION_INTRO_LINE
    print("✅ conclusion이 고정 채널 언급 인트로 문구를 그대로 씀")


def test_market_indicators_deterministic_no_interpretation():
    reordered = build_mention_briefing(_base_script())
    market = next(s for s in reordered["sections"] if s["id"] == "market_summary")
    assert market["corner_summary"] == "", "해석성 corner_summary는 비워야 함"
    assert market["points"] == [], "해석성 points는 비워야 함"
    assert "상승세" not in market["narration"], "진행형 표현이 섞이면 안 됨(코드로 직접 생성)"
    assert "마감" in market["narration"]
    assert "2,650.32" in market["narration"] and "+0.82%" in market["narration"]
    print("✅ 주요 지표 내레이션이 해석 없이 코드로 결정적으로 생성됨")


def test_market_indicators_skipped_without_data():
    reordered = build_mention_briefing(_base_script(include_market_data=False))
    ids = [s["id"] for s in reordered["sections"]]
    assert "market_summary" not in ids, "market_data가 없으면 주요 지표 섹션 자체를 건너뛰어야 함"
    print("✅ market_data 없으면 주요 지표 섹션 생략 확인")


def test_leader_and_watchlist_transitions():
    """개별 종목 섹션은 narration_summary가 실제 TTS 원문이다
    (generate_voice.py._build_jobs()가 narration_summary를 우선 읽고
    narration은 안 봄) — 전환 멘트가 narration_summary에 붙는지 검증한다."""
    reordered = build_mention_briefing(_base_script())
    by_id = {s["id"]: s for s in reordered["sections"]}

    assert by_id["stock_대형주1"]["narration_summary"].startswith(_LEADER_TRANSITION)
    assert "narration" not in by_id["stock_대형주1"], (
        "개별 종목 섹션에 narration 키가 생기면 안 됨(실제로 안 읽히는 죽은 필드)"
    )
    assert not by_id["stock_대형주2"]["narration_summary"].startswith(_LEADER_TRANSITION), (
        "전환 멘트는 대형 주도주 그룹의 첫 종목에만 붙어야 함"
    )
    assert by_id["stock_관심종목1"]["narration_summary"].startswith(_WATCHLIST_TRANSITION)
    assert not by_id["stock_관심종목2"]["narration_summary"].startswith(_WATCHLIST_TRANSITION)
    print("✅ 대형 주도주/관심종목 전환 멘트가 각 그룹 첫 항목의 narration_summary에만 붙음")


def test_hidden_pick_transition_when_present_and_absent():
    with_hidden = build_mention_briefing(_base_script(include_hidden=True))
    hidden_sec = next(s for s in with_hidden["sections"] if s["id"] == "stock_오늘의픽")
    assert hidden_sec["narration"].startswith(_HIDDEN_PICK_TRANSITION)

    without_hidden = build_mention_briefing(_base_script(include_hidden=False))
    ids = [s["id"] for s in without_hidden["sections"]]
    assert "stock_오늘의픽" not in ids, "히든픽 데이터가 없으면 섹션 자체가 없어야 함"
    print("✅ AI 히든픽: 데이터 있을 때만 전환 멘트+섹션 포함")


def test_stock_tier_fallback_when_missing():
    """stock_tier 필드가 없는 과거 script.json도 앞 2개를 대형 주도주로
    추정해 정상 동작해야 한다(하위 호환)."""
    script_data = _base_script()
    for sid in ("stock_대형주1", "stock_대형주2", "stock_관심종목1", "stock_관심종목2"):
        sec = next(s for s in script_data["sections"] if s["id"] == sid)
        sec.pop("stock_tier", None)

    reordered = build_mention_briefing(script_data)
    by_id = {s["id"]: s for s in reordered["sections"]}
    assert by_id["stock_대형주1"]["narration_summary"].startswith(_LEADER_TRANSITION)
    print("✅ stock_tier 없는 과거 데이터도 원본 순서 앞 2개를 대형 주도주로 추정해 동작")


def test_closing_preserved_last_with_original_content():
    reordered = build_mention_briefing(_base_script())
    closing = reordered["sections"][-1]
    assert closing["id"] == "closing"
    assert closing["narration"] == "마무리"
    print("✅ 클로징(투자 유의사항)이 맨 끝에 원문 그대로 유지됨")


def test_script_json_not_mutated():
    script_data = _base_script()
    snapshot = copy.deepcopy(script_data)
    build_mention_briefing(script_data)
    assert script_data == snapshot, "build_mention_briefing()이 입력 딕셔너리를 변형함"
    print("✅ script_data 원본 불변 확인")


if __name__ == "__main__":
    test_order_and_excluded_sections()
    test_conclusion_is_fixed_mention_intro()
    test_market_indicators_deterministic_no_interpretation()
    test_market_indicators_skipped_without_data()
    test_leader_and_watchlist_transitions()
    test_hidden_pick_transition_when_present_and_absent()
    test_stock_tier_fallback_when_missing()
    test_closing_preserved_last_with_original_content()
    test_script_json_not_mutated()
    print("\n✅ build_mention_briefing 테스트 전체 통과")
