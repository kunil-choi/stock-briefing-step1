# tests/test_review_checklist.py
"""
review-checklist.md 생성 로직 검증. pytest 미사용, 순수 assert 기반.
실행: python tests/test_review_checklist.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from generate_review_checklist import build_checklist  # noqa: E402


def test_checklist_flags_issues_correctly():
    scene_plan = {"sections": [
        {"id": "hook", "screenText": ["AI 반도체 급락", "오늘 시장의 방향은?"], "priority_score": 0.8},
        {"id": "stock_뉴스경제방송유튜브", "screenText": ["관심 종목 강세"], "needsDataReview": True, "priority_score": 0.5},
        {"id": "stock_over", "screenText": ["한줄", "두줄", "세줄초과"], "priority_score": 0.4},
    ]}
    asset_manifest = {"assets": [
        {"assetId": "a1", "sceneId": "hook", "needsReview": False, "selected": True, "isForeignAgency": False},
        {"assetId": "a2", "sceneId": "stock_x", "needsReview": True, "selected": False, "isForeignAgency": True},
    ]}
    md = build_checklist(scene_plan, asset_manifest, {"sections": []})

    assert "[x] 오프닝 화면 텍스트" in md
    assert "[ ] 모든 섹션의 화면 텍스트가 2줄 이내인가" in md and "stock_over" in md
    assert "[ ] 종목명이 오염되지 않았는가" in md and "stock_뉴스경제방송유튜브" in md
    assert "[ ] 외신 자산이 없는가" in md and "a2" in md
    assert "검토된 후보: 2개" in md and "검수 대기(needsReview): 1개" in md
    print("✅ build_checklist: 2줄 초과/오염 종목명/외신 자산을 정확히 감지")


def test_checklist_all_clean():
    scene_plan = {"sections": [{"id": "hook", "screenText": ["짧은 헤드라인"], "priority_score": 0.8}]}
    asset_manifest = {"assets": [{"assetId": "a1", "sceneId": "hook", "needsReview": False,
                                   "selected": True, "isForeignAgency": False}]}
    md = build_checklist(scene_plan, asset_manifest, {"sections": []})
    assert "[x] 오프닝 화면 텍스트" in md
    assert "⚠️" not in md and "❌" not in md
    print("✅ build_checklist: 문제 없을 때는 경고 표시가 전혀 없음")


if __name__ == "__main__":
    test_checklist_flags_issues_correctly()
    test_checklist_all_clean()
    print("\n✅ review_checklist 테스트 전체 통과")
