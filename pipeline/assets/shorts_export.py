# pipeline/assets/shorts_export.py
"""
"주도주 랭킹형" 플롯 — TOP1~3 종목을 30~45초 쇼츠 클립으로 export한다.

기존 종목 요약 카드 이미지 1장 + 그 종목의 요약 나레이션 오디오로
Phase D의 FFmpegVideoRenderer.compose_scene()(Ken Burns 포함)을 그대로
재사용해 만든다. 새로운 ffmpeg 로직을 추가하지 않는다.

★ 30~45초 제약: 종목 요약 나레이션은 보통 400자 이상(약 60~90초)이라 그대로
쓰면 쇼츠 목표 길이를 넘는다. 이 모듈은 오디오가 45초보다 길면 앞부분만
잘라 쓴다(compose_scene의 -shortest -t 옵션 재사용). 별도 요약(LLM) 없이
원본 나레이션의 도입부만 쓰는 것이므로, 문장이 중간에 끊길 수 있다는
한계가 있다(README에 명시).
"""
from typing import Optional

from .video_renderer import FFmpegVideoRenderer

SHORTS_MIN_SECONDS = 30.0
SHORTS_MAX_SECONDS = 45.0


def export_shorts_clip(frame_path: str, audio_path: str, out_path: str,
                        audio_duration: float, scene_index: int = 0,
                        renderer: Optional[FFmpegVideoRenderer] = None) -> Optional[str]:
    """종목 요약 카드 이미지 1장 + 요약 오디오로 30~45초 쇼츠 클립을 만든다.
    오디오가 목표 최대 길이보다 길면 앞부분만 사용하고, 짧으면 있는 그대로
    사용한다(무음 패딩으로 억지로 늘리지 않음 — 로그로만 경고)."""
    renderer = renderer or FFmpegVideoRenderer()
    duration = min(audio_duration, SHORTS_MAX_SECONDS)
    if duration < SHORTS_MIN_SECONDS:
        print(f"  ⚠️ 쇼츠 길이가 목표({SHORTS_MIN_SECONDS:.0f}~{SHORTS_MAX_SECONDS:.0f}초)보다 짧음: "
              f"{duration:.1f}초 (원본 오디오가 그보다 짧음)")
    return renderer.compose_scene(frame_path, audio_path, out_path, duration, scene_index=scene_index)
