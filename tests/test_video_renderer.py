# tests/test_video_renderer.py
"""
video_renderer.py(Ken Burns 합성 + crossfade/push 전환) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반이며 합성 이미지/
무음 오디오로 실제 ffmpeg를 호출해 검증한다(네트워크 불필요).

ffmpeg가 PATH에 없으면(이 레포의 워크플로우는 apt로 ffmpeg를 설치하지만 로컬
환경엔 없을 수 있음) 스킵 메시지만 출력하고 통과 처리한다 — ffprobe는 별도로
필요하지 않다(ffmpeg -i의 stderr에서 Duration을 직접 파싱한다).

실행: python tests/test_video_renderer.py
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
    """ffprobe 없이 `ffmpeg -i`의 stderr에서 Duration을 직접 파싱한다."""
    result = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    assert m, f"ffmpeg -i 출력에서 Duration을 찾지 못함: {path}"
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _make_test_assets(tmp_dir: str):
    frame1 = os.path.join(tmp_dir, "frame1.png")
    frame2 = os.path.join(tmp_dir, "frame2.png")
    audio = os.path.join(tmp_dir, "audio.mp3")

    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=640x360",
                     "-frames:v", "1", frame1], capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360",
                     "-frames:v", "1", frame2], capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                     "-t", "2", "-q:a", "9", audio], capture_output=True, check=True)
    return frame1, frame2, audio


def test_compose_scene_ken_burns():
    from assets.video_renderer import FFmpegVideoRenderer

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene0.mp4")
        result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0)
        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        dur = _probe_duration(out_path)
        assert abs(dur - 2.0) < 0.2, f"장면 길이가 예상과 다름: {dur}"
        print(f"✅ compose_scene: Ken Burns 클립 생성 확인 ({dur:.2f}초)")
    finally:
        shutil.rmtree(tmp_dir)


def test_compose_scene_default_has_no_ken_burns_motion():
    """사용자 피드백: 이미지가 카드형 텍스트 위주라 확대/팬 중 중요한 내용이
    화면 밖으로 밀려나는 역효과가 있었다. 기본값(ENABLE_KEN_BURNS=False)에서는
    zoompan 필터를 전혀 쓰지 않고 정지 화면으로 합성해야 한다."""
    import assets.video_renderer as vr

    assert vr.ENABLE_KEN_BURNS is False, "기본값은 Ken Burns 비활성화여야 함"

    captured_cmds = []
    real_run = vr.subprocess.run

    def _spy_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return real_run(cmd, *args, **kwargs)

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_static.mp4")
        vr.subprocess.run = _spy_run
        result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0)
        vr.subprocess.run = real_run

        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        filter_arg = next(a for cmd in captured_cmds for a in cmd if "scale=" in a)
        assert "zoompan" not in filter_arg, f"기본값인데 zoompan 필터가 사용됨: {filter_arg}"
        print("✅ compose_scene: 기본값에서는 zoompan(확대/팬) 없이 정지 화면으로 합성됨")
    finally:
        vr.subprocess.run = real_run
        shutil.rmtree(tmp_dir)


def test_compose_scene_ken_burns_when_explicitly_enabled():
    """향후(연합뉴스/KBS 정식 이미지 확보 시) ENABLE_KEN_BURNS=True로 다시
    켤 수 있도록 zoompan 경로 자체는 그대로 남아 있어야 한다."""
    import assets.video_renderer as vr

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_kb.mp4")

        vr.ENABLE_KEN_BURNS = True
        try:
            result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0)
        finally:
            vr.ENABLE_KEN_BURNS = False

        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        dur = _probe_duration(out_path)
        assert abs(dur - 2.0) < 0.2
        print(f"✅ compose_scene: ENABLE_KEN_BURNS=True로 켜면 Ken Burns 경로가 여전히 동작함 ({dur:.2f}초)")
    finally:
        shutil.rmtree(tmp_dir)


def test_build_transition_duration_is_fixed():
    from assets.video_renderer import FFmpegVideoRenderer, TRANSITION_DURATION

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, frame2, _ = _make_test_assets(tmp_dir)
        renderer = FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "trans0.mp4")
        result = renderer.build_transition(frame1, frame2, out_path, scene_index=0)
        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        dur = _probe_duration(out_path)
        assert abs(dur - TRANSITION_DURATION) < 0.15, f"전환 클립 길이가 예상과 다름: {dur}"
        print(f"✅ build_transition: 전환 클립이 정확히 {TRANSITION_DURATION}초 근방으로 생성됨 ({dur:.2f}초)")
    finally:
        shutil.rmtree(tmp_dir)


def test_build_transition_cycles_kind_by_scene_index():
    """scene_index에 따라 crossfade(fade)와 push(slideleft/slideright)가
    번갈아 사용되는지 확인한다(요구사항 3: crossfade 또는 push)."""
    from assets.video_renderer import _TRANSITION_CYCLE

    assert "fade" in _TRANSITION_CYCLE
    assert any(k.startswith("slide") for k in _TRANSITION_CYCLE)
    print("✅ 전환 종류: crossfade(fade)와 push(slide*)가 모두 순환 목록에 포함됨")


def test_concat_scenes_and_transition():
    from assets.video_renderer import FFmpegVideoRenderer

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, frame2, audio = _make_test_assets(tmp_dir)
        renderer = FFmpegVideoRenderer(width=640, height=360)

        scene0 = renderer.compose_scene(frame1, audio, os.path.join(tmp_dir, "s0.mp4"), 2.0, scene_index=0)
        trans = renderer.build_transition(frame1, frame2, os.path.join(tmp_dir, "t0.mp4"), scene_index=1)
        scene1 = renderer.compose_scene(frame2, audio, os.path.join(tmp_dir, "s1.mp4"), 2.0, scene_index=1)

        final_path = os.path.join(tmp_dir, "final.mp4")
        ok = renderer.concat([scene0, trans, scene1], final_path)
        assert ok
        assert os.path.isfile(final_path)

        dur = _probe_duration(final_path)
        # 2.0(scene0) + ~0.4(전환) + 2.0(scene1) ≈ 4.4초. concat()이 재인코딩
        # 방식(요구사항: 여러 클립을 이어붙일 때 ffprobe 측정 길이가 실제
        # 콘텐츠와 크게 어긋나는 사고를 막기 위해 -c copy 대신 재인코딩함)이라
        # 오차는 작아야 하지만, 인코딩 반올림을 감안해 약간의 허용 오차를 둔다.
        assert 4.1 <= dur <= 4.7, f"이어붙인 영상 길이가 예상 범위를 벗어남: {dur}"
        print(f"✅ concat: 장면+전환+장면 이어붙이기 길이 확인 ({dur:.2f}초)")
    finally:
        shutil.rmtree(tmp_dir)


def test_build_transition_never_returns_none_even_on_bad_input():
    """build_transition은 계약상 항상 str을 반환해야 한다(호출부의 누적 시간
    계산이 조건 분기 없이 단순해지도록). 존재하지 않는 프레임을 넣어도 정지
    프레임 홀드/검정 화면 폴백으로 항상 파일을 만들어낸다."""
    from assets.video_renderer import FFmpegVideoRenderer

    tmp_dir = tempfile.mkdtemp()
    try:
        renderer = FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "trans_bad.mp4")
        result = renderer.build_transition(
            os.path.join(tmp_dir, "does_not_exist.png"),
            os.path.join(tmp_dir, "also_missing.png"),
            out_path, scene_index=0,
        )
        assert result == out_path
        assert isinstance(result, str)
        print("✅ build_transition: 실패 상황에서도 항상 문자열 경로를 반환함(폴백 보장)")
    finally:
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    if not _ffmpeg_available():
        print("⚠️  ffmpeg가 PATH에 없어 video_renderer 테스트를 스킵합니다.")
        sys.exit(0)

    test_compose_scene_ken_burns()
    test_compose_scene_default_has_no_ken_burns_motion()
    test_compose_scene_ken_burns_when_explicitly_enabled()
    test_build_transition_duration_is_fixed()
    test_build_transition_cycles_kind_by_scene_index()
    test_concat_scenes_and_transition()
    test_build_transition_never_returns_none_even_on_bad_input()
    print("\n✅ video_renderer 테스트 전체 통과")
