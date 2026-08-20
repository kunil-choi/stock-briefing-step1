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
    사라지지 않고 첫 페이지 오디오 텍스트 앞으로 옮겨져야 한다(화면에는
    어차피 안 나오므로 narration_text만 확인하면 됨)."""
    transition = "인기 유튜브 채널에서 언급된 관심종목에 대해 분석해보겠습니다."
    original = "다음은 오늘의 추가 관심 종목입니다. 먼저 A는... 다음으로 B는..."
    prefixed = f"{transition} {original}"

    sec = _section(prefixed, [
        {"name": "종목A", "text": "종목A 설명입니다."},
        {"name": "종목B", "text": "종목B 설명입니다."},
    ])
    pages = build_watchlist_pages(sec)
    assert pages[0]["narration_text"].startswith(transition), "전환 문구가 첫 페이지 오디오 텍스트 앞에 살아있어야 함"
    assert "종목A 설명입니다." in pages[0]["narration_text"]
    assert pages[0]["display_text"] == "종목A 설명입니다.", "화면 텍스트엔 전환 문구가 없어야 함"
    assert pages[1]["narration_text"] == pages[1]["display_text"] == "종목B 설명입니다.", "전환 문구는 첫 페이지에만 붙어야 함"
    print("✅ 챕터 전환 문구가 사라지지 않고 첫 페이지 오디오로만 옮겨짐(화면엔 없음)")


def test_no_transition_when_narration_starts_with_fixed_opener():
    """이 섹션이 관심종목 그룹의 첫 항목이 아니라서 전환 문구가 안 붙은
    경우(narration이 고정 오프너로 바로 시작), 챕터 전환 문구는 안 붙어야
    한다 — 다만 고정 인트로(아래 테스트)는 전환 문구와 무관하게 항상
    붙는다."""
    sec = _section(
        "다음은 오늘의 추가 관심 종목입니다. 먼저 A는...",
        [{"name": "종목A", "text": "종목A 설명입니다."}],
    )
    pages = build_watchlist_pages(sec)
    assert "종목A 설명입니다." in pages[0]["narration_text"]
    assert not pages[0]["narration_text"].startswith("인기"), "전환 문구가 없는데 엉뚱한 문구가 붙으면 안 됨"
    print("✅ 전환 문구가 없으면 붙이지 않음(고정 인트로만 붙음)")


def test_first_page_narration_has_intro_display_has_no_intro():
    """WATCHLIST-INTRO-2(사용자 피드백, 2026-08-20): 첫 페이지 오디오는
    "다음은 추가 관심종목입니다."로 시작하되(종목명 나열 없음 — 각 종목
    설명이 이미 종목명으로 시작하므로 나열은 불필요한 반복이었음), 화면
    카드에는 이 인트로 문구가 절대 나오지 않고 종목 설명만 보여야 한다."""
    sec = _section(
        "다음은 오늘의 추가 관심 종목입니다. 먼저 A는... 다음으로 B는...",
        [
            {"name": "한국콜마", "text": "한국콜마는 실적이 개선됐습니다."},
            {"name": "코스맥스", "text": "코스맥스는 사상 최대 실적을 기록했습니다."},
        ],
    )
    pages = build_watchlist_pages(sec)
    assert pages[0]["narration_text"].startswith("다음은 추가 관심종목입니다."), (
        f"첫 페이지 오디오에 고정 인트로가 없음: {pages[0]['narration_text'][:60]!r}"
    )
    assert "한국콜마" not in pages[0]["narration_text"].split("다음은 추가 관심종목입니다.", 1)[0], (
        "인트로 부분에 종목명이 나열되면 안 됨"
    )
    assert "코스맥스" not in pages[0]["narration_text"].split("한국콜마는 실적이 개선됐습니다.", 1)[0], (
        "다른 종목명이 첫 페이지 인트로에 미리 나오면 안 됨"
    )
    assert pages[0]["display_text"] == "한국콜마는 실적이 개선됐습니다.", "화면 텍스트에 인트로가 섞이면 안 됨"
    assert pages[1]["narration_text"] == pages[1]["display_text"] == "코스맥스는 사상 최대 실적을 기록했습니다."
    print("✅ 첫 페이지: 오디오엔 종목명 나열 없는 고정 인트로, 화면엔 인트로 없이 종목 설명만")


if __name__ == "__main__":
    test_one_page_per_item_in_order()
    test_empty_items_returns_no_pages()
    test_items_without_text_are_skipped()
    test_chapter_transition_moved_to_first_page()
    test_no_transition_when_narration_starts_with_fixed_opener()
    test_first_page_narration_has_intro_display_has_no_intro()
    print("\n✅ watchlist_pages 테스트 전체 통과")
