"""
pipeline/generate_video.py
===========================
KBS 머니올라 — 동영상 합성 모듈
PNG 프레임 + MP3 오디오 + ASS 자막 → MP4

프레임 → 오디오 매핑 규칙:
  00_opening.png             → opening.mp3
  01_market_00.png           → market_summary.mp3
  02_sector.png              → sectors.mp3
  NN_종목명_1_summary.png    → stock_종목명_summary.mp3
  NN_종목명_2_chart.png      → stock_종목명_chart.mp3
  NN_종목명_3_mention.png    → stock_종목명_mention.mp3
  NN_종목명_3_mention_MM.png → stock_종목명_mention_MM.mp3
  90_extra_watchlist.png     → stock_추가관심종목.mp3
  91_today_pick.png          → stock_오늘의픽.mp3
  92_brokerage_report.png    → stock_증권사리포트.mp3
  98_ai_strategy.png         → ai_strategy.mp3
  99_closing.png             → closing.mp3

자막 처리:
  - ASS burn-in 방식: ffmpeg libass 필터로 자막을 영상에 직접 합성
  - 나레이션 타이밍과 동기화된 하단 자막 표출
  - 자막 텍스트: subtitle 필드 (한글 맞춤법, 숫자 원문, 용어 설명 병기)
"""
import os
import sys
import json
import re
import subprocess
import urllib.request

# 목표 길이 설정
TARGET_MIN = float(os.environ.get("TARGET_MIN_SECONDS", "870"))   # 14분 30초
TARGET_MAX = float(os.environ.get("TARGET_MAX_SECONDS", "930"))   # 15분 30초
TARGET_IDEAL = 900.0  # 15분 정확

# BGM 볼륨 설정 (0.0~1.0)
BGM_URL    = os.environ.get("BGM_URL", "")
BGM_VOLUME = 0.065   # 주 오디오를 방해하지 않는 낮은 볼륨


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


# ── 프레임 스템 → 오디오 ID 변환 ─────────────────────────────────────────

def _frame_stem_to_audio_id(stem: str, sections: list) -> str:
    fixed_patterns = [
        (r'^00_opening$',           'opening'),
        (r'^01_market',             'market_summary'),
        (r'^02_sector',             'sectors'),
        (r'^90_extra_watchlist$',   'stock_추가관심종목'),
        (r'^91_today_pick$',        'stock_오늘의픽'),
        (r'^92_brokerage_report$',  'stock_증권사리포트'),
        (r'^98_ai_strategy',        'ai_strategy'),
        (r'^99_closing',            'closing'),
    ]
    for pattern, audio_id in fixed_patterns:
        if re.match(pattern, stem):
            return audio_id

    m = re.match(r'^\d{2}_(.+)_3_mention_(\d{2})$', stem)
    if m:
        stock_name = m.group(1)
        page_num   = m.group(2)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_mention_{page_num}"

    m = re.match(r'^\d{2}_(.+)_3_mention$', stem)
    if m:
        stock_name = m.group(1)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_mention_00"

    m = re.match(r'^\d{2}_(.+)_1_summary$', stem)
    if m:
        stock_name = m.group(1)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_summary"

    print(f"  ⚠️ 오디오 ID 매핑 실패 — 스템: {stem}")
    return stem


def _find_stock_section_id(stock_name: str, sections: list) -> str:
    for sec in sections:
        sid = sec.get("id", "")
        if sid in (f"stock_{stock_name}", f"hidden_{stock_name}"):
            return sid
    for sec in sections:
        sid = sec.get("id", "")
        if stock_name in sid:
            return sid
    return f"stock_{stock_name}"


# ── 섹션 영상 생성 (PNG + MP3 → MP4) ─────────────────────────────────────

def build_section_video(png_path: str, mp3_path: str, out_path: str) -> bool:
    duration = get_audio_duration(mp3_path)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", png_path,
        "-i",    mp3_path,
        "-c:v",  "libx264", "-tune", "stillimage",
        "-c:a",  "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-t", f"{duration:.3f}",
        out_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ 실패: {os.path.basename(out_path)}")
        print(result.stderr[-600:])
        return False

    print(f"  ✅ {os.path.basename(out_path)} ({duration:.1f}초)")
    return True


# ── 영상 합치기 ───────────────────────────────────────────────────────────

def concat_videos(video_list: list, out_path: str) -> bool:
    list_file = out_path.replace(".mp4", "_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for v in video_list:
            f.write(f"file '{os.path.abspath(v)}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        out_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(list_file)
    if result.returncode != 0:
        print("  ❌ 영상 합치기 실패")
        print(result.stderr[-400:])
        return False
    print("  ✅ 합치기 완료")
    return True


# ── 영상 길이 조정 (15분에 맞추기) ───────────────────────────────────────

def adjust_to_target_duration(input_path: str, output_path: str,
                               current_duration: float) -> float:
    """
    영상 길이를 목표 시간(15분)에 맞게 조정합니다.
    - 너무 짧으면 (< 14분30초): 마지막 프레임 반복으로 늘림
    - 너무 길면 (> 15분30초): 속도 미세 조정으로 줄임
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


# ── BGM 믹싱 ─────────────────────────────────────────────────────────────

def mix_bgm(video_path: str, bgm_path: str, out_path: str) -> bool:
    if not os.path.isfile(bgm_path):
        print(f"  ⚠️ BGM 없음 → BGM 없이 진행")
        import shutil
        shutil.copy2(video_path, out_path)
        return True

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        f"[1:a]volume={BGM_VOLUME}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ BGM 믹싱 실패")
        print(result.stderr[-400:])
        return False
    print("  ✅ BGM 믹싱 완료")
    return True


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
        generate_ass(sections, lang, ass_path, frames, time_scale=time_scale)
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
    script_path    = os.path.join(root, "output", lang, "scripts", "script.json")
    audio_dir      = os.path.join(root, "output", lang, "audio")
    video_dir      = os.path.join(root, "output", lang, "video")
    asset_map_path = os.path.join(root, "output", lang, "asset_map.json")
    bgm_path       = os.path.join(root, "assets", "music", "bgm.mp3")

    os.makedirs(video_dir, exist_ok=True)

    if not os.path.isfile(script_path):
        print("❌ script.json 없음"); sys.exit(1)
    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)
    sections = script.get("sections", [])
    print(f"📂 섹션 수: {len(sections)}")
    print(f"🎯 방송 목표 길이: 15분 ({TARGET_MIN:.0f}~{TARGET_MAX:.0f}초)")

    if not os.path.isfile(asset_map_path):
        print("❌ asset_map.json 없음"); sys.exit(1)
    with open(asset_map_path, encoding="utf-8") as f:
        asset_map = json.load(f)
    frames = asset_map.get("frames", [])
    print(f"📂 프레임 수: {len(frames)}")

    os.makedirs(os.path.dirname(bgm_path), exist_ok=True)
    download_bgm(bgm_path)

    # ── 섹션 영상 생성 ─────────────────────────────────────────────────
    section_videos = []
    print(f"\n🎬 섹션 영상 생성 시작\n")

    missing_audio = []
    total_audio_duration = 0.0

    for frame_path in frames:
        frame_name = os.path.basename(frame_path)
        frame_stem = os.path.splitext(frame_name)[0]

        audio_id = _frame_stem_to_audio_id(frame_stem, sections)
        mp3_path = os.path.join(audio_dir, f"{audio_id}.mp3")

        if not os.path.isfile(mp3_path):
            missing_audio.append(audio_id)
            print(f"  ❌ MP3 없음 [{audio_id}] → 파이프라인 실패 처리")
            continue

        dur = get_audio_duration(mp3_path)
        total_audio_duration += dur

        out_video = os.path.join(video_dir, f"{frame_stem}.mp4")
        ok = build_section_video(frame_path, mp3_path, out_video)
        if ok:
            section_videos.append(out_video)

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

    # ── 15분 길이 조정 ─────────────────────────────────────────────────
    print(f"\n⏱ 영상 길이 조정 중...\n")
    merged_duration = get_audio_duration(merged_path)
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

    # ── BGM 믹싱 ───────────────────────────────────────────────────────
    print(f"\n🎵 BGM 믹싱 중...\n")
    final_path = os.path.join(video_dir, "final.mp4")
    if not mix_bgm(source_for_bgm, bgm_path, final_path):
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
    print(f"   길이: {mins}분 {secs}초 (목표: 15분)")
    if not (TARGET_MIN <= total_duration <= TARGET_MAX):
        print(f"   ⚠️ 경고: 목표 길이({int(TARGET_MIN//60)}분~{int(TARGET_MAX//60)}분)를 벗어났습니다")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
