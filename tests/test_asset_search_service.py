# tests/test_asset_search_service.py
"""
2차 작업(AssetSearchService/권리검수/asset-manifest.json) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크 불필요
(모두 오프라인 mock/스텁으로 검증).
실행: python tests/test_asset_search_service.py
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.media_providers import (  # noqa: E402
    MediaCandidate, MockProvider, NaverDiscoveryConnector, KbsInternalConnector,
    KbsBadaConnector, PublicAgencyConnector, StockPhotoConnector,
    _parse_og_image_from_html,
)
from assets.rights_review import classify_rights  # noqa: E402
from assets.media_pipeline import (  # noqa: E402
    _order_providers, _keywords_for_section, _cached_download, build_asset_manifest,
)
from assets.asset_search_service import AssetSearchService  # noqa: E402


def test_classify_rights_current_behavior_preserved_for_real_connectors():
    yonhap_no_key = MediaCandidate(url="https://img.yna.co.kr/x.jpg", source="yonhap",
                                    asset_source="YONHAP", license="editorial_search")
    status, needs_review = classify_rights(yonhap_no_key)
    assert status == "editorial_search"
    assert needs_review is False, "사용자 확인: 현재 동작(자동 사용) 유지돼야 함"

    kbs_website = MediaCandidate(url="https://news.kbs.co.kr/x.jpg", source="kbs",
                                  asset_source="KBS_WEBSITE", license="editorial_search")
    assert classify_rights(kbs_website) == ("editorial_search", False)
    print("✅ classify_rights: YONHAP/KBS_WEBSITE editorial_search는 현재 동작(자동 사용) 유지")


def test_classify_rights_naver_discovery_always_review():
    cand = MediaCandidate(url="", source="naver_discovery", asset_source="NAVER_DISCOVERY",
                           license="unclear")
    status, needs_review = classify_rights(cand)
    assert status == "unclear"
    assert needs_review is True, "네이버 discovery는 직접 렌더링 후보로 취급하면 안 됨"
    print("✅ classify_rights: NAVER_DISCOVERY는 항상 검수 대상")


def test_classify_rights_foreign_agency_always_review():
    cand = MediaCandidate(url="https://www.reuters.com/photo.jpg", source="kbs",
                           asset_source="KBS_WEBSITE", license="editorial_search")
    status, needs_review = classify_rights(cand)
    assert needs_review is True, "외신 사진은 소스와 무관하게 항상 검수 대상이어야 함"

    cand2 = MediaCandidate(url="https://img.yna.co.kr/x.jpg", source="yonhap",
                            asset_source="YONHAP", license="editorial_search",
                            is_foreign_agency=True)
    assert classify_rights(cand2)[1] is True
    print("✅ classify_rights: 외신(URL 휴리스틱 또는 명시 플래그)은 항상 검수 대상")


def test_classify_rights_mock_always_usable():
    cand = MediaCandidate(url="mock://x-0", source="mock", license="mock")
    assert classify_rights(cand) == ("cleared", False)
    print("✅ classify_rights: MockProvider 데이터는 항상 사용 가능(오프라인 테스트 데이터)")


def test_mock_only_connectors_disabled_without_env():
    for env_key in ("KBS_INTERNAL_API_BASE_URL", "KBS_INTERNAL_API_KEY",
                     "KBS_BADA_API_KEY", "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET",
                     "ENABLE_NAVER_DISCOVERY", "PEXELS_API_KEY"):
        os.environ.pop(env_key, None)

    assert KbsInternalConnector().search("삼성전자") == []
    assert KbsBadaConnector().search("삼성전자") == []
    assert PublicAgencyConnector().search("삼성전자") == []
    assert NaverDiscoveryConnector().search("삼성전자") == []
    assert StockPhotoConnector().search("semiconductor") == []
    print("✅ 실 API 키/설정이 없으면 신규 커넥터가 안전하게 빈 리스트를 반환(비활성)")


def test_naver_discovery_resolves_confirmed_source_to_yonhap_kbs():
    # FIX-NAVER-DISCOVERY-1: 예전에는 discovery 전용(download()가 항상 None)
    # 이었지만, 이제는 네이버 뉴스 검색으로 찾은 연합뉴스/KBS 원문 기사의
    # og:image를 직접 추출해 실제로 다운로드 가능한 이미지 후보를 만든다.
    # download()가 더 이상 오버라이드돼 있지 않으므로 기본 MediaProvider.download()
    # (일반 HTTP GET)를 그대로 상속받는다.
    conn = NaverDiscoveryConnector()
    assert "download" not in NaverDiscoveryConnector.__dict__, (
        "download()를 더 이상 오버라이드하지 않아야 함 — 실제로 이미지를 받아야 하므로 "
        "기본 MediaProvider.download() 동작(HTTP GET)을 그대로 써야 한다"
    )
    print("✅ NaverDiscoveryConnector: og:image로 확인된 이미지는 기본 download() 경로로 실제 다운로드됨")


def test_parse_og_image_from_html_handles_both_attribute_orders():
    html_content_last = '<meta property="og:image" content="https://img.yna.co.kr/photo/1.jpg">'
    html_content_first = "<meta content='https://news.kbs.co.kr/img/2.jpg' property='og:image'>"
    assert _parse_og_image_from_html(html_content_last) == "https://img.yna.co.kr/photo/1.jpg"
    assert _parse_og_image_from_html(html_content_first) == "https://news.kbs.co.kr/img/2.jpg"
    assert _parse_og_image_from_html("<html><body>no meta here</body></html>") == ""
    print("✅ _parse_og_image_from_html: content/property 속성 순서 둘 다 처리, 없으면 빈 문자열")


def test_order_providers_by_preferred_sources():
    providers = [MockProvider()]  # asset_source="GENERATED_ABSTRACT"
    ordered = _order_providers(providers, ["YONHAP", "GENERATED_ABSTRACT"])
    assert ordered[0].asset_source == "GENERATED_ABSTRACT"

    # preferredSources가 없으면 원래 순서 그대로(기존 동작 불변)
    assert _order_providers(providers, []) == providers
    print("✅ _order_providers: preferredSources 순서를 반영, 없으면 원래 순서 유지")


def test_keywords_for_section_needs_data_review_gate():
    sec = {
        "visual_keywords": ["뉴스경제방송유튜브"],
        "visualKeywordsEn": ["business chart"],
    }
    normal = _keywords_for_section(sec, restrict_to_stock_fallback=False)
    assert "뉴스경제방송유튜브" in normal and "business chart" in normal

    restricted = _keywords_for_section(sec, restrict_to_stock_fallback=True)
    assert restricted == ["business chart"], (
        "needsDataReview일 때는 오염된 한국어 종목명으로 검색하면 안 되고 영어 키워드만 써야 함"
    )
    print("✅ _keywords_for_section: needsDataReview 게이트가 한국어 종목명 검색을 차단함")


def test_cached_download_avoids_repeat_download():
    calls = {"n": 0}

    class _CountingProvider(MockProvider):
        def download(self, candidate):
            calls["n"] += 1
            return super().download(candidate)

    provider = _CountingProvider()
    cand = MediaCandidate(url="mock://cache-test-0", source="mock", asset_source="GENERATED_ABSTRACT")

    with tempfile.TemporaryDirectory() as cache_dir:
        content1 = _cached_download(provider, cand, cache_dir)
        content2 = _cached_download(provider, cand, cache_dir)
        assert content1 == content2
        assert calls["n"] == 1, "같은 URL은 캐시에서 재사용하고 재다운로드하면 안 됨"
    print("✅ _cached_download: 같은 URL 재요청 시 캐시를 재사용(중복 다운로드 없음)")


def test_asset_search_service_end_to_end_mock():
    scene_plan = {
        "title": "테스트", "date": "2026-07-21",
        "sections": [
            {"id": "stock_삼성전자", "label": "종목 분석 - 삼성전자",
             "visual_keywords": ["삼성전자"], "visualKeywordsEn": ["Samsung Electronics"],
             "preferredSources": [], "needsDataReview": False,
             "assetRequirements": {"allowStockFallback": True}, "entities": []},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        img_dir = os.path.join(tmp, "media")
        log_path = os.path.join(tmp, "license_log.csv")
        service = AssetSearchService(mock_mode=True)
        media_map, manifest = service.build_for_scene_plan(scene_plan, img_dir, log_path)

        assert "stock_삼성전자" in media_map
        assert manifest["assets"], "asset_manifest에 검토된 후보가 기록돼야 함"
        selected_rows = [a for a in manifest["assets"] if a["selected"]]
        assert len(selected_rows) == 1
        assert selected_rows[0]["sceneId"] == "stock_삼성전자"
        assert selected_rows[0]["localPath"] == media_map["stock_삼성전자"]["image_path"]
        for a in manifest["assets"]:
            assert set(a.keys()) >= {
                "assetId", "sceneId", "source", "type", "title", "credit", "sourceUrl",
                "localPath", "searchQuery", "rightsStatus", "allowedPlatforms",
                "restrictions", "needsReview", "selected",
            }
    print("✅ AssetSearchService.build_for_scene_plan: media_map/asset_manifest 동시 생성 확인")


def test_build_asset_manifest_wraps_rows():
    manifest = build_asset_manifest([{"assetId": "a"}], project="test-proj")
    assert manifest["project"] == "test-proj"
    assert manifest["assets"] == [{"assetId": "a"}]
    assert "generatedAt" in manifest
    print("✅ build_asset_manifest: 최상위 구조(generatedAt/project/assets) 확인")


if __name__ == "__main__":
    test_classify_rights_current_behavior_preserved_for_real_connectors()
    test_classify_rights_naver_discovery_always_review()
    test_classify_rights_foreign_agency_always_review()
    test_classify_rights_mock_always_usable()
    test_mock_only_connectors_disabled_without_env()
    test_naver_discovery_resolves_confirmed_source_to_yonhap_kbs()
    test_parse_og_image_from_html_handles_both_attribute_orders()
    test_order_providers_by_preferred_sources()
    test_keywords_for_section_needs_data_review_gate()
    test_cached_download_avoids_repeat_download()
    test_asset_search_service_end_to_end_mock()
    test_build_asset_manifest_wraps_rows()
    print("\n✅ asset_search_service 테스트 전체 통과")
