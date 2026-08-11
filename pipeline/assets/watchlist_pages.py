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
# items[].text를 오디오/자막으로 쓰기 시작하면서 기존 narration 전체는 더 이상
# 쓰이지 않으므로, 그 안에 있던 전환 문구를 옮겨주지 않으면 조용히 사라진다.
_FIXED_OPENER = "다음은 오늘의 추가 관심 종목입니다."


def build_watchlist_pages(section: dict) -> list:
    """반환: [{"name": 종목명, "text": 그 종목 페이지의 낭독/자막 텍스트}, ...].
    items가 비어 있으면 빈 리스트(호출부가 섹션 자체를 건너뛰어야 함)."""
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
        if i == 0 and transition:
            text = f"{transition} {text}".strip()
        pages.append({"name": name, "text": text})
    return pages
