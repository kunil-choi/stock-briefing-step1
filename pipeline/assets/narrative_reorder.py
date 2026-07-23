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
from .korean_numbers import pick_eun_neun

# ─────────────────────────────────────────────────────────────────────────────
# 섹션 분류
# ─────────────────────────────────────────────────────────────────────────────

_AGGREGATE_STOCK_IDS = {"stock_추가관심종목", "stock_증권사리포트"}


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

# 오프닝 시그니처 멘트 — 채널 브랜딩 목적상 매일 동일한 문구를 사용한다(의도적
# 고정, LLM 재생성 대상 아님). 문구를 바꾸려면 이 상수만 수정하면 된다.
OPENING_HOOK_LINE = "오늘 투자자들의 관심이 집중될 종목은?"

# 훅 타이틀 화면(00_hook_1_title.png)에 큰 제목 문구 아래 작게 들어가는 부제.
# 화면에만 표시되는 시각 요소이며 내레이션(TTS)에는 포함되지 않는다.
OPENING_HOOK_SUBLINE = (
    "지난 24시간 업로드된 구독자 상위권 유튜브 콘텐츠와 "
    "증권사 경제방송 채널을 AI로 분석했습니다"
)


def _build_hook_section() -> dict:
    """15초 훅: 시그니처 질문(OPENING_HOOK_LINE) 한 줄짜리 타이틀 화면 하나뿐.
    제목 화면처럼 텍스트만 보여주고 내레이션·자막은 넣지 않는다(builders.build_hook()이
    hook_title 필드를 화면 렌더링에만 쓴다 — generate_voice.py/_build_jobs(),
    generate_subtitles.py/_build_subtitle_map()도 hook_title에 대해 오디오·자막을
    만들지 않는다). 화면 표시 시간은 generate_video.py의 무음 프레임 처리를 참고."""
    return {
        "id": "hook", "label": "훅 타이틀", "section_type": "hook",
        "importance": 1.0, "entities": [],
        "narration": "", "subtitle": "",
        "hook_title": OPENING_HOOK_LINE,
        "hook_subline": OPENING_HOOK_SUBLINE,
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

def _trim_to_core_mention(section: dict) -> dict:
    """짧은 하이라이트(short_form) 포맷용: TOP 종목이라도 channel_summaries를
    (있다면) 가장 앞의 1개로만 줄여 "핵심만" 다룬다. 원본 section은 그대로
    두고 복사본만 반환한다."""
    summaries = section.get("channel_summaries") or []
    if len(summaries) <= 1:
        return section
    return {**section, "channel_summaries": summaries[:1]}


def reorder_sections(script_data: dict, top_movers_count: int = 3,
                      short_form: bool = False) -> dict:
    """script_data(원본 script.json)를 재정렬한다.

    short_form=False(기본): 8단계 "장전 의사결정형" 전체 구성
      (훅 → 결론 → TOP3 → 시장배경 → 섹터분석 → 체크포인트 → 리스크 → 체크리스트 → 클로징)
    short_form=True: 출퇴근길에 빠르게 볼 수 있는 하이라이트 구성만
      (훅 → 결론 → TOP{top_movers_count}(핵심 멘션 1개로 축소) → 클로징)
      — 5~8분 목표 길이(config/schedule.yml)에 맞춘 축약판."""
    scene_plan = build_scene_plan(script_data)
    importance_by_id = {s.id: s.priority_score for s in scene_plan.sections}
    entities_by_id = {s.id: [e.model_dump() for e in s.entities] for s in scene_plan.sections}

    sections = script_data.get("sections") or []
    by_id = {s.get("id", ""): s for s in sections}

    stock_candidates = [s for s in sections if classify_section_type(s.get("id", "")) == "stock_candidate"]
    stock_candidates.sort(key=lambda s: importance_by_id.get(s.get("id", ""), 0.0), reverse=True)
    top_movers = stock_candidates[:top_movers_count]
    top_mover_ids = {s.get("id", "") for s in top_movers}

    market_sec = by_id.get("market_summary")
    closing_sec = by_id.get("closing")

    ordered = [
        _build_hook_section(),
        _build_conclusion_section(market_sec, importance_by_id, entities_by_id),
    ]
    if short_form:
        ordered += [
            _annotate(_trim_to_core_mention(s), "top_mover", importance_by_id, entities_by_id)
            for s in top_movers
        ]
    else:
        ordered += [_annotate(s, "top_mover", importance_by_id, entities_by_id) for s in top_movers]

        sector_sec = by_id.get("sectors")
        ai_strategy_sec = by_id.get("ai_strategy")
        checkpoint_sections = [
            s for s in sections
            if classify_section_type(s.get("id", "")) in ("stock_candidate", "stock_checkpoint")
            and s.get("id", "") not in top_mover_ids
        ]

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
    # short_form 여부와 무관하게 누락 없이 맨 끝에 그대로 유지한다.
    if closing_sec:
        ordered.append(_annotate(closing_sec, "closing", importance_by_id, entities_by_id))

    return {
        "title": script_data.get("title", ""),
        "date": script_data.get("date", ""),
        "sections": ordered,
    }


# ─────────────────────────────────────────────────────────────────────────────
# "종목 언급 중심" 플롯 — 개장 전 전일 데이터로 만드는 "시장 요약/전망" 해설이
# 시의성에 안 맞는다는 판단 하에, v3-1의 핵심 데이터(지난 24시간 채널 언급 종목)
# 정리에 집중하는 구성. reorder_sections()와는 독립된 함수라 기존 8단계/
# short_form 경로와 그 테스트에는 전혀 영향이 없다.
#
# 구성: 훅 → (고정) 채널 언급 인트로 → 주요 지표(있으면, 해석 없이 수치만) →
#       대형 주도주 → 관심종목(유튜브/경제방송 언급) → AI 히든픽(있으면) → 클로징
# market_summary의 해설(corner_summary/points)·섹터분석·AI 투자전략·리스크
# 다이제스트는 이 구성에서 전부 제외한다.
# ─────────────────────────────────────────────────────────────────────────────

MENTION_INTRO_LINE = (
    "지난 24시간 동안 인기 유튜브 채널에서 가장 많이 언급된 종목은 무엇이었을까요? "
    "KBS 머니올라가 관련 영상을 AI로 분석해, "
    "전문가들이 주목한 종목과 언급 포인트를 핵심만 빠르게 정리해드립니다. "
    "바로 확인해보시죠."
)

_LEADER_TRANSITION     = "우선 시장을 이끌고 있는 대형 주도주 상황 살펴보겠습니다."
_WATCHLIST_TRANSITION  = "인기 유튜브 채널에서 언급된 관심종목에 대해 분석해보겠습니다."


def _prefix_narration(section: dict, prefix: str) -> dict:
    """섹션 사본의 narration/subtitle 맨 앞에 고정 전환 멘트를 붙인다(원본은
    불변). 화면 렌더러(builders.py)는 narration 텍스트를 그대로 그리는 게
    아니라 섹션을 id로 다시 찾아 화면을 구성하므로, 이 접두어는 내레이션·
    자막에만 반영되고 화면 구성에는 영향을 주지 않는다."""
    narration = (prefix + " " + (section.get("narration") or "")).strip()
    subtitle  = (prefix + " " + (section.get("subtitle") or "")).strip()
    return {**section, "narration": narration, "subtitle": subtitle}


def _build_mention_intro_section(importance_by_id: dict, entities_by_id: dict) -> dict:
    """"오늘의 한 줄 결론" 자리를 대체하는 고정 멘트. 시장 방향 해설 대신 이
    영상의 핵심(채널 언급 종목 정리)을 그대로 알린다 — 매일 동일한 문구다."""
    return {
        "id": "conclusion", "label": "오늘의 브리핑 소개", "section_type": "conclusion",
        "importance": round(importance_by_id.get("market_summary", 0.6), 2),
        "entities": entities_by_id.get("market_summary", []),
        "narration": MENTION_INTRO_LINE, "subtitle": MENTION_INTRO_LINE,
    }


def _fmt_index_line(name: str, value: str, change: str) -> str:
    if not value:
        return ""
    # FIX-JOSA-1: "는"을 무조건 고정하면 받침 있는 지표명(코스닥/나스닥 등)에서
    # "코스닥는"처럼 문법이 틀린 조사가 붙는다 — 받침 유무로 은/는을 고른다.
    josa = pick_eun_neun(name)
    return (
        f"{name}{josa} {value}, 전일 대비 {change}로 마감했습니다." if change
        else f"{name}{josa} {value}로 마감했습니다."
    )


def _build_market_indicators_section(market_sec: Optional[dict], importance_by_id: dict,
                                      entities_by_id: dict) -> Optional[dict]:
    """주요 지표: 해석·전망 없이 전일 코스피/코스닥 종가와 오늘 새벽 마감된
    미국 시장 수치만 코드에서 직접 낭독 문장으로 만든다 — LLM 해설을 거치지
    않으므로 "상승세"류 진행형 표현이 섞일 여지 자체가 없다. market_data가
    없으면 섹션 자체를 건너뛴다(반환값 None)."""
    if not market_sec or not market_sec.get("kospi_value"):
        return None
    lines = [
        _fmt_index_line("코스피", market_sec.get("kospi_value", ""), market_sec.get("kospi_change", "")),
        _fmt_index_line("코스닥", market_sec.get("kosdaq_value", ""), market_sec.get("kosdaq_change", "")),
        _fmt_index_line("나스닥", market_sec.get("nasdaq_value", ""), market_sec.get("nasdaq_change", "")),
        _fmt_index_line("S&P500", market_sec.get("sp500_value", ""), market_sec.get("sp500_change", "")),
    ]
    if market_sec.get("usdkrw_value"):
        lines.append(f"원달러 환율은 {market_sec['usdkrw_value']}원으로 마감했습니다.")
    narration = (
        "우선 어제 마감된 국내 증시와, 오늘 새벽 마감된 미국 증시 주요 지표를 전해드립니다. "
        + " ".join(l for l in lines if l)
    ).strip()
    # 시각 카드(builders.build_market_summary의 코스피/코스닥/나스닥/S&P500/환율
    # 숫자 표)는 그대로 재사용하되, points 같은 해석성 문구는 비워 카드에
    # 노출되지 않게 한다 — 해석 없이 지표만 보여주는 짧은 카드로. corner_summary는
    # 화면 헤드라인 전용 고정 문구로 둔다(narration을 그대로 압축하면 어색하게
    # 잘리므로 — scene_plan._screen_text_base()가 corner_summary를 최우선으로
    # 쓴다).
    return {
        **market_sec,
        "id": "market_summary", "section_type": "market_indicators",
        "importance": round(importance_by_id.get("market_summary", 0.5), 2),
        "entities": entities_by_id.get("market_summary", []),
        "narration": narration, "subtitle": narration,
        "corner_summary": "국내 증시 전일 종가와 미국 주요 지수", "points": [],
    }


def build_mention_briefing(script_data: dict) -> dict:
    """"종목 언급 중심" 구성으로 재정렬한다(reorder_sections()와 독립적).

    훅 → 채널 언급 인트로(고정) → 주요 지표(있으면) → 대형 주도주 →
    관심종목 → AI 히든픽(있으면) → 클로징."""
    scene_plan = build_scene_plan(script_data)
    importance_by_id = {s.id: s.priority_score for s in scene_plan.sections}
    entities_by_id = {s.id: [e.model_dump() for e in s.entities] for s in scene_plan.sections}

    sections = script_data.get("sections") or []
    by_id = {s.get("id", ""): s for s in sections}

    stock_candidates = [s for s in sections if classify_section_type(s.get("id", "")) == "stock_candidate"]

    leaders = [s for s in stock_candidates if s.get("stock_tier") == "market_leader"]
    if leaders:
        leader_ids = {s.get("id", "") for s in leaders}
        others = [s for s in stock_candidates if s.get("id", "") not in leader_ids]
    else:
        # stock_tier가 없는 과거 script.json 호환: generate_script.py는 항상
        # market_leaders를 먼저 생성하므로, 원본 순서의 앞 2개를 대형 주도주로
        # 추정한다.
        leaders, others = stock_candidates[:2], stock_candidates[2:]

    market_sec    = by_id.get("market_summary")
    watchlist_sec = by_id.get("stock_추가관심종목")
    closing_sec   = by_id.get("closing")

    ordered = [
        _build_hook_section(),
        _build_mention_intro_section(importance_by_id, entities_by_id),
    ]

    indicators_section = _build_market_indicators_section(market_sec, importance_by_id, entities_by_id)
    if indicators_section:
        ordered.append(indicators_section)

    if leaders:
        leader_group = [_annotate(s, "top_mover", importance_by_id, entities_by_id) for s in leaders]
        leader_group[0] = _prefix_narration(leader_group[0], _LEADER_TRANSITION)
        ordered += leader_group

    watchlist_group = [_annotate(s, "top_mover", importance_by_id, entities_by_id) for s in others]
    if watchlist_sec:
        watchlist_group.append(_annotate(watchlist_sec, "stock_checkpoint", importance_by_id, entities_by_id))
    if watchlist_group:
        watchlist_group[0] = _prefix_narration(watchlist_group[0], _WATCHLIST_TRANSITION)
        ordered += watchlist_group


    if closing_sec:
        ordered.append(_annotate(closing_sec, "closing", importance_by_id, entities_by_id))

    return {
        "title": script_data.get("title", ""),
        "date": script_data.get("date", ""),
        "sections": ordered,
    }
