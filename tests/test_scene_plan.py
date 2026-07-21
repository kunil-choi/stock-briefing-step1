# tests/test_scene_plan.py
"""
scene_plan 빌더 검증 스크립트 (pytest 미사용, 이 레포의 나머지 파이프라인과
동일하게 순수 assert 기반). 실행: python tests/test_scene_plan.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.scene_plan import build_scene_plan  # noqa: E402


def _load_fixture():
    path = os.path.join(_HERE, "fixtures", "sample_script.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_dirty_fixture():
    path = os.path.join(_HERE, "fixtures", "sample_script_dirty_name.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _entity_values(section, entity_type):
    return {e.value for e in section.entities if e.type == entity_type}


def run():
    script_data = _load_fixture()
    plan = build_scene_plan(script_data)

    by_id = {s.id: s for s in plan.sections}
    assert len(plan.sections) == 7, f"섹션 수 불일치: {len(plan.sections)}"
    assert plan.title == script_data["title"]
    assert plan.date == script_data["date"]

    # visual_type 매핑
    assert by_id["opening"].visual_type == "title_card"
    assert by_id["market_summary"].visual_type == "market_chart"
    assert by_id["sectors"].visual_type == "sector_grid"
    assert by_id["stock_삼성전자"].visual_type == "stock_chart"
    assert by_id["stock_추가관심종목"].visual_type == "list_card"
    assert by_id["ai_strategy"].visual_type == "strategy_card"
    assert by_id["closing"].visual_type == "closing_card"

    # opening: keywords 필드가 visual_keywords에 반영되어야 함
    assert "삼성전자" in by_id["opening"].visual_keywords
    assert "반도체" in by_id["opening"].visual_keywords

    # sectors: 기업명 2개 + 섹터 1개 인식
    assert _entity_values(by_id["sectors"], "기업명") >= {"삼성전자", "SK하이닉스"}
    assert "반도체" in _entity_values(by_id["sectors"], "섹터")

    # market_summary: 지역(미국) 인식
    assert "미국" in _entity_values(by_id["market_summary"], "지역")

    # stock_삼성전자: 증권사/인물/뉴스키워드 인식
    assert _entity_values(by_id["stock_삼성전자"], "증권사") >= {"미래에셋증권", "키움증권"}
    assert "김철수 위원장" in _entity_values(by_id["stock_삼성전자"], "인물")
    assert "목표주가" in _entity_values(by_id["stock_삼성전자"], "뉴스키워드")

    # stock_추가관심종목: items 안의 기업명(현대차)도 인식
    assert "현대차" in _entity_values(by_id["stock_추가관심종목"], "기업명")

    # priority_score: 종목 섹션이 클로징보다 비중이 높아야 함
    assert by_id["stock_삼성전자"].priority_score > by_id["closing"].priority_score
    for sec in plan.sections:
        assert 0.0 <= sec.priority_score <= 1.0

    # JSON 직렬화 가능해야 함 (pydantic model_dump → json.dumps)
    dumped = json.dumps(plan.model_dump(), ensure_ascii=False)
    assert '"visual_keywords"' in dumped

    # ── Phase 1 확장 필드 ────────────────────────────────────────────────
    all_sources = {"KBS_INTERNAL", "KBS_BADA", "KBS_WEBSITE", "YONHAP", "NAVER_DISCOVERY",
                   "PUBLIC_AGENCY", "OFFICIAL_COMPANY", "STOCK", "GENERATED_ABSTRACT"}

    samsung = by_id["stock_삼성전자"]
    assert samsung.narration, "narration 필드가 비어있으면 안 됨"
    assert 1 <= len(samsung.screenText) <= 2
    assert samsung.narration.strip() != " ".join(samsung.screenText).strip(), (
        "narration을 화면에 그대로 복붙하면 안 됨")
    assert samsung.visualKeywordsKo == samsung.visual_keywords, "하위호환: 동일 값 노출"
    assert samsung.visualKeywordsEn, "종목 매핑에서 영어 키워드가 나와야 함"
    assert set(samsung.preferredSources) <= all_sources
    assert samsung.backgroundType in ("image", "video_or_image", "none")
    assert set(samsung.motion.keys()) == {"entry", "text", "transition"}
    assert samsung.dataOverlay is not None
    assert samsung.dataOverlay["marketMood"] in ("bullish", "bearish", "neutral")
    assert samsung.assetRequirements["avoidGenericBusinessHandshake"] is True
    assert samsung.needsDataReview is False
    assert samsung.safeDisplayName is None

    closing = by_id["closing"]
    assert closing.dataOverlay is None
    assert closing.backgroundType == "none"

    # videoMeta / globalVisualStyle
    assert plan.videoMeta.resolution == "1920x1080"
    assert plan.videoMeta.aspectRatio == "16:9"
    from assets.html_theme import PALETTE  # noqa: E402
    assert plan.globalVisualStyle.primaryColor == PALETTE["accent"]
    assert plan.globalVisualStyle.upColor == PALETTE["up"]
    assert plan.globalVisualStyle.downColor == PALETTE["down"]

    print(f"✅ scene_plan 테스트 통과 ({len(plan.sections)}개 섹션)")


def run_dirty_name_case():
    script_data = _load_dirty_fixture()
    plan = build_scene_plan(script_data)
    by_id = {s.id: s for s in plan.sections}

    dirty = by_id["stock_뉴스경제방송유튜브"]
    assert dirty.needsDataReview is True, "출처 라벨이 섞인 종목명은 오염으로 탐지돼야 함"
    assert dirty.safeDisplayName == "관심 종목"
    assert dirty.assetRequirements["allowStockFallback"] is False

    watchlist = by_id["stock_추가관심종목"]
    assert watchlist.needsDataReview is True, "items 안의 오염 종목명도 섹션 단위로 탐지돼야 함"
    assert watchlist.safeDisplayName == "관심 종목"

    print("✅ scene_plan 오염 종목명(needsDataReview) 테스트 통과")


if __name__ == "__main__":
    run()
    run_dirty_name_case()
