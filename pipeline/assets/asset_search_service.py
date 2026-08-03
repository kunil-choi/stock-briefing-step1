"""
AssetSearchService — scene_plan.json을 입력으로 받아 KBS/연합뉴스(+신규
커넥터)에서 이미지를 검색·선택하고, media_map.json(하위호환)과
asset_manifest.json(권리 정보 포함)을 함께 만드는 오케스트레이터.

내부적으로 기존 media_pipeline.build_scene_images()/build_asset_manifest()를
그대로 재사용한다 — 선택/스코어링/중복방지 로직을 중복 구현하지 않는다.
커넥터 인스턴스화는 환경변수 존재 여부로 자동 결정되며(키가 없는 커넥터는
항상 빈 리스트를 반환하므로 등록해도 안전하다), config/media.yml의
`providers` 목록에 명시된 것만 활성화된다(기존 관례 유지).
"""
import os
from typing import List, Optional

from .media_providers import (
    MediaProvider,
    YonhapProvider,
    KbsProvider,
    MockProvider,
    KbsInternalConnector,
    KbsBadaConnector,
    PublicAgencyConnector,
    OfficialCompanyConnector,
    StockPhotoConnector,
    NaverDiscoveryConnector,
    GeneratedAbstractConnector,
)
from .media_pipeline import build_scene_images, build_asset_manifest

CONNECTOR_REGISTRY = {
    "yonhap": YonhapProvider,
    "kbs": KbsProvider,
    "mock": MockProvider,
    "kbs_internal": KbsInternalConnector,
    "kbs_bada": KbsBadaConnector,
    "public_agency": PublicAgencyConnector,
    "official_company": OfficialCompanyConnector,
    "stock_photo": StockPhotoConnector,
    "naver_discovery": NaverDiscoveryConnector,
    "generated_abstract": GeneratedAbstractConnector,
}


class AssetSearchService:
    """provider_names(config/media.yml의 providers 목록)를 받아 실제
    커넥터를 인스턴스화하고, scene_plan.json 하나에 대해 media_map과
    asset_manifest를 함께 만들어 반환한다."""

    def __init__(self, provider_names: Optional[List[str]] = None,
                 mock_mode: bool = False):
        if mock_mode:
            self.providers: List[MediaProvider] = [MockProvider()]
            return
        names = provider_names or ["yonhap", "kbs"]
        providers = []
        for name in names:
            cls = CONNECTOR_REGISTRY.get(name)
            if cls:
                providers.append(cls())
            else:
                print(f"  [asset_search_service] 알 수 없는 provider 설정 무시: {name}")
        self.providers = providers or [MockProvider()]

    def build_for_scene_plan(self, scene_plan: dict, img_dir: str, log_path: str,
                              cache_dir: Optional[str] = None,
                              dedup_window_days: Optional[int] = None,
                              dedup_threshold: Optional[int] = None,
                              max_candidates: Optional[int] = None) -> tuple:
        """(media_map, asset_manifest) 튜플을 반환한다."""
        kwargs = {}
        if dedup_window_days is not None:
            kwargs["dedup_window_days"] = dedup_window_days
        if dedup_threshold is not None:
            kwargs["dedup_threshold"] = dedup_threshold
        if max_candidates is not None:
            kwargs["max_candidates"] = max_candidates

        manifest_rows: list = []
        media_map = build_scene_images(
            scene_plan, img_dir, self.providers, log_path,
            cache_dir=cache_dir, manifest_rows=manifest_rows, **kwargs,
        )
        asset_manifest = build_asset_manifest(manifest_rows)
        return media_map, asset_manifest
