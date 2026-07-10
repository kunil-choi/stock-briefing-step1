import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

TARGET_MIN_SECONDS = int(os.environ.get("TARGET_MIN_SECONDS", "870"))
TARGET_MAX_SECONDS = int(os.environ.get("TARGET_MAX_SECONDS", "930"))

KST = timezone(timedelta(hours=9))
REQUIRED_METADATA_FIELDS = [
    "briefing_type", "video_format", "briefing_date", "status",
    "title", "description", "tags",
]


def check_metadata(root: str = ".") -> None:
    """output/{date}/metadata.json이 존재하고 필수 필드를 갖췄는지 검증한다.
    generate_metadata.py가 실패(status="failed")로 남긴 경우도 여기서 걸러진다."""
    today_dir = os.path.join(root, "output", datetime.now(KST).strftime("%Y-%m-%d"))
    meta_path = os.path.join(today_dir, "metadata.json")
    if not os.path.isfile(meta_path):
        raise SystemExit(f"metadata.json 없음: {meta_path}")

    meta = json.load(open(meta_path, encoding="utf-8"))
    missing = [f for f in REQUIRED_METADATA_FIELDS if not meta.get(f)]
    if missing:
        raise SystemExit(f"metadata.json 필수 필드 누락: {missing} ({meta_path})")

    if meta.get("status") not in ("success", "partial"):
        raise SystemExit(f"metadata.json status={meta.get('status')!r} — 실패로 표시됨 ({meta_path})")

    # video_format에 맞는 길이 범위로 검증 (longform/shorts 분기)
    try:
        from config_schedule import duration_for
        bounds = duration_for(meta.get("video_format", "longform"))
    except Exception:
        bounds = {"min_seconds": TARGET_MIN_SECONDS, "max_seconds": TARGET_MAX_SECONDS}

    duration = meta.get("duration_seconds", 0)
    if duration and not (bounds["min_seconds"] <= duration <= bounds["max_seconds"]):
        print(f"⚠️  metadata.json duration_seconds={duration}가 목표 범위"
              f"({bounds['min_seconds']}~{bounds['max_seconds']}s)를 벗어남 — 경고만 출력")

    print(f"✅ metadata.json 검증 통과 ({meta_path}, status={meta['status']})")

def media_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def main(lang: str = "KO"):
    base = os.path.join("output", lang.upper())
    asset_map = os.path.join(base, "asset_map.json")
    script_path = os.path.join(base, "scripts", "script.json")
    audio_dir = os.path.join(base, "audio")
    video_path = os.path.join(base, "video", "final.mp4")

    if not os.path.isfile(asset_map):
        raise SystemExit(f"asset_map.json 없음: {asset_map}")
    if not os.path.isfile(script_path):
        raise SystemExit(f"script.json 없음: {script_path}")

    # frame stem → audio_id 매핑은 generate_subtitles.py가 이미 갖고 있는 검증된
    # 로직을 그대로 재사용한다(정규식 기반, hidden_/stock_ 접두어 구분까지
    # 정확히 처리함). 예전에는 이 파일에 독립적으로 재구현한 버전이 있었는데,
    # mention 페이지처럼 세그먼트 수가 다른 stem에서 슬라이싱 오프셋이 어긋나
    # (예: "10_삼성전자_3_mention_00" → 잘못된 "stock_삼성전자_3_mention_00")
    # 실제로 존재하는 mp3와 이름이 달라 "누락 오디오"로 오판하는 버그가 있었다.
    from generate_subtitles import _frame_stem_to_audio_id

    sections = json.load(open(script_path, encoding="utf-8")).get("sections", [])
    frames = json.load(open(asset_map, encoding="utf-8")).get("frames", [])
    missing = []
    for frame in frames:
        stem = os.path.splitext(os.path.basename(frame))[0]
        audio_id = _frame_stem_to_audio_id(stem, sections)
        mp3 = os.path.join(audio_dir, f"{audio_id}.mp3")
        if not os.path.isfile(mp3):
            missing.append(mp3)

    if missing:
        print("누락 오디오:")
        for m in missing:
            print(m)
        raise SystemExit(1)

    if not os.path.isfile(video_path):
        raise SystemExit(f"final.mp4 없음: {video_path}")

    duration = media_duration(video_path)
    print(f"final.mp4 duration={duration:.2f}s")
    if not (TARGET_MIN_SECONDS <= duration <= TARGET_MAX_SECONDS):
        raise SystemExit(f"최종 영상 길이가 목표 범위를 벗어남: {duration:.2f}s")

    check_metadata()

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "KO")
