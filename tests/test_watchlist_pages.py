# tests/test_watchlist_pages.py
"""
assets.watchlist_pages.build_watchlist_pages() 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크/렌더링
불필요(순수 함수).

builders.py(화면)/generate_voice.py(오디오)/generate_subtitles.py(자막)가
전부 이 함수 하나로 "종목 1개당 1페이지" 목록을 공유하므로, 이 함수의
페이지 수·순서·텍스트가 곧 세 파일 전체의 계약이다.

실행: python tests/test_watchlist_pages.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.watchlist_pages import build_watchlist_pages  # noqa: E402


def _section(narration, items):
    return {"id": "stock_추가관심종목", "narration": narration, "subtitle": narration, "items": items}


def test_one_page_per_item_in_order():
    sec = _section(
        "다음은 오늘의 추가 관심 종목입니다. 먼저 A는... 다음으로 B는...",
        [
            {"name": "종목A", "text": "종목A 설명입니다."},
            {"name": "종목B", "text": "종목B 설명입니다."},
            {"name": "종목C", "text": "종목C 설명입니다."},
        ],
    )
    pages = build_watchlist_pages(sec)
    assert len(pages) == 3
    assert [p["name"] for p in pages] == ["종목A", "종목B", "종목C"]
    print("✅ items 개수만큼, 순서 그대로 1개씩 페이지가 만들어짐")


def test_empty_items_returns_no_pages():
    sec = _section("다음은 오늘의 추가 관심 종목입니다.", [])
    assert build_watchlist_pages(sec) == []
    print("✅ items가 없으면 빈 리스트(호출부가 섹션 자체를 건너뛰어야 함)")


def test_items_without_text_are_skipped():
    sec = _section("다음은 오늘의 추가 관심 종목입니다.", [
        {"name": "종목A", "text": "종목A 설명입니다."},
        {"name": "종목B", "text": ""},
        {"name": "종목C", "text": "   "},
    ])
    pages = build_watchlist_pages(sec)
    assert [p["name"] for p in pages] == ["종목A"]
    print("✅ text가 비어있는 item은 페이지로 만들지 않음")


def test_chapter_transition_moved_to_first_page():
    """narrative_reorder._prefix_narration()이 이 섹션을 관심종목 그룹의 첫
    항목으로 골라 챕터 전환 문구를 narration 앞에 붙인 경우, 그 전환 문구가
    사라지지 않고 첫 페이지 텍스트 앞으로 옮겨져야 한다."""
    transition = "인기 유튜브 채널에서 언급된 관심종목에 대해 분석해보겠습니다."
    original = "다음은 오늘의 추가 관심 종목입니다. 먼저 A는... 다음으로 B는..."
    prefixed = f"{transition} {original}"

    sec = _section(prefixed, [
        {"name": "종목A", "text": "종목A 설명입니다."},
        {"name": "종목B", "text": "종목B 설명입니다."},
    ])
    pages = build_watchlist_pages(sec)
    assert pages[0]["text"].startswith(transition), "전환 문구가 첫 페이지 텍스트 앞에 살아있어야 함"
    assert "종목A 설명입니다." in pages[0]["text"]
    assert pages[1]["text"] == "종목B 설명입니다.", "전환 문구는 첫 페이지에만 붙어야 함"
    print("✅ 챕터 전환 문구가 사라지지 않고 첫 페이지로 옮겨짐")


def test_no_transition_when_narration_starts_with_fixed_opener():
    """이 섹션이 관심종목 그룹의 첫 항목이 아니라서 전환 문구가 안 붙은
    경우(narration이 고정 오프너로 바로 시작), item 텍스트를 그대로 써야
    한다 — 엉뚱한 문구를 지어내 붙이면 안 됨."""
    sec = _section(
        "다음은 오늘의 추가 관심 종목입니다. 먼저 A는...",
        [{"name": "종목A", "text": "종목A 설명입니다."}],
    )
    pages = build_watchlist_pages(sec)
    assert pages[0]["text"] == "종목A 설명입니다."
    print("✅ 전환 문구가 없으면 item 텍스트를 그대로 사용")


if __name__ == "__main__":
    test_one_page_per_item_in_order()
    test_empty_items_returns_no_pages()
    test_items_without_text_are_skipped()
    test_chapter_transition_moved_to_first_page()
    test_no_transition_when_narration_starts_with_fixed_opener()
    print("\n✅ watchlist_pages 테스트 전체 통과")
