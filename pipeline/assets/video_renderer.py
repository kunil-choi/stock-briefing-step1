# pipeline/assets/video_renderer.py
"""
장면(scene) 단위 영상 합성 계층. HTML→PNG 프레임 렌더링(render.py)과는 별개로,
'PNG+MP3 → Ken Burns 효과가 적용된 짧은 영상 클립'을 만들고, 클립 사이에
crossfade/push 전환 클립을 끼워 넣어 이어붙이는 역할을 한다.

VideoRenderer는 추상 인터페이스이고 FFmpegVideoRenderer가 현재 유일한 구현체다.
추후 Remotion 등 다른 엔진으로 바꿀 때는 이 인터페이스를 만족하는 새 클래스만
추가하면 되고, generate_video.py 등 호출부는 그대로 둘 수 있다.

★ 설계 노트 — 전환을 클립 사이에 "삽입"하지 "겹치지" 않는 이유
ffmpeg의 xfade로 인접한 두 클립을 실제로 겹쳐 붙이면(오디오까지 acrossfade로
겹치면) 전체 재생 시간이 전환 길이만큼 줄어든다. 이 레포의 generate_subtitles.py는
각 장면의 오디오 길이를 그대로 누적해 자막 타임라인을 만드는, 이미 촘촘하게
튜닝된 로직이라 그 위에 "겹침 보정(뺄셈)"을 얹으면 아주 쉽게 어긋난다. 대신
각 장면 클립은 원래 오디오 길이를 그대로 유지하고, 전환은 장면 사이에 별도의
짧은(오디오 없는) 세그먼트로 "삽입"한다 — 그러면 자막 타임라인은 전환 구간만큼
"더하기"만 하면 되므로(뺄셈 없음) 기존 로직을 거의 건드리지 않고 안전하게
확장할 수 있다. build_transition()은 항상 정확히 `duration`초짜리 클립을
반환하도록 보장한다(내부 xfade가 실패해도 정지 프레임 홀드로 대체) — 이 덕분에
"장면 N개 사이에 항상 N-1개의 고정 길이 전환이 들어간다"는 불변식이 always
성립해서, 호출부의 누적 시간 계산이 조건 분기 없이 단순해진다.
"""
import os
import subprocess
from abc import ABC, abstractmethod
from typing import List, Optional

FPS = 30
KEN_BURNS_ZOOM_MAX = 1.08
TRANSITION_DURATION = 0.4

# 장면(나레이션 mp3)의 파형이 정확히 0이 아닌 지점에서 시작/끝나는 경우가
# 대부분이라(TTS 합성 특성), 이전 장면 오디오가 뚝 끊기고 곧바로 다음 장면
# 오디오가 뚝 시작되는 지점에서 파형이 갑자기 튀는 클릭/팝 잡음이 난다 —
# 종목이 바뀔 때마다 매번 똑같은 짧은 "뿡" 소리가 들린다는 사용자 피드백과
# 일치한다(전환 구간 자체는 무음 클립이라 소리가 날 수 없고, 그 앞뒤로
# 붙는 실제 나레이션 클립의 시작/끝 경계가 원인). 아주 짧은 페이드(30ms)로
# 각 장면 오디오의 시작/끝을 0으로 부드럽게 만들면 내용은 들리지 않을
# 만큼 짧으면서 파형 불연속(클릭음)은 없앨 수 있다.
AUDIO_CLICK_FADE = 0.03

# 모든 장면/전환 클립의 오디오 스트림을 이 스펙으로 강제 통일한다(사용자
# 피드백, 2026-08-13 — 특정 장면 전환 지점 직후부터 배경에 "지지직" 하는
# 잡음이 깔리는 문제 재현·확인됨). compose_scene()의 오디오는 나레이션
# mp3(TTS provider가 만든 원본 샘플레이트·채널 그대로, provider마다 다를 수
# 있음)를 -ar/-ac 지정 없이 그대로 aac로 인코딩하는 반면, build_transition()/
# _static_hold()의 무음 오디오는 anullsrc=r=44100:cl=stereo로 고정돼 있었다
# — 이렇게 서로 다른 샘플레이트/채널 레이아웃의 클립들이 이어붙여지면
# concat()의 ffmpeg concat 데뮤서(모든 입력이 동일한 스트림 파라미터라고
# 가정함, https://ffmpeg.org/ffmpeg-formats.html#concat-1 참고)가 전환 경계
# 직후의 오디오 디코딩을 어긋나게 시작해, 그 뒤 장면 전체에 잡음이 깔리는
# 증상으로 이어질 수 있다. 모든 오디오 인코딩 지점에 동일한 -ar/-ac를 못박아
# 이 불일치 자체를 없앤다.
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 2

# Ken Burns(장면 내 확대/팬) 효과 스위치. 예전엔 이 값 하나로 전역 on/off
# 했었다 — 현재 이미지 소스가 연합뉴스/KBS 정식 API가 아니라 텍스트 카드
# 위주(공개 검색 폴백/섹터 대체 이미지)라, 화면 확대·이동 중 카드의 중요한
# 텍스트가 프레임 밖으로 밀려나는 역효과가 있었기 때문이다(사용자 피드백).
#
# ★ 영상 모션그래픽 업그레이드(Phase 0, P0-1): 이 판단 자체는 맞았지만
# 해법은 "끄는" 게 아니라 "슬라이드 종류별로 강도를 다르게" 주는 것이었다.
# compose_scene()의 motion 인자("none"/"subtle"/"photo")가 이제 그 역할을
# 대신한다 — "subtle"(줌만 살짝, 팬 없음)은 텍스트가 화면 밖으로 밀려날
# 여지가 없어 ENABLE_KEN_BURNS 값과 무관하게 항상 적용된다. 이 환경변수는
# 하위호환으로만 남긴다: 명시적으로 motion을 안 넘긴 호출부가
# ENABLE_KEN_BURNS=True를 설정해 뒀다면 "subtle" 대신 기존 "photo"(줌+팬)
# 강도로 승격시키는 데만 쓰인다(운영 중이던 설정을 조용히 무력화하지 않기
# 위함) — 완전 정지가 필요하면 이제 MOTION_DISABLE=true를 쓴다.
ENABLE_KEN_BURNS = os.environ.get("ENABLE_KEN_BURNS", "false").strip().lower() == "true"

# 킬스위치(절대 규칙 7): true면 motion 인자가 뭐든 전부 무시하고 완전 정지로
# 렌더링한다 — 모션 관련 기능에 문제가 생기면 배포 없이 즉시 예전 동작으로
# 되돌릴 수 있어야 한다.
MOTION_DISABLE = os.environ.get("MOTION_DISABLE", "false").strip().lower() == "true"

# "subtle" 모션(텍스트 카드 기본값)의 줌 상한. "photo"(KEN_BURNS_ZOOM_MAX=1.08)
# 보다 훨씬 미세해서 팬 없이 중심 고정으로만 써도 카드 텍스트가 프레임 밖으로
# 밀려날 걱정이 없다 — 그래서 배경 유무와 무관하게 기본값으로 항상 켜둔다.
SUBTLE_ZOOM_MAX = 1.02

# 장면마다 살짝 다른 팬(pan) 방향을 순환시켜 매번 같은 방식으로 확대되는 단조로움을
# 피한다. (cx, cy)는 줌 중심을 이미지의 어느 지점(0~1 비율)에 둘지를 뜻한다.
# "photo" 모션에서만 쓴다 — "subtle"은 팬 없이 항상 중심 고정.
_PAN_CYCLE = [(0.5, 0.5), (0.3, 0.4), (0.7, 0.4), (0.5, 0.65)]

# 화면 전환 기본값: slideleft(기존 화면이 왼쪽으로 빠지고 새 화면이 오른쪽에서
# 들어옴). 예전엔 fade/slideleft/slideright를 번갈아 써서 장면마다 전환
# 방향/방식이 달라 산만하다는 피드백이 있어 하나로 통일했다(사용자 요청).
# 이름은 ffmpeg xfade 필터가 기본 제공하는 transition 값이다.
#
# ★ P0-2(전환 위계): build_transition()이 이제 kind 인자를 명시적으로 받는다
# — 호출부(generate_video.py)가 섹션 경계 여부를 판정해 wipeleft(경계)/
# slideleft(섹션 내부)를 골라 넘긴다. kind를 안 넘기면(다른 호출부 하위호환)
# 이 리스트로 순환 선택하던 기존 동작을 그대로 유지한다.
_TRANSITION_CYCLE = ["slideleft"]


def _run(cmd: List[str], label: str) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ {label} 실패")
        print(result.stderr[-800:])
        return False
    return True


class VideoRenderer(ABC):
    """장면(이미지+오디오) → 영상 클립, 클립들 → 최종 이어붙이기 인터페이스.
    Remotion 등 다른 렌더링 엔진으로 교체하려면 이 인터페이스만 구현하면 된다."""

    @abstractmethod
    def compose_scene(self, image_path: str, audio_path: str, out_path: str,
                       duration: float, scene_index: int = 0,
                       motion: str = "subtle") -> Optional[str]:
        """정지 이미지 + 오디오를 모션 효과가 적용된 영상 클립으로 만든다.
        motion: "none"(완전 정지) / "subtle"(줌만 살짝, 텍스트 카드 기본값) /
        "photo"(줌+팬, 배경 사진 전용). 실패하면 None을 반환한다(호출부가
        해당 장면을 건너뛸 수 있도록)."""
        ...

    @abstractmethod
    def build_transition(self, from_frame: str, to_frame: str, out_path: str,
                          scene_index: int = 0,
                          duration: float = TRANSITION_DURATION,
                          kind: Optional[str] = None) -> str:
        """두 장면 사이에 삽입할 짧은(무음) 전환 클립을 만든다. 항상 정확히
        `duration`초짜리 클립 경로를 반환한다(실패해도 정지 프레임 홀드로 대체).
        kind를 안 넘기면 기존 순환 선택(_TRANSITION_CYCLE) 방식을 그대로 쓴다."""
        ...

    @abstractmethod
    def concat(self, clip_paths: List[str], out_path: str) -> bool:
        """이미 같은 코덱/해상도/fps로 인코딩된 클립들을 순서대로 이어붙인다."""
        ...


class FFmpegVideoRenderer(VideoRenderer):
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = FPS):
        self.width = width
        self.height = height
        self.fps = fps

    def compose_scene(self, image_path: str, audio_path: str, out_path: str,
                       duration: float, scene_index: int = 0,
                       motion: str = "subtle") -> Optional[str]:
        if duration <= 0:
            duration = 3.0

        if MOTION_DISABLE:
            motion = "none"
        elif motion == "subtle" and ENABLE_KEN_BURNS:
            # 하위호환: 호출부가 motion을 명시적으로 안 정했는데(기본값
            # "subtle") 운영 환경이 예전 스위치(ENABLE_KEN_BURNS=True)를 이미
            # 켜 뒀다면, 그 설정을 조용히 무력화하지 않고 기존 "photo"(줌+팬)
            # 강도로 승격한다.
            motion = "photo"

        if motion in ("subtle", "photo"):
            zoom_max = SUBTLE_ZOOM_MAX if motion == "subtle" else KEN_BURNS_ZOOM_MAX
            cx, cy = (0.5, 0.5) if motion == "subtle" else _PAN_CYCLE[scene_index % len(_PAN_CYCLE)]
            frames = max(1, int(round(duration * self.fps)))
            # 고정 스텝(예: 초당 일정량) 대신 장면 길이 전체에 걸쳐 딱
            # zoom_max까지 도달하도록 프레임 수로 나눈 스텝을 쓴다 — 고정
            # 스텝이면 긴 장면(예: 30초)에서 줌이 1~2초 만에 끝나버리고
            # 나머지는 그대로 멈춰 있어("subtle"의 취지인 은은한 드리프트가
            # 아니라 급정지로 보임) 오히려 부자연스럽다.
            zoom_step = (zoom_max - 1.0) / frames
            zoom_expr = f"min(zoom+{zoom_step:.6f},{zoom_max})"
            x_expr = f"iw*{cx}-(iw/zoom/2)"
            y_expr = f"ih*{cy}-(ih/zoom/2)"
            vf = (
                f"scale=3840:-2,"
                f"zoompan=z='{zoom_expr}':d={frames}:x='{x_expr}':y='{y_expr}':"
                f"s={self.width}x{self.height}:fps={self.fps}"
            )
            label = f"Ken Burns({motion})"
        else:
            # 정지 화면: 카드 텍스트가 확대/팬으로 잘려나가는 문제를 피하기
            # 위해 원본 비율을 유지한 채 캔버스에 맞추기만 한다.
            vf = f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={self.fps}"
            label = "정지 화면"

        fade = min(AUDIO_CLICK_FADE, duration / 2)
        fade_out_start = max(duration - fade, 0.0)
        af = f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={fade_out_start:.3f}:d={fade:.3f}"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS),
            "-pix_fmt", "yuv420p",
            "-shortest", "-t", f"{duration:.3f}",
            out_path,
        ]
        if not _run(cmd, f"장면 합성 ({os.path.basename(out_path)})"):
            return None
        print(f"  ✅ {os.path.basename(out_path)} ({duration:.1f}초, {label})")
        return out_path

    def _static_hold(self, frame_path: str, out_path: str, duration: float) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-t", f"{duration}",
            "-i", f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=stereo",
            "-loop", "1", "-t", f"{duration}", "-i", frame_path,
            "-vf", f"scale={self.width}:{self.height},setsar=1",
            "-map", "1:v", "-map", "0:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS),
            "-pix_fmt", "yuv420p",
            out_path,
        ]
        return _run(cmd, f"전환 대체(정지 홀드) ({os.path.basename(out_path)})")

    def build_transition(self, from_frame: str, to_frame: str, out_path: str,
                          scene_index: int = 0,
                          duration: float = TRANSITION_DURATION,
                          kind: Optional[str] = None) -> str:
        if kind is None:
            kind = _TRANSITION_CYCLE[scene_index % len(_TRANSITION_CYCLE)]
        vf = (
            f"[0:v]scale={self.width}:{self.height},fps={self.fps},setsar=1[v0];"
            f"[1:v]scale={self.width}:{self.height},fps={self.fps},setsar=1[v1];"
            f"[v0][v1]xfade=transition={kind}:duration={duration}:offset=0[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{duration}", "-i", from_frame,
            "-loop", "1", "-t", f"{duration}", "-i", to_frame,
            "-f", "lavfi", "-t", f"{duration}",
            "-i", f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=stereo",
            "-filter_complex", vf,
            "-map", "[vout]", "-map", "2:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS),
            "-pix_fmt", "yuv420p",
            out_path,
        ]
        if _run(cmd, f"전환 합성 ({kind}, {os.path.basename(out_path)})"):
            print(f"  ✅ {os.path.basename(out_path)} ({duration:.1f}초, {kind})")
            return out_path

        print(f"  ⚠️ xfade 전환 실패 → 정지 프레임 홀드로 대체 ({os.path.basename(out_path)})")
        if self._static_hold(to_frame, out_path, duration):
            return out_path

        # 정지 홀드마저 실패하는 극단적인 경우에도 duration초짜리 파일은 반드시
        # 반환해야 호출부의 누적 시간 계산이 깨지지 않는다 — 검정 화면으로 대체.
        print(f"  ⚠️ 정지 프레임 홀드도 실패 → 검정 화면으로 대체 ({os.path.basename(out_path)})")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-t", f"{duration}", "-i", f"color=c=black:s={self.width}x{self.height}:r={self.fps}",
            "-f", "lavfi", "-t", f"{duration}",
            "-i", f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=stereo",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS),
            "-pix_fmt", "yuv420p",
            out_path,
        ]
        _run(cmd, f"전환 최종 대체(검정 화면) ({os.path.basename(out_path)})")
        return out_path

    def concat(self, clip_paths: List[str], out_path: str) -> bool:
        # ★ 스트림 카피(-c copy)로 이어붙이지 않는다: zoompan/xfade로 각각 독립
        # 인코딩된 클립을 -c copy로 이어붙이면 컨테이너의 PTS/DTS가 깨끗하게
        # 이어지지 않아 ffprobe가 읽는 전체 길이가 실제 콘텐츠 길이와 크게
        # 어긋나는 문제가 있었다(실측: 여러 Ken Burns+전환 클립 63초 분량을
        # 이어붙였는데 32초로 잘못 측정됨 — 반대로 실제 운영에서는 755초가
        # 1300초로 부풀려 측정되기도 함). 이 잘못된 길이 때문에
        # generate_video.py의 adjust_to_target_duration()이 "영상이 길다"고
        # 오판해 배속을 줄여, 원래는 패딩돼야 할 짧은 영상이 오히려 더
        # 짧아지는 사고로 이어졌다. 재인코딩(+genpts로 타임스탬프 재생성)하면
        # 이 클래스의 버그 자체가 사라진다.
        list_file = out_path.replace(".mp4", "_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for v in clip_paths:
                f.write(f"file '{os.path.abspath(v)}'\n")
        cmd = [
            "ffmpeg", "-y", "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-r", str(self.fps),
            out_path,
        ]
        ok = _run(cmd, "장면 이어붙이기")
        try:
            os.remove(list_file)
        except OSError:
            pass
        if ok:
            print("  ✅ 이어붙이기 완료")
        return ok
