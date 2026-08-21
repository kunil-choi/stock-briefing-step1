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


def test_compose_scene_default_is_subtle_no_pan():
    """영상 모션그래픽 업그레이드(P0-1): 예전엔 ENABLE_KEN_BURNS=False(기본값)면
    zoompan을 아예 안 썼다(카드 텍스트가 확대/팬으로 잘려나가는 문제 때문).
    이제는 motion 기본값이 "subtle"이라 zoompan 자체는 항상 켜지지만, 팬이
    없고(중심 고정) 줌도 아주 미세해서(SUBTLE_ZOOM_MAX=1.02) 예전 문제(팬 중
    중요한 텍스트가 프레임 밖으로 밀려남)가 재발하지 않는다 — 그래서 zoompan
    유무가 아니라 "팬 없음 + 줌 상한이 photo보다 훨씬 작음"을 확인한다."""
    import assets.video_renderer as vr

    assert vr.ENABLE_KEN_BURNS is False, "기본값은 ENABLE_KEN_BURNS 비활성화여야 함"
    assert vr.MOTION_DISABLE is False, "기본값은 MOTION_DISABLE 비활성화여야 함"

    captured_cmds = []
    real_run = vr.subprocess.run

    def _spy_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return real_run(cmd, *args, **kwargs)

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_subtle.mp4")
        vr.subprocess.run = _spy_run
        result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0)
        vr.subprocess.run = real_run

        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        filter_arg = next(a for cmd in captured_cmds for a in cmd if "scale=" in a)
        assert "zoompan" in filter_arg, f"기본값(subtle)인데 zoompan 필터가 없음: {filter_arg}"
        assert f"{vr.SUBTLE_ZOOM_MAX}" in filter_arg, "subtle 줌 상한(1.02)이 필터에 없음"
        assert f"{vr.KEN_BURNS_ZOOM_MAX}" not in filter_arg, "기본값인데 photo 줌 상한(1.08)이 쓰임"
        assert "iw*0.5-" in filter_arg and "ih*0.5-" in filter_arg, "subtle은 팬 없이 중심 고정이어야 함"
        print("✅ compose_scene: 기본값(subtle)은 팬 없이 미세한 줌만 적용됨")
    finally:
        vr.subprocess.run = real_run
        shutil.rmtree(tmp_dir)


def test_compose_scene_motion_none_is_fully_static():
    """motion="none"을 명시하면(P1의 실패 폴백 경로 등) 예전처럼 zoompan을
    전혀 안 쓰는 완전 정지 화면으로 합성돼야 한다."""
    import assets.video_renderer as vr

    captured_cmds = []
    real_run = vr.subprocess.run

    def _spy_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return real_run(cmd, *args, **kwargs)

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_none.mp4")
        vr.subprocess.run = _spy_run
        result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0, motion="none")
        vr.subprocess.run = real_run

        assert result == out_path
        filter_arg = next(a for cmd in captured_cmds for a in cmd if "scale=" in a)
        assert "zoompan" not in filter_arg, f"motion='none'인데 zoompan 필터가 사용됨: {filter_arg}"
        print("✅ compose_scene: motion='none'은 zoompan 없이 완전 정지로 합성됨")
    finally:
        vr.subprocess.run = real_run
        shutil.rmtree(tmp_dir)


def test_compose_scene_motion_disable_killswitch_forces_static():
    """절대 규칙 7(킬스위치): MOTION_DISABLE=true면 motion="photo"를 명시해도
    무조건 완전 정지로 렌더링돼야 한다."""
    import assets.video_renderer as vr

    captured_cmds = []
    real_run = vr.subprocess.run

    def _spy_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return real_run(cmd, *args, **kwargs)

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_killswitch.mp4")

        vr.MOTION_DISABLE = True
        try:
            vr.subprocess.run = _spy_run
            result = renderer.compose_scene(frame1, audio, out_path, duration=2.0,
                                             scene_index=0, motion="photo")
            vr.subprocess.run = real_run
        finally:
            vr.MOTION_DISABLE = False

        assert result == out_path
        filter_arg = next(a for cmd in captured_cmds for a in cmd if "scale=" in a)
        assert "zoompan" not in filter_arg, f"MOTION_DISABLE=true인데 zoompan이 사용됨: {filter_arg}"
        print("✅ compose_scene: MOTION_DISABLE=true 킬스위치가 motion 인자를 무시하고 완전 정지 강제함")
    finally:
        vr.subprocess.run = real_run
        shutil.rmtree(tmp_dir)


def test_compose_scene_ken_burns_when_explicitly_enabled():
    """하위호환: 호출부가 motion을 명시하지 않았는데(기본값 "subtle")
    ENABLE_KEN_BURNS=True가 이미 켜져 있으면, 이 레거시 스위치를 무력화하지
    않고 기존 "photo"(줌+팬) 강도로 승격해야 한다."""
    import assets.video_renderer as vr

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, _, audio = _make_test_assets(tmp_dir)
        renderer = vr.FFmpegVideoRenderer(width=640, height=360)
        out_path = os.path.join(tmp_dir, "scene_kb.mp4")

        captured_cmds = []
        real_run = vr.subprocess.run

        def _spy_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            return real_run(cmd, *args, **kwargs)

        vr.ENABLE_KEN_BURNS = True
        try:
            vr.subprocess.run = _spy_run
            result = renderer.compose_scene(frame1, audio, out_path, duration=2.0, scene_index=0)
            vr.subprocess.run = real_run
        finally:
            vr.ENABLE_KEN_BURNS = False

        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        dur = _probe_duration(out_path)
        assert abs(dur - 2.0) < 0.2
        filter_arg = next(a for cmd in captured_cmds for a in cmd if "scale=" in a)
        assert f"{vr.KEN_BURNS_ZOOM_MAX}" in filter_arg, "ENABLE_KEN_BURNS=True인데 photo 줌 상한(1.08)이 안 쓰임"
        print(f"✅ compose_scene: ENABLE_KEN_BURNS=True로 켜면 photo(줌+팬)로 승격됨 ({dur:.2f}초)")
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


def test_transition_is_unified_slideleft():
    """전환 효과는 slideleft(기존 화면이 왼쪽으로 빠지고 새 화면이 오른쪽에서
    들어옴) 하나로 통일돼야 한다(사용자 요청 — 예전엔 fade/slideleft/slideright를
    장면마다 번갈아 써서 산만했다). scene_index가 몇이든 항상 같은 종류가
    나와야 한다."""
    from assets.video_renderer import _TRANSITION_CYCLE

    assert _TRANSITION_CYCLE == ["slideleft"]
    for scene_index in range(5):
        assert _TRANSITION_CYCLE[scene_index % len(_TRANSITION_CYCLE)] == "slideleft"
    print("✅ 전환 종류: scene_index와 무관하게 항상 slideleft로 통일됨")


def test_build_transition_explicit_kind_overrides_cycle():
    """P0-2(전환 위계): kind를 명시하면 _TRANSITION_CYCLE 순환 대신 그 값을
    그대로 써야 한다(호출부가 섹션 경계에서 wipeleft를 강제할 수 있어야 함).
    kind를 안 넘기면(None) 기존 순환 선택 동작이 유지돼야 한다."""
    from assets.video_renderer import FFmpegVideoRenderer

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1, frame2, _ = _make_test_assets(tmp_dir)
        renderer = FFmpegVideoRenderer(width=640, height=360)

        out_path = os.path.join(tmp_dir, "trans_wipe.mp4")
        result = renderer.build_transition(frame1, frame2, out_path, scene_index=0, kind="wipeleft")
        assert result == out_path
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        dur = _probe_duration(out_path)
        assert abs(dur - 0.4) < 0.15
        print("✅ build_transition: kind='wipeleft' 명시 시 섹션 경계 전환이 정상 생성됨")
    finally:
        shutil.rmtree(tmp_dir)


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


def _probe_audio_stream(path: str) -> tuple:
    """ffprobe 없이 `ffmpeg -i`의 stderr에서 오디오 스트림의 (샘플레이트, 채널 수)를
    직접 파싱한다. 예: "Audio: aac (LC)..., 44100 Hz, stereo, ..." → (44100, 2)."""
    result = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
    m = re.search(r"Audio:.*?(\d+) Hz, (mono|stereo)", result.stderr)
    assert m, f"ffmpeg -i 출력에서 오디오 스트림 정보를 찾지 못함: {path}\n{result.stderr[-500:]}"
    channels = 1 if m.group(2) == "mono" else 2
    return int(m.group(1)), channels


def test_compose_scene_normalizes_audio_format_regardless_of_source():
    """사용자 피드백(2026-08-13): 특정 장면 전환 직후부터 배경에 "지지직"
    잡음이 깔리는 문제가 있었다 — TTS provider가 만든 나레이션 mp3의 원본
    샘플레이트가 build_transition()/_static_hold()가 고정으로 쓰는
    44100Hz/스테레오 무음 오디오와 달라, concat()의 ffmpeg concat 데뮤서가
    전환 경계에서 오디오 디코딩을 어긋나게 시작하는 것으로 재현·확인됨.
    나레이션 오디오가 (OpenAI TTS 등에서 흔한) 24000Hz/모노처럼 다른 포맷이어도
    compose_scene()이 항상 AUDIO_SAMPLE_RATE/AUDIO_CHANNELS로 강제 통일하는지
    확인한다."""
    from assets.video_renderer import FFmpegVideoRenderer, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS

    tmp_dir = tempfile.mkdtemp()
    try:
        frame1 = os.path.join(tmp_dir, "frame1.png")
        odd_audio = os.path.join(tmp_dir, "odd_audio.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=640x360",
                         "-frames:v", "1", frame1], capture_output=True, check=True)
        # OpenAI TTS 등에서 흔한 24000Hz/모노 나레이션 오디오를 재현한다(전환
        # 클립이 쓰는 44100Hz/스테레오와 의도적으로 다르게).
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                         "-ar", "24000", "-ac", "1", "-q:a", "9", odd_audio],
                        capture_output=True, check=True)

        renderer = FFmpegVideoRenderer(width=640, height=360)
        scene_out = os.path.join(tmp_dir, "scene0.mp4")
        assert renderer.compose_scene(frame1, odd_audio, scene_out, duration=2.0, scene_index=0)

        trans_out = os.path.join(tmp_dir, "trans0.mp4")
        assert renderer.build_transition(frame1, frame1, trans_out, scene_index=0)

        scene_sr, scene_ch = _probe_audio_stream(scene_out)
        trans_sr, trans_ch = _probe_audio_stream(trans_out)
        assert scene_sr == AUDIO_SAMPLE_RATE and scene_ch == AUDIO_CHANNELS, (
            f"compose_scene 출력 오디오 포맷이 통일되지 않음: {scene_sr}Hz/{scene_ch}ch"
        )
        assert trans_sr == AUDIO_SAMPLE_RATE and trans_ch == AUDIO_CHANNELS, (
            f"build_transition 출력 오디오 포맷이 통일되지 않음: {trans_sr}Hz/{trans_ch}ch"
        )
        assert (scene_sr, scene_ch) == (trans_sr, trans_ch), (
            "장면 클립과 전환 클립의 오디오 포맷이 서로 다름 — concat 경계에서 "
            "디코딩 아티팩트(잡음)를 유발할 수 있음"
        )
        print(f"✅ compose_scene/build_transition: 원본 나레이션이 24000Hz/모노여도 "
              f"출력은 항상 {AUDIO_SAMPLE_RATE}Hz/{AUDIO_CHANNELS}ch로 통일됨")
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
    test_compose_scene_default_is_subtle_no_pan()
    test_compose_scene_motion_none_is_fully_static()
    test_compose_scene_motion_disable_killswitch_forces_static()
    test_compose_scene_ken_burns_when_explicitly_enabled()
    test_build_transition_duration_is_fixed()
    test_transition_is_unified_slideleft()
    test_build_transition_explicit_kind_overrides_cycle()
    test_concat_scenes_and_transition()
    test_compose_scene_normalizes_audio_format_regardless_of_source()
    test_build_transition_never_returns_none_even_on_bad_input()
    print("\n✅ video_renderer 테스트 전체 통과")
