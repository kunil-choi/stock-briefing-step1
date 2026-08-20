# tests/test_korean_numbers.py
"""
assets.korean_numbers.py 검증 스크립트(정수/소수/연도/금액 한글 발음 변환).
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크/ffmpeg
불필요(순수 함수).

실행: python tests/test_korean_numbers.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.korean_numbers import (  # noqa: E402
    read_integer_ko, read_decimal_numbers_ko, read_year_numbers_ko, read_won_amounts_ko,
    read_jeonil_date_ko,
)


def test_read_integer_ko_basic_values():
    assert read_integer_ko(0) == "영"
    assert read_integer_ko(3000) == "삼천"
    assert read_integer_ko(1103) == "천백삼"
    assert read_integer_ko(259) == "이백오십구"
    print("✅ read_integer_ko: 기본 값 확인")


def test_read_won_amounts_ko_comma_grouped():
    """사용자 피드백(2026-08-13): "1,103억원"을 TTS가 "천....삼억원"처럼
    불분명하게 읽던 문제 — 콤마 구분 금액이 정확히 풀어써져야 한다."""
    assert read_won_amounts_ko("시가총액은 1,103억원입니다.") == "시가총액은 천백삼억원입니다."
    assert read_won_amounts_ko("매출은 259만원 증가했습니다.") == "매출은 이백오십구만원 증가했습니다."
    print("✅ read_won_amounts_ko: 콤마 구분 금액 정확히 변환")


def test_read_won_amounts_ko_plain_digits_without_comma():
    """콤마 없는 4자리 이상 숫자(예: 3000억원)도 전체 자릿수가 매치돼야 한다
    — 정규식이 단위 앞 최대 3자리만 욕심껏 집어삼키다 실패해 뒷부분만 매치되는
    회귀(예: "3000억원" → "3영억원")가 없어야 한다."""
    assert read_won_amounts_ko("부채는 3000억원입니다.") == "부채는 삼천억원입니다."
    assert read_won_amounts_ko("부채는 12조3000억원입니다.") == "부채는 12조삼천억원입니다."
    print("✅ read_won_amounts_ko: 콤마 없는 숫자도 전체 자릿수 정확히 변환")


def test_read_won_amounts_ko_leaves_plain_won_untouched():
    """만/억/조 단위가 없는 순수 "숫자원"은 이미 TTS가 올바르게 읽고 있어
    건드리지 않는다(의도적으로 범위를 좁힘)."""
    assert read_won_amounts_ko("가격은 259,000원입니다.") == "가격은 259,000원입니다."
    print("✅ read_won_amounts_ko: 단위 없는 순수 금액은 건드리지 않음")


def test_won_amount_after_decimal_conversion_no_corruption():
    """apply_pronunciation_rules()와 동일한 순서(소수점 변환 → 금액 변환)로
    적용했을 때, "1.5억원"처럼 소수부 뒤에 단위가 붙은 경우가 깨지지 않아야
    한다 — 금액 변환이 소수점 변환보다 먼저 실행되면 소수부 숫자만 따로
    떼어 잘못 매치하는 사고가 날 수 있다."""
    text = "시가총액은 1.5억원 수준입니다."
    after_decimal = read_decimal_numbers_ko(text)
    result = read_won_amounts_ko(after_decimal)
    assert result == "시가총액은 일쩜오억원 수준입니다.", result
    print("✅ 소수점 변환 이후 금액 변환을 적용해도 깨지지 않음")


def test_read_year_numbers_ko():
    assert read_year_numbers_ko("2028년까지") == "이천이십팔년까지"
    print("✅ read_year_numbers_ko: 연도 변환 확인")


def test_read_jeonil_date_ko():
    """LLM 내레이션이 v3-1 원본 가격 라벨의 "전일(M/D)" 축약 표기를 그대로
    베껴 쓰는 경우가 있다(사용자 피드백) — TTS가 괄호/슬래시를 그대로 읽지
    않도록 "전일인 M월 D일"로 풀어쓴다."""
    assert read_jeonil_date_ko("전일(8/19) 종가 기준") == "전일인 8월 19일 종가 기준"
    assert read_jeonil_date_ko("전일(12/5) 대비") == "전일인 12월 5일 대비"
    assert read_jeonil_date_ko("변화 없음") == "변화 없음"
    print("✅ read_jeonil_date_ko: 전일(M/D) → 전일인 M월 D일 변환")


if __name__ == "__main__":
    test_read_integer_ko_basic_values()
    test_read_won_amounts_ko_comma_grouped()
    test_read_won_amounts_ko_plain_digits_without_comma()
    test_read_won_amounts_ko_leaves_plain_won_untouched()
    test_won_amount_after_decimal_conversion_no_corruption()
    test_read_year_numbers_ko()
    test_read_jeonil_date_ko()
    print("\n✅ korean_numbers 테스트 전체 통과")
