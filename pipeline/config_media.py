# pipeline/config_media.py
"""config/media.yml 로더 — media 파이프라인의 provider 목록/중복감지 설정을 노출한다."""
import os
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_MEDIA_PATH = os.path.join(_HERE, "..", "config", "media.yml")

with open(_MEDIA_PATH, "r", encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f) or {}

PROVIDER_NAMES = _CFG.get("providers") or ["yonhap", "kbs"]
DEDUP_WINDOW_DAYS = (_CFG.get("dedup") or {}).get("window_days", 7)
DEDUP_HAMMING_THRESHOLD = (_CFG.get("dedup") or {}).get("hamming_threshold", 6)
MAX_CANDIDATES_PER_SECTION = _CFG.get("max_candidates_per_section", 8)

# yaml 값 또는 환경변수 MEDIA_MOCK=1 둘 중 하나만 true여도 mock 모드로 동작한다.
MOCK_MODE = bool(_CFG.get("mock_mode", False)) or os.environ.get("MEDIA_MOCK") == "1"


if __name__ == "__main__":
    print(f"PROVIDER_NAMES              = {PROVIDER_NAMES}")
    print(f"DEDUP_WINDOW_DAYS           = {DEDUP_WINDOW_DAYS}")
    print(f"DEDUP_HAMMING_THRESHOLD     = {DEDUP_HAMMING_THRESHOLD}")
    print(f"MAX_CANDIDATES_PER_SECTION  = {MAX_CANDIDATES_PER_SECTION}")
    print(f"MOCK_MODE                   = {MOCK_MODE}")
