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
from dataclasses import dataclass
from datetime import datetime
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


class MediaProvider(ABC):
    name: str = "base"

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
                MediaCandidate(url=u, source=self.name, keyword=keyword, license=license_)
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
                        candidates.append(MediaCandidate(url=u, source=self.name, keyword=keyword, license=license_))
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
