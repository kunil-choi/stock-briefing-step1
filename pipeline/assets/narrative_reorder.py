# pipeline/assets/narrative_reorder.py
"""
"장전 의사결정형" 플롯 — script.json의 섹션들을 재정렬해 reordered_script.json을
만든다.

구성 순서(요구사항):
  1. 15초 훅          2. 오늘의 한 줄 결론   3. 주도주 후보 TOP3
  4. 시장 배경        5. 섹터별 분석         6. 종목별 체크포인트
  7. 리스크           8. 오늘 장 체크리스트

importance/entities는 Phase B의 scene_plan.build_scene_plan()을 그대로
재사용해 계산한다(중복 구현하지 않음) — script.json 원문에서 이미 검증된
개체명 추출·비중 점수 로직을 그대로 신뢰한다.

★ 기존 렌더링 파이프라인과의 호환성: 이 모듈은 script.json을 읽기만 하고
절대 수정하지 않는다. generate_assets.py/generate_video.py는 지금까지와
똑같이 script.json을 그대로 소비하므로 기존 영상 제작 경로는 전혀 바뀌지
않는다. reordered_script.json은 이 구조를 실제로 렌더링에 반영하려는
후속 통합 작업(별도 스코프)을 위한 산출물이다.
"""
import re
from typing import Optional

from .scene_plan import build_scene_plan

# ─────────────────────────────────────────────────────────────────────────────
# 섹션 분류
# ─────────────────────────────────────────────────────────────────────────────

_AGGREGATE_STOCK_IDS = {"stock_추가관심종목", "stock_오늘의픽", "stock_증권사리포트"}


def classify_section_type(section_id: str) -> str:
    if section_id == "opening":
        return "intro"
    if section_id == "market_summary":
        return "market_background"
    if section_id == "sectors":
        return "sector_analysis"
    if section_id in _AGGREGATE_STOCK_IDS:
        return "stock_checkpoint"
    if section_id.startswith("stock_") or section_id.startswith("hidden_"):
        return "stock_candidate"   # top_mover 후보. TOP3 안에 못 들면 stock_checkpoint로 재분류됨
    if section_id == "ai_strategy":
        return "checklist_source"
    if section_id == "closing":
        return "closing"
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# 투자 조언체 완화 — "~하세요"/"~추천합니다" 류를 관찰형 표현으로 순화
# ─────────────────────────────────────────────────────────────────────────────
# 규칙 기반 경량 치환이며 모든 문장 구조를 완벽히 커버하지는 못한다(완전한
# 자연어 재작성은 LLM 호출이 필요해 이 모듈의 스코프 밖). 기존 ai_strategy/
# catalysts 필드에서 실제로 관찰된 조언체 패턴 위주로 등록했다.
_ADVICE_PATTERNS = [
    (re.compile(r"비중을?\s*확대(?:하세요|하시길 권합니다|해야\s*합니다|할\s*만합니다)?"),
     "비중 변화 여부를 확인할 필요가 있다"),
    (re.compile(r"매수(?:를)?\s*(?:추천(?:합니다)?|권합니다|하세요|적기입니다|시점입니다)"),
     "매수 여부는 투자자 스스로 판단이 필요한 관전 포인트다"),
    (re.compile(r"매도(?:를)?\s*(?:추천(?:합니다)?|권합니다|하세요|시점입니다)"),
     "매도 여부는 투자자 스스로 판단이 필요한 관전 포인트다"),
    (re.compile(r"담아볼\s*만하다"), "관심을 가져볼 만한 관전 포인트다"),
    (re.compile(r"투자(?:하기)?\s*좋은\s*시점"), "주목할 시점"),
    (re.compile(r"제안합니다"), "점검해볼 필요가 있다"),
    (re.compile(r"추천합니다"), "확인할 필요가 있다"),
    (re.compile(r"사도\s*좋다"), "관전 포인트가 될 수 있다"),
]


def soften_advice_language(text: str) -> str:
    """투자 조언처럼 들리는 표현을 관찰형 표현으로 순화합니다. 완벽한 재작성이
    아니라 알려진 패턴 치환이므로, 치환되지 않은 조언체 표현이 남아 있을 수
    있습니다(한계를 README에 명시)."""
    if not text:
        return text
    out = text
    for pattern, replacement in _ADVICE_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 주석(annotate) — 기존 내용은 보존하고 section_type/importance/entities만 추가
# ─────────────────────────────────────────────────────────────────────────────

def _annotate(section: dict, section_type: str, importance_by_id: dict,
              entities_by_id: dict) -> dict:
    sid = section.get("id", "")
    return {
        **section,
        "section_type": section_type,
        "importance": round(importance_by_id.get(sid, 0.0), 2),
        "entities": entities_by_id.get(sid, []),
    }


def _section_summary_text(section: dict) -> str:
    return (
        section.get("corner_summary")
        or section.get("summary")
        or section.get("narration_summary")
        or section.get("narration")
        or ""
    ).strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. 훅 / 2. 결론 / 7. 리스크 / 8. 체크리스트 — 신규 합성 섹션
# ─────────────────────────────────────────────────────────────────────────────

def _build_hook_section(hook_sources: list) -> dict:
    """15초 훅: 전체 브리핑에서 importance가 가장 높은 2~3개 이슈를 요약한다."""
    blurbs = [soften_advice_language(_section_summary_text(s)) for s in hook_sources]
    blurbs = [b for b in blurbs if b]
    narration = (
        "오늘 장 시작 전 반드시 확인할 이슈들을 짚어드립니다. " + " ".join(blurbs[:3])
    ).strip()
    return {
        "id": "hook", "label": "15초 훅", "section_type": "hook",
        "importance": 1.0, "entities": [],
        "narration": narration, "subtitle": narration,
    }


def _build_conclusion_section(market_sec: dict, importance_by_id: dict,
                               entities_by_id: dict) -> dict:
    """오늘의 한 줄 결론: 시장 요약 헤드라인을 조언체 완화해 재사용한다."""
    headline = _section_summary_text(market_sec) if market_sec else ""
    narration = (
        soften_advice_language(headline) if headline
        else "오늘 시장 흐름을 확인해야 할 포인트를 정리합니다."
    )
    return {
        "id": "conclusion", "label": "오늘의 한 줄 결론", "section_type": "conclusion",
        "importance": round(importance_by_id.get("market_summary", 0.6), 2),
        "entities": entities_by_id.get("market_summary", []),
        "narration": narration, "subtitle": narration,
    }


def _build_risk_section(sections: list, importance_by_id: dict) -> Optional[dict]:
    """리스크: 모든 종목 섹션의 risks 필드를 모아 중복 제거 후 조언체를 완화한다."""
    seen = []
    for s in sections:
        for r in s.get("risks") or []:
            r = (r or "").strip()
            if r and r not in seen:
                seen.append(r)
    if not seen:
        return None
    items = [soften_advice_language(r) for r in seen[:8]]
    narration = ("오늘 함께 점검할 리스크 요인은 다음과 같습니다. " + " ".join(items)).strip()
    max_importance = max(
        (importance_by_id.get(s.get("id", ""), 0.0) for s in sections if s.get("risks")),
        default=0.5,
    )
    return {
        "id": "risks", "label": "리스크", "section_type": "risks",
        "importance": round(max_importance, 2), "entities": [],
        "narration": narration, "subtitle": narration, "items": items,
    }


def _build_checklist_section(ai_strategy_sec: dict, importance_by_id: dict,
                              entities_by_id: dict) -> Optional[dict]:
    """오늘 장 체크리스트: ai_strategy의 bullet_points를 조언체 완화해
    "확인 포인트" 형태로 재구성한다(투자 전략 제안 문구를 대체)."""
    if not ai_strategy_sec:
        return None
    bullets = ai_strategy_sec.get("bullet_points") or []
    if not bullets:
        return None
    items = [soften_advice_language(b) for b in bullets]
    narration = ("오늘 장에서 확인해볼 체크리스트입니다. " + " ".join(items)).strip()
    return {
        "id": "checklist", "label": "오늘 장 체크리스트", "section_type": "checklist",
        "importance": round(importance_by_id.get("ai_strategy", 0.5), 2),
        "entities": entities_by_id.get("ai_strategy", []),
        "narration": narration, "subtitle": narration, "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 최상위 재정렬 함수
# ─────────────────────────────────────────────────────────────────────────────

def reorder_sections(script_data: dict, top_movers_count: int = 3) -> dict:
    scene_plan = build_scene_plan(script_data)
    importance_by_id = {s.id: s.priority_score for s in scene_plan.sections}
    entities_by_id = {s.id: [e.model_dump() for e in s.entities] for s in scene_plan.sections}

    sections = script_data.get("sections") or []
    by_id = {s.get("id", ""): s for s in sections}

    stock_candidates = [s for s in sections if classify_section_type(s.get("id", "")) == "stock_candidate"]
    stock_candidates.sort(key=lambda s: importance_by_id.get(s.get("id", ""), 0.0), reverse=True)
    top_movers = stock_candidates[:top_movers_count]
    top_mover_ids = {s.get("id", "") for s in top_movers}

    checkpoint_sections = [
        s for s in sections
        if classify_section_type(s.get("id", "")) in ("stock_candidate", "stock_checkpoint")
        and s.get("id", "") not in top_mover_ids
    ]

    market_sec = by_id.get("market_summary")
    sector_sec = by_id.get("sectors")
    ai_strategy_sec = by_id.get("ai_strategy")
    closing_sec = by_id.get("closing")

    hook_sources = [s for s in sections if s.get("id") not in ("opening", "closing")]
    hook_sources.sort(key=lambda s: importance_by_id.get(s.get("id", ""), 0.0), reverse=True)

    ordered = [
        _build_hook_section(hook_sources[:3]),
        _build_conclusion_section(market_sec, importance_by_id, entities_by_id),
    ]
    ordered += [_annotate(s, "top_mover", importance_by_id, entities_by_id) for s in top_movers]
    if market_sec:
        ordered.append(_annotate(market_sec, "market_background", importance_by_id, entities_by_id))
    if sector_sec:
        ordered.append(_annotate(sector_sec, "sector_analysis", importance_by_id, entities_by_id))
    ordered += [_annotate(s, "stock_checkpoint", importance_by_id, entities_by_id) for s in checkpoint_sections]

    risk_section = _build_risk_section(sections, importance_by_id)
    if risk_section:
        ordered.append(risk_section)

    checklist_section = _build_checklist_section(ai_strategy_sec, importance_by_id, entities_by_id)
    if checklist_section:
        ordered.append(checklist_section)

    # closing(투자 유의사항 고지)은 8단계 구성엔 없지만 컴플라이언스 문구라
    # 누락 없이 맨 끝에 그대로 유지한다.
    if closing_sec:
        ordered.append(_annotate(closing_sec, "closing", importance_by_id, entities_by_id))

    return {
        "title": script_data.get("title", ""),
        "date": script_data.get("date", ""),
        "sections": ordered,
    }
