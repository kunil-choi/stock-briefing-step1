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

from generate_video import resolve_merged_duration  # noqa: E402


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


if __name__ == "__main__":
    test_trusts_measurement_when_close_to_expected()
    test_falls_back_to_expected_when_measurement_is_way_off()
    test_boundary_within_tolerance_is_trusted()
    test_boundary_beyond_tolerance_falls_back()
    test_zero_expected_duration_trusts_measurement()
    print("\n✅ generate_video 테스트 전체 통과")
