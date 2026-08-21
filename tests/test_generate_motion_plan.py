# tests/test_generate_motion_plan.py
"""
generate_motion_plan.py의 순수 로직(네트워크/OpenAI 호출 없음) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반.

- _mock_emphasis(): MOTION_PLAN_MOCK 규칙 기반 폴백이 "12조원"/"1.2%"/
  "3,152포인트" 같은 화면 표기(숫자가 실제 자릿수로 적힌 subtitle 텍스트)에서
  강조 후보를 뽑아내는지 확인. narration처럼 완전히 한글로 풀어쓴 텍스트
  ("십이조원")에서는 아무것도 못 뽑는 게 정상임도 함께 확인한다.
- _validate_plan(): LLM(혹은 목업)이 지어낸 emphasis 텍스트(섹션 표시
  텍스트에 실제로 없는 문구)를 조용히 버리는지, 모르는 id를 버리는지,
  잘못된 template/camera/tone 값을 안전한 기본값으로 대체하는지 확인.
- build_motion_plan(): 나레이션/자막이 모두 빈 섹션은 후보에서 제외되는지,
  MOTION_PLAN_MOCK=True일 때 LLM 호출 없이 끝까지 동작하는지 확인.

실행: OPENAI_API_KEY=dummy python tests/test_generate_motion_plan.py
"""
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

import generate_motion_plan  # noqa: E402
from generate_motion_plan import (  # noqa: E402
    _mock_emphasis, _mock_plan_for_section, _validate_plan, _display_text,
    build_motion_plan,
)


def test_mock_emphasis_extracts_display_style_numbers():
    text = "2분기 영업이익은 12조원, 전년 대비 1.2% 늘었고 코스피는 3,152포인트를 기록했습니다."
    found = [e["text"] for e in _mock_emphasis(text)]
    assert "12조원" in found, found
    assert "1.2%" in found, found
    assert "3,152포인트" in found, found
    print("✅ _mock_emphasis: 조원/퍼센트/포인트 화면 표기를 강조 후보로 추출")


def test_mock_emphasis_finds_nothing_in_fully_spelled_narration():
    # narration은 TTS용으로 숫자를 완전히 한글로 풀어쓴다 — 여기서 뽑을 게
    # 없는 게 정상(그래서 검증 기준을 narration이 아니라 subtitle로 삼았다).
    narration = "이 분기 영업이익은 십이조원으로 전년 대비 일점이 퍼센트 늘었습니다."
    assert _mock_emphasis(narration) == []
    print("✅ _mock_emphasis: 한글로 완전히 풀어쓴 나레이션에서는 아무것도 못 뽑음(의도된 동작)")


def test_mock_emphasis_caps_at_three_and_dedupes():
    text = "1%, 2%, 3%, 4%, 1%"
    found = [e["text"] for e in _mock_emphasis(text)]
    assert len(found) == 3, found
    assert found == ["1%", "2%", "3%"], found
    print("✅ _mock_emphasis: 최대 3개로 제한하고 중복은 한 번만 담음")


def test_mock_plan_for_section_picks_big_number_when_emphasis_found():
    plan = _mock_plan_for_section("stock_삼성전자", "영업이익 12조원 달성")
    assert plan["id"] == "stock_삼성전자"
    assert plan["template"] == "big_number"
    assert plan["camera"] == "static"
    assert plan["tone"] == "neutral"
    assert plan["emphasis"] == [{"text": "12조원", "style": "pop_highlight"}]
    print("✅ _mock_plan_for_section: 강조 후보가 있으면 big_number 템플릿 선택")


def test_mock_plan_for_section_falls_back_to_chart_focus():
    plan = _mock_plan_for_section("market_summary", "오늘 증시는 혼조세로 마감했습니다")
    assert plan["template"] == "chart_focus"
    assert plan["emphasis"] == []
    print("✅ _mock_plan_for_section: 강조 후보가 없으면 chart_focus로 폴백")


def test_validate_plan_drops_hallucinated_emphasis_text():
    source_by_id = {"stock_삼성전자": "영업이익 12조원 달성"}
    raw = [{
        "id": "stock_삼성전자",
        "template": "big_number",
        "emphasis": [
            {"text": "12조원", "style": "pop_highlight"},   # 실제로 있음 → 유지
            {"text": "20조원", "style": "pop_highlight"},   # 지어낸 수치 → 버려야 함
        ],
        "camera": "static",
        "tone": "bullish",
    }]
    result = _validate_plan(raw, source_by_id)
    assert len(result) == 1
    assert result[0]["emphasis"] == [{"text": "12조원", "style": "pop_highlight"}]
    print("✅ _validate_plan: 섹션 텍스트에 실제로 없는 emphasis 문구만 조용히 버림")


def test_validate_plan_drops_unknown_section_id():
    source_by_id = {"stock_삼성전자": "영업이익 12조원 달성"}
    raw = [{"id": "stock_없는섹션", "template": "big_number", "emphasis": [],
            "camera": "static", "tone": "neutral"}]
    assert _validate_plan(raw, source_by_id) == []
    print("✅ _validate_plan: 입력에 없던(모르는) id는 통째로 버림")


def test_validate_plan_replaces_invalid_enum_values_with_safe_defaults():
    source_by_id = {"market_summary": "오늘 증시는 혼조세로 마감했습니다"}
    raw = [{
        "id": "market_summary",
        "template": "존재하지않는템플릿",
        "emphasis": [],
        "camera": "빠른줌",
        "tone": "매우긍정적",
    }]
    result = _validate_plan(raw, source_by_id)
    assert result[0]["template"] == "chart_focus"
    assert result[0]["camera"] == "static"
    assert result[0]["tone"] == "neutral"
    print("✅ _validate_plan: 허용값이 아닌 template/camera/tone은 안전한 기본값으로 대체")


def test_validate_plan_caps_emphasis_at_three_even_from_llm():
    source_by_id = {"s1": "1% 2% 3% 4%"}
    raw = [{
        "id": "s1", "template": "big_number",
        "emphasis": [{"text": "1%"}, {"text": "2%"}, {"text": "3%"}, {"text": "4%"}],
        "camera": "static", "tone": "neutral",
    }]
    result = _validate_plan(raw, source_by_id)
    assert len(result[0]["emphasis"]) == 3
    print("✅ _validate_plan: LLM이 3개 넘게 반환해도 최대 3개까지만 채택")


def test_display_text_prefers_subtitle_over_narration():
    section = {
        "narration": "이 분기 영업이익은 십이조원입니다",
        "subtitle": "영업이익 12조원",
    }
    assert _display_text(section) == "영업이익 12조원"
    print("✅ _display_text: narration보다 subtitle(화면 표기)을 우선 사용")


def test_display_text_falls_back_through_summary_fields():
    assert _display_text({"narration_summary": "요약 나레이션"}) == "요약 나레이션"
    assert _display_text({"narration": "본문 나레이션"}) == "본문 나레이션"
    assert _display_text({}) == ""
    print("✅ _display_text: subtitle 계열이 없으면 narration 계열로, 전부 없으면 빈 문자열로 폴백")


def test_build_motion_plan_skips_sections_without_display_text():
    reordered = {"sections": [
        {"id": "hook", "narration": "", "subtitle": ""},
        {"id": "market_summary", "narration": "십이조원", "subtitle": "12조원 기록"},
    ]}
    generate_motion_plan.MOTION_PLAN_MOCK = True
    try:
        plan = build_motion_plan(reordered)
    finally:
        generate_motion_plan.MOTION_PLAN_MOCK = False
    ids = [s["id"] for s in plan["sections"]]
    assert ids == ["market_summary"], ids
    print("✅ build_motion_plan: narration/subtitle이 모두 빈 섹션은 후보에서 제외")


def test_build_motion_plan_mock_mode_never_calls_llm():
    reordered = {"sections": [
        {"id": "stock_삼성전자", "narration": "영업이익 십이조원",
         "subtitle": "영업이익 12조원 달성"},
    ]}
    generate_motion_plan.MOTION_PLAN_MOCK = True
    try:
        plan = build_motion_plan(reordered)
    finally:
        generate_motion_plan.MOTION_PLAN_MOCK = False
    assert plan == {"sections": [{
        "id": "stock_삼성전자",
        "template": "big_number",
        "emphasis": [{"text": "12조원", "style": "pop_highlight"}],
        "camera": "static",
        "tone": "neutral",
    }]}
    print("✅ build_motion_plan: MOTION_PLAN_MOCK=True면 LLM 없이 규칙 기반으로만 동작")


def test_build_motion_plan_empty_sections_returns_empty_plan():
    assert build_motion_plan({"sections": []}) == {"sections": []}
    print("✅ build_motion_plan: 섹션이 없으면 빈 계획을 반환")


if __name__ == "__main__":
    test_mock_emphasis_extracts_display_style_numbers()
    test_mock_emphasis_finds_nothing_in_fully_spelled_narration()
    test_mock_emphasis_caps_at_three_and_dedupes()
    test_mock_plan_for_section_picks_big_number_when_emphasis_found()
    test_mock_plan_for_section_falls_back_to_chart_focus()
    test_validate_plan_drops_hallucinated_emphasis_text()
    test_validate_plan_drops_unknown_section_id()
    test_validate_plan_replaces_invalid_enum_values_with_safe_defaults()
    test_validate_plan_caps_emphasis_at_three_even_from_llm()
    test_display_text_prefers_subtitle_over_narration()
    test_display_text_falls_back_through_summary_fields()
    test_build_motion_plan_skips_sections_without_display_text()
    test_build_motion_plan_mock_mode_never_calls_llm()
    test_build_motion_plan_empty_sections_returns_empty_plan()
    print("\n✅ generate_motion_plan 테스트 전체 통과")
