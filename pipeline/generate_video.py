"""
pipeline/generate_video.py
===========================
KBS 머니올라 — 동영상 합성 모듈
PNG 프레임 + MP3 오디오 + ASS 자막 → MP4

프레임 → 오디오 매핑 규칙은 generate_subtitles.py의
_frame_stem_to_audio_id() docstring을 참고(중복 구현 방지를 위해 이 모듈이
그 함수를 그대로 재사용한다).

자막 처리:
  - ASS burn-in 방식: ffmpeg libass 필터로 자막을 영상에 직접 합성
  - 나레이션 타이밍과 동기화된 하단 자막 표출
  - 자막 텍스트: subtitle 필드 (한글 맞춤법, 숫자 원문, 용어 설명 병기)
"""
import os
import sys
import json
import subprocess
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.video_renderer import FFmpegVideoRenderer, TRANSITION_DURATION
from assets.audio_post import mix_bgm_with_ducking
from config_audio import (
    BGM_INTRO_VOLUME, BGM_BODY_VOLUME, BGM_OUTRO_VOLUME,
    BGM_DUCKING_THRESHOLD_DB, BGM_DUCKING_RATIO,
)
from config_schedule import duration_for
from generate_subtitles import _frame_stem_to_audio_id

# 목표 길이 설정 — config/schedule.yml의 duration.longform을 그대로 쓴다
# (예전엔 여기 하드코딩된 15분짜리 값이 schedule.yml과 별개로 존재해서,
# schedule.yml을 5~8분으로 바꿔도 실제 영상 길이는 그대로 15분이 나오는
# 불일치가 있었다).
_DURATION_BOUNDS = duration_for("longform")
TARGET_MIN = float(os.environ.get("TARGET_MIN_SECONDS", _DURATION_BOUNDS["min_seconds"]))
TARGET_MAX = float(os.environ.get("TARGET_MAX_SECONDS", _DURATION_BOUNDS["max_seconds"]))
TARGET_IDEAL = (TARGET_MIN + TARGET_MAX) / 2

# BGM 다운로드 URL. 실제 볼륨/덕킹 파라미터는 config/audio.yml(config_audio.py)에서 관리한다.
BGM_URL = os.environ.get("BGM_URL", "")


# ── BGM 다운로드 ──────────────────────────────────────────────────────────

def download_bgm(save_path: str):
    if not BGM_URL:
        print("  [bgm] BGM_URL 미설정 → 외부 데모 음악 다운로드 안 함")
        return
    if os.path.exists(save_path):
        print(f"  [bgm] 캐시 사용: {save_path}")
        return
    print(f"  [bgm] 다운로드 중...")
    try:
        urllib.request.urlretrieve(BGM_URL, save_path)
        print(f"  [bgm] 완료: {save_path}")
    except Exception as e:
        print(f"  [bgm] 다운로드 실패: {e}")


# 오디오 없이 텍스트만 보여주는 화면(예: 훅 타이틀 카드)의 고정 표시 시간.
# generate_subtitles.py의 동명 상수(SILENT_DURATION)와 값을 맞춰야 두 모듈이
# 계산하는 장면 길이/자막 타임라인이 어긋나지 않는다.
SILENT_FRAME_AUDIO_IDS = {"hook_title"}
SILENT_FRAME_DURATION = 3.0


def _ensure_silent_audio(mp3_path: str, duration: float) -> str:
    """audio_id가 SILENT_FRAME_AUDIO_IDS에 있어 의도적으로 내레이션이 없는
    프레임을 위해, duration초짜리 무음 mp3를 만든다(없으면). compose_scene()이
    Ken Burns 클립을 만들 때 오디오 스트림이 있어야 하므로 실제 파일이 필요하다."""
    if not os.path.isfile(mp3_path):
        os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:a", "aac", "-b:a", "192k",
            mp3_path,
        ]
        subprocess.run(cmd, capture_output=True)
    return mp3_path


# ── 오디오 길이 ───────────────────────────────────────────────────────────

def get_audio_duration(mp3_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        mp3_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        dur = float(result.stdout.strip())
        return dur if dur > 0 else 3.0
    except Exception:
        return 3.0


# ── 장면 영상 생성 (PNG + MP3 → Ken Burns 클립) + 전환 삽입 ────────────────
#
# ★ 방송형 렌더링(Phase D): 정지 이미지를 그대로 -loop 1로 홀드하던 예전 방식
# 대신, FFmpegVideoRenderer.compose_scene()으로 Ken Burns(서서히 확대/이동)
# 효과를 적용한다. 장면 사이에는 build_transition()으로 만든 짧은(기본 0.4초)
# crossfade/push 전환 클립을 삽입한다 — 겹쳐서(overlap) 이어붙이는 대신 별도
# 세그먼트로 "삽입"하므로 각 장면의 오디오 길이는 전혀 바뀌지 않고, 자막
# 타임라인은 전환 구간만큼 더하기만 하면 된다(video_renderer.py 모듈 docstring
# 참고). concat()은 이미 같은 코덱으로 인코딩된 클립들을 스트림 복사로
# 이어붙인다(예전 concat_videos()와 동일한 방식).

_renderer = FFmpegVideoRenderer()


def build_scene_clips(frame_audio_pairs: list, video_dir: str) -> list:
    """[(frame_path, mp3_path, duration), ...] → Ken Burns 클립과 전환 클립을
    번갈아 만든 파일 경로 리스트를 반환한다. 장면 합성이 실패하면 그 장면만
    건너뛰고(기존 build_section_video() 실패 시 동작과 동일하게) 계속 진행한다."""
    clips = []
    prev_frame = None
    for i, (frame_path, mp3_path, duration) in enumerate(frame_audio_pairs):
        frame_stem = os.path.splitext(os.path.basename(frame_path))[0]

        transition_added = False
        if prev_frame is not None:
            trans_path = os.path.join(video_dir, f"trans_{i:03d}.mp4")
            clips.append(_renderer.build_transition(prev_frame, frame_path, trans_path, scene_index=i))
            transition_added = True

        scene_path = os.path.join(video_dir, f"{frame_stem}.mp4")
        clip = _renderer.compose_scene(frame_path, mp3_path, scene_path, duration, scene_index=i)
        if clip:
            clips.append(clip)
            prev_frame = frame_path
        else:
            print(f"  ⚠️ 장면 합성 실패 — 건너뜀: {frame_stem}")
            # 이 장면으로 들어가는 전환은 어차피 갈 곳을 잃었으므로 되돌린다
            # (prev_frame은 그대로 두어, 다음 성공 장면과의 전환이 마지막
            # 성공 장면을 기준으로 다시 만들어지게 한다).
            if transition_added:
                clips.pop()

    return clips


def concat_videos(video_list: list, out_path: str) -> bool:
    return _renderer.concat(video_list, out_path)


def resolve_merged_duration(measured_duration: float, expected_duration: float,
                             tolerance: float = 0.2) -> float:
    """이어붙인 영상의 ffprobe 측정 길이(measured_duration)가 이미 알고 있는
    입력값으로 계산한 기대 길이(expected_duration)와 tolerance 비율 이상
    어긋나면 기대 길이로 대체한다.

    여러 Ken Burns/전환 클립을 이어붙인 뒤 ffprobe가 읽는 길이가 (ffmpeg
    버전/환경에 따라) 실제 콘텐츠 길이와 크게 어긋나는 사례가 있었다(예: 실측
    755초 분량이 1300초로 잘못 측정돼 adjust_to_target_duration()이 "영상이
    길다"고 오판 → 배속을 줄여 오히려 목표보다 짧은 영상을 만든 사고). 이
    안전장치는 그 오판을 막는다."""
    if expected_duration <= 0:
        return measured_duration
    if abs(measured_duration - expected_duration) > expected_duration * tolerance:
        print(f"  ⚠️ 이어붙인 영상 측정 길이({measured_duration:.1f}초)가 예상 길이"
              f"({expected_duration:.1f}초)와 크게 다릅니다 — ffprobe 측정을 신뢰할 수 없다고 "
              f"판단해 예상 길이로 대체합니다.")
        return expected_duration
    return measured_duration


# ── 영상 길이 조정 (config/schedule.yml의 목표 길이에 맞추기) ─────────────

def adjust_to_target_duration(input_path: str, output_path: str,
                               current_duration: float) -> float:
    """
    영상 길이를 목표 시간(TARGET_MIN~TARGET_MAX, config/schedule.yml에서 로드)에
    맞게 조정합니다.
    - 너무 짧으면 (< TARGET_MIN): 마지막 프레임 반복으로 늘림
    - 너무 길면 (> TARGET_MAX): 속도 미세 조정으로 줄임
    - 범위 내이면: 그대로 유지

    반환값: 적용된 배속(speed factor). 1.0이면 배속 조정 없음(패딩만 적용됐거나
    조정이 필요 없었던 경우). 자막 타임라인을 이 값으로 나눠 보정해야 합니다.
    """
    if TARGET_MIN <= current_duration <= TARGET_MAX:
        import shutil
        shutil.copy2(input_path, output_path)
        print(f"  ✅ 영상 길이 정상 ({current_duration:.0f}초 = {int(current_duration//60)}분{int(current_duration%60)}초)")
        return 1.0

    if current_duration < TARGET_MIN:
        # 마지막 프레임 반복으로 패딩 (배속 변화 없음 → 자막 타임라인 그대로 유효)
        pad_seconds = TARGET_IDEAL - current_duration
        print(f"  ⏱ 영상이 짧음 ({current_duration:.0f}초) → {pad_seconds:.0f}초 패딩 추가")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.1f}",
            "-af", f"apad=pad_dur={pad_seconds:.1f}",
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
        speed = 1.0
    else:
        # 속도 조정으로 줄이기 (최대 10% 빠르게)
        speed = current_duration / TARGET_IDEAL
        if speed > 1.1:
            speed = 1.1
        print(f"  ⏱ 영상이 길음 ({current_duration:.0f}초) → {speed:.3f}배속으로 조정")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter_complex", f"[0:v]setpts={1/speed:.4f}*PTS[v];[0:a]atempo={speed:.4f}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ 길이 조정 실패: {result.stderr[-400:]}")
        import shutil
        shutil.copy2(input_path, output_path)
        return 1.0
    return speed


# ── ASS 자막 burn-in ──────────────────────────────────────────────────────

def burn_subtitles(video_path: str, ass_path: str, out_path: str) -> bool:
    if not os.path.isfile(ass_path):
        print(f"  ⚠️ ASS 자막 파일 없음: {ass_path}")
        return False

    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass={ass_escaped}",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "copy",
        out_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ ASS burn-in 실패")
        print(result.stderr[-800:])
        return False

    print("  ✅ ASS 자막 burn-in 완료")
    return True


# ── BGM 믹싱 (Phase H: 사이드체인 덕킹 + intro/body/outro 구간별 볼륨) ────────

def compute_bgm_bounds(frame_audio_pairs: list, transition_count: int,
                        time_scale: float = 1.0) -> tuple:
    """[(frame_path, mp3_path, duration), ...]에서 첫 장면(intro)이 끝나는
    시점과 마지막 장면(outro)이 시작하는 시점을 계산한다. 배속 조정
    (adjust_to_target_duration)이 적용됐다면 자막과 동일한 time_scale
    (1/speed_factor)로 축소해, 최종(배속 조정 후) 타임라인 기준 시각을
    반환한다."""
    if not frame_audio_pairs:
        return 0.0, 0.0
    intro_end = frame_audio_pairs[0][2] * time_scale
    last_duration = frame_audio_pairs[-1][2] * time_scale
    total = (
        sum(d for _, _, d in frame_audio_pairs) * time_scale
        + transition_count * TRANSITION_DURATION * time_scale
    )
    outro_start = max(intro_end, total - last_duration)
    return intro_end, outro_start


# ── ASS 자막 자동 생성 ────────────────────────────────────────────────────

def _auto_generate_subtitles(lang: str, root: str, sections: list, frames: list,
                              time_scale: float = 1.0) -> str:
    sub_dir  = os.path.join(root, "output", lang, "subtitles")
    ass_path = os.path.join(sub_dir, "subtitle.ass")

    if os.path.isfile(ass_path):
        print(f"  [subtitle] 기존 ASS 파일 사용: {ass_path}")
        return ass_path

    print(f"  [subtitle] ASS 자막 자동 생성 중...")
    try:
        sys.path.insert(0, os.path.join(root, "pipeline"))
        from generate_subtitles import generate_ass
        generate_ass(sections, lang, ass_path, frames, time_scale=time_scale,
                     transition_duration=TRANSITION_DURATION)
        return ass_path
    except Exception as e:
        print(f"  [subtitle] 자막 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return ""


# ── 메인 실행 ─────────────────────────────────────────────────────────────

def run(lang: str = "KO"):
    lang           = lang.upper()
    root           = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    script_path    = os.path.join(root, "output", lang, "scripts", "reordered_script.json")
    audio_dir      = os.path.join(root, "output", lang, "audio")
    video_dir      = os.path.join(root, "output", lang, "video")
    asset_map_path = os.path.join(root, "output", lang, "asset_map.json")
    bgm_path       = os.path.join(root, "assets", "music", "bgm.mp3")

    os.makedirs(video_dir, exist_ok=True)

    if not os.path.isfile(script_path):
        print("❌ reordered_script.json 없음"); sys.exit(1)
    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)
    sections = script.get("sections", [])
    print(f"📂 섹션 수: {len(sections)}")
    print(f"🎯 방송 목표 길이: {TARGET_MIN/60:.0f}~{TARGET_MAX/60:.0f}분 ({TARGET_MIN:.0f}~{TARGET_MAX:.0f}초)")

    if not os.path.isfile(asset_map_path):
        print("❌ asset_map.json 없음"); sys.exit(1)
    with open(asset_map_path, encoding="utf-8") as f:
        asset_map = json.load(f)
    frames = asset_map.get("frames", [])
    print(f"📂 프레임 수: {len(frames)}")

    os.makedirs(os.path.dirname(bgm_path), exist_ok=True)
    download_bgm(bgm_path)

    # ── 장면 영상 생성 (Ken Burns + 전환) ─────────────────────────────────
    print(f"\n🎬 장면 영상 생성 시작 (Ken Burns + crossfade/push 전환)\n")

    missing_audio = []
    total_audio_duration = 0.0
    frame_audio_pairs = []

    for frame_path in frames:
        frame_name = os.path.basename(frame_path)
        frame_stem = os.path.splitext(frame_name)[0]

        audio_id = _frame_stem_to_audio_id(frame_stem, sections)
        mp3_path = os.path.join(audio_dir, f"{audio_id}.mp3")

        if not os.path.isfile(mp3_path):
            if audio_id in SILENT_FRAME_AUDIO_IDS:
                mp3_path = _ensure_silent_audio(mp3_path, SILENT_FRAME_DURATION)
            else:
                missing_audio.append(audio_id)
                print(f"  ❌ MP3 없음 [{audio_id}] → 파이프라인 실패 처리")
                continue

        dur = get_audio_duration(mp3_path)
        total_audio_duration += dur
        frame_audio_pairs.append((frame_path, mp3_path, dur))

    section_videos = build_scene_clips(frame_audio_pairs, video_dir)

    if missing_audio:
        print("\n⚠️  누락된 오디오가 있어 해당 섹션을 건너뜁니다.")
        for audio_id in missing_audio:
            print(f"   - {audio_id}.mp3")

    if not section_videos:
        print("❌ 생성된 섹션 영상 없음"); sys.exit(1)

    total_mins = int(total_audio_duration // 60)
    total_secs = int(total_audio_duration % 60)
    print(f"\n📊 총 오디오 길이: {total_mins}분 {total_secs}초")

    # ── 영상 합치기 ────────────────────────────────────────────────────
    print(f"\n✂️ 영상 컷 연결 중...\n")
    merged_path = os.path.join(video_dir, "merged.mp4")
    if not concat_videos(section_videos, merged_path):
        sys.exit(1)

    # ── 목표 길이 조정 ─────────────────────────────────────────────────
    print(f"\n⏱ 영상 길이 조정 중...\n")
    merged_duration = get_audio_duration(merged_path)

    transition_count = sum(1 for p in section_videos if os.path.basename(p).startswith("trans_"))
    expected_duration = total_audio_duration + transition_count * TRANSITION_DURATION
    merged_duration = resolve_merged_duration(merged_duration, expected_duration)
    adjusted_path = os.path.join(video_dir, "adjusted.mp4")
    speed_factor = adjust_to_target_duration(merged_path, adjusted_path, merged_duration)
    if os.path.isfile(adjusted_path):
        try: os.remove(merged_path)
        except: pass
        source_for_sub = adjusted_path
    else:
        source_for_sub = merged_path

    # ── ASS 자막 자동 생성 및 burn-in ──────────────────────────────────
    print(f"\n📝 자막 처리 중...\n")
    # 영상이 배속 조정됐다면 자막 타임라인도 동일 비율로 압축해야 나레이션과 어긋나지 않음
    subtitle_time_scale = 1.0 / speed_factor if speed_factor else 1.0
    ass_path = _auto_generate_subtitles(lang, root, sections, frames, subtitle_time_scale)
    subtitled_path = os.path.join(video_dir, "with_subtitles.mp4")

    if ass_path and os.path.isfile(ass_path):
        sub_ok = burn_subtitles(source_for_sub, ass_path, subtitled_path)
        if sub_ok:
            try: os.remove(source_for_sub)
            except: pass
            source_for_bgm = subtitled_path
        else:
            print("  ⚠️ 자막 burn-in 실패 → 자막 없는 영상으로 진행")
            source_for_bgm = source_for_sub
    else:
        print("  ⚠️ 자막 파일 없음 → 자막 없는 영상으로 진행")
        source_for_bgm = source_for_sub

    # ── BGM 믹싱 (사이드체인 덕킹 + intro/body/outro 구간별 볼륨) ──────────
    print(f"\n🎵 BGM 믹싱 중...\n")
    final_path = os.path.join(video_dir, "final.mp4")
    # total_duration은 패딩/배속 조정과 자막 burn-in까지 모두 반영된 실제 최종
    # 길이를 써야 한다(merged_duration은 조정 "이전" 길이라 outro 구간을 짧게
    # 잘못 계산할 수 있다).
    bgm_total_duration = get_audio_duration(source_for_bgm)
    intro_end, outro_start = compute_bgm_bounds(
        frame_audio_pairs, transition_count, time_scale=subtitle_time_scale
    )
    if not mix_bgm_with_ducking(
        source_for_bgm, bgm_path, final_path,
        intro_end=intro_end, outro_start=outro_start, total_duration=bgm_total_duration,
        intro_volume=BGM_INTRO_VOLUME, body_volume=BGM_BODY_VOLUME, outro_volume=BGM_OUTRO_VOLUME,
        threshold_db=BGM_DUCKING_THRESHOLD_DB, ratio=BGM_DUCKING_RATIO,
    ):
        sys.exit(1)

    # 임시 파일 정리
    for temp in [merged_path, adjusted_path, subtitled_path, source_for_sub, source_for_bgm]:
        if os.path.isfile(temp) and temp != final_path:
            try: os.remove(temp)
            except: pass
    for v in section_videos:
        try: os.remove(v)
        except: pass

    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    total_duration = get_audio_duration(final_path)
    mins = int(total_duration // 60)
    secs = int(total_duration % 60)

    print(f"\n{'='*50}")
    print(f"✅ 최종 영상 완성!")
    print(f"   파일: {final_path}")
    print(f"   크기: {size_mb:.1f} MB")
    print(f"   길이: {mins}분 {secs}초 (목표: {int(TARGET_MIN//60)}~{int(TARGET_MAX//60)}분)")
    if not (TARGET_MIN <= total_duration <= TARGET_MAX):
        print(f"   ⚠️ 경고: 목표 길이({int(TARGET_MIN//60)}분~{int(TARGET_MAX//60)}분)를 벗어났습니다")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
