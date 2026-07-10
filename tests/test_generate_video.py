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

from generate_video import resolve_merged_duration, compute_bgm_bounds, TARGET_MIN, TARGET_MAX, TARGET_IDEAL  # noqa: E402
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
    assert TARGET_MIN == 300.0 and TARGET_MAX == 480.0, (
        f"짧은 하이라이트 포맷(5~8분) 목표값이 아님: {TARGET_MIN}~{TARGET_MAX}"
    )
    assert TARGET_IDEAL == (TARGET_MIN + TARGET_MAX) / 2
    print(f"✅ TARGET_MIN/MAX/IDEAL이 config/schedule.yml을 그대로 반영함: "
          f"{TARGET_MIN}~{TARGET_MAX}s (IDEAL={TARGET_IDEAL})")


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
    print("\n✅ generate_video 테스트 전체 통과")
