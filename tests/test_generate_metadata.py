# tests/test_generate_metadata.py
"""
generate_metadata.py의 날짜 계산/파일명 헬퍼 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크/
playwright(썸네일 렌더링에 필요) 불필요 — 이 모듈은 run()에서만 그 무거운
의존성을 지연 import하므로, 순수 함수만 떼어서 테스트한다.
실행: python tests/test_generate_metadata.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from generate_metadata import _kdate_to_iso, video_filename  # noqa: E402


def test_video_filename_uses_yymmdd():
    """최종 영상 파일명에 날짜(YYMMDD)가 들어가야 한다 — 예: final_260801.mp4
    (사용자 요청: 폴더 밖에서도 파일만 보고 날짜를 구분할 수 있어야 함)."""
    assert video_filename("2026-08-01") == "final_260801.mp4"
    assert video_filename("2026-12-31") == "final_261231.mp4"
    assert video_filename("2026-01-05") == "final_260105.mp4"
    print("✅ video_filename: YYMMDD 형식(final_260801.mp4)으로 정확히 만들어짐")


def test_video_filename_matches_kdate_to_iso_output():
    """generate_metadata.run()이 실제로 쓰는 흐름(한글 날짜 → _kdate_to_iso →
    video_filename)을 그대로 이어붙여도 정상 동작해야 한다."""
    date_iso = _kdate_to_iso("2026년 8월 1일")
    assert date_iso == "2026-08-01"
    assert video_filename(date_iso) == "final_260801.mp4"
    print("✅ video_filename: _kdate_to_iso가 만든 날짜를 그대로 받아도 정확함")


if __name__ == "__main__":
    test_video_filename_uses_yymmdd()
    test_video_filename_matches_kdate_to_iso_output()
    print("\n✅ generate_metadata 테스트 전체 통과")
