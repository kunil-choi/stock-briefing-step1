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
import re
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
    BGM_DUCKING_THRESHOLD_DB, BGM_DUCKING_RATIO, ATEMPO_MAX_SPEED,
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
            "-c:a", "libmp3lame", "-b:a", "192k",
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


# ── 목표 길이 초과 시 우선순위에 따른 콘텐츠 삭제 ──────────────────────────
#
# adjust_to_target_duration()의 배속 보정(최대 ATEMPO_MAX_SPEED배)만으로는
# 목표 최대 길이(TARGET_MAX)를 못 맞출 만큼 스크립트 분량이 많을 때, 예전에는
# quality_gate.py가 최종적으로 실패 처리했다. 이제는 그 전에 우선순위가 낮은
# 콘텐츠부터 하나씩 빼서 다시 계산해, 배속 보정만으로 목표를 맞출 수 있는
# 수준까지 분량을 줄인다.
#
# ★ 원칙: 대형 주도주/관심종목의 "개수"는 절대 줄이지 않는다 — 어떤 종목을
# 통째로 들어내거나(개별 요약 삭제) 관심종목 집계 카드를 통째로 빼는 방식은
# 쓰지 않고, 각 종목에 딸린 세부 항목(패널/채널 언급 코멘트, AI 부가 설명)만
# 조금씩 줄인다(사용자 요청 — 길이가 문제라도 다루는 종목 수는 그대로 유지).
#
# 삭제 우선순위(낮을수록 먼저 빠짐), 전부 라운드로빈으로 하나씩:
#   0. 대형 주도주가 아닌 종목의 채널 언급(멘션) 페이지 — "이 종목이
#      유튜브/경제방송/증권사에서 이렇게 언급됐다"는 부가 코멘트라, 정보량
#      대비 분량이 가장 크다. 특정 종목의 패널 코멘트를 통째로 먼저 없애는
#      대신 라운드로빈으로 뺀다: 아직 하나도 안 뺀 종목이 있으면 그 종목의
#      (가장 뒤 페이지) 멘션을, 그중에서도 importance가 낮은 종목을 먼저
#      뺀다 — 모든 종목이 1개씩 빠진 뒤에야 다시 2번째 페이지를 빼기 시작한다.
#   1. AI 히든픽의 부가 설명(애널리스트 코멘트 → 포인트) — 핵심 시나리오는
#      끝까지 남긴다.
#   2. 대형 주도주의 멘션 페이지 — 그 외 모든 종목의 멘션과 AI 부가 설명을
#      다 빼고도 부족할 때만 건드린다(0번과 같은 라운드로빈 규칙 공유).
# 훅/채널언급 인트로/시장 지표/개별 종목 요약(주도주·관심종목 모두)/관심종목·
# 증권사 리포트 집계 카드/AI 히든픽 핵심 시나리오/클로징은 절대 빼지 않는다
# (= 종목 개수와 각 종목의 핵심 요약은 항상 보존됨) — 그래도 목표를 못
# 맞추면 quality_gate.py가 최종 안전장치로 남아 실패 처리한다.

_DROP_TIER_MINOR_MENTION = 0
_DROP_TIER_AI_STRATEGY_EXTRA = 1
_DROP_TIER_LEADER_MENTION = 2

_MENTION_ID_RE = re.compile(r"^(.+)_mention_(\d+)$")


def _classify_drop_candidate(audio_id: str, leader_ids: set, importance_by_sid: dict,
                              mention_rounds: dict):
    """audio_id가 분량 초과 시 삭제 후보면 (tier, 정렬키)를, 핵심 콘텐츠라
    삭제 금지면 None을 반환한다. tier가 낮을수록, 정렬키가 작을수록 먼저
    삭제된다. 종목 요약/집계 카드는 어떤 경우에도 삭제 후보가 아니다(종목
    개수를 줄이지 않는다는 원칙).

    mention_rounds: {종목id: 이번 트림에서 이미 뺀 멘션 개수}. 멘션 페이지의
    정렬키 맨 앞자리로 써서, 한 종목의 멘션을 다 빼기 전에 다른 종목들의
    멘션을 1개씩 먼저 빼는 라운드로빈이 되게 한다(호출부(trim_to_fit_budget)가
    한 프레임을 뺄 때마다 그 종목의 카운트를 올려준다)."""
    m = _MENTION_ID_RE.match(audio_id)
    if m:
        sid, page = m.group(1), int(m.group(2))
        importance = importance_by_sid.get(sid, 0.0)
        tier = _DROP_TIER_LEADER_MENTION if sid in leader_ids else _DROP_TIER_MINOR_MENTION
        round_ = mention_rounds.get(sid, 0)
        return (tier, (round_, importance, -page))

    if audio_id in ("ai_strategy_analyst", "ai_strategy_points"):
        rank = 0 if audio_id == "ai_strategy_analyst" else 1
        return (_DROP_TIER_AI_STRATEGY_EXTRA, (rank,))

    return None


def _fits_within_target(frame_audio_pairs: list, target_max: float,
                         atempo_max_speed: float, transition_duration: float) -> bool:
    """adjust_to_target_duration()이 실제로 적용할 계산(속도 = min(길이/IDEAL,
    상한), 조정 후 길이 = 길이/속도)과 동일한 식으로, 지금 프레임 구성이
    배속 보정만으로 target_max 이내에 들어올 수 있는지 미리 판단한다."""
    if not frame_audio_pairs:
        return True
    total = sum(d for _, _, d in frame_audio_pairs)
    expected = total + max(0, len(frame_audio_pairs) - 1) * transition_duration
    return expected / atempo_max_speed <= target_max


def trim_to_fit_budget(frame_audio_pairs: list, sections: list, target_max: float,
                        atempo_max_speed: float, transition_duration: float) -> list:
    """frame_audio_pairs가 최대 배속으로도 target_max를 못 맞추면, 우선순위가
    낮은 프레임부터 하나씩 빼며 다시 계산한다. 이미 맞으면 그대로 반환."""
    if _fits_within_target(frame_audio_pairs, target_max, atempo_max_speed, transition_duration):
        return frame_audio_pairs

    leader_ids = {s.get("id", "") for s in sections if s.get("stock_tier") == "market_leader"}
    importance_by_sid = {s.get("id", ""): s.get("importance", 0.0) for s in sections}
    mention_rounds: dict = {}  # sid -> 이번 트림에서 이미 뺀 멘션 개수(라운드로빈용)

    pairs = list(frame_audio_pairs)
    dropped_labels = []
    dropped_seconds = 0.0
    while not _fits_within_target(pairs, target_max, atempo_max_speed, transition_duration) and pairs:
        candidates = []
        for frame_path, mp3_path, duration in pairs:
            stem = os.path.splitext(os.path.basename(frame_path))[0]
            audio_id = _frame_stem_to_audio_id(stem, sections)
            classified = _classify_drop_candidate(audio_id, leader_ids, importance_by_sid, mention_rounds)
            if classified:
                tier, sort_key = classified
                candidates.append((tier, sort_key, frame_path, duration, audio_id))

        if not candidates:
            print("  ⚠️ 목표 길이를 맞추기 위한 삭제 후보가 더 없습니다(핵심 콘텐츠만 "
                  "남음) — 배속 보정 결과가 여전히 목표를 넘으면 quality_gate에서 "
                  "최종 실패 처리됩니다.")
            break

        candidates.sort(key=lambda c: (c[0], c[1]))
        _, _, drop_frame, drop_dur, drop_audio_id = candidates[0]
        pairs = [p for p in pairs if p[0] != drop_frame]
        dropped_labels.append(f"{drop_audio_id}({drop_dur:.1f}s)")
        dropped_seconds += drop_dur

        mention_match = _MENTION_ID_RE.match(drop_audio_id)
        if mention_match:
            sid = mention_match.group(1)
            mention_rounds[sid] = mention_rounds.get(sid, 0) + 1

    if dropped_labels:
        print(f"  ✂️ 배속 보정만으로 목표 길이를 못 맞춰 우선순위 낮은 콘텐츠 "
              f"{len(dropped_labels)}개(총 {dropped_seconds:.1f}초)를 뺐습니다: "
              f"{', '.join(dropped_labels)}")
    return pairs


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


def build_scene_clips(frame_audio_pairs: list, video_dir: str) -> tuple:
    """[(frame_path, mp3_path, duration), ...] → Ken Burns 클립과 전환 클립을
    번갈아 만든 파일 경로 리스트를 반환한다. 장면 합성이 실패하면 그 장면만
    건너뛰고(기존 build_section_video() 실패 시 동작과 동일하게) 계속 진행한다.

    반환값: (clips, rendered_pairs). rendered_pairs는 실제로 최종 영상에
    포함된 (frame_path, mp3_path, duration)만 담은 부분집합이다 — 호출부가
    자막/BGM 구간 계산을 "계획된 프레임 전체"가 아니라 "실제로 렌더링된
    장면"에 맞춰야, 합성 실패로 빠진 장면 때문에 이후 자막 타임라인 전체가
    밀리는 문제(FIX-SCENE-SUBTITLE-DRIFT-1)를 피할 수 있다."""
    clips = []
    rendered_pairs = []
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
            rendered_pairs.append((frame_path, mp3_path, duration))
            prev_frame = frame_path
        else:
            print(f"  ⚠️ 장면 합성 실패 — 건너뜀: {frame_stem}")
            # 이 장면으로 들어가는 전환은 어차피 갈 곳을 잃었으므로 되돌린다
            # (prev_frame은 그대로 두어, 다음 성공 장면과의 전환이 마지막
            # 성공 장면을 기준으로 다시 만들어지게 한다).
            if transition_added:
                clips.pop()

    return clips, rendered_pairs


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
        # 속도 조정으로 줄이기 (config/audio.yml의 atempo.max_speed로 상한 clamp —
        # 이전에는 여기서 1.1을 하드코딩해 config 값과 실제 동작이 어긋나 있었다)
        speed = current_duration / TARGET_IDEAL
        if speed > ATEMPO_MAX_SPEED:
            speed = ATEMPO_MAX_SPEED
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

    # CI에서 generate_subtitles.py를 먼저 돌려 만들어둔 캐시 파일이 있어도
    # 항상 여기서 다시 생성한다 — 그 사전 단계는 asset_map.json의 계획된
    # 프레임 전체를 기준으로 만들어지므로, 이 시점에 실제로 오디오가 없거나
    # 합성에 실패해 최종 영상에서 빠진 장면이 하나라도 있으면(호출부가 넘기는
    # frames는 이미 그걸 걸러낸 목록) 캐시 파일의 타임라인은 어긋나 있다
    # (FIX-SCENE-SUBTITLE-DRIFT-1). ASS 생성 자체는 ffmpeg 인코딩 없는
    # 가벼운 텍스트 작업이라 매번 다시 만들어도 비용이 거의 없다.
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
        frame_audio_pairs.append((frame_path, mp3_path, dur))

    # 배속 보정(최대 ATEMPO_MAX_SPEED배)만으로는 목표 최대 길이를 못 맞출
    # 만큼 분량이 많으면, 여기서 우선순위 낮은 콘텐츠부터 미리 줄인다(실제
    # ffmpeg 합성 전에 걸러내 불필요한 렌더링도 피한다).
    frame_audio_pairs = trim_to_fit_budget(
        frame_audio_pairs, sections, TARGET_MAX, ATEMPO_MAX_SPEED, TRANSITION_DURATION,
    )

    section_videos, rendered_pairs = build_scene_clips(frame_audio_pairs, video_dir)

    if missing_audio:
        print("\n⚠️  누락된 오디오가 있어 해당 섹션을 건너뜁니다.")
        for audio_id in missing_audio:
            print(f"   - {audio_id}.mp3")

    if not section_videos:
        print("❌ 생성된 섹션 영상 없음"); sys.exit(1)

    dropped = len(frame_audio_pairs) - len(rendered_pairs)
    if dropped:
        print(f"\n⚠️  장면 합성 실패로 {dropped}개 프레임이 최종 영상에서 빠졌습니다 — "
              f"자막/BGM 타임라인은 실제로 렌더링된 장면 기준으로 다시 계산합니다.")

    # 자막/BGM 구간 계산은 asset_map.json에 계획된 프레임 전체가 아니라, 실제로
    # 최종 영상에 들어간 장면(rendered_pairs)만 기준으로 해야 한다 — 그래야
    # 오디오 누락/합성 실패로 빠진 장면 때문에 그 뒤 모든 자막 타임코드가
    # 밀려버리는 문제(FIX-SCENE-SUBTITLE-DRIFT-1)가 생기지 않는다.
    total_audio_duration = sum(d for _, _, d in rendered_pairs)
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
    rendered_frames = [p for p, _, _ in rendered_pairs]
    ass_path = _auto_generate_subtitles(lang, root, sections, rendered_frames, subtitle_time_scale)
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
        rendered_pairs, transition_count, time_scale=subtitle_time_scale
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
