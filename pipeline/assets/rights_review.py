"""
자산 권리(rights) 분류 — MediaCandidate 하나를 보고 (rights_status, needs_review)를
판정한다. 자동 렌더링에 쓸지(needs_review=False) 사람 검수를 거쳐야 하는지
(needs_review=True)를 이 판정 결과가 결정한다(media_pipeline.select_best_image()가
소비).

사용자와 확인한 원칙:
- YONHAP/KBS_WEBSITE(현재 공개 검색 페이지 스크래핑 방식)는 지금 동작을
  유지한다 — editorial_search도 needs_review=False(자동 사용 가능)로 둔다.
  실제 계약 API 키가 생기면 license가 "api_licensed"/"contracted"로 바뀔 뿐
  needs_review 판정 로직은 그대로 재사용된다.
- 네이버 discovery(NaverDiscoveryConnector)는 네이버 뉴스 검색으로 연합뉴스/
  KBS 원문 기사를 찾아 그 페이지의 og:image를 직접 추출하므로, 원문 도메인이
  확인된 후보는 asset_source를 YONHAP/KBS_WEBSITE로 재태깅해 그 두 소스와
  동일하게 취급한다(아래 규칙이 그대로 적용됨). asset_source가 여전히
  NAVER_DISCOVERY로 남아있는 경우(원문 도메인을 확인 못한 레거시/예외 상황)만
  아래에서 항상 검수 대상으로 처리한다.
- 외신(is_foreign_agency=True)은 소스가 무엇이든 항상 검수 대상 — 이 규칙은
  "현재 동작 유지" 결정과 무관하게 예외 없이 적용한다.
- MockProvider(license=="mock")는 오프라인 테스트/시뮬레이션 데이터이므로
  항상 사용 가능 처리한다(실제 저작권 대상이 아님).
"""
from .media_providers import MediaCandidate

_FOREIGN_AGENCY_DOMAINS = (
    "afp.com", "reuters.com", "apimages.com", "ap.org", "epa.eu", "gettyimages.com",
)


def looks_foreign_agency(url: str) -> bool:
    url = (url or "").lower()
    return any(domain in url for domain in _FOREIGN_AGENCY_DOMAINS)


def classify_rights(candidate: MediaCandidate) -> tuple:
    """(rights_status, needs_review) 반환."""
    if candidate.license == "mock":
        return "cleared", False

    is_foreign = candidate.is_foreign_agency or looks_foreign_agency(candidate.url) or looks_foreign_agency(candidate.source_url)
    if is_foreign:
        return "needs_review", True

    src = candidate.asset_source
    if src == "NAVER_DISCOVERY":
        return "unclear", True
    if src in ("YONHAP", "KBS_WEBSITE"):
        status = candidate.license if candidate.license not in ("", "unknown") else "editorial_search"
        return status, False
    if src in ("KBS_INTERNAL", "KBS_BADA", "PUBLIC_AGENCY", "STOCK", "GENERATED_ABSTRACT"):
        return "cleared", False
    if src == "OFFICIAL_COMPANY":
        # 실제 이미지가 아니라 출처 페이지 링크만 제공하므로(download()가 항상
        # None) 렌더링 후보로 선택될 일이 없지만, 명시적으로 검수 대상으로 표시.
        return "needs_review", True
    return "unclear", True


def apply_rights(candidate: MediaCandidate) -> MediaCandidate:
    """candidate.rights_status/needs_review를 분류 결과로 채워 반환한다."""
    rights_status, needs_review = classify_rights(candidate)
    candidate.rights_status = rights_status
    candidate.needs_review = needs_review
    return candidate
