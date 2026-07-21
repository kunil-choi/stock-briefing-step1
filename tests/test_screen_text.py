# tests/test_screen_text.py
"""
screen_text 압축 로직 검증 (pytest 미사용, 순수 assert 기반).
실행: python tests/test_screen_text.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.screen_text import (  # noqa: E402
    strip_sentence_ending,
    drop_leading_filler,
    to_keyword_form,
    compress_line,
    compress_to_screen_text,
)


def run():
    # strip_sentence_ending
    assert strip_sentence_ending("미래에셋증권은 목표주가를 상향했습니다.") == "미래에셋증권은 목표주가를 상향"
    assert strip_sentence_ending("코스피 상승 마감") == "코스피 상승 마감"  # 종결어 없으면 그대로

    # drop_leading_filler
    assert drop_leading_filler("오늘 코스피는 상승했습니다") == "코스피는 상승했습니다"
    assert drop_leading_filler("코스피는 상승했습니다") == "코스피는 상승했습니다"

    # to_keyword_form: 필러+종결어+가격 숫자 모두 제거
    t = to_keyword_form("오늘 삼성전자는 85,400원에 마감했습니다.")
    assert "오늘" not in t
    assert "85,400" not in t
    assert "마감했습니다" not in t

    # compress_line: 18자 초과 시 단어 경계에서 트림
    long_line = compress_line("미래에셋증권과 키움증권은 목표주가를 상향 조정했다고 분석했습니다", max_chars=18)
    assert len(long_line) <= 20  # 단어 경계 컷이라 약간의 여유는 허용
    short_line = compress_line("코스피 상승 마감", max_chars=18)
    assert short_line == "코스피 상승 마감"

    # compress_to_screen_text: 기본 케이스
    lines = compress_to_screen_text(
        headline_base="삼성전자 실적 기대감에 상승",
        narration="다음은 삼성전자 분석입니다. 미래에셋증권은 목표주가를 상향했습니다.",
        entities=["삼성전자", "반도체"],
    )
    assert 1 <= len(lines) <= 2
    assert lines != ["다음은 삼성전자 분석입니다. 미래에셋증권은 목표주가를 상향했습니다."]

    # compress_to_screen_text: headline_base가 비어있으면 빈 리스트
    assert compress_to_screen_text(headline_base="") == []

    # compress_to_screen_text: headline과 narration이 완전히 동일하면 entity로 폴백
    lines2 = compress_to_screen_text(
        headline_base="상승",
        narration="상승",
        entities=["삼성전자", "반도체"],
    )
    assert lines2 and lines2[0] != ""

    print("✅ screen_text 테스트 통과")


if __name__ == "__main__":
    run()
