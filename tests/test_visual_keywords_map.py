# tests/test_visual_keywords_map.py
"""
visual_keywords_map 매핑 로직 검증 (pytest 미사용, 순수 assert 기반).
실행: python tests/test_visual_keywords_map.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.visual_keywords_map import (  # noqa: E402
    get_visual_keywords_for_stock,
    get_visual_keywords_for_sector,
    build_visual_keywords_bilingual,
)
from assets.scene_plan import Entity  # noqa: E402


def run():
    # 종목 오버라이드가 있는 경우
    ko, en = get_visual_keywords_for_stock("삼성전자")
    assert "삼성전자" in ko
    assert "Samsung Electronics" in en

    # 오버라이드가 없는 종목은 STOCK_SECTORS 경유로 섹터 매핑에 폴백
    # (코셈 → 반도체, config.STOCK_SECTORS에 등록돼 있음)
    ko2, en2 = get_visual_keywords_for_stock("코셈")
    assert ko2 == get_visual_keywords_for_sector("반도체")[0]
    assert en2 == get_visual_keywords_for_sector("반도체")[1]
    assert "semiconductor" in en2

    # 완전히 미지의 이름은 빈 리스트
    ko3, en3 = get_visual_keywords_for_stock("존재하지않는가상종목")
    assert ko3 == [] and en3 == []

    # 섹터 직접 조회
    ko4, en4 = get_visual_keywords_for_sector("방산")
    assert "방산" in ko4
    assert "defense industry" in en4

    # entity 리스트 → bilingual 키워드
    entities = [
        Entity(type="기업명", value="삼성전자", normalized="삼성전자", code="005930"),
        Entity(type="섹터", value="반도체", normalized="반도체"),
        Entity(type="인물", value="김철수 위원장", normalized="김철수"),
    ]
    ko5, en5 = build_visual_keywords_bilingual(entities)
    assert "삼성전자" in ko5
    assert "Samsung Electronics" in en5
    # 인물 타입은 매핑 대상이 아니므로 조용히 무시됨(에러 없이)

    print("✅ visual_keywords_map 테스트 통과")


if __name__ == "__main__":
    run()
