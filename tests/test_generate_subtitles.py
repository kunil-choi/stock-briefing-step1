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


def test_extra_watchlist_paginated_frame_mapping():
    """stock_추가관심종목은 이제 종목 1개당 1페이지(assets.watchlist_pages)라
    90_extra_watchlist_MM 형태의 프레임이 stock_추가관심종목_MM으로 매핑돼야
    한다. 옛 단일 프레임 패턴(90_extra_watchlist, 페이지 번호 없음)도 하위
    호환으로 계속 지원된다."""
    from generate_subtitles import _frame_stem_to_audio_id

    assert _frame_stem_to_audio_id("90_extra_watchlist_00", []) == "stock_추가관심종목_00"
    assert _frame_stem_to_audio_id("90_extra_watchlist_03", []) == "stock_추가관심종목_03"
    assert _frame_stem_to_audio_id("90_extra_watchlist", []) == "stock_추가관심종목"
    print("✅ 추가 관심 종목 페이지별 프레임(90_extra_watchlist_MM) 매핑 확인")


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


def _parse_dialogue_time(event: str) -> tuple:
    """"Dialogue: 0,H:MM:SS.CC,H:MM:SS.CC,..." 문자열에서 (start, end)를 초 단위로 파싱."""
    parts = event.split(",")
    start_str, end_str = parts[1], parts[2]

    def to_seconds(ts):
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    return to_seconds(start_str), to_seconds(end_str)


def test_speech_weight_estimates_number_reading_length():
    from generate_subtitles import _speech_weight

    # 숫자 구간은 그대로의 글자 수보다 실제 한글 발음 길이에 더 가깝게
    # 보정돼야 한다(자막 "85,400"(6자) → 실제 발음 "팔만오천사백"(6음절)).
    assert abs(_speech_weight("85,400") - 6.5) < 0.5
    # "%"/소수점이 있으면 raw 글자 수보다 뚜렷하게 커야 한다("플러스"는 "+"에서
    # 오는 것이라 이 함수의 대상이 아니지만, "%"→"퍼센트"/소수점→"쩜" 확장은 반영돼야 함).
    assert _speech_weight("+1.2%") > len("+1.2%")
    # 숫자가 없는 일반 텍스트는 원래 글자 수와 동일해야 한다(회귀 없음).
    assert _speech_weight("반도체 업종 강세") == len("반도체 업종 강세")
    print("✅ _speech_weight: 숫자 구간을 실제 발음 길이에 가깝게 보정, 일반 텍스트는 글자 수 그대로")


def test_make_dialogue_events_gives_number_heavy_chunk_more_time():
    """긴 문장이 여러 화면 청크로 쪼개질 때, 숫자가 몰린 청크가 예전(글자 수
    기준)보다 더 많은 시간을 배정받아야 한다 — 이게 사용자가 보고한
    "내레이션과 자막 속도가 안 맞는" 버그의 핵심 수정 지점이다."""
    from generate_subtitles import _make_dialogue_events, _split_subtitle_text

    subtitle = ("오늘 발표된 실적 자료에 따르면 이 회사의 매출과 영업이익이 시장 예상치를 "
                "크게 뛰어넘는 놀라운 성장세를 보이며 주가는 급등해 전일 대비 85,400원 "
                "+12.8%를 기록했습니다")
    narration = subtitle  # 문장 수 1개로 맞춰 폴백 경로(_speech_weight 가중치)를 그대로 태움
    chunks = _split_subtitle_text(subtitle)
    assert len(chunks) == 2, f"테스트 전제(2개 청크로 분할)가 깨짐: {chunks}"
    # "+12.8%"가 들어있는 짧은 꼬리 청크가 글자 수 대비 숫자 밀도가 가장 높은
    # 구간이다(앞 청크는 84자 대부분이 일반 텍스트이고 숫자는 "85,400" 하나뿐).
    number_chunk_idx = next(i for i, c in enumerate(chunks) if "+12.8" in c)

    events = _make_dialogue_events(narration, subtitle, start_time=0.0, duration=20.0)
    assert len(events) == 2

    durations = [_parse_dialogue_time(e)[1] - _parse_dialogue_time(e)[0] + 0.08 for e in events]
    number_chunk_duration = durations[number_chunk_idx]
    naive_share = len(chunks[number_chunk_idx]) / sum(len(c) for c in chunks)
    actual_share = number_chunk_duration / sum(durations)

    assert actual_share > naive_share, (
        f"숫자가 몰린 청크가 글자 수 기준(naive={naive_share:.3f})보다 "
        f"더 많은 시간(actual={actual_share:.3f})을 배정받아야 함"
    )
    print(f"✅ _make_dialogue_events: 숫자 청크 시간 배분 개선 확인 "
          f"(글자수 기준 {naive_share:.1%} → 발화가중치 기준 {actual_share:.1%})")


def test_make_dialogue_events_total_duration_unchanged():
    """가중치 계산 방식이 바뀌어도 슬라이드 전체 길이(duration)는 정확히
    보존돼야 한다 — 배분 "비율"만 바뀌고 총합은 실측 오디오 길이 그대로."""
    from generate_subtitles import _make_dialogue_events

    subtitle = "코스피는 2,650.32포인트로 전일 대비 +0.82%를 기록하며 상승 마감했습니다."
    events = _make_dialogue_events(subtitle, subtitle, start_time=0.0, duration=10.0)
    assert events
    last_end = _parse_dialogue_time(events[-1])[1]
    assert abs(last_end - (0.0 + 10.0 - 0.08)) < 0.05, "총 길이가 실측 duration과 어긋남(회귀)"
    print("✅ _make_dialogue_events: 가중치 방식이 바뀌어도 총 duration은 정확히 보존됨")


def test_export_subtitle_timeline_gives_scene_relative_seconds():
    """P2-2: export_subtitle_timeline()은 오디오 파일이 없어도(이 테스트는
    ffmpeg/실제 오디오 없이 순수 로직만 검증) SILENT_DURATION 폴백으로
    안전하게 동작하고, 각 청크의 start가 0초부터 시작하는 "장면 상대 시각"
    이어야 한다(영상 전체 누적 시각이 아님)."""
    from generate_subtitles import export_subtitle_timeline, SILENT_DURATION

    sections = [{
        "id": "market_summary", "section_type": "market_background",
        "narration": "코스피 지수는 오늘 상승 마감했습니다.",
        "subtitle": "코스피 지수는 오늘 상승 마감했습니다.",
    }]
    timeline = export_subtitle_timeline(sections, "KO")
    assert "market_summary" in timeline
    segs = timeline["market_summary"]
    assert segs, "타임라인 청크가 비어 있음"
    assert segs[0]["start"] == 0.0, f"첫 청크는 장면 시작(0초) 기준이어야 함: {segs[0]}"
    assert segs[-1]["end"] <= SILENT_DURATION, "끝 시각이 오디오 길이(폴백값) 안에 있어야 함"
    print("✅ export_subtitle_timeline: 장면 상대 시각(0초 시작) 타임라인 확인")


def test_format_ass_text_wraps_before_inserting_emphasis_tags():
    """FIX-EMPHASIS-WRAP-1(P2-4) 회귀 가드: 태그를 넣기 전에 줄바꿈을
    먼저 계산해야 한다. 순수 텍스트만으로는 한 줄(45자 이내)에 들어가지만,
    색상 태그(약 30자)를 먼저 심으면 CHARS_PER_LINE을 넘겨 불필요하게
    두 줄로 쪼개지는 게 실제로 재현되는 버그였다."""
    from generate_subtitles import _format_ass_text, CHARS_PER_LINE

    text = "코스피는 3,152포인트로 강하게 상승 마감했습니다"
    assert len(text) <= CHARS_PER_LINE, "테스트 전제: 순수 텍스트는 한 줄에 들어가야 함"

    plain = _format_ass_text(text)
    assert r"\N" not in plain, "순수 텍스트는 한 줄이어야 함(대조군)"

    emphasized = _format_ass_text(text, emphasis_texts=["3,152포인트"])
    assert r"\N" not in emphasized, (
        f"태그 삽입 때문에 불필요하게 줄바꿈됨(태그 길이가 줄바꿈 계산에 새어 들어감): {emphasized}"
    )
    assert r"{\c&H0066E0FF&}3,152포인트{\c&H00FFFFFF&}" in emphasized, "강조 태그가 정확히 삽입되지 않음"
    print("✅ _format_ass_text: 태그 삽입이 줄바꿈 판단에 영향을 주지 않음(줄바꿈 먼저, 태그는 나중)")


def test_format_ass_text_skips_emphasis_spanning_line_break():
    """강조 문구가 줄 경계를 가로지르면(단어 경계 줄바꿈이 문구 내부의
    공백에서 일어나 앞부분/뒷부분이 서로 다른 줄에 나뉘면) 그 문구는 어느
    줄에도 통째로 없으므로 태그가 안 붙는다 — 원문이 깨지는 것보다 강조를
    포기하는 게 안전하다."""
    from generate_subtitles import _format_ass_text, _wrap_words, CHARS_PER_LINE

    # "가"*42 + " 나다"가 정확히 45자(CHARS_PER_LINE)라 1번째 줄로, 그 다음
    # " 라마바사"는 넘쳐서 2번째 줄로 밀린다 — "나다 라마바사"라는 문구가
    # 두 줄에 걸쳐 쪼개지는 상황을 그대로 재현한다.
    text = "가" * 42 + " 나다 라마바사"
    lines = _wrap_words(text, CHARS_PER_LINE)
    assert len(lines) >= 2 and lines[0].endswith("나다") and lines[1] == "라마바사", (
        f"테스트 전제(줄바꿈이 문구 중간에서 일어남)가 깨짐: {lines}"
    )

    result = _format_ass_text(text, emphasis_texts=["나다 라마바사"])
    assert r"\c&H0066E0FF&" not in result, "줄을 가로지르는 강조 문구인데 태그가 삽입됨(원문 손상 위험)"
    assert "나다" in result and "라마바사" in result, "태그를 안 붙이더라도 원문 텍스트 자체는 그대로 남아야 함"
    print("✅ _format_ass_text: 줄 경계를 가로지르는 강조는 안전하게 건너뜀")


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
    test_extra_watchlist_paginated_frame_mapping()
    test_legacy_longform_patterns_still_supported()
    test_speech_weight_estimates_number_reading_length()
    test_make_dialogue_events_gives_number_heavy_chunk_more_time()
    test_make_dialogue_events_total_duration_unchanged()
    test_export_subtitle_timeline_gives_scene_relative_seconds()
    test_format_ass_text_wraps_before_inserting_emphasis_tags()
    test_format_ass_text_skips_emphasis_spanning_line_break()
    test_generate_video_reuses_shared_mapping_function()
    print("\n✅ generate_subtitles 매핑 테스트 전체 통과")
