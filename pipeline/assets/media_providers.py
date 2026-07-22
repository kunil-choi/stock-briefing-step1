# pipeline/assets/media_providers.py
"""
MediaProvider 추상화 — scene_plan.json의 visual_keywords로 연합뉴스/KBS에서
뉴스 이미지를 검색하는 provider들과, 네트워크 없이 테스트 가능한 MockProvider.

기존 image_fetch.py(종목명 단일 키워드로 첫 성공 이미지를 즉시 다운로드하는
방식)와 달리, 여기서는 search()가 후보 목록(메타데이터만)을 반환하고
media_pipeline.py가 여러 후보를 점수화해 최적 이미지를 선택한다.
"""
import hashlib
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from typing import List, Optional

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


@dataclass
class MediaCandidate:
    url: str
    source: str                     # provider name: yonhap / kbs / mock
    keyword: str = ""
    title: str = ""
    published_at: Optional[datetime] = None
    license: str = "unknown"        # api_licensed | editorial_search | mock

    # ── 2차 작업(AssetSearchService/권리검수) 확장 필드 ──────────────────────
    # 전부 기본값이 있어 기존 MediaCandidate(...) 생성 코드/테스트에 영향 없음.
    asset_source: str = ""          # scene_plan.AssetSource 8종과 일치하는 표준 소스명
    credit: str = ""
    photographer: str = ""
    source_url: str = ""
    download_url: str = ""
    caption: str = ""
    rights_status: str = "unclear"  # cleared|contracted|internal_only|needs_review|unclear|rejected
    allowed_platforms: List[str] = field(default_factory=list)
    restrictions: List[str] = field(default_factory=list)
    contains_person: bool = False
    contains_logo: bool = False
    is_foreign_agency: bool = False
    needs_review: bool = True
    search_query: str = ""


class MediaProvider(ABC):
    name: str = "base"
    # scene_plan.AssetSource 8종과 일치하는 표준 소스명(클래스 상수) — preferredSources
    # 순서로 provider를 정렬할 때, 후보를 만들지 않고도 바로 조회할 수 있게 한다.
    asset_source: str = ""

    @abstractmethod
    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        """키워드에 대한 이미지 후보 메타데이터 목록을 반환합니다(다운로드는
        하지 않음). 실패 시 빈 리스트를 반환합니다(예외를 밖으로 던지지 않음)."""
        ...

    def download(self, candidate: MediaCandidate) -> Optional[bytes]:
        """후보 이미지를 실제로 내려받습니다. 5KB 미만이거나 image/* 응답이
        아니면 실패로 간주해 None을 반환합니다."""
        try:
            r = requests.get(candidate.url, headers=HEADERS, timeout=10)
            content_type = r.headers.get("Content-Type", "")
            if r.status_code == 200 and len(r.content) > 5000 and "image" in content_type:
                return r.content
        except Exception as e:
            print(f"  [media:{self.name}] 다운로드 실패 ({candidate.url[:60]}): {e}")
        return None


class YonhapProvider(MediaProvider):
    """연합뉴스 검색 결과에서 이미지를 찾는다. YONHAP_API_KEY가 .env에 있으면
    인증 헤더를 실어 보내지만(향후 정식 계약 API를 위한 플러그인 지점),
    현재 공개적으로 문서화된 연합뉴스 인증 이미지 API는 없으므로 실제로는
    공개 검색 페이지 스크래핑으로 동작한다(license="editorial_search")."""
    name = "yonhap"
    asset_source = "YONHAP"

    def __init__(self):
        self.api_key = os.environ.get("YONHAP_API_KEY", "")

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        try:
            url = f"https://www.yna.co.kr/search/index?query={requests.utils.quote(keyword)}&period=D7"
            headers = dict(HEADERS)
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return []
            img_urls = re.findall(r"https://img\.yna\.co\.kr/etc/inner/[A-Z0-9/]+\.jpg", r.text)
            if not img_urls:
                img_urls = re.findall(r"https://img\.yna\.co\.kr/photo/[A-Z0-9/]+\.jpg", r.text)
            license_ = "api_licensed" if self.api_key else "editorial_search"
            return [
                MediaCandidate(url=u, source=self.name, keyword=keyword, license=license_,
                                asset_source="YONHAP", source_url=url, search_query=keyword,
                                credit="사진: 연합뉴스")
                for u in img_urls[:count]
            ]
        except Exception as e:
            print(f"  [media:yonhap] 검색 실패 ({keyword}): {e}")
            return []


class KbsProvider(MediaProvider):
    """KBS 뉴스 검색(JSON API 우선, 실패 시 HTML 검색)에서 이미지를 찾는다.
    KBS_API_KEY가 있으면 인증 헤더를 실어 보낸다(YonhapProvider와 동일한 이유로
    현재는 플러그인 지점 성격)."""
    name = "kbs"
    asset_source = "KBS_WEBSITE"

    def __init__(self):
        self.api_key = os.environ.get("KBS_API_KEY", "")

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        headers = dict(HEADERS)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        license_ = "api_licensed" if self.api_key else "editorial_search"

        candidates: List[MediaCandidate] = []
        try:
            api_url = (f"https://news.kbs.co.kr/api/search/news?q={requests.utils.quote(keyword)}"
                       f"&page=1&per_page={count}")
            r = requests.get(api_url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items") or data.get("data") or []
                for item in items[:count]:
                    img_url = item.get("image_url") or item.get("thumbnail")
                    if img_url:
                        candidates.append(MediaCandidate(
                            url=img_url, source=self.name, keyword=keyword,
                            title=item.get("title", ""), license=license_,
                            asset_source="KBS_WEBSITE", source_url=api_url,
                            search_query=keyword, credit="사진: KBS",
                        ))
        except Exception as e:
            print(f"  [media:kbs] API 검색 실패 ({keyword}): {e}")

        if candidates:
            return candidates

        try:
            html_url = f"https://news.kbs.co.kr/news/search.do?searchKeyword={requests.utils.quote(keyword)}"
            r = requests.get(html_url, headers=headers, timeout=10)
            if r.status_code == 200:
                img_urls = re.findall(r"https://[a-zA-Z0-9./\-_]+\.(?:jpg|jpeg|png)", r.text)
                for u in img_urls:
                    if "thumbnail" in u or "news" in u:
                        candidates.append(MediaCandidate(
                            url=u, source=self.name, keyword=keyword, license=license_,
                            asset_source="KBS_WEBSITE", source_url=html_url,
                            search_query=keyword, credit="사진: KBS",
                        ))
                    if len(candidates) >= count:
                        break
        except Exception as e:
            print(f"  [media:kbs] HTML 검색 실패 ({keyword}): {e}")
        return candidates


class MockProvider(MediaProvider):
    """네트워크 없이 결정적(deterministic) 합성 이미지를 만드는 테스트용
    provider. search()는 키워드+인덱스로 고유한 mock:// URL을 생성하고,
    download()는 실제 요청 대신 PIL로 색상/크기가 결정적으로 정해지는 이미지를
    그 자리에서 그린다(가로형/세로형이 섞이도록 인덱스에 따라 번갈아 생성해
    스코어링 로직의 가로형 선호를 테스트할 수 있게 한다)."""
    name = "mock"
    asset_source = "GENERATED_ABSTRACT"  # 오프라인 테스트 데이터 — rights_review에서 license=="mock"으로 별도 판별

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        return [
            MediaCandidate(
                url=f"mock://{keyword}-{i}",
                source=self.name,
                keyword=keyword,
                title=f"mock image for {keyword} #{i}",
                published_at=datetime.now(),
                license="mock",
            )
            for i in range(count)
        ]

    def download(self, candidate: MediaCandidate) -> Optional[bytes]:
        from PIL import Image

        # 단색 이미지는 pHash가 저주파(DCT) 성분만 보므로 색만 달라도 거의 같은
        # 해시가 나와 서로 다른 mock 이미지를 구분하지 못한다. 해시 바이트로
        # 8x8 블록 패턴을 만들어 실제 공간 주파수 차이를 부여한다.
        digest = hashlib.sha256(candidate.url.encode()).digest()
        landscape = digest[0] % 2 == 0
        size = (1280, 720) if landscape else (720, 1280)

        grid = 8
        small = Image.new("RGB", (grid, grid))
        px = small.load()
        for y in range(grid):
            for x in range(grid):
                v = digest[(y * grid + x) % len(digest)]
                px[x, y] = (v, (v * 3) % 256, (v * 7) % 256)
        img = small.resize(size, Image.NEAREST)

        buf = BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 2차 작업: AssetSearchService용 신규 커넥터
#
# KBS_INTERNAL/KBS_BADA/PUBLIC_AGENCY/OFFICIAL_COMPANY는 이 세션에서 실제 API
# 스펙이나 인증 정보에 접근할 수 없어, 필요한 환경변수가 없으면 항상 빈
# 리스트를 반환하는 "비활성 상태"로 구현한다(에러를 던지지 않음). 환경변수가
# 채워지면 바로 동작을 시도하도록 요청 스켈레톤만 남겨둔다. StockPhotoConnector
# (Pexels)와 NaverDiscoveryConnector(네이버 오픈API)는 공개 문서화된 API라
# 키만 있으면 실제로 동작한다.
# ─────────────────────────────────────────────────────────────────────────────


class KbsInternalConnector(MediaProvider):
    """KBS 내부망/내부 아카이브 커넥터. KBS_INTERNAL_API_BASE_URL/
    KBS_INTERNAL_API_KEY가 없으면(이 세션 기본 상태) 항상 빈 리스트를 반환한다
    — 사내망 접근 권한이 없는 환경에서 안전하게 비활성화되도록."""
    name = "kbs_internal"
    asset_source = "KBS_INTERNAL"

    def __init__(self):
        self.base_url = os.environ.get("KBS_INTERNAL_API_BASE_URL", "")
        self.api_key = os.environ.get("KBS_INTERNAL_API_KEY", "")

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        if not self.base_url or not self.api_key:
            return []
        try:
            r = requests.get(
                f"{self.base_url.rstrip('/')}/search",
                params={"q": keyword, "count": count},
                headers={**HEADERS, "Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            items = (r.json().get("items") or [])[:count]
            return [
                MediaCandidate(
                    url=item.get("url", ""), source=self.name, keyword=keyword,
                    title=item.get("title", ""), license="internal",
                    asset_source="KBS_INTERNAL", source_url=item.get("source_url", ""),
                    search_query=keyword, credit="KBS 내부 자료",
                )
                for item in items if item.get("url")
            ]
        except Exception as e:
            print(f"  [media:kbs_internal] 검색 실패 ({keyword}): {e}")
            return []


class KbsBadaConnector(MediaProvider):
    """KBS 바다(bada.kbs.co.kr) 커넥터. KBS_BADA_API_KEY가 없으면 비활성."""
    name = "kbs_bada"
    asset_source = "KBS_BADA"

    def __init__(self):
        self.base_url = os.environ.get("KBS_BADA_BASE_URL", "https://bada.kbs.co.kr")
        self.api_key = os.environ.get("KBS_BADA_API_KEY", "")

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        if not self.api_key:
            return []
        try:
            r = requests.get(
                f"{self.base_url.rstrip('/')}/api/search",
                params={"q": keyword, "count": count},
                headers={**HEADERS, "Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            items = (r.json().get("items") or [])[:count]
            return [
                MediaCandidate(
                    url=item.get("url", ""), source=self.name, keyword=keyword,
                    title=item.get("title", ""), license="cleared",
                    asset_source="KBS_BADA", source_url=item.get("source_url", ""),
                    search_query=keyword, credit="KBS 바다",
                )
                for item in items if item.get("url")
            ]
        except Exception as e:
            print(f"  [media:kbs_bada] 검색 실패 ({keyword}): {e}")
            return []


class PublicAgencyConnector(MediaProvider):
    """공공기관 공식 이미지(공공누리 등) 커넥터. 정식 연동 API가 아직 없어
    현재는 항상 빈 리스트를 반환하는 스켈레톤이다."""
    name = "public_agency"
    asset_source = "PUBLIC_AGENCY"

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        return []


# 종목명 → 공식 보도자료/IR 페이지 URL (참고용 예시. 실제 이미지 다운로드
# API가 아니라 사람이 검수 시 참고할 출처 링크 역할까지만 한다).
OFFICIAL_COMPANY_PRESS_URLS = {
    "삼성전자": "https://news.samsung.com/kr/",
    "SK하이닉스": "https://news.skhynix.co.kr/",
    "카카오": "https://www.kakaocorp.com/page/newsroom",
}


class OfficialCompanyConnector(MediaProvider):
    """기업 공식 보도자료/IR 페이지 커넥터. 실제 이미지 다운로드 자동화 없이,
    OFFICIAL_COMPANY_PRESS_URLS에 등록된 종목만 출처 링크 후보를 만든다(실제
    이미지 URL이 아니라 사람이 확인할 페이지 링크 — needs_review=True로 항상
    표시돼 자동 렌더링에는 쓰이지 않는다)."""
    name = "official_company"
    asset_source = "OFFICIAL_COMPANY"

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        press_url = OFFICIAL_COMPANY_PRESS_URLS.get(keyword)
        if not press_url:
            return []
        return [MediaCandidate(
            url="", source=self.name, keyword=keyword, title=f"{keyword} 공식 보도자료 페이지",
            license="cleared", asset_source="OFFICIAL_COMPANY", source_url=press_url,
            search_query=keyword, credit=f"{keyword} 공식",
        )]

    def download(self, candidate: MediaCandidate) -> Optional[bytes]:
        return None  # 페이지 링크만 제공 — 실제 이미지 자동 다운로드는 하지 않음


class StockPhotoConnector(MediaProvider):
    """Pexels 스톡 이미지 커넥터(공개 문서화된 API). PEXELS_API_KEY가 없으면
    비활성. 클래스명에 "Photo"를 명시해 이 레포의 지배적 어휘인 종목(equity
    stock)과 구분한다. visualKeywordsEn(영어 키워드)로 검색해야 한다."""
    name = "stock_photo"
    asset_source = "STOCK"

    def __init__(self):
        self.api_key = os.environ.get("PEXELS_API_KEY", "")

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        if not self.api_key:
            return []
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "per_page": count},
                headers={"Authorization": self.api_key},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            photos = (r.json().get("photos") or [])[:count]
            return [
                MediaCandidate(
                    url=p.get("src", {}).get("large", ""), source=self.name, keyword=keyword,
                    title=p.get("alt", ""), license="cleared",
                    asset_source="STOCK", source_url=p.get("url", ""),
                    search_query=keyword, credit=f"Photo by {p.get('photographer', 'Pexels')}",
                    photographer=p.get("photographer", ""),
                )
                for p in photos if p.get("src", {}).get("large")
            ]
        except Exception as e:
            print(f"  [media:stock_photo] 검색 실패 ({keyword}): {e}")
            return []


_OGIMAGE_RE = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.IGNORECASE),
]


def _parse_og_image_from_html(html: str) -> str:
    """HTML 문자열에서 og:image 메타태그의 이미지 URL을 뽑는 순수 함수(네트워크
    없음, 테스트 용이). 속성 순서(content가 먼저/나중)가 사이트마다 달라 두
    패턴을 모두 시도한다."""
    for pattern in _OGIMAGE_RE:
        m = pattern.search(html or "")
        if m:
            return m.group(1)
    return ""


def _extract_og_image(article_url: str) -> str:
    """기사 페이지를 실제로 내려받아 og:image를 추출한다(네트워크 필요)."""
    try:
        r = requests.get(article_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return ""
        return _parse_og_image_from_html(r.text)
    except Exception as e:
        print(f"  [media:naver_discovery] og:image 추출 실패 ({article_url[:60]}): {e}")
    return ""


def _parse_naver_pubdate(pub_date: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(pub_date) if pub_date else None
    except Exception:
        return None


class NaverDiscoveryConnector(MediaProvider):
    """네이버 뉴스 검색 API로 연합뉴스/KBS 원문 기사를 찾은 뒤, 그 기사
    페이지의 og:image를 추출해 실제로 다운로드 가능한 이미지 후보를 만든다.

    출처 확인 방법으로 "네이버 이미지 검색 API"가 아니라 "네이버 뉴스 검색
    API + 원문 페이지 og:image 추출"을 쓰는 이유: 네이버 이미지 검색 결과의
    link는 네이버 자체 CDN(pstatic.net 등)으로 프록시되는 경우가 많아 URL만
    보고 원 출처 도메인을 신뢰하기 어렵다. 뉴스 검색 API의 link/originallink는
    언론사 원문 URL 그대로이므로 yna.co.kr/kbs.co.kr인지 확실히 판별할 수
    있고, 그 페이지에서 직접 뽑은 og:image는 그 기사의 대표 사진이 맞다는
    보장이 있다.

    일단 원문이 yna.co.kr/kbs.co.kr로 확인되면, 이후 신뢰도·권리 판정은
    YonhapProvider/KbsProvider와 완전히 동일하게 취급한다(asset_source를
    "YONHAP"/"KBS_WEBSITE"로 설정 — rights_review.classify_rights()가 이미
    이 두 값을 editorial_search/needs_review=False로 자동 승인 처리한다).
    이 커넥터 자체가 발견한 이미지가 아니라, "연합뉴스/KBS 원문 페이지에서
    직접 가져온 이미지"이므로 같은 신뢰 등급이 맞다 — NAVER_DISCOVERY라는
    별도 미확인 등급을 쓸 이유가 없다(og:image 추출에 실패해 원문 이미지를
    확인 못한 경우에만 이 후보를 아예 만들지 않고 건너뛴다).

    NAVER_SEARCH_CLIENT_ID/SECRET와 ENABLE_NAVER_DISCOVERY=true가 모두 있어야
    동작한다(둘 다 없으면 빈 리스트 — 기존 도메인 사이트 직접 검색인
    YonhapProvider/KbsProvider가 못 찾은 경우를 보완하는 2차 경로)."""
    name = "naver_discovery"
    asset_source = "NAVER_DISCOVERY"  # search()가 실제로 반환하는 후보는 개별적으로 YONHAP/KBS_WEBSITE로 재설정됨

    _SOURCE_BY_DOMAIN = [("yna.co.kr", "YONHAP", "사진: 연합뉴스"), ("kbs.co.kr", "KBS_WEBSITE", "사진: KBS")]

    def __init__(self):
        self.client_id = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
        self.client_secret = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")
        self.enabled = os.environ.get("ENABLE_NAVER_DISCOVERY", "false").lower() == "true"

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        if not (self.enabled and self.client_id and self.client_secret):
            return []
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                params={"query": keyword, "display": count},
                headers={
                    "X-Naver-Client-Id": self.client_id,
                    "X-Naver-Client-Secret": self.client_secret,
                },
                timeout=10,
            )
            if r.status_code != 200:
                return []
            items = (r.json().get("items") or [])[:count]
            out = []
            for item in items:
                # originallink가 있으면 그게 진짜 언론사 원문(link는 네이버뉴스
                # 자체 페이지로 리다이렉트되는 경우가 흔함) — originallink 우선.
                link = item.get("originallink") or item.get("link", "")
                match = next((m for m in self._SOURCE_BY_DOMAIN if m[0] in link), None)
                if not match:
                    continue  # 연합뉴스/KBS 원문만 발견 대상으로 삼는다(그 외 출처는 무시)
                _, asset_source, credit = match

                image_url = _extract_og_image(link)
                if not image_url:
                    continue  # 원문 확인은 됐지만 대표 이미지를 못 뽑았으면 후보로 만들지 않음

                out.append(MediaCandidate(
                    url=image_url, source=self.name, keyword=keyword,
                    title=re.sub(r"<.*?>", "", item.get("title", "")),
                    published_at=_parse_naver_pubdate(item.get("pubDate", "")),
                    license="editorial_search", asset_source=asset_source, credit=credit,
                    source_url=link, search_query=keyword,
                ))
            return out
        except Exception as e:
            print(f"  [media:naver_discovery] 검색 실패 ({keyword}): {e}")
            return []


class GeneratedAbstractConnector(MediaProvider):
    """모든 실검색이 실패했을 때의 최종 폴백. 기존 config.get_sector_fallback_image()를
    그대로 재사용해 로컬 섹터 추상 그래픽 파일을 candidate로 감싼다(다운로드가
    아니라 로컬 파일 읽기)."""
    name = "generated_abstract"
    asset_source = "GENERATED_ABSTRACT"

    def search(self, keyword: str, count: int = 5) -> List[MediaCandidate]:
        from .config import get_sector_fallback_image
        path = get_sector_fallback_image(keyword)
        if not path:
            return []
        return [MediaCandidate(
            url=f"file://{path}", source=self.name, keyword=keyword,
            title=f"{keyword} 추상 그래픽", license="cleared",
            asset_source="GENERATED_ABSTRACT", search_query=keyword,
            credit="자체 제작 그래픽",
        )]

    def download(self, candidate: MediaCandidate) -> Optional[bytes]:
        path = candidate.url.replace("file://", "", 1)
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None
