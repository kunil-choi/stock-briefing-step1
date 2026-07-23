# pipeline/assets/image_fetch.py
import os
import re
import requests
from typing import List, Optional
from .config import NEWS_IMAGE_FALLBACKS
from .media_providers import NaverDiscoveryConnector

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _try_download(url: str, save_path: str) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        content_type = r.headers.get("Content-Type", "")
        if (
            r.status_code == 200
            and len(r.content) > 5000
            and "image" in content_type
        ):
            with open(save_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


def _search_yonhap(stock_name: str, img_dir: str) -> Optional[str]:
    """연합뉴스에서 종목명 관련 뉴스 이미지를 검색합니다."""
    save_path = os.path.join(img_dir, f"news_{stock_name}.jpg")
    try:
        search_url = f"https://www.yna.co.kr/search/index?query={requests.utils.quote(stock_name)}&period=D7"
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        # 뉴스 이미지 URL 패턴 추출
        img_urls = re.findall(
            r'https://img\.yna\.co\.kr/etc/inner/[A-Z0-9/]+\.jpg',
            r.text
        )
        if not img_urls:
            img_urls = re.findall(
                r'https://img\.yna\.co\.kr/photo/[A-Z0-9/]+\.jpg',
                r.text
            )
        for url in img_urls[:3]:
            if _try_download(url, save_path):
                print(f"  [image] 연합뉴스 이미지: {stock_name} → {url[:70]}")
                return save_path
    except Exception as e:
        print(f"  [image] 연합뉴스 검색 실패 ({stock_name}): {e}")
    return None


def _search_naver_discovery(stock_name: str, img_dir: str) -> Optional[str]:
    """네이버 뉴스 검색 API로 연합뉴스/KBS 원문을 찾아 그 기사의 og:image를
    가져온다(media_providers.NaverDiscoveryConnector 재사용). 원문 도메인을
    직접 확인하므로 아래 _search_yonhap/_search_kbs의 정규식 스크래핑보다
    신뢰도가 높다 — NAVER_SEARCH_CLIENT_ID/SECRET + ENABLE_NAVER_DISCOVERY=true가
    없으면 connector.search()가 즉시 빈 리스트를 반환해 기존 동작과 동일하다."""
    save_path = os.path.join(img_dir, f"news_{stock_name}.jpg")
    try:
        for cand in NaverDiscoveryConnector().search(stock_name, count=20):
            if _try_download(cand.url, save_path):
                print(f"  [image] 네이버 발견({cand.asset_source}) 이미지: {stock_name}")
                return save_path
    except Exception as e:
        print(f"  [image] 네이버 검색 실패 ({stock_name}): {e}")
    return None


def _search_kbs(stock_name: str, img_dir: str) -> Optional[str]:
    """KBS 뉴스에서 종목명 관련 뉴스 이미지를 검색합니다."""
    save_path = os.path.join(img_dir, f"news_{stock_name}.jpg")
    try:
        search_url = f"https://news.kbs.co.kr/api/search/news?q={requests.utils.quote(stock_name)}&page=1&per_page=5"
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            import json
            data = r.json()
            items = data.get("items") or data.get("data") or []
            for item in items[:5]:
                img_url = item.get("image_url", item.get("thumbnail", ""))
                if img_url and _try_download(img_url, save_path):
                    print(f"  [image] KBS 이미지: {stock_name}")
                    return save_path
        # KBS 뉴스 HTML 검색도 시도
        html_url = f"https://news.kbs.co.kr/news/search.do?searchKeyword={requests.utils.quote(stock_name)}"
        r = requests.get(html_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            img_urls = re.findall(
                r'https://[a-zA-Z0-9./\-_]+\.(?:jpg|jpeg|png)',
                r.text
            )
            for url in img_urls[:5]:
                if "thumbnail" in url or "news" in url:
                    if _try_download(url, save_path):
                        print(f"  [image] KBS HTML 이미지: {stock_name}")
                        return save_path
    except Exception as e:
        print(f"  [image] KBS 검색 실패 ({stock_name}): {e}")
    return None


def fetch_news_image(stock_name: str, img_dir: str,
                     extra_urls: Optional[List[str]] = None) -> Optional[str]:
    save_path = os.path.join(img_dir, f"news_{stock_name}.jpg")
    if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
        return save_path

    # 1순위: 직접 지정 URL
    for url in (extra_urls or []):
        if _try_download(url, save_path):
            print(f"  [image] 직접 URL 성공: {stock_name}")
            return save_path

    # 2순위: 네이버 뉴스 검색 API로 연합뉴스/KBS 원문 확인(가장 신뢰도 높음)
    result = _search_naver_discovery(stock_name, img_dir)
    if result:
        return result

    # 3순위: 연합뉴스 직접 크롤링
    result = _search_yonhap(stock_name, img_dir)
    if result:
        return result

    # 4순위: KBS 뉴스 직접 크롤링
    result = _search_kbs(stock_name, img_dir)
    if result:
        return result

    # 5순위: config.py fallback URL (기업 로고)
    fallback = NEWS_IMAGE_FALLBACKS.get(stock_name)
    if fallback:
        if _try_download(fallback, save_path):
            print(f"  [image] Fallback 로고: {stock_name}")
            return save_path

    print(f"  [image] 이미지 없음: {stock_name}")
    return None
