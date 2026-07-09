# pipeline/assets/scene_plan.py
"""
scene_plan.json 생성 — script.json의 각 섹션에서 개체명(기업명/종목코드/섹터/
뉴스키워드/인물/지역/증권사명)을 추출하고, 섹션별 priority_score/visual_type/
visual_keywords를 계산해 향후 미디어 검색·방송형 렌더링 파이프라인(Phase C/D)이
소비할 수 있는 별도 스키마를 만든다.

기존 script.json/asset_map.json 소비 경로는 건드리지 않으므로(별도 파일로만
출력) 기존 영상 제작 파이프라인과 완전히 하위 호환된다.
"""
import re
from typing import List, Optional, Literal

from pydantic import BaseModel, Field

from .config import (
    STOCK_CODES,
    STOCK_SECTORS,
    BROKERAGE_FIRMS,
    PERSON_TITLE_SUFFIXES,
    REGION_NAMES,
    NEWS_KEYWORD_TERMS,
    get_all_krx_names_codes,
    get_stock_sector,
)

EntityType = Literal["기업명", "종목코드", "섹터", "뉴스키워드", "인물", "지역", "증권사"]


class Entity(BaseModel):
    type: EntityType
    value: str
    normalized: Optional[str] = None
    code: Optional[str] = None


class ScenePlanSection(BaseModel):
    id: str
    label: str = ""
    priority_score: float
    visual_type: str
    visual_keywords: List[str] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)


class ScenePlan(BaseModel):
    title: str = ""
    date: str = ""
    sections: List[ScenePlanSection] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 → 평문 텍스트 수집
# ─────────────────────────────────────────────────────────────────────────────

def _collect_text(obj) -> str:
    """섹션 dict를 재귀 순회하며 모든 문자열 값을 하나의 블롭으로 합칩니다.
    필드명이 섹션 종류마다 제각각(narration/subtitle/items/channel_summaries 등)
    이라 개별 필드를 일일이 지정하는 대신 전체 텍스트에서 개체명을 스캔한다."""
    if isinstance(obj, dict):
        return " ".join(_collect_text(v) for k, v in obj.items() if k != "id")
    if isinstance(obj, list):
        return " ".join(_collect_text(v) for v in obj)
    if isinstance(obj, str):
        return obj
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 개체명 추출
# ─────────────────────────────────────────────────────────────────────────────

_CODE_RE = re.compile(r"\b\d{6}\b")


def extract_company_entities(text: str) -> List[Entity]:
    """기업명 추출. 이 파이프라인이 실제로 다루는 큐레이션된 STOCK_CODES를
    1순위로 스캔하고, 전체 KRX 사전은 3자 이상 종목명만 보조로 스캔해 오탐을
    줄인다(2자 종목명은 일반 어휘와 겹칠 위험이 커서 제외)."""
    if not text:
        return []
    found = {}
    for name, code in STOCK_CODES.items():
        if name in text:
            found[name] = code
    try:
        for name, code in get_all_krx_names_codes().items():
            if name in found or len(name) < 3:
                continue
            if name in text:
                found[name] = code
    except Exception:
        pass
    return [Entity(type="기업명", value=name, normalized=name, code=str(code))
            for name, code in found.items()]


def extract_code_entities(text: str) -> List[Entity]:
    """본문에 등장하는 6자리 종목코드 중 실제 아는 종목코드만 채택합니다
    (임의의 6자리 숫자를 종목코드로 오인하지 않도록)."""
    if not text:
        return []
    known_codes = {str(c) for c in STOCK_CODES.values()}
    found = {m for m in _CODE_RE.findall(text) if m in known_codes}
    return [Entity(type="종목코드", value=c, normalized=c) for c in sorted(found)]


_ALL_SECTOR_NAMES = sorted({s for s in STOCK_SECTORS.values() if s})


def extract_sector_entities(text: str, company_entities: List[Entity]) -> List[Entity]:
    found = set()
    for e in company_entities:
        sector = get_stock_sector(e.value)
        if sector:
            found.add(sector)
    for sector in _ALL_SECTOR_NAMES:
        if sector in text:
            found.add(sector)
    return [Entity(type="섹터", value=s, normalized=s) for s in sorted(found)]


def extract_broker_entities(text: str) -> List[Entity]:
    if not text:
        return []
    found = {b for b in BROKERAGE_FIRMS if b in text}
    return [Entity(type="증권사", value=b, normalized=b) for b in sorted(found)]


_PERSON_RE = re.compile(
    r"([가-힣]{2,4})\s?(" + "|".join(re.escape(t) for t in PERSON_TITLE_SUFFIXES) + r")"
)


def extract_person_entities(text: str) -> List[Entity]:
    """직함 접미사 기반 규칙 추출(경량, 정밀도는 낮음). '홍길동 위원장' 같은
    이름+직함 패턴만 인식하고 그 외 인물 식별은 하지 않는다."""
    if not text:
        return []
    found = {}
    for m in _PERSON_RE.finditer(text):
        name, title = m.group(1), m.group(2)
        found[f"{name} {title}"] = name
    return [Entity(type="인물", value=key, normalized=name)
            for key, name in found.items()]


def extract_region_entities(text: str) -> List[Entity]:
    if not text:
        return []
    found = {r for r in REGION_NAMES if r in text}
    return [Entity(type="지역", value=r, normalized=r) for r in sorted(found)]


def extract_news_keyword_entities(text: str) -> List[Entity]:
    if not text:
        return []
    found = {k for k in NEWS_KEYWORD_TERMS if k in text}
    return [Entity(type="뉴스키워드", value=k, normalized=k) for k in sorted(found)]


def extract_entities(text: str) -> List[Entity]:
    """텍스트 블롭 하나에서 7종 개체명을 모두 추출합니다."""
    company_entities = extract_company_entities(text)
    return (
        company_entities
        + extract_code_entities(text)
        + extract_sector_entities(text, company_entities)
        + extract_broker_entities(text)
        + extract_person_entities(text)
        + extract_region_entities(text)
        + extract_news_keyword_entities(text)
    )


# ─────────────────────────────────────────────────────────────────────────────
# visual_type / priority_score / visual_keywords
# ─────────────────────────────────────────────────────────────────────────────

_AGGREGATE_STOCK_IDS = {"stock_추가관심종목", "stock_오늘의픽", "stock_증권사리포트"}

_VISUAL_TYPE_BY_ID = {
    "opening": "title_card",
    "market_summary": "market_chart",
    "sectors": "sector_grid",
    "ai_strategy": "strategy_card",
    "closing": "closing_card",
}


def visual_type_for(section: dict) -> str:
    sid = section.get("id", "")
    if sid in _VISUAL_TYPE_BY_ID:
        return _VISUAL_TYPE_BY_ID[sid]
    if sid in _AGGREGATE_STOCK_IDS:
        return "list_card"
    if sid.startswith("stock_") or sid.startswith("hidden_"):
        return "stock_chart"
    return "generic_card"


_BASE_WEIGHT_BY_ID = {
    "opening": 0.5,
    "market_summary": 0.6,
    "sectors": 0.65,
    "ai_strategy": 0.55,
    "closing": 0.3,
}


def _base_weight_for(sid: str) -> float:
    if sid in _BASE_WEIGHT_BY_ID:
        return _BASE_WEIGHT_BY_ID[sid]
    if sid in _AGGREGATE_STOCK_IDS:
        return 0.55
    if sid.startswith("stock_") or sid.startswith("hidden_"):
        return 0.8  # 종목 섹션이 이 영상의 핵심 콘텐츠
    return 0.4


def compute_priority_score(section: dict, entities: List[Entity], text_len: int) -> float:
    """0.0~1.0 범위의 비주얼 비중 점수. 섹션 종류별 기본 가중치에 개체명 밀도와
    분량(narration이 길수록 화면 전환/비주얼 자산이 더 필요)을 더해 계산한다."""
    base = _base_weight_for(section.get("id", ""))
    entity_bonus = min(0.2, 0.02 * len(entities))
    length_bonus = min(0.15, text_len / 4000)
    return round(min(1.0, base + entity_bonus + length_bonus), 2)


_KEYWORD_TYPE_ORDER = ["기업명", "섹터", "인물", "증권사", "지역", "뉴스키워드"]


def build_visual_keywords(entities: List[Entity], extra: Optional[List[str]] = None,
                           limit: int = 8) -> List[str]:
    by_type: dict = {}
    for e in entities:
        by_type.setdefault(e.type, []).append(e.value)
    out: List[str] = []
    for t in _KEYWORD_TYPE_ORDER:
        for v in by_type.get(t, []):
            if v not in out:
                out.append(v)
    for v in (extra or []):
        if v and v not in out:
            out.append(v)
    return out[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# 최상위 빌더
# ─────────────────────────────────────────────────────────────────────────────

def build_scene_plan(script_data: dict) -> ScenePlan:
    sections = script_data.get("sections") or []
    opening_keywords = next(
        (s.get("keywords") or [] for s in sections if s.get("id") == "opening"), []
    )

    out_sections = []
    for sec in sections:
        text = _collect_text(sec)
        entities = extract_entities(text)
        extra_kw = opening_keywords if sec.get("id") == "opening" else []
        out_sections.append(ScenePlanSection(
            id=sec.get("id", ""),
            label=sec.get("label", ""),
            priority_score=compute_priority_score(sec, entities, len(text)),
            visual_type=visual_type_for(sec),
            visual_keywords=build_visual_keywords(entities, extra=extra_kw),
            entities=entities,
        ))

    return ScenePlan(
        title=script_data.get("title", ""),
        date=script_data.get("date", ""),
        sections=out_sections,
    )
