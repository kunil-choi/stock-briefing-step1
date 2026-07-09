# pipeline/config_schedule.py
"""config/schedule.yml 로더 — briefing_type/window/duration 상수를 노출한다."""
import os
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCHEDULE_PATH = os.path.join(_HERE, "..", "config", "schedule.yml")

with open(_SCHEDULE_PATH, "r", encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f) or {}

BRIEFING_TYPE   = _CFG.get("briefing_type", "morning_core")
WINDOW_START    = (_CFG.get("window") or {}).get("start", "07:10")
WINDOW_END      = (_CFG.get("window") or {}).get("end", "08:20")
REPORT_DECISION = _CFG.get("report_decision") or {}
DURATION        = _CFG.get("duration") or {}
DEFAULT_VIDEO_FORMAT = _CFG.get("default_video_format", "longform")


def duration_for(video_format: str) -> dict:
    """video_format("longform"|"shorts")에 해당하는 {min_seconds, max_seconds} 반환.
    정의가 없으면 longform 값으로 폴백."""
    return DURATION.get(video_format) or DURATION.get("longform") or {
        "min_seconds": 780, "max_seconds": 1200,
    }


if __name__ == "__main__":
    print(f"BRIEFING_TYPE   = {BRIEFING_TYPE}")
    print(f"WINDOW          = {WINDOW_START} ~ {WINDOW_END}")
    print(f"REPORT_DECISION = {REPORT_DECISION}")
    print(f"DURATION        = {DURATION}")
    print(f"DEFAULT_VIDEO_FORMAT = {DEFAULT_VIDEO_FORMAT}")
