# pipeline/assets/watchlist_pages.py
"""
stock_추가관심종목("오늘의 추가 관심 종목", remaining_stocks 집계 섹션)을
종목 1개당 1페이지로 나눌 때 쓰는 페이지 텍스트를 만든다.

builders.py(화면 프레임)·generate_voice.py(오디오)·generate_subtitles.py(자막)
세 곳이 전부 "몇 번째 페이지에 어떤 종목/문구가 들어가는지"를 알아야 하는데,
각자 따로 계산하면 페이지 수·순서가 어긋날 위험이 있다. 이 모듈 하나로
페이지 목록을 만들어 세 곳이 공유한다(단일 진실 공급원).

이전에는 이 섹션 전체가 한 화면(builders._build_aggregate_stock_slide)에
종목 카드 여러 개를 욱여넣는 방식이었다 — "화면에 종목이 4~5개씩 한꺼번에
나온다"는 사용자 피드백으로 종목 1개당 1페이지로 바꿨다.
"""

# generate_script.py가 stock_추가관심종목.narration에 항상 이 문장으로
# 시작하도록 지시한다(프롬프트 참고). narrative_reorder._prefix_narration()이
# 이 섹션을 관심종목 그룹의 첫 항목으로 골랐을 때만 그 앞에 챕터 전환 문구를
# 덧붙이므로, narration이 이 고정 문장으로 시작하지 않으면 전환 문구가 붙은
# 것으로 보고 그 부분만 떼어 페이지 1의 텍스트 앞에 옮겨 붙인다 — 페이지별
# items[].narration_text를 오디오로 쓰기 시작하면서 기존 narration 전체는
# 더 이상 쓰이지 않으므로, 그 안에 있던 전환 문구를 옮겨주지 않으면 조용히
# 사라진다.
_FIXED_OPENER = "다음은 오늘의 추가 관심 종목입니다."

# WATCHLIST-INTRO-2: 예전엔 여기에 전체 종목명을 나열했다(사용자 피드백,
# 2026-08-13 — 종목명 언급 없이 바로 개별 종목 설명이 시작돼 지금 어느
# 종목 얘기인지 알 수 없었다). 그런데 각 페이지의 종목 설명 자체가 이미
# 종목명으로 시작하므로 나열은 불필요한 반복이었다(사용자 피드백,
# 2026-08-20) — 나열 없이 이 문구만 말하고 바로 첫 종목 설명으로 넘어간다.
_INTRO = "다음은 추가 관심종목입니다."


def build_watchlist_pages(section: dict) -> list:
    """반환: [{"name": 종목명, "narration_text": 오디오용(인트로 포함),
    "display_text": 화면 카드용(인트로 없이 종목 설명만)}, ...].
    items가 비어 있으면 빈 리스트(호출부가 섹션 자체를 건너뛰어야 함).

    ★ WATCHLIST-INTRO-2: 인트로 문구("다음은 추가 관심종목입니다.")는
    음성으로만 나오고 화면 카드에는 절대 나오지 않는다 — narration_text와
    display_text를 분리해서, 오디오는 인트로+종목 설명 전체를 읽지만
    builders.py가 그리는 카드는 display_text(종목 설명만)만 쓴다."""
    items = [
        it for it in (section.get("items") or [])
        if isinstance(it, dict) and (it.get("text") or "").strip()
    ]
    if not items:
        return []

    narration_field = section.get("narration") or ""
    transition = ""
    if _FIXED_OPENER in narration_field and not narration_field.startswith(_FIXED_OPENER):
        transition = narration_field.split(_FIXED_OPENER, 1)[0].strip()

    pages = []
    for i, it in enumerate(items):
        name = (it.get("name") or "").strip()
        text = (it.get("text") or "").strip()
        narration_text = text
        if i == 0:
            prefix = " ".join(p for p in (transition, _INTRO) if p)
            if prefix:
                narration_text = f"{prefix} {text}".strip()
        pages.append({"name": name, "narration_text": narration_text, "display_text": text})
    return pages
