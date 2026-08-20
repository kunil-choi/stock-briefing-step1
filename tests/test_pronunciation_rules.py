# tests/test_pronunciation_rules.py
"""
config/pronunciation_ko.yml + config_audio.apply_pronunciation_rules() 검증
스크립트. pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크
불필요(순수 문자열 치환).

이 파일이 생기기 전까지는 pronunciation_ko.yml의 개별 단어 규칙을 직접
검증하는 테스트가 없었다 — 규칙 순서가 뒤바뀌면(더 긴 패턴이 뒤에 오면)
조용히 오독으로 되돌아갈 수 있으므로, 사용자가 실제로 지적했던 단어들만이라도
회귀 가드로 남긴다.

실행: python tests/test_pronunciation_rules.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from config_audio import apply_pronunciation_rules  # noqa: E402


def test_dangi_jeogin_and_banghyangseong():
    assert apply_pronunciation_rules("단기적인 부담 요인") == "당기적인 부담 요인"
    assert apply_pronunciation_rules("단기 방향성을 봐야 한다") == "당기 방향성을 봐야 한다"
    print("✅ '단기적인'/'단기 방향성' → '당기적인'/'당기 방향성' 확인")


def test_dangi_generic_rule_unaffected():
    """"단기적인"/"단기 방향성" 전용 규칙을 추가해도, 그 두 표현이 아닌
    일반적인 "단기" 사용(예: "단기 급등")은 기존 동작(공백 삽입)이 그대로
    유지돼야 한다."""
    assert apply_pronunciation_rules("단기 급등") == "단 기 급뜽"
    print("✅ 그 외 '단기' 사용은 기존 규칙(공백 삽입) 그대로 유지됨")


def test_gukchae_geumni():
    assert apply_pronunciation_rules("국채금리 급등") == "국채 금리 급뜽"
    print("✅ '국채금리 급등' → '국채 금리 급뜽' 확인")


def test_gukchae_alone_still_tensified():
    """"국채금리"가 아닌 단독 "국채" 사용은 기존처럼 경음화("국째")된 채로
    유지돼야 한다(이번 수정은 "국채금리" 조합에만 예외를 둔 것)."""
    assert apply_pronunciation_rules("국채 발행이 늘었다") == "국째 발행이 늘었다"
    print("✅ 단독 '국채' 사용은 기존 경음화('국째') 유지됨")


def test_ikwonhui_pronunciation():
    assert apply_pronunciation_rules("이권희 대표") == "이궈니 대표"
    print("✅ '이권희 대표' → '이궈니 대표' 확인(기존 규칙 이미 정상)")


if __name__ == "__main__":
    test_dangi_jeogin_and_banghyangseong()
    test_dangi_generic_rule_unaffected()
    test_gukchae_geumni()
    test_gukchae_alone_still_tensified()
    test_ikwonhui_pronunciation()
    print("\n✅ pronunciation_rules 테스트 전체 통과")
