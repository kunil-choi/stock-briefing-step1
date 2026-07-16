# tests/test_quality_gate.py
"""
quality_gate.check_no_placeholder_content() 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반.

실제 운영 중 발견된 사고: 장 개시 전(morning_core) V3_1 시세는 전일종가
기준이라 change_pct가 실제로 0.00%인 종목이 흔한데, "+0.00%"를 placeholder로
취급하는 바람에 정상 데이터가 매번 오탐으로 quality_gate를 막았다
(GitHub Actions 실행 로그: "placeholder 콘텐츠가 화면에 노출될 위험 — 5건").
이 테스트는 그 회귀를 재현/고정한다.

실행: python tests/test_quality_gate.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from quality_gate import check_no_placeholder_content  # noqa: E402


def _write_script(tmp_path, stock_overrides):
    sections = [{
        "id": "stock_삼성전자",
        "price": "279,500",
        "change": "+0.00%",
        "summary": "반도체 수출 호조로 외국인 매수세 지속",
        "corner_summary": "반도체 수출 호조로 외국인 매수 집중",
        **stock_overrides,
    }]
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"sections": sections}, f, ensure_ascii=False)


def test_real_zero_percent_change_not_flagged():
    """장 개시 전 change_pct==0.0(전일종가 기준)은 실제 데이터이지 placeholder가
    아니므로 통과해야 한다 — 이번에 실제로 파이프라인을 막은 회귀 케이스."""
    path = "/tmp/test_qg_ok.json"
    _write_script(path, {})
    check_no_placeholder_content(path)  # SystemExit이 나면 테스트 실패
    print("✅ change='+0.00%'는 실제 값으로 통과함(오탐 아님)")


def test_placeholder_price_detected():
    path = "/tmp/test_qg_price.json"
    _write_script(path, {"price": "000,000"})
    try:
        check_no_placeholder_content(path)
        assert False, "placeholder price를 감지하지 못함"
    except SystemExit:
        pass
    print("✅ price='000,000' placeholder 감지")


def test_placeholder_summary_detected():
    path = "/tmp/test_qg_summary.json"
    _write_script(path, {"summary": "한줄 요약"})
    try:
        check_no_placeholder_content(path)
        assert False, "placeholder summary를 감지하지 못함"
    except SystemExit:
        pass
    print("✅ summary='한줄 요약' placeholder 감지")


def test_placeholder_corner_summary_detected():
    path = "/tmp/test_qg_corner.json"
    _write_script(path, {"corner_summary": "삼성전자 한줄 요약"})
    try:
        check_no_placeholder_content(path)
        assert False, "placeholder corner_summary를 감지하지 못함"
    except SystemExit:
        pass
    print("✅ corner_summary='{종목명} 한줄 요약' placeholder 감지")


def test_empty_price_detected():
    """stock_market_data 조회가 실패해 price가 빈 문자열로 남은 경우도 잡아야 한다."""
    path = "/tmp/test_qg_empty.json"
    _write_script(path, {"price": ""})
    try:
        check_no_placeholder_content(path)
        assert False, "빈 price를 감지하지 못함"
    except SystemExit:
        pass
    print("✅ price='' (빈 값) 감지")


def test_aggregate_sections_not_flagged():
    """stock_추가관심종목/stock_오늘의픽/stock_증권사리포트는 items:[{name,text}]
    구조라 price/change/summary/corner_summary 필드 자체가 없다. id가
    "stock_"로 시작한다고 개별 종목 카드와 동일하게 검사하면, 실제 운영 중
    발견된 것처럼 정상 섹션이 매번 "빈 값"으로 오탐된다(SCRIPT_MOCK 드라이런
    중 재현됨)."""
    path = "/tmp/test_qg_aggregate.json"
    sections = [
        {
            "id": "stock_추가관심종목",
            "corner_summary": "추가 관심 종목 한줄 요약",
            "items": [{"name": "카카오", "text": "더미 설명"}],
        },
        {
            "id": "stock_오늘의픽",
            "corner_summary": "오늘의 픽 한줄 요약",
            "items": [{"name": "삼성전기", "text": "더미 설명"}],
        },
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sections": sections}, f, ensure_ascii=False)
    check_no_placeholder_content(path)  # SystemExit이 나면 테스트 실패
    print("✅ 집계 섹션(stock_추가관심종목/stock_오늘의픽)은 price/change/summary 검사에서 제외됨")


if __name__ == "__main__":
    test_real_zero_percent_change_not_flagged()
    test_placeholder_price_detected()
    test_placeholder_summary_detected()
    test_placeholder_corner_summary_detected()
    test_empty_price_detected()
    test_aggregate_sections_not_flagged()
    print("\n✅ quality_gate placeholder 테스트 전체 통과")
