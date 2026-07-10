# tests/test_generate_subtitles.py
"""
generate_subtitles._frame_stem_to_audio_id() 프레임→오디오ID 매핑 검증.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크/ffmpeg
불필요(순수 문자열 매핑 로직).

숏폼(short_form=True) 재정렬 통합으로 새로 추가된 00_hook/01_conclusion
패턴과, 구 8단계 롱폼(short_form=False)에서만 나타나는 패턴들의 하위
호환을 함께 검증한다. generate_video.py가 이 함수를 자체 구현 없이
그대로 import해서 쓰는지도 확인한다(중복 구현 방지).

실행: python tests/test_generate_subtitles.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)


def test_hook_and_conclusion_frame_mapping():
    from generate_subtitles import _frame_stem_to_audio_id

    assert _frame_stem_to_audio_id("00_hook", []) == "hook"
    assert _frame_stem_to_audio_id("01_conclusion", []) == "conclusion"
    print("✅ 00_hook/01_conclusion → hook/conclusion 매핑 확인")


def test_closing_frame_mapping_unchanged():
    from generate_subtitles import _frame_stem_to_audio_id

    assert _frame_stem_to_audio_id("99_closing", []) == "closing"
    print("✅ 99_closing → closing 매핑 확인(변경 없음)")


def test_stock_summary_and_mention_mapping_with_short_form_prefix():
    """short_form에서 종목 프레임은 10_종목명 형태의 접두어를 쓴다(hook=00,
    conclusion=01 다음부터 순번). 접두어 숫자와 무관하게 종목명 기준으로
    매핑되는지 확인한다."""
    from generate_subtitles import _frame_stem_to_audio_id

    sections = [{"id": "stock_삼성전자"}, {"id": "hidden_두산에너빌리티"}]

    assert _frame_stem_to_audio_id("10_삼성전자_1_summary", sections) == "stock_삼성전자_summary"
    assert _frame_stem_to_audio_id("10_삼성전자_3_mention_00", sections) == "stock_삼성전자_mention_00"
    assert _frame_stem_to_audio_id("11_두산에너빌리티_1_summary", sections) == "hidden_두산에너빌리티_summary"
    print("✅ short_form 종목 프레임(10_.../11_...) 매핑 확인")


def test_legacy_longform_patterns_still_supported():
    """short_form=False(구 8단계 롱폼)에서만 나오는 패턴들의 하위 호환."""
    from generate_subtitles import _frame_stem_to_audio_id

    assert _frame_stem_to_audio_id("00_opening", []) == "opening"
    assert _frame_stem_to_audio_id("01_market_00", []) == "market_summary"
    assert _frame_stem_to_audio_id("02_sector", []) == "sectors"
    assert _frame_stem_to_audio_id("90_extra_watchlist", []) == "stock_추가관심종목"
    assert _frame_stem_to_audio_id("91_today_pick", []) == "stock_오늘의픽"
    assert _frame_stem_to_audio_id("92_brokerage_report", []) == "stock_증권사리포트"
    assert _frame_stem_to_audio_id("98_ai_strategy", []) == "ai_strategy"
    print("✅ 구 8단계 롱폼 패턴 하위 호환 확인")


def test_generate_video_reuses_shared_mapping_function():
    """generate_video.py가 _frame_stem_to_audio_id를 독립적으로 재구현하지
    않고 generate_subtitles.py의 것을 그대로 import해 쓰는지 확인한다
    (예전에 두 벌의 구현이 따로 있다가 한쪽만 고쳐서 실제 오탐 버그가 났던
    적이 있음 — quality_gate.py 버그 수정과 동일한 이유로 단일화한다)."""
    import generate_subtitles
    import generate_video

    assert generate_video._frame_stem_to_audio_id is generate_subtitles._frame_stem_to_audio_id
    print("✅ generate_video.py가 generate_subtitles.py의 매핑 함수를 그대로 재사용함(중복 구현 없음)")


if __name__ == "__main__":
    test_hook_and_conclusion_frame_mapping()
    test_closing_frame_mapping_unchanged()
    test_stock_summary_and_mention_mapping_with_short_form_prefix()
    test_legacy_longform_patterns_still_supported()
    test_generate_video_reuses_shared_mapping_function()
    print("\n✅ generate_subtitles 매핑 테스트 전체 통과")
