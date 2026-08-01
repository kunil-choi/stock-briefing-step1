# tests/test_generate_video.py
"""
generate_video.py의 resolve_merged_duration() 안전장치 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크/ffmpeg
불필요(순수 계산 함수).
실행: python tests/test_generate_video.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from generate_video import (  # noqa: E402
    resolve_merged_duration, compute_bgm_bounds, TARGET_MIN, TARGET_MAX, TARGET_IDEAL,
    _classify_drop_candidate, _fits_within_target, trim_to_fit_budget,
)
from config_schedule import duration_for  # noqa: E402


def test_trusts_measurement_when_close_to_expected():
    # 실제 CI에서 관측된 정상 케이스: 측정값과 기대값이 거의 일치
    result = resolve_merged_duration(measured_duration=754.82, expected_duration=754.8)
    assert abs(result - 754.82) < 0.01
    print("✅ 측정값이 기대값과 가까우면 측정값을 그대로 신뢰")


def test_falls_back_to_expected_when_measurement_is_way_off():
    # 실제 사고 재현: 755초 분량이 1300초로 잘못 측정된 경우
    result = resolve_merged_duration(measured_duration=1300.0, expected_duration=754.8)
    assert result == 754.8, f"기대값으로 대체돼야 하는데 {result}가 나옴"
    print("✅ 측정값이 기대값과 20% 넘게 어긋나면 기대값으로 대체 (실제 사고 재현)")


def test_boundary_within_tolerance_is_trusted():
    # 20% 경계 바로 안쪽(19%)은 측정값을 신뢰해야 함
    expected = 800.0
    measured = expected * 1.19
    result = resolve_merged_duration(measured, expected)
    assert result == measured
    print("✅ 허용 오차(20%) 이내면 측정값 유지")


def test_boundary_beyond_tolerance_falls_back():
    # 20% 경계 바로 바깥쪽(21%)은 기대값으로 대체돼야 함
    expected = 800.0
    measured = expected * 1.21
    result = resolve_merged_duration(measured, expected)
    assert result == expected
    print("✅ 허용 오차(20%)를 넘으면 기대값으로 대체")


def test_zero_expected_duration_trusts_measurement():
    # expected_duration을 계산할 수 없는 극단적인 경우(0) 방어
    result = resolve_merged_duration(measured_duration=123.4, expected_duration=0.0)
    assert result == 123.4
    print("✅ expected_duration=0이면 측정값을 그대로 사용(0-division 방지)")


def test_compute_bgm_bounds_basic():
    # 3개 장면(각 10s) + 전환 2개(0.4s) = 전체 30.8s. intro는 첫 장면 끝(10s),
    # outro는 마지막 장면 시작(전체 30.8s - 마지막 장면 10s = 20.8s)
    pairs = [("f0.png", "a0.mp3", 10.0), ("f1.png", "a1.mp3", 10.0), ("f2.png", "a2.mp3", 10.0)]
    intro_end, outro_start = compute_bgm_bounds(pairs, transition_count=2, time_scale=1.0)
    assert abs(intro_end - 10.0) < 0.01
    assert abs(outro_start - 20.8) < 0.01
    print(f"✅ compute_bgm_bounds: intro_end={intro_end}, outro_start={outro_start}")


def test_compute_bgm_bounds_scales_with_time_scale():
    # 배속 조정(speed_factor)이 적용됐다면 time_scale(=1/speed_factor)만큼 축소돼야 함
    pairs = [("f0.png", "a0.mp3", 10.0), ("f1.png", "a1.mp3", 10.0)]
    intro_end, outro_start = compute_bgm_bounds(pairs, transition_count=1, time_scale=0.5)
    assert abs(intro_end - 5.0) < 0.01
    assert abs(outro_start - 5.2) < 0.01
    print(f"✅ compute_bgm_bounds: time_scale 적용 시 축소 확인 (intro_end={intro_end}, outro_start={outro_start})")


def test_compute_bgm_bounds_empty_pairs():
    intro_end, outro_start = compute_bgm_bounds([], transition_count=0)
    assert intro_end == 0.0 and outro_start == 0.0
    print("✅ compute_bgm_bounds: 빈 목록은 (0.0, 0.0) 반환")


def test_compute_bgm_bounds_single_scene_outro_not_before_intro():
    # 장면이 1개뿐이면 intro/outro가 같은 장면을 가리키므로 outro_start가
    # intro_end보다 앞서면 안 된다(max()로 방어)
    pairs = [("f0.png", "a0.mp3", 5.0)]
    intro_end, outro_start = compute_bgm_bounds(pairs, transition_count=0)
    assert outro_start >= intro_end
    print("✅ compute_bgm_bounds: 장면이 1개뿐이어도 outro_start < intro_end가 되지 않음")


def test_target_duration_reads_from_config_schedule():
    """TARGET_MIN/MAX가 하드코딩된 15분이 아니라 config/schedule.yml의
    duration.longform을 실제로 읽는지 확인한다 — 예전에는 이 값이
    schedule.yml과 무관하게 870/930으로 고정돼 있어서, schedule.yml을
    5~8분으로 바꿔도 실제 영상 길이는 그대로 15분이 나오는 불일치가 있었다
    (사용자가 실제로 겪은 버그)."""
    bounds = duration_for("longform")
    assert TARGET_MIN == bounds["min_seconds"], (
        f"TARGET_MIN({TARGET_MIN})이 config/schedule.yml의 "
        f"duration.longform.min_seconds({bounds['min_seconds']})와 다름"
    )
    assert TARGET_MAX == bounds["max_seconds"]
    assert TARGET_MIN == 480.0 and TARGET_MAX == 600.0, (
        f"'종목 언급 중심' 구성(약 8~10분) 목표값이 아님: {TARGET_MIN}~{TARGET_MAX}"
    )
    assert TARGET_IDEAL == (TARGET_MIN + TARGET_MAX) / 2
    print(f"✅ TARGET_MIN/MAX/IDEAL이 config/schedule.yml을 그대로 반영함: "
          f"{TARGET_MIN}~{TARGET_MAX}s (IDEAL={TARGET_IDEAL})")


def test_fits_within_target_basic():
    pairs = [("f0.png", "a0.mp3", 100.0), ("f1.png", "a1.mp3", 100.0)]
    # 210s(200s 오디오 + 전환 10s) / 1.0배속 = 210s > 200s 목표 → 초과
    assert not _fits_within_target(pairs, target_max=200.0, atempo_max_speed=1.0, transition_duration=10.0)
    # 1.05배속까지 허용하면 210/1.05=200s로 딱 맞음
    assert _fits_within_target(pairs, target_max=200.0, atempo_max_speed=1.05, transition_duration=10.0)
    assert _fits_within_target([], target_max=1.0, atempo_max_speed=1.0, transition_duration=0.0)
    print("✅ _fits_within_target: 배속 상한을 반영한 예상 길이 계산 확인")


def test_classify_drop_candidate_tiers():
    leaders = {"stock_삼성전자"}
    importance = {"stock_삼성전자": 0.9, "stock_현대차": 0.5, "stock_카카오": 0.3}

    # tier 0: 비주도주 멘션 페이지. 낮은 importance가 먼저, 같은 종목이면
    # 페이지 번호가 큰 쪽이 먼저(정렬키가 더 작아야 함).
    kakao_p1 = _classify_drop_candidate("stock_카카오_mention_01", leaders, importance)
    kakao_p0 = _classify_drop_candidate("stock_카카오_mention_00", leaders, importance)
    hyundai_p0 = _classify_drop_candidate("stock_현대차_mention_00", leaders, importance)
    assert kakao_p1[0] == kakao_p0[0] == hyundai_p0[0] == 0
    assert kakao_p1[1] < kakao_p0[1] < hyundai_p0[1]

    # tier 1: 집계 카드
    assert _classify_drop_candidate("stock_추가관심종목", leaders, importance)[0] == 1
    assert _classify_drop_candidate("stock_증권사리포트", leaders, importance)[0] == 1

    # tier 2: AI 히든픽 부가 설명 (애널리스트 → 포인트 순)
    analyst = _classify_drop_candidate("ai_strategy_analyst", leaders, importance)
    points = _classify_drop_candidate("ai_strategy_points", leaders, importance)
    assert analyst[0] == points[0] == 2
    assert analyst[1] < points[1]

    # tier 3: 대형 주도주가 아닌 종목의 요약 전체
    assert _classify_drop_candidate("stock_카카오_summary", leaders, importance)[0] == 3
    hyundai_summary = _classify_drop_candidate("stock_현대차_summary", leaders, importance)
    kakao_summary = _classify_drop_candidate("stock_카카오_summary", leaders, importance)
    assert kakao_summary[1] < hyundai_summary[1], "importance가 낮은 종목의 요약이 먼저 빠져야 함"

    # tier 4: 대형 주도주의 멘션 페이지 — 다른 모든 티어(0~3)보다 나중에 빠져야 함
    leader_p1 = _classify_drop_candidate("stock_삼성전자_mention_01", leaders, importance)
    leader_p0 = _classify_drop_candidate("stock_삼성전자_mention_00", leaders, importance)
    assert leader_p1[0] == leader_p0[0] == 4
    assert leader_p1[0] > hyundai_summary[0], "주도주 멘션은 비주도주 요약보다도 나중에 빠져야 함"
    assert leader_p1[1] < leader_p0[1], "같은 주도주면 페이지 번호가 큰 쪽이 먼저"
    print("✅ _classify_drop_candidate: 티어/정렬 순서(비주도주 멘션→집계→AI 부가→비주도주 "
          "요약→주도주 멘션) 확인")


def test_classify_drop_candidate_protects_core_content():
    leaders = {"stock_삼성전자"}
    importance = {"stock_삼성전자": 0.9}
    protected_ids = [
        "hook_title", "mention_intro", "market_indicators",
        "stock_삼성전자_summary",  # 대형 주도주 요약은 삭제 금지
        "ai_strategy_core", "closing",
    ]
    for audio_id in protected_ids:
        assert _classify_drop_candidate(audio_id, leaders, importance) is None, \
            f"{audio_id}는 핵심 콘텐츠라 삭제 후보가 되면 안 됨"
    print("✅ _classify_drop_candidate: 훅/인트로/지표/주도주 요약/AI 핵심/클로징은 삭제 후보에서 제외")


def _pair(stem: str, duration: float) -> tuple:
    return (f"/tmp/frames/{stem}.png", f"/tmp/audio/{stem}.mp3", duration)


def _sample_sections():
    return [
        {"id": "stock_삼성전자", "stock_tier": "market_leader", "importance": 0.9},
        {"id": "stock_현대차", "importance": 0.5},
        {"id": "stock_카카오", "importance": 0.3},
    ]


def test_trim_to_fit_budget_noop_when_already_fits():
    pairs = [_pair("10_삼성전자_1_summary", 80.0), _pair("99_closing", 20.0)]
    result = trim_to_fit_budget(pairs, _sample_sections(), target_max=200.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    assert result == pairs, "이미 목표 안에 들어오면 그대로 반환해야 함(불필요한 삭제 없음)"
    print("✅ trim_to_fit_budget: 이미 목표 길이 안이면 아무것도 빼지 않음")


def test_trim_to_fit_budget_drops_by_priority_and_stops_once_it_fits():
    pairs = [
        _pair("10_삼성전자_1_summary", 80.0),
        _pair("10_삼성전자_3_mention_00", 30.0),
        _pair("10_삼성전자_3_mention_01", 25.0),
        _pair("11_현대차_1_summary", 60.0),
        _pair("11_현대차_3_mention_00", 20.0),
        _pair("12_카카오_1_summary", 50.0),
        _pair("12_카카오_3_mention_00", 15.0),
        _pair("12_카카오_3_mention_01", 10.0),
        _pair("90_extra_watchlist", 40.0),
        _pair("95_ai_strategy_1_core", 30.0),
        _pair("95_ai_strategy_2_points", 20.0),
        _pair("95_ai_strategy_3_analyst", 15.0),
        _pair("99_closing", 20.0),
        _pair("01_mention_intro", 15.0),  # 고정 매핑에 없는 스템 → 매핑 실패로 원문 그대로
    ]
    total_before = sum(d for _, _, d in pairs)
    assert total_before == 430.0

    result = trim_to_fit_budget(pairs, _sample_sections(), target_max=200.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)

    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 200.0, f"목표(200s) 안으로 줄어야 하는데 {total_after}s"
    # 핵심 콘텐츠(주도주 요약/멘션, 클로징, 매핑 안 되는 고정 프레임)는 끝까지 남아야 함
    for keep in ("10_삼성전자_1_summary", "10_삼성전자_3_mention_00", "10_삼성전자_3_mention_01",
                 "99_closing", "01_mention_intro"):
        assert keep in remaining_ids, f"핵심 콘텐츠 {keep}가 삭제되면 안 됨"
    # 가장 먼저 빠져야 할 것들(비주도주 멘션 전부, 집계 카드, AI 부가 설명)은 없어야 함
    for dropped in ("12_카카오_3_mention_00", "12_카카오_3_mention_01", "11_현대차_3_mention_00",
                    "90_extra_watchlist", "95_ai_strategy_2_points", "95_ai_strategy_3_analyst"):
        assert dropped not in remaining_ids, f"{dropped}는 우선순위상 먼저 빠졌어야 함"
    print(f"✅ trim_to_fit_budget: 우선순위대로 삭제하며 목표 길이({total_after:.0f}s ≤ 200s) 안으로 "
          f"줄이고 핵심 콘텐츠는 보존함")


def test_trim_to_fit_budget_touches_leader_mentions_only_as_last_resort():
    """0~3번 티어를 다 빼도 부족할 만큼 목표가 빡빡하면(target_max=150), 그때만
    대형 주도주의 멘션(4번 티어)까지 빠지고, 주도주 요약/AI 핵심/클로징/매핑 안
    되는 고정 프레임은 그래도 끝까지 남아야 한다."""
    pairs = [
        _pair("10_삼성전자_1_summary", 80.0),
        _pair("10_삼성전자_3_mention_00", 30.0),
        _pair("10_삼성전자_3_mention_01", 25.0),
        _pair("11_현대차_1_summary", 60.0),
        _pair("11_현대차_3_mention_00", 20.0),
        _pair("12_카카오_1_summary", 50.0),
        _pair("12_카카오_3_mention_00", 15.0),
        _pair("12_카카오_3_mention_01", 10.0),
        _pair("90_extra_watchlist", 40.0),
        _pair("95_ai_strategy_1_core", 30.0),
        _pair("95_ai_strategy_2_points", 20.0),
        _pair("95_ai_strategy_3_analyst", 15.0),
        _pair("99_closing", 20.0),
        _pair("01_mention_intro", 15.0),
    ]

    result = trim_to_fit_budget(pairs, _sample_sections(), target_max=150.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 150.0, f"목표(150s) 안으로 줄어야 하는데 {total_after}s"
    assert "10_삼성전자_3_mention_00" not in remaining_ids and \
           "10_삼성전자_3_mention_01" not in remaining_ids, \
           "이 정도로 빡빡한 목표에서는 주도주 멘션까지 빠져야 함(최후 수단)"
    for keep in ("10_삼성전자_1_summary", "95_ai_strategy_1_core", "99_closing", "01_mention_intro"):
        assert keep in remaining_ids, f"{keep}는 어떤 경우에도 삭제되면 안 됨"
    print(f"✅ trim_to_fit_budget: 다른 티어를 다 빼도 부족하면 최후 수단으로 주도주 "
          f"멘션까지 빼되({total_after:.0f}s ≤ 150s), 주도주 요약/AI 핵심/클로징은 보존함")


if __name__ == "__main__":
    test_trusts_measurement_when_close_to_expected()
    test_falls_back_to_expected_when_measurement_is_way_off()
    test_boundary_within_tolerance_is_trusted()
    test_boundary_beyond_tolerance_falls_back()
    test_zero_expected_duration_trusts_measurement()
    test_compute_bgm_bounds_basic()
    test_compute_bgm_bounds_scales_with_time_scale()
    test_compute_bgm_bounds_empty_pairs()
    test_compute_bgm_bounds_single_scene_outro_not_before_intro()
    test_target_duration_reads_from_config_schedule()
    test_fits_within_target_basic()
    test_classify_drop_candidate_tiers()
    test_classify_drop_candidate_protects_core_content()
    test_trim_to_fit_budget_noop_when_already_fits()
    test_trim_to_fit_budget_drops_by_priority_and_stops_once_it_fits()
    test_trim_to_fit_budget_touches_leader_mentions_only_as_last_resort()
    print("\n✅ generate_video 테스트 전체 통과")
