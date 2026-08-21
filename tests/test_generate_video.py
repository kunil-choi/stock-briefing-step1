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
    _motion_for, _is_section_boundary, _motion_source_for,
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
    # 페이지 번호가 큰 쪽이 먼저(정렬키가 더 작아야 함). mention_rounds가
    # 비어 있으면(아직 아무것도 안 뺀 상태) 모든 종목이 라운드 0으로 동일.
    kakao_p1 = _classify_drop_candidate("stock_카카오_mention_01", leaders, importance, {})
    kakao_p0 = _classify_drop_candidate("stock_카카오_mention_00", leaders, importance, {})
    hyundai_p0 = _classify_drop_candidate("stock_현대차_mention_00", leaders, importance, {})
    assert kakao_p1[0] == kakao_p0[0] == hyundai_p0[0] == 0
    assert kakao_p1[1] < kakao_p0[1] < hyundai_p0[1]

    # 라운드로빈: 카카오가 이미 1개 빠진 상태(mention_rounds)면, 아직 하나도
    # 안 뺀 현대차의 멘션이 카카오의 다음 멘션보다 먼저 나와야 한다(importance는
    # 카카오가 더 낮지만, 라운드가 더 중요한 1순위 기준).
    rounds_after_one_kakao_drop = {"stock_카카오": 1}
    kakao_p0_round1 = _classify_drop_candidate("stock_카카오_mention_00", leaders, importance,
                                                rounds_after_one_kakao_drop)
    hyundai_p0_round0 = _classify_drop_candidate("stock_현대차_mention_00", leaders, importance,
                                                  rounds_after_one_kakao_drop)
    assert hyundai_p0_round0[1] < kakao_p0_round1[1], \
        "라운드로빈: 아직 안 빠진 종목이 이미 1개 빠진 종목보다 먼저 빠져야 함"

    # tier 1: AI 히든픽 부가 설명 (애널리스트 → 포인트 순)
    analyst = _classify_drop_candidate("ai_strategy_analyst", leaders, importance, {})
    points = _classify_drop_candidate("ai_strategy_points", leaders, importance, {})
    assert analyst[0] == points[0] == 1
    assert analyst[1] < points[1]

    # tier 2: 대형 주도주의 멘션 페이지 — 다른 모든 티어(0~1)보다 나중에 빠져야 함
    leader_p1 = _classify_drop_candidate("stock_삼성전자_mention_01", leaders, importance, {})
    leader_p0 = _classify_drop_candidate("stock_삼성전자_mention_00", leaders, importance, {})
    assert leader_p1[0] == leader_p0[0] == 2
    assert leader_p1[0] > points[0], "주도주 멘션은 AI 부가 설명보다도 나중에 빠져야 함"
    assert leader_p1[1] < leader_p0[1], "같은 주도주면 페이지 번호가 큰 쪽이 먼저"
    print("✅ _classify_drop_candidate: 티어/정렬 순서(비주도주 멘션→AI 부가→주도주 멘션) "
          "+ 멘션 라운드로빈 확인")


def test_classify_drop_candidate_protects_core_content():
    """종목 개수를 줄이지 않는다는 원칙 — 개별 종목 요약(주도주/비주도주 모두)과
    관심종목/증권사 리포트 집계 카드는 어떤 경우에도 삭제 후보가 되면 안 된다."""
    leaders = {"stock_삼성전자"}
    importance = {"stock_삼성전자": 0.9, "stock_현대차": 0.5}
    protected_ids = [
        "hook_title", "mention_intro", "market_indicators",
        "stock_삼성전자_summary",   # 대형 주도주 요약
        "stock_현대차_summary",     # 비주도주 요약도 보호(종목 개수 유지 원칙)
        "stock_추가관심종목",       # 관심종목 집계 카드
        "stock_증권사리포트",       # 증권사 리포트 집계 카드
        "ai_strategy_core", "closing",
    ]
    for audio_id in protected_ids:
        assert _classify_drop_candidate(audio_id, leaders, importance, {}) is None, \
            f"{audio_id}는 핵심 콘텐츠라 삭제 후보가 되면 안 됨"
    print("✅ _classify_drop_candidate: 훅/인트로/지표/종목 요약(전체)/집계 카드/AI 핵심/"
          "클로징은 삭제 후보에서 제외(종목 개수 유지 원칙)")


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


def _sample_pairs():
    """모든 트림 통합 테스트가 공유하는 기준 시나리오. 총 430s, 삭제 가능한
    분량은 135s(0번 티어 45s + 1번 35s + 2번 55s)뿐 — 개별 종목 요약(80+60+50)
    /관심종목 집계 카드(40)/AI 핵심(30)/클로징(20)/매핑 안 되는 고정 프레임(15)
    합 295s는 어떤 target_max에도 항상 남아야 한다."""
    return [
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


_PROTECTED_STEMS = (
    "10_삼성전자_1_summary", "11_현대차_1_summary", "12_카카오_1_summary",
    "90_extra_watchlist", "95_ai_strategy_1_core", "99_closing", "01_mention_intro",
)


def test_trim_to_fit_budget_partial_tier0_only():
    """살짝만 넘칠 때(30s만 빼면 됨)는 0번 티어(비주도주 멘션) 일부만 빠지고,
    종목 요약/집계 카드/AI 핵심/주도주 멘션은 전혀 건드리지 않아야 한다."""
    pairs = _sample_pairs()
    assert sum(d for _, _, d in pairs) == 430.0

    result = trim_to_fit_budget(pairs, _sample_sections(), target_max=400.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 400.0, f"목표(400s) 안으로 줄어야 하는데 {total_after}s"
    for keep in _PROTECTED_STEMS + ("10_삼성전자_3_mention_00", "10_삼성전자_3_mention_01",
                                     "12_카카오_3_mention_00"):
        assert keep in remaining_ids, f"{keep}는 이 정도로 살짝 넘칠 땐 안 빠져야 함"
    for dropped in ("11_현대차_3_mention_00", "12_카카오_3_mention_01"):
        assert dropped not in remaining_ids, f"{dropped}는 0번 티어 라운드로빈으로 빠졌어야 함"
    print(f"✅ trim_to_fit_budget: 살짝 초과({total_after:.0f}s ≤ 400s)면 0번 티어(비주도주 "
          f"멘션) 일부만 라운드로빈으로 빠지고 종목 요약/집계 카드는 그대로 보존")


def test_trim_to_fit_budget_exhausts_tier0_then_tier1():
    """0번 티어(비주도주 멘션 45s)를 다 빼도 부족하면 1번 티어(AI 부가 설명)까지
    빠지지만, 종목 요약/집계 카드/주도주 멘션은 여전히 보존돼야 한다."""
    result = trim_to_fit_budget(_sample_pairs(), _sample_sections(), target_max=350.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 350.0, f"목표(350s) 안으로 줄어야 하는데 {total_after}s"
    for keep in _PROTECTED_STEMS + ("10_삼성전자_3_mention_00", "10_삼성전자_3_mention_01"):
        assert keep in remaining_ids, f"{keep}는 종목 요약/주도주 멘션이라 보존돼야 함"
    for dropped in ("11_현대차_3_mention_00", "12_카카오_3_mention_00", "12_카카오_3_mention_01",
                    "95_ai_strategy_2_points", "95_ai_strategy_3_analyst"):
        assert dropped not in remaining_ids, f"{dropped}는 0~1번 티어라 다 빠졌어야 함"
    print(f"✅ trim_to_fit_budget: 0번 티어를 다 빼도 부족하면 1번 티어(AI 부가 설명)까지 "
          f"빠지되({total_after:.0f}s ≤ 350s), 종목 요약/집계 카드/주도주 멘션은 보존")


def test_trim_to_fit_budget_touches_leader_mentions_only_as_last_resort():
    """0~1번 티어(비주도주 멘션 + AI 부가 설명, 총 80s)를 다 빼도 부족할 만큼
    목표가 빡빡하면(target_max=300, 135s 전부 삭제 필요) 그때만 대형 주도주의
    멘션(2번 티어)까지 빠지고, 종목 요약/집계 카드/AI 핵심/클로징은 그래도
    끝까지 남아야 한다(= 종목 개수는 항상 유지)."""
    result = trim_to_fit_budget(_sample_pairs(), _sample_sections(), target_max=300.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 300.0, f"목표(300s) 안으로 줄어야 하는데 {total_after}s"
    assert "10_삼성전자_3_mention_00" not in remaining_ids and \
           "10_삼성전자_3_mention_01" not in remaining_ids, \
           "이 정도로 빡빡한 목표에서는 주도주 멘션까지 빠져야 함(최후 수단)"
    for keep in _PROTECTED_STEMS:
        assert keep in remaining_ids, f"{keep}는 어떤 경우에도 삭제되면 안 됨(종목 개수 유지 원칙)"
    print(f"✅ trim_to_fit_budget: 0~1번 티어를 다 빼도 부족하면 최후 수단으로 주도주 "
          f"멘션까지 빼되({total_after:.0f}s ≤ 300s), 종목 요약/집계 카드/AI 핵심/클로징은 보존")


def test_trim_to_fit_budget_never_drops_below_protected_floor():
    """삭제 가능한 135s를 전부 빼도(잔여 295s) 목표(200s)를 못 맞추는 극단적인
    경우, 더 뺄 후보가 없다는 경고만 찍고 멈춘다 — 종목 요약/집계 카드 등
    보호 대상은 quality_gate가 최종 실패 처리하는 한이 있어도 자동으로는
    건드리지 않는다."""
    result = trim_to_fit_budget(_sample_pairs(), _sample_sections(), target_max=200.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after == 295.0, f"삭제 가능한 135s를 전부 빼고 남는 보호 콘텐츠 총합(295s)이어야 하는데 {total_after}s"
    assert total_after > 200.0, "이 케이스는 자동 삭제만으로는 목표를 못 맞추는 게 정상(quality_gate가 최종 처리)"
    assert remaining_ids == set(_PROTECTED_STEMS), "보호 콘텐츠만 남아야 함(종목 요약/집계 카드 포함)"
    print(f"✅ trim_to_fit_budget: 삭제 가능한 콘텐츠를 다 빼도 부족하면({total_after:.0f}s > 200s) "
          f"더 건드리지 않고 멈춤(종목 요약/집계 카드는 끝까지 보존)")


def test_trim_to_fit_budget_mentions_round_robin_across_stocks():
    """세 종목이 각각 멘션 2개씩 있고, 그중 3개만 빼면 목표를 맞출 수 있는
    상황에서, 한 종목의 멘션을 통째로(2개 다) 먼저 빼는 대신 세 종목 모두
    1개씩 먼저 빠져야 한다(사용자 요청: 특정 종목 패널 코멘트가 통째로
    사라지지 않게 라운드로빈으로 줄이기)."""
    sections = [
        {"id": "stock_가", "importance": 0.2},
        {"id": "stock_나", "importance": 0.5},
        {"id": "stock_다", "importance": 0.8},
    ]
    pairs = [
        _pair("99_closing", 100.0),  # 보호 대상, 절대 안 빠짐
        _pair("10_가_3_mention_00", 10.0),
        _pair("10_가_3_mention_01", 10.0),
        _pair("11_나_3_mention_00", 10.0),
        _pair("11_나_3_mention_01", 10.0),
        _pair("12_다_3_mention_00", 10.0),
        _pair("12_다_3_mention_01", 10.0),
    ]
    total_before = sum(d for _, _, d in pairs)
    assert total_before == 160.0

    # 30초만 빼면 되는 목표(정확히 멘션 3개 분량) — 라운드로빈이면 각 종목의
    # "01"(뒤 페이지) 하나씩만 빠지고, 종목별 "00" 페이지는 전부 남아야 한다.
    result = trim_to_fit_budget(pairs, sections, target_max=130.0,
                                 atempo_max_speed=1.0, transition_duration=0.0)
    remaining_ids = {os.path.splitext(os.path.basename(p[0]))[0] for p in result}
    total_after = sum(d for _, _, d in result)

    assert total_after <= 130.0
    for keep in ("99_closing", "10_가_3_mention_00", "11_나_3_mention_00", "12_다_3_mention_00"):
        assert keep in remaining_ids, f"{keep}는 라운드로빈이면 남아있어야 함(각 종목 1개씩만 빠짐)"
    for dropped in ("10_가_3_mention_01", "11_나_3_mention_01", "12_다_3_mention_01"):
        assert dropped not in remaining_ids, f"{dropped}는 라운드로빈 1순번으로 빠졌어야 함"
    print("✅ trim_to_fit_budget: 멘션 삭제가 한 종목을 통째로 비우지 않고 종목마다 "
          "1개씩 라운드로빈으로 빠짐 확인")


def test_motion_for_uses_background_image_presence():
    """P0-1: _motion_meta.json에 hasBackgroundImage=True인 프레임만 photo(줌+팬),
    나머지는 subtle(카드 텍스트 안전)로 판단해야 한다. 메타가 아예 없는
    프레임은(구버전 캐시 등) 안전한 기본값 subtle로 폴백한다(회귀 없음)."""
    frame_meta = {
        "02_sector": {"sectionType": "sector", "hasBackgroundImage": True},
        "10_삼성전자_1_summary": {"sectionType": "top_mover", "hasBackgroundImage": False},
    }
    assert _motion_for("02_sector", frame_meta) == "photo"
    assert _motion_for("10_삼성전자_1_summary", frame_meta) == "subtle"
    assert _motion_for("99_unknown_stem", frame_meta) == "subtle"
    print("✅ _motion_for: 배경 사진 실존 여부로 photo/subtle 판단, 메타 없으면 subtle 폴백")


def test_is_section_boundary_detects_section_type_change():
    """P0-2: 두 프레임의 section_type이 다르면 경계(wipeleft 대상)로 판단해야
    한다. 같은 섹션 내부거나 메타가 없으면 경계가 아니어야(slideleft 유지)
    한다."""
    frame_meta = {
        "01_market_00": {"sectionType": "market_summary", "hasBackgroundImage": False},
        "02_sector": {"sectionType": "sector", "hasBackgroundImage": True},
        "10_삼성전자_1_summary": {"sectionType": "top_mover", "hasBackgroundImage": False},
        "10_삼성전자_2_chart": {"sectionType": "top_mover", "hasBackgroundImage": False},
    }
    assert _is_section_boundary("01_market_00", "02_sector", frame_meta) is True
    assert _is_section_boundary("10_삼성전자_1_summary", "10_삼성전자_2_chart", frame_meta) is False
    assert _is_section_boundary("01_market_00", "99_unknown", frame_meta) is False
    print("✅ _is_section_boundary: section_type 변경 지점만 경계로 판단, 메타 없으면 False 폴백")


def test_motion_source_for_uses_motion_dir_when_present_and_nonempty():
    """P1-3/P1-4: frames/_motion/{stem}/에 실제 프레임(.png)이 있으면 그
    디렉토리를 쓰고, 없거나 비어 있으면 기존 정지 PNG 경로를 그대로 쓴다."""
    import tempfile
    import os as _os

    tmp_dir = tempfile.mkdtemp()
    try:
        frame_path = _os.path.join(tmp_dir, "02_sector.png")
        with open(frame_path, "w") as f:
            f.write("fake png")

        # 모션 디렉토리가 아예 없음
        assert _motion_source_for(frame_path, "02_sector") == frame_path

        # 모션 디렉토리는 있는데 비어 있음(캡처 실패 등)
        empty_motion = _os.path.join(tmp_dir, "_motion", "02_sector")
        _os.makedirs(empty_motion)
        assert _motion_source_for(frame_path, "02_sector") == frame_path

        # 모션 디렉토리에 실제 프레임이 있음
        with open(_os.path.join(empty_motion, "f_00000.png"), "w") as f:
            f.write("fake frame")
        assert _motion_source_for(frame_path, "02_sector") == empty_motion
        print("✅ _motion_source_for: 모션 프레임이 실제로 있을 때만 그 디렉토리를 씀")
    finally:
        import shutil
        shutil.rmtree(tmp_dir)


def test_motion_max_scenes_caps_scenes_using_frame_sequence():
    """성능 가드: MOTION_MAX_SCENES를 넘는 장면은 모션 프레임 디렉토리가
    있어도 정지 PNG로 합성해야 한다. 실제 ffmpeg를 부르지 않도록 렌더러를
    스파이로 바꿔 build_scene_clips()의 제어 흐름만 검증한다(이 파일의
    다른 테스트와 동일하게 ffmpeg 불필요)."""
    import tempfile
    import os as _os
    import shutil as _shutil
    import generate_video as gv

    tmp_dir = tempfile.mkdtemp()
    try:
        frame_audio_pairs = []
        for i in range(3):
            frame_path = _os.path.join(tmp_dir, f"scene{i}.png")
            with open(frame_path, "w") as f:
                f.write("fake")
            motion_dir = _os.path.join(tmp_dir, "_motion", f"scene{i}")
            _os.makedirs(motion_dir)
            with open(_os.path.join(motion_dir, "f_00000.png"), "w") as f:
                f.write("fake frame")
            frame_audio_pairs.append((frame_path, f"{frame_path}.mp3", 2.0))

        composed_with = []

        class _SpyRenderer:
            def build_transition(self, *a, **k):
                return _os.path.join(tmp_dir, "trans.mp4")

            def compose_scene(self, image_path, *a, **k):
                # build_scene_clips()가 성공한 장면의 모션 디렉토리를 인코딩
                # 직후 지우므로(성능 가드), 디렉토리였는지 여부는 호출 시점에
                # 바로 기록해야 한다(나중에 os.path.isdir()로 다시 확인하면
                # 이미 지워진 뒤라 항상 False가 나옴).
                composed_with.append((image_path, _os.path.isdir(image_path)))
                return _os.path.join(tmp_dir, "scene_out.mp4")

        real_renderer = gv._renderer
        real_cap = gv.MOTION_MAX_SCENES
        gv._renderer = _SpyRenderer()
        gv.MOTION_MAX_SCENES = 1
        try:
            gv.build_scene_clips(frame_audio_pairs, tmp_dir, frame_meta={})
        finally:
            gv._renderer = real_renderer
            gv.MOTION_MAX_SCENES = real_cap

        motion_used = [p for p, was_dir in composed_with if was_dir]
        static_used = [p for p, was_dir in composed_with if not was_dir]
        assert len(motion_used) == 1, f"MOTION_MAX_SCENES=1인데 모션 디렉토리를 {len(motion_used)}번 씀"
        assert len(static_used) == 2, f"나머지 2개 장면은 정지 PNG로 폴백해야 함: {static_used}"
        print("✅ MOTION_MAX_SCENES: 상한을 넘는 장면은 모션 디렉토리가 있어도 정지 PNG로 합성됨")
    finally:
        _shutil.rmtree(tmp_dir)


def test_motion_frames_dir_cleaned_up_after_successful_compose():
    """성능 가드: 장면 클립 합성이 성공하면 그 장면의 모션 프레임 디렉토리는
    바로 지워져야 한다(러너 디스크 용량 절약). 합성이 실패한 장면은
    호출부가 재시도할 수도 있으니 지우지 않는다."""
    import tempfile
    import os as _os
    import shutil as _shutil
    import generate_video as gv

    tmp_dir = tempfile.mkdtemp()
    try:
        frame_path = _os.path.join(tmp_dir, "scene0.png")
        with open(frame_path, "w") as f:
            f.write("fake")
        motion_dir = _os.path.join(tmp_dir, "_motion", "scene0")
        _os.makedirs(motion_dir)
        with open(_os.path.join(motion_dir, "f_00000.png"), "w") as f:
            f.write("fake frame")

        class _SpyRenderer:
            def build_transition(self, *a, **k):
                return _os.path.join(tmp_dir, "trans.mp4")

            def compose_scene(self, image_path, *a, **k):
                return _os.path.join(tmp_dir, "scene_out.mp4")

        real_renderer = gv._renderer
        gv._renderer = _SpyRenderer()
        try:
            gv.build_scene_clips([(frame_path, f"{frame_path}.mp3", 2.0)], tmp_dir, frame_meta={})
        finally:
            gv._renderer = real_renderer

        assert not _os.path.isdir(motion_dir), "합성 성공 후에도 모션 프레임 디렉토리가 안 지워짐"
        print("✅ 모션 프레임 디렉토리: 장면 합성 성공 후 바로 정리됨")
    finally:
        _shutil.rmtree(tmp_dir)


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
    test_trim_to_fit_budget_partial_tier0_only()
    test_trim_to_fit_budget_exhausts_tier0_then_tier1()
    test_trim_to_fit_budget_touches_leader_mentions_only_as_last_resort()
    test_trim_to_fit_budget_never_drops_below_protected_floor()
    test_trim_to_fit_budget_mentions_round_robin_across_stocks()
    test_motion_for_uses_background_image_presence()
    test_is_section_boundary_detects_section_type_change()
    test_motion_source_for_uses_motion_dir_when_present_and_nonempty()
    test_motion_max_scenes_caps_scenes_using_frame_sequence()
    test_motion_frames_dir_cleaned_up_after_successful_compose()
    print("\n✅ generate_video 테스트 전체 통과")
