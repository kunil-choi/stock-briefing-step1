import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config_schedule import duration_for

_DURATION_BOUNDS = duration_for("longform")
TARGET_MIN_SECONDS = int(os.environ.get("TARGET_MIN_SECONDS", _DURATION_BOUNDS["min_seconds"]))
TARGET_MAX_SECONDS = int(os.environ.get("TARGET_MAX_SECONDS", _DURATION_BOUNDS["max_seconds"]))

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

# 스크립트 생성 프롬프트의 예시 스키마 값이 실제 값 대신 그대로 출력에 남는
# 사고(과거 "₩000,000 / 현대차 한줄 요약"가 화면에 그대로 노출된 사례)를 화면에
# 실리기 전에 걸러낸다.
# ★ "+0.00%"는 여기 포함하지 않는다 — generate_script.py가 종목 price/change를
# V3_1 원본 시세로 채우는데, 장 개시 전(morning_core)에는 전일종가 기준이라
# change_pct가 실제로 0.00%인 종목이 흔하다. 이걸 placeholder로 취급하면 정상
# 데이터가 매번 오탐으로 파이프라인을 막는다(실제로 발생한 사고).
_PLACEHOLDER_LITERALS = {"000,000", "한줄 요약"}


def check_no_placeholder_content(script_path: str) -> None:
    """reordered_script.json의 종목 섹션에 미채움 placeholder 문구나 빈 값이
    남아있지 않은지 검사한다. 하나라도 발견되면 화면에 그대로 노출되기 전에
    파이프라인을 중단시킨다."""
    sections = json.load(open(script_path, encoding="utf-8")).get("sections", [])
    offenders = []
    for sec in sections:
        sid = sec.get("id", "")
        if not (sid.startswith("stock_") or sid.startswith("hidden_")):
            continue
        stock_name = sid.split("_", 1)[-1]
        # price/change: 실제 값이 있어야 한다(비어있으면 stock_market_data 조회가
        # 실패했다는 뜻). "000,000"처럼 값 자체가 명백한 placeholder인 경우도 포함.
        # "+0.00%"는 장 개시 전 정상적으로 나올 수 있는 실제 값이라 걸러내지 않는다.
        for field in ("price", "change"):
            value = str(sec.get(field, "")).strip()
            if not value or value in _PLACEHOLDER_LITERALS:
                offenders.append(f"{sid}.{field}={value!r}")
        # summary/corner_summary: LLM이 스키마 예시를 그대로 베낀 경우를 잡는다.
        for field in ("summary", "corner_summary"):
            value = str(sec.get(field, "")).strip()
            if not value or value in _PLACEHOLDER_LITERALS or value == f"{stock_name} 한줄 요약":
                offenders.append(f"{sid}.{field}={value!r}")

    if offenders:
        print("❌ placeholder 미채움 콘텐츠 발견:")
        for o in offenders:
            print(f"  {o}")
        raise SystemExit(f"placeholder 콘텐츠가 화면에 노출될 위험 — {len(offenders)}건 ({script_path})")

    print(f"✅ placeholder 미채움 콘텐츠 없음 확인 ({script_path})")


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
    script_path = os.path.join(base, "scripts", "reordered_script.json")
    audio_dir = os.path.join(base, "audio")
    video_path = os.path.join(base, "video", "final.mp4")

    if not os.path.isfile(asset_map):
        raise SystemExit(f"asset_map.json 없음: {asset_map}")
    if not os.path.isfile(script_path):
        raise SystemExit(f"reordered_script.json 없음: {script_path}")

    check_no_placeholder_content(script_path)

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
