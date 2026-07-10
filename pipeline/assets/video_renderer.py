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
KEN_BURNS_ZOOM_STEP = 0.0015
TRANSITION_DURATION = 0.4

# Ken Burns(장면 내 확대/팬) 효과 스위치. 현재 이미지 소스가 연합뉴스/KBS
# 정식 API가 아니라 텍스트 카드 위주(공개 검색 폴백/섹터 대체 이미지)라, 화면
# 확대·이동 중 카드의 중요한 텍스트가 프레임 밖으로 밀려나는 역효과가
# 있었다(사용자 피드백). 실제 보도사진처럼 여백이 넉넉한 편집용 이미지를
# 안정적으로 확보하게 되면(Phase C의 YONHAP_API_KEY/KBS_API_KEY 정식 연동)
# 다시 켤 수 있도록 코드는 그대로 두고 기본값만 꺼둔다.
ENABLE_KEN_BURNS = os.environ.get("ENABLE_KEN_BURNS", "false").strip().lower() == "true"

# 장면마다 살짝 다른 팬(pan) 방향을 순환시켜 매번 같은 방식으로 확대되는 단조로움을
# 피한다. (cx, cy)는 줌 중심을 이미지의 어느 지점(0~1 비율)에 둘지를 뜻한다.
_PAN_CYCLE = [(0.5, 0.5), (0.3, 0.4), (0.7, 0.4), (0.5, 0.65)]

# crossfade(fade)와 push(slideleft/slideright)를 번갈아 사용해 화면 전환에
# 변화를 준다. 이름은 모두 ffmpeg xfade 필터가 기본 제공하는 transition 값이다.
_TRANSITION_CYCLE = ["fade", "slideleft", "fade", "slideright"]


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
                       duration: float, scene_index: int = 0) -> Optional[str]:
        """정지 이미지 + 오디오를 Ken Burns 효과가 적용된 영상 클립으로 만든다.
        실패하면 None을 반환한다(호출부가 해당 장면을 건너뛸 수 있도록)."""
        ...

    @abstractmethod
    def build_transition(self, from_frame: str, to_frame: str, out_path: str,
                          scene_index: int = 0,
                          duration: float = TRANSITION_DURATION) -> str:
        """두 장면 사이에 삽입할 짧은(무음) 전환 클립을 만든다. 항상 정확히
        `duration`초짜리 클립 경로를 반환한다(실패해도 정지 프레임 홀드로 대체)."""
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
                       duration: float, scene_index: int = 0) -> Optional[str]:
        if duration <= 0:
            duration = 3.0

        if ENABLE_KEN_BURNS:
            frames = max(1, int(round(duration * self.fps)))
            cx, cy = _PAN_CYCLE[scene_index % len(_PAN_CYCLE)]
            zoom_expr = f"min(zoom+{KEN_BURNS_ZOOM_STEP},{KEN_BURNS_ZOOM_MAX})"
            x_expr = f"iw*{cx}-(iw/zoom/2)"
            y_expr = f"ih*{cy}-(ih/zoom/2)"
            vf = (
                f"scale=3840:-2,"
                f"zoompan=z='{zoom_expr}':d={frames}:x='{x_expr}':y='{y_expr}':"
                f"s={self.width}x{self.height}:fps={self.fps}"
            )
            label = "Ken Burns"
        else:
            # 정지 화면: 카드 텍스트가 확대/팬으로 잘려나가는 문제를 피하기
            # 위해 원본 비율을 유지한 채 캔버스에 맞추기만 한다.
            vf = f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={self.fps}"
            label = "정지 화면"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-filter_complex", f"[0:v]{vf}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
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
            "-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=44100:cl=stereo",
            "-loop", "1", "-t", f"{duration}", "-i", frame_path,
            "-vf", f"scale={self.width}:{self.height},setsar=1",
            "-map", "1:v", "-map", "0:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            out_path,
        ]
        return _run(cmd, f"전환 대체(정지 홀드) ({os.path.basename(out_path)})")

    def build_transition(self, from_frame: str, to_frame: str, out_path: str,
                          scene_index: int = 0,
                          duration: float = TRANSITION_DURATION) -> str:
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
            "-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", vf,
            "-map", "[vout]", "-map", "2:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
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
            "-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
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
