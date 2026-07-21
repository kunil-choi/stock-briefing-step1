"""
종목/섹터 → (한국어, 영어) 비주얼 검색 키워드 매핑.

2차 작업(AssetSearchService)이 소비할 키워드 후보만 만드는 순수 함수 모듈이다
— 네트워크 호출이나 이미지 다운로드는 하지 않는다. 한국어 키워드는
KBS/연합뉴스/네이버 discovery 검색용, 영어 키워드는 Pexels/Unsplash 등
스톡 이미지 fallback 검색용이다.
"""
from typing import Dict, List, Tuple

from .config import normalize_stock_name, get_stock_sector

# config.STOCK_SECTORS의 실제 섹터명(대분류)과 1:1로 맞춘다.
SECTOR_VISUAL_KEYWORDS: Dict[str, Tuple[List[str], List[str]]] = {
    "반도체": (["반도체", "AI반도체", "HBM"], ["semiconductor", "AI chip", "HBM"]),
    "2차전지": (["2차전지", "배터리"], ["EV battery", "battery cell"]),
    "자동차": (["자동차", "완성차", "전기차"], ["automobile", "EV", "car factory"]),
    "방산": (["방산", "K-방산", "무기체계"], ["defense industry", "K-defense", "weapons"]),
    "조선": (["조선", "조선소"], ["shipbuilding", "shipyard"]),
    "바이오/제약": (["바이오", "제약", "신약"], ["biotech", "pharmaceutical"]),
    "금융": (["금융", "은행", "증권"], ["finance", "banking"]),
    "인터넷/게임": (["인터넷", "플랫폼", "게임"], ["tech platform", "gaming"]),
    "건설": (["건설", "건설현장"], ["construction"]),
    "항공": (["항공", "항공기"], ["airline", "aircraft"]),
    "철강/소재": (["철강", "소재"], ["steel", "materials"]),
    "에너지": (["에너지", "발전", "원자력"], ["energy", "power plant", "nuclear"]),
    "전력기기": (["전력기기", "전력망"], ["power equipment", "electric grid"]),
    "엔터": (["엔터테인먼트"], ["entertainment"]),
    "화장품/뷰티": (["화장품", "뷰티"], ["cosmetics", "beauty"]),
    "유통": (["유통", "리테일"], ["retail"]),
    "부품": (["부품", "제조"], ["components", "manufacturing"]),
    "기타": (["산업"], ["industry"]),
}

# 섹터 기본값으로는 부족한 종목만 선별 등록. 미등록 종목은 config.STOCK_SECTORS
# 경유로 섹터 매핑에 자동 폴백하므로, 신규 종목은 STOCK_SECTORS에만 등록해도
# 영어 키워드가 함께 붙는다.
STOCK_VISUAL_KEYWORDS: Dict[str, Tuple[List[str], List[str]]] = {
    "삼성전자": (["삼성전자", "반도체"], ["Samsung Electronics", "semiconductor"]),
    "SK하이닉스": (["SK하이닉스", "HBM"], ["SK Hynix", "HBM memory"]),
    "카카오": (["카카오", "플랫폼"], ["Kakao", "tech platform"]),
    "두산에너빌리티": (["원자력", "SMR"], ["nuclear power", "SMR"]),
    "두산퓨얼셀": (["ESS", "연료전지"], ["ESS", "fuel cell"]),
    "한화에어로스페이스": (["방산", "K-방산"], ["defense industry", "K-defense"]),
    "현대로템": (["방산", "K2전차"], ["defense industry", "K2 tank"]),
}

_EMPTY: Tuple[List[str], List[str]] = ([], [])


def get_visual_keywords_for_stock(name: str) -> Tuple[List[str], List[str]]:
    canonical = normalize_stock_name(name)
    if canonical in STOCK_VISUAL_KEYWORDS:
        ko, en = STOCK_VISUAL_KEYWORDS[canonical]
        return list(ko), list(en)
    sector = get_stock_sector(canonical)
    return get_visual_keywords_for_sector(sector)


def get_visual_keywords_for_sector(sector: str) -> Tuple[List[str], List[str]]:
    ko, en = SECTOR_VISUAL_KEYWORDS.get(sector, _EMPTY)
    return list(ko), list(en)


def build_visual_keywords_bilingual(entities, limit: int = 8) -> Tuple[List[str], List[str]]:
    """scene_plan.Entity 리스트(기업명/섹터 타입 위주) → (ko, en) 키워드 튜플."""
    ko: List[str] = []
    en: List[str] = []
    for e in entities:
        if e.type == "기업명":
            k, x = get_visual_keywords_for_stock(e.value)
        elif e.type == "섹터":
            k, x = get_visual_keywords_for_sector(e.value)
        else:
            k, x = _EMPTY
        for v in k:
            if v not in ko:
                ko.append(v)
        for v in x:
            if v not in en:
                en.append(v)
    return ko[:limit], en[:limit]
