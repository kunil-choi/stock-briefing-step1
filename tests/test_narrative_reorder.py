# tests/test_narrative_reorder.py
"""
narrative_reorder.py("장전 의사결정형" 플롯) 검증 스크립트. pytest 미사용,
다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크 불필요.
실행: python tests/test_narrative_reorder.py
"""
import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.narrative_reorder import reorder_sections, soften_advice_language  # noqa: E402


def _load_fixture():
    path = os.path.join(_HERE, "fixtures", "sample_script.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _make_multi_stock_script():
    """종목 섹션 4개(우선순위가 뚜렷하게 갈리도록 텍스트/개체명 밀도를 다르게
    구성)를 가진 스크립트를 만든다 — TOP3 선정 로직 검증용."""
    def stock(name, extra_entities_text):
        return {
            "id": f"stock_{name}",
            "label": f"종목 분석 - {name}",
            "corner_summary": f"{name} 관련 요약",
            "narration_summary": f"{name} 분석입니다. {extra_entities_text}",
            "subtitle_summary": f"{name} 분석입니다.",
            "price": "10,000", "change": "+1.0%", "change_positive": True,
            "catalysts": ["호재1"], "risks": ["리스크1"],
        }

    return {
        "title": "테스트", "date": "2026년 07월 10일",
        "sections": [
            {"id": "opening", "narration": "오프닝", "subtitle": "오프닝", "keywords": []},
            {"id": "market_summary", "corner_summary": "코스피 상승", "narration": "코스피 상승했습니다.", "subtitle": "코스피 상승했습니다.", "points": []},
            {"id": "sectors", "corner_summary": "반도체 강세", "narration": "반도체 업종 강세", "subtitle": "반도체 업종 강세", "sector_list": []},
            # 텍스트를 미래에셋증권/목표주가/실적 등으로 채워 개체명 밀도(=importance)를 인위적으로 높인다
            stock("가장중요종목", "미래에셋증권과 키움증권은 목표주가를 상향했고 실적 기대감도 큽니다. 반도체 업종 전반에 긍정적입니다."),
            stock("두번째종목", "한국투자증권은 목표주가를 유지했습니다."),
            stock("세번째종목", "실적이 개선되고 있습니다."),
            stock("네번째종목", "특별한 이슈 없음"),
            {"id": "ai_strategy", "corner_summary": "전략", "narration": "전략 안내",
             "subtitle": "전략 안내", "bullet_points": ["반도체 비중을 확대하세요", "삼성전자 매수를 추천합니다"]},
            {"id": "closing", "narration": "마무리", "subtitle": "마무리", "disclaimer": "투자 유의사항"},
        ],
    }


def test_eight_part_order():
    script_data = _load_fixture()
    reordered = reorder_sections(script_data)
    types = [s["section_type"] for s in reordered["sections"]]

    # hook과 conclusion은 항상 맨 앞 2개, closing은 항상 맨 끝
    assert types[0] == "hook"
    assert types[1] == "conclusion"
    assert types[-1] == "closing"

    # 정의된 순서 그룹을 벗어나지 않는지 확인 (그룹 내 순서는 유동적이어도
    # 그룹 간 순서는 hook < conclusion < top_mover < market_background <
    # sector_analysis < stock_checkpoint < risks < checklist < closing 이어야 함)
    order_rank = {
        "hook": 0, "conclusion": 1, "top_mover": 2, "market_background": 3,
        "sector_analysis": 4, "stock_checkpoint": 5, "risks": 6,
        "checklist": 7, "closing": 8,
    }
    ranks = [order_rank[t] for t in types]
    assert ranks == sorted(ranks), f"섹션 그룹 순서가 어긋남: {types}"
    print(f"✅ 8단계 순서 확인: {types}")


def test_top3_selection_by_importance():
    script_data = _make_multi_stock_script()
    reordered = reorder_sections(script_data, top_movers_count=3)

    top_movers = [s["id"] for s in reordered["sections"] if s["section_type"] == "top_mover"]
    checkpoints = [s["id"] for s in reordered["sections"] if s["section_type"] == "stock_checkpoint"]

    assert len(top_movers) == 3, f"TOP3여야 하는데 {len(top_movers)}개: {top_movers}"
    assert "stock_가장중요종목" in top_movers, "개체명 밀도가 가장 높은 종목이 TOP3에 없음"
    assert "stock_네번째종목" in checkpoints, "가장 개체명이 적은 종목은 체크포인트로 밀려나야 함"
    assert set(top_movers).isdisjoint(set(checkpoints))
    print(f"✅ TOP3 선정: {top_movers} / 체크포인트: {checkpoints}")


def test_importance_matches_scene_plan():
    from assets.scene_plan import build_scene_plan

    script_data = _load_fixture()
    scene_plan = build_scene_plan(script_data)
    expected = {s.id: s.priority_score for s in scene_plan.sections}

    reordered = reorder_sections(script_data)
    for s in reordered["sections"]:
        if s["id"] in expected:
            assert abs(s["importance"] - expected[s["id"]]) < 0.01, (
                f"{s['id']}의 importance가 scene_plan의 priority_score와 다름: "
                f"{s['importance']} vs {expected[s['id']]}"
            )
    print("✅ importance 값이 scene_plan.build_scene_plan()의 priority_score와 일치")


def test_soften_advice_language():
    assert "확대하세요" not in soften_advice_language("반도체 비중을 확대하세요")
    assert "추천합니다" not in soften_advice_language("삼성전자 매수를 추천합니다")
    assert "확인" in soften_advice_language("반도체 비중을 확대하세요") or \
           "관전 포인트" in soften_advice_language("삼성전자 매수를 추천합니다")
    # 조언체가 아닌 일반 문장은 그대로 보존
    assert soften_advice_language("코스피가 상승 마감했습니다.") == "코스피가 상승 마감했습니다."
    print("✅ 투자 조언체 완화 확인")


def test_checklist_uses_softened_language():
    script_data = _make_multi_stock_script()
    reordered = reorder_sections(script_data)
    checklist = next((s for s in reordered["sections"] if s["id"] == "checklist"), None)
    assert checklist is not None
    assert "확대하세요" not in checklist["narration"]
    assert "매수를 추천합니다" not in checklist["narration"]
    print("✅ 체크리스트 문구가 조언체 완화를 거쳤음을 확인")


def test_script_json_not_mutated():
    """reorder_sections()가 입력 script_data를 변형하지 않는지 확인한다
    (script.json은 읽기 전용으로 유지되어야 기존 렌더링 파이프라인과 호환)."""
    script_data = _load_fixture()
    snapshot = copy.deepcopy(script_data)
    reorder_sections(script_data)
    assert script_data == snapshot, "reorder_sections()가 입력 딕셔너리를 변형함"
    print("✅ script_data 원본 불변 확인 (기존 렌더링 파이프라인과의 호환성)")


if __name__ == "__main__":
    test_eight_part_order()
    test_top3_selection_by_importance()
    test_importance_matches_scene_plan()
    test_soften_advice_language()
    test_checklist_uses_softened_language()
    test_script_json_not_mutated()
    print("\n✅ narrative_reorder 테스트 전체 통과")
