# tests/test_audio_post.py
"""
audio_post.py(Phase H — atempo/loudnorm 후처리, BGM 사이드체인 덕킹, 과장 표현
탐지, audio_report.json 구조) 검증 스크립트. pytest 미사용, 다른 tests/*.py와
동일하게 순수 assert 기반이며 합성 오디오/영상으로 실제 ffmpeg를 호출해
검증한다(네트워크 불필요).

ffmpeg가 PATH에 없으면 스킵 메시지만 출력하고 통과 처리한다.

실행: python tests/test_audio_post.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _probe_duration(path: str) -> float:
    """ffprobe 없이 `ffmpeg -i`의 stderr에서 Duration을 직접 파싱한다(다른
    tests/*.py와 동일한 방식 — 로컬 환경에 ffprobe가 없을 수 있음)."""
    result = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    assert m, f"ffmpeg -i 출력에서 Duration을 찾지 못함: {path}"
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _make_test_tone(path: str, seconds: float = 10.0, freq: int = 440, volume: float = 0.05):
    """지정한 진폭(볼륨)의 사인파 톤을 만든다 — loudnorm 전/후 실측치가
    유의미하게 달라지도록 일부러 표준(-16 LUFS)보다 훨씬 낮은 볼륨으로 만든다."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={seconds}",
         "-af", f"volume={volume}",
         "-c:a", "libmp3lame", "-b:a", "192k", path],
        capture_output=True, check=True,
    )


def test_apply_post_processing_speed_and_loudness():
    from assets.audio_post import apply_post_processing, measure_duration, measure_loudness

    tmp_dir = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp_dir, "tone.mp3")
        out = os.path.join(tmp_dir, "processed.mp3")
        _make_test_tone(src, seconds=10.0, volume=0.05)

        before_dur = measure_duration(src)
        before_lufs = measure_loudness(src)
        assert before_dur > 9.5, f"원본 길이가 예상과 다름: {before_dur}"
        assert before_lufs is not None and before_lufs < -20, (
            f"조용한 톤인데 러프니스가 너무 높게 측정됨(측정 버그 의심): {before_lufs}"
        )

        speed = 1.1
        target_lufs = -16.0
        ok = apply_post_processing(src, out, speed=speed, target_lufs=target_lufs)
        assert ok and os.path.isfile(out) and os.path.getsize(out) > 0

        after_dur = measure_duration(out)
        after_lufs = measure_loudness(out)
        expected_dur = before_dur / speed
        assert abs(after_dur - expected_dur) < 0.5, (
            f"atempo={speed} 적용 후 길이가 예상과 다름: {after_dur} (기대: {expected_dur:.2f})"
        )
        assert after_lufs is not None and abs(after_lufs - target_lufs) < 1.0, (
            f"loudnorm 후 러프니스가 목표({target_lufs})와 크게 다름: {after_lufs}"
        )
        print(f"✅ apply_post_processing: {before_dur:.2f}s/{before_lufs:.1f}LUFS → "
              f"{after_dur:.2f}s/{after_lufs:.1f}LUFS (speed={speed}, target={target_lufs})")
    finally:
        shutil.rmtree(tmp_dir)


def test_apply_post_processing_no_speed_change_when_speed_is_one():
    from assets.audio_post import apply_post_processing, measure_duration

    tmp_dir = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp_dir, "tone.mp3")
        out = os.path.join(tmp_dir, "processed.mp3")
        _make_test_tone(src, seconds=5.0, volume=0.05)

        before_dur = measure_duration(src)
        ok = apply_post_processing(src, out, speed=1.0, target_lufs=-16.0)
        assert ok
        after_dur = measure_duration(out)
        assert abs(after_dur - before_dur) < 0.3, (
            f"speed=1.0인데 길이가 바뀜(atempo가 불필요하게 적용됨): {before_dur} → {after_dur}"
        )
        print(f"✅ apply_post_processing: speed=1.0일 때 길이 변화 없음 확인 ({after_dur:.2f}s)")
    finally:
        shutil.rmtree(tmp_dir)


def test_measure_duration_missing_file_returns_zero():
    from assets.audio_post import measure_duration

    dur = measure_duration("/nonexistent/path/does_not_exist.mp3")
    assert dur == 0.0
    print("✅ measure_duration: 존재하지 않는 파일은 0.0 반환")


def _make_test_video(path: str, seconds: float = 20.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=640x360:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
         "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True,
    )


def _make_test_bgm(path: str, seconds: float = 5.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=880:duration={seconds}",
         "-c:a", "libmp3lame", "-b:a", "192k", path],
        capture_output=True, check=True,
    )


def test_mix_bgm_with_ducking_produces_valid_output():
    from assets.audio_post import mix_bgm_with_ducking

    tmp_dir = tempfile.mkdtemp()
    try:
        video = os.path.join(tmp_dir, "video.mp4")
        bgm = os.path.join(tmp_dir, "bgm.mp3")
        out = os.path.join(tmp_dir, "mixed.mp4")
        _make_test_video(video, seconds=20.0)
        _make_test_bgm(bgm, seconds=5.0)

        ok = mix_bgm_with_ducking(
            video, bgm, out,
            intro_end=3.0, outro_start=17.0, total_duration=20.0,
            intro_volume=0.08, body_volume=0.045, outro_volume=0.08,
        )
        assert ok and os.path.isfile(out) and os.path.getsize(out) > 0

        dur = _probe_duration(out)
        assert abs(dur - 20.0) < 0.5, f"믹싱 후 길이가 원본과 크게 다름: {dur}"

        probe = subprocess.run(["ffmpeg", "-i", out], capture_output=True, text=True).stderr
        assert "Video:" in probe and "Audio:" in probe, "믹싱 결과에 비디오/오디오 스트림이 없음"
        print(f"✅ mix_bgm_with_ducking: 정상 믹싱, 길이 {dur:.2f}s, 비디오/오디오 스트림 확인")
    finally:
        shutil.rmtree(tmp_dir)


def test_mix_bgm_with_ducking_falls_back_when_bgm_missing():
    from assets.audio_post import mix_bgm_with_ducking

    tmp_dir = tempfile.mkdtemp()
    try:
        video = os.path.join(tmp_dir, "video.mp4")
        out = os.path.join(tmp_dir, "mixed.mp4")
        _make_test_video(video, seconds=3.0)

        ok = mix_bgm_with_ducking(
            video, os.path.join(tmp_dir, "no_such_bgm.mp3"), out,
            intro_end=1.0, outro_start=2.0, total_duration=3.0,
        )
        assert ok and os.path.isfile(out)
        # BGM 없으면 원본을 그대로 복사(폴백) — 기존 mix_bgm()과 동일한 계약
        assert os.path.getsize(out) == os.path.getsize(video)
        print("✅ mix_bgm_with_ducking: BGM 파일 없으면 원본을 그대로 복사(폴백)")
    finally:
        shutil.rmtree(tmp_dir)


def test_detect_advice_language_finds_hits_without_mutating_text():
    from assets.audio_post import detect_advice_language

    text = "이 종목은 매수 추천합니다. 비중 확대하세요. 실적은 견조합니다."
    hits = detect_advice_language(text)
    assert len(hits) >= 2, f"과장 표현 탐지 개수가 예상보다 적음: {hits}"
    assert any("매수" in h for h in hits)
    assert any("비중" in h for h in hits)
    print(f"✅ detect_advice_language: {len(hits)}개 탐지 — {hits}")


def test_detect_advice_language_clean_text_has_no_hits():
    from assets.audio_post import detect_advice_language

    text = "이 종목은 오늘 3% 상승했습니다. 외국인 매수세가 유입됐습니다."
    hits = detect_advice_language(text)
    assert hits == [], f"과장 표현이 없는 문장인데 탐지됨(오탐): {hits}"
    print("✅ detect_advice_language: 과장 표현이 없는 문장은 빈 목록 반환")


def test_detect_advice_language_empty_text():
    from assets.audio_post import detect_advice_language

    assert detect_advice_language("") == []
    assert detect_advice_language(None) == []
    print("✅ detect_advice_language: 빈 문자열/None은 빈 목록 반환")


def test_build_audio_report_structure():
    from assets.audio_post import build_audio_report

    entries = [
        {"id": "opening", "provider": "openai", "duration_seconds": 5.0,
         "speed": 1.0, "loudness_lufs": -16.1, "warnings": []},
        {"id": "stock_삼성전자_summary", "provider": "azure", "duration_seconds": 8.2,
         "speed": 1.05, "loudness_lufs": -15.8, "warnings": ["매수 추천합니다"]},
    ]
    report = build_audio_report(entries)
    assert report["total"] == 2
    assert report["providers_used"] == ["azure", "openai"]
    assert report["total_advice_language_warnings"] == 1
    assert report["entries"] == entries
    print(f"✅ build_audio_report: 구조 확인 — {report['providers_used']}, "
          f"경고 {report['total_advice_language_warnings']}건")


def test_build_audio_report_empty_entries():
    from assets.audio_post import build_audio_report

    report = build_audio_report([])
    assert report["total"] == 0
    assert report["providers_used"] == []
    assert report["total_advice_language_warnings"] == 0
    print("✅ build_audio_report: 빈 entries도 안전하게 처리")


if __name__ == "__main__":
    if not _ffmpeg_available():
        print("⚠️  ffmpeg가 PATH에 없어 audio_post 오디오/영상 테스트를 스킵합니다.")
        test_detect_advice_language_finds_hits_without_mutating_text()
        test_detect_advice_language_clean_text_has_no_hits()
        test_detect_advice_language_empty_text()
        test_build_audio_report_structure()
        test_build_audio_report_empty_entries()
        print("\n✅ audio_post 순수 로직 테스트 통과(ffmpeg 필요 테스트는 스킵됨)")
        sys.exit(0)

    test_apply_post_processing_speed_and_loudness()
    test_apply_post_processing_no_speed_change_when_speed_is_one()
    test_measure_duration_missing_file_returns_zero()
    test_mix_bgm_with_ducking_produces_valid_output()
    test_mix_bgm_with_ducking_falls_back_when_bgm_missing()
    test_detect_advice_language_finds_hits_without_mutating_text()
    test_detect_advice_language_clean_text_has_no_hits()
    test_detect_advice_language_empty_text()
    test_build_audio_report_structure()
    test_build_audio_report_empty_entries()
    print("\n✅ audio_post 테스트 전체 통과")
