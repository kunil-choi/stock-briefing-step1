# tests/test_builders_visual.py
"""
3차 작업(scene_plan/media_map을 실제 화면에 연결) 검증 스크립트.
pytest 미사용, 순수 assert 기반. Playwright 렌더링 없이 HTML 문자열 생성
로직만 검증한다(실제 PNG 렌더링 확인은 별도 수동 스크립트로 진행).
실행: python tests/test_builders_visual.py
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.html_theme import (  # noqa: E402
    background_layer, text_plate, news_ticker, shell, centered_shell,
    set_ticker_text,
)
from assets.builders import build_hook, _build_stock_summary  # noqa: E402
from generate_assets import _resolve_visual, _compute_ticker  # noqa: E402


def test_background_layer_empty_without_valid_file():
    assert background_layer(None) == ""
    assert background_layer("") == ""
    assert background_layer("/no/such/file.jpg") == ""
    print("✅ background_layer: 이미지가 없거나 파일이 없으면 빈 문자열(회귀 없음)")


def test_background_layer_present_for_real_file():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff" + b"0" * 100)  # 최소한의 더미 바이트(실제 디코딩은 안 함)
        path = f.name
    try:
        html = background_layer(path)
        assert "background-image" in html
        assert "linear-gradient" in html
    finally:
        os.unlink(path)
    print("✅ background_layer: 유효한 파일이면 배경+그라디언트 오버레이 반환")


def test_text_plate_wraps_content():
    html = text_plate("<div>hello</div>")
    assert "hello" in html
    assert "rgba(5,7,13" in html
    print("✅ text_plate: 반투명 다크 판으로 내용을 감쌈")


def test_news_ticker_empty_and_present():
    assert news_ticker("") == ""
    html = news_ticker("AI 반도체 변동성 확대 · 유가 급등", tone="bearish")
    assert "AI 반도체 변동성 확대" in html
    print("✅ news_ticker: 빈 텍스트는 생략, 있으면 표시")


def test_shell_ticker_global_and_suppress():
    set_ticker_text("코스피 상승 · 반도체 강세", tone="bullish")
    html_with_ticker = shell("테스트", "<div>content</div>")
    assert "코스피 상승" in html_with_ticker

    html_suppressed = shell("테스트", "<div>content</div>", suppress_ticker=True)
    assert "코스피 상승" not in html_suppressed
    set_ticker_text("")  # 다른 테스트에 영향 주지 않도록 리셋
    print("✅ shell: set_ticker_text() 전역값을 자동 소비, suppress_ticker로 끌 수 있음")


def test_shell_background_image_param():
    html = shell("테스트", "<div>content</div>", background_image="/no/such/file.jpg")
    assert "background-image" not in html  # 파일 없으면 배경 없이 정상 렌더링
    print("✅ shell: background_image가 유효하지 않으면 기존 레이아웃 그대로")


def test_build_hook_falls_back_without_visual():
    # 훅은 제목 카드 화면 한 장뿐이다(내레이션/자막 없음) — build_hook()은
    # 그 한 장의 경로만 담은 리스트를 반환한다.
    sec = {
        "id": "hook",
        "hook_title": "오늘 투자자들의 관심이 집중될 종목은?",
        "hook_subline": "지난 24시간 유튜브·증권사 방송을 AI로 분석했습니다",
    }
    with tempfile.TemporaryDirectory() as tmp:
        paths = build_hook(sec, tmp, visual=None)
        assert isinstance(paths, list) and len(paths) == 1
        assert all(os.path.isfile(p) for p in paths)
    print("✅ build_hook: visual 없이도 타이틀 카드 1장 렌더링(기존처럼 예외 없이 동작)")


def test_build_hook_uses_screen_text_with_image():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff" + b"0" * 100)
        img_path = f.name
    try:
        sec = {
            "id": "hook", "keywords": ["반도체", "실적"],
            "hook_title": "오늘 투자자들의 관심이 집중될 종목은?",
            "hook_subline": "지난 24시간 유튜브·증권사 방송을 AI로 분석했습니다",
        }
        visual = {"screenText": ["AI 반도체 급락", "오늘 시장의 방향은?"], "image_path": img_path}
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_hook(sec, tmp, visual=visual)
            assert isinstance(paths, list) and len(paths) == 1
            assert all(os.path.isfile(p) for p in paths)
    finally:
        os.unlink(img_path)
    print("✅ build_hook: screenText+이미지가 있으면 배경 사진 경로로 타이틀 카드 1장 렌더링(예외 없이 완료)")


def test_stock_summary_uses_safe_display_name_when_data_review_flagged():
    sec = {
        "id": "stock_뉴스경제방송유튜브", "corner_summary": "관심 종목 강세",
        "price": "12,300", "change": "+0.8%", "change_positive": True,
        "catalysts": ["실적 기대감"], "risks": ["변동성 확대"],
    }
    visual = {"needsDataReview": True, "safeDisplayName": "관심 종목", "screenText": [], "image_path": None}
    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "stock.png")
        _build_stock_summary(sec, out_path, tmp, visual=visual)
        assert os.path.isfile(out_path)
    print("✅ _build_stock_summary: needsDataReview 플래그가 있으면 예외 없이 안전 표시명 경로로 렌더링")


def test_resolve_visual_join_and_missing_file_guard():
    scene_by_id = {
        "stock_삼성전자": {
            "screenText": ["삼성전자 실적 기대감에 상승"],
            "visualKeywordsKo": ["삼성전자", "반도체"],
            "needsDataReview": False,
        }
    }
    media_map = {"stock_삼성전자": {"image_path": "/no/such/file.jpg", "source": "mock"}}
    visual = _resolve_visual("stock_삼성전자", scene_by_id, media_map)
    assert visual["image_path"] is None, "존재하지 않는 파일 경로는 None으로 방어적으로 처리돼야 함"
    assert visual["screenText"] == ["삼성전자 실적 기대감에 상승"]

    visual_missing = _resolve_visual("stock_없음", scene_by_id, media_map)
    assert visual_missing["screenText"] == [] and visual_missing["image_path"] is None
    print("✅ _resolve_visual: scene_plan/media_map 조인 + 존재하지 않는 이미지 파일 방어 확인")


def test_compute_ticker_ranks_by_priority_and_dedupes():
    # FIX-TICKER-1: 티커가 임의 섹션의 visualKeywordsKo[0](섹터명 등 종목이
    # 아닌 키워드 포함 가능)이 아니라, 오늘 이 영상이 다루는 "종목 섹션"의
    # 종목명만 모아 "오늘의 주요 관심종목: " 라벨을 붙이도록 바뀌었다.
    sections = [
        {"id": "closing", "priority_score": 0.3, "visualKeywordsKo": ["마무리"]},
        {"id": "stock_삼성전자", "priority_score": 0.9, "visualKeywordsKo": ["삼성전자", "반도체"]},
        {"id": "stock_추가관심종목", "priority_score": 0.95, "visualKeywordsKo": ["추가관심종목"]},
        {"id": "market_summary", "priority_score": 0.6, "visualKeywordsKo": ["코스피"],
         "dataOverlay": {"marketMood": "bearish"}},
    ]
    text, tone = _compute_ticker(sections, max_items=6)
    assert text.startswith("오늘의 주요 관심종목: "), "종목 목록임을 밝히는 라벨이 붙어야 함"
    names = text.removeprefix("오늘의 주요 관심종목: ").split(" · ")
    assert names[0] == "삼성전자", "priority_score가 가장 높은 종목 섹션의 이름이 먼저 나와야 함"
    assert "추가관심종목" not in names, "집계 섹션(stock_추가관심종목)은 개별 종목이 아니므로 제외돼야 함"
    assert "마무리" not in names and "코스피" not in names, "종목이 아닌 섹션의 키워드는 섞이면 안 됨"
    assert tone == "bearish"
    print("✅ _compute_ticker: 종목 섹션만 priority_score 순으로 모으고 집계 섹션은 제외")


if __name__ == "__main__":
    test_background_layer_empty_without_valid_file()
    test_background_layer_present_for_real_file()
    test_text_plate_wraps_content()
    test_news_ticker_empty_and_present()
    test_shell_ticker_global_and_suppress()
    test_shell_background_image_param()
    test_build_hook_falls_back_without_visual()
    test_build_hook_uses_screen_text_with_image()
    test_stock_summary_uses_safe_display_name_when_data_review_flagged()
    test_resolve_visual_join_and_missing_file_guard()
    test_compute_ticker_ranks_by_priority_and_dedupes()
    print("\n✅ builders_visual 테스트 전체 통과")
