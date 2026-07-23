# pipeline/assets/media_pipeline.py
"""
scene_plan.json의 visual_keywords를 입력으로 받아 MediaProvider들에서 이미지
후보를 모으고, 관련도/최근성/가로형 여부/사용권/중복 사용 여부로 점수를 매겨
장면별 최적 이미지를 선택한다. 선택 근거는 license_log.csv에 남기고, 7일 내
재사용된 이미지는 imagehash 기반 perceptual hash로 걸러낸다. 모든 후보가
실패하면 섹터 fallback 이미지로 대체한다.
"""
import csv
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List, Optional

import imagehash
from PIL import Image

from .config import get_sector_fallback_image
from .media_providers import MediaCandidate, MediaProvider, NaverDiscoveryConnector
from .rights_review import apply_rights

LICENSE_LOG_FIELDS = [
    "date", "section_id", "keyword", "provider", "url",
    "license", "phash", "width", "height", "score",
]

_PROVIDER_TRUST = {"yonhap": 0.3, "kbs": 0.3, "naver_discovery": 0.28, "mock": 0.15}
_LICENSE_SCORE = {"api_licensed": 0.2, "editorial_search": 0.1, "mock": 0.05, "unknown": 0.0}

DEDUP_WINDOW_DAYS = 7
DEDUP_HAMMING_THRESHOLD = 6   # phash 해밍 거리 이 값 이하면 "같은 이미지"로 간주
MAX_CANDIDATES_PER_SECTION = 8


@dataclass
class SelectedImage:
    section_id: str
    keyword: str
    provider: str
    url: str
    license: str
    phash: str
    width: int
    height: int
    score: float
    image_path: str
    # ── 2차 작업: asset-manifest.json용 확장 필드 ──────────────────────────
    asset_source: str = ""
    title: str = ""
    credit: str = ""
    source_url: str = ""
    rights_status: str = "unclear"
    allowed_platforms: list = None
    restrictions: list = None
    needs_review: bool = True
    search_query: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# license_log.csv I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_license_log(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_license_log(path: str, rows: List[dict]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.isfile(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LICENSE_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _recent_phashes(log_rows: List[dict], now: datetime,
                     days: int = DEDUP_WINDOW_DAYS) -> List[imagehash.ImageHash]:
    cutoff = now - timedelta(days=days)
    out = []
    for row in log_rows:
        try:
            row_date = datetime.fromisoformat(row["date"])
        except Exception:
            continue
        if row_date < cutoff:
            continue
        try:
            out.append(imagehash.hex_to_hash(row["phash"]))
        except Exception:
            continue
    return out


def is_duplicate(phash: imagehash.ImageHash, recent: List[imagehash.ImageHash],
                  threshold: int = DEDUP_HAMMING_THRESHOLD) -> bool:
    return any((phash - h) <= threshold for h in recent)


# ─────────────────────────────────────────────────────────────────────────────
# 스코어링
# ─────────────────────────────────────────────────────────────────────────────

def _as_naive(dt: datetime) -> datetime:
    """RFC 2822 pubDate(예: 네이버 뉴스)는 타임존 오프셋이 붙어 aware
    datetime으로 파싱되는 반면, 이 모듈의 `now`는 항상 naive
    datetime.now()다. naive/aware를 그대로 빼면 TypeError가 나므로,
    aware datetime은 UTC 기준 naive로 맞춰 비교 가능하게 만든다."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def score_candidate(candidate: MediaCandidate, keyword_rank: int,
                     width: int, height: int, now: datetime) -> float:
    """관련도(키워드 우선순위) + 최근성 + 가로형 여부 + 사용권을 합산한
    0에 가까운 음수부터 1을 넘길 수 있는 점수(정규화하지 않음, 상대 비교용)."""
    score = _PROVIDER_TRUST.get(candidate.source, 0.15)
    # 관련도: visual_keywords는 이미 우선순위(기업명>섹터>인물>증권사>지역>뉴스키워드)
    # 순서이므로, 몇 번째 키워드로 찾았는지를 관련도의 근사치로 사용한다.
    score += max(0.0, 0.3 - 0.06 * keyword_rank)
    if candidate.published_at:
        days = max(0, (now - _as_naive(candidate.published_at)).days)
        score += max(0.0, 0.2 - 0.02 * days)
    else:
        score += 0.1  # 게시일 정보 없음 → 중립
    if width and height:
        score += 0.2 if width >= height else -0.1
    score += _LICENSE_SCORE.get(candidate.license, 0.0)
    return round(score, 3)


# ─────────────────────────────────────────────────────────────────────────────
# 다운로드 캐시 — 같은 URL을 반복 실행마다 다시 받지 않는다
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(cache_dir: str, candidate: MediaCandidate) -> str:
    source = (candidate.asset_source or candidate.source or "unknown").lower()
    url_hash = hashlib.sha1(candidate.url.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache_dir, source, f"{source}_{url_hash}.jpg")


def _cached_download(provider: MediaProvider, candidate: MediaCandidate,
                      cache_dir: Optional[str]) -> Optional[bytes]:
    """provider.download()를 감싸 같은 URL은 캐시에서 재사용한다. 인터페이스는
    바꾸지 않고(호출부는 그대로 bytes|None을 받음), URL 해시 기반으로
    cache_dir/{source}/{source}_{hash}.jpg에 저장·재사용한다."""
    if not cache_dir or not candidate.url or candidate.url.startswith("file://"):
        return provider.download(candidate)
    path = _cache_path(cache_dir, candidate)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    content = provider.download(candidate)
    if content:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
    return content


# ─────────────────────────────────────────────────────────────────────────────
# 선택 파이프라인
# ─────────────────────────────────────────────────────────────────────────────

def select_best_image(section_id: str, keywords: List[str], providers: List[MediaProvider],
                       recent_hashes: List[imagehash.ImageHash], img_dir: str,
                       now: Optional[datetime] = None,
                       max_candidates: int = MAX_CANDIDATES_PER_SECTION,
                       dedup_threshold: int = DEDUP_HAMMING_THRESHOLD,
                       cache_dir: Optional[str] = None,
                       manifest_rows: Optional[list] = None) -> Optional[SelectedImage]:
    """manifest_rows가 주어지면, 검토된 모든 후보(다운로드 성공분 + 권리
    검수로 건너뛴 분)를 asset-manifest.json용 dict로 append한다."""
    now = now or datetime.now()
    scored = []
    probed = 0
    rows_by_candidate_id = {}  # id(cand) -> manifest row dict (선택 확정 시 in-place로 갱신)

    def _record(cand, width=None, height=None, score=0.0):
        if manifest_rows is None:
            return
        row = _manifest_row(section_id, cand, width, height, score)
        rows_by_candidate_id[id(cand)] = row
        manifest_rows.append(row)

    for rank, keyword in enumerate(keywords):
        if probed >= max_candidates:
            break
        for provider in providers:
            if probed >= max_candidates:
                break
            for cand in provider.search(keyword, count=3):
                if probed >= max_candidates:
                    break
                apply_rights(cand)

                if cand.needs_review:
                    # 권리 불명확 후보는 다운로드하지 않는다(대역폭 낭비 방지 +
                    # 검수 전 콘텐츠를 로컬에 받아두지 않기 위함). 네이버
                    # discovery는 애초에 download()가 항상 None이라 이 분기가
                    # 아니어도 아래에서 걸러지지만, 다른 소스(외신 등)도 같은
                    # 규칙을 적용한다.
                    probed += 1
                    _record(cand)
                    continue

                content = _cached_download(provider, cand, cache_dir)
                probed += 1
                if not content:
                    continue
                try:
                    img = Image.open(BytesIO(content))
                    width, height = img.size
                    phash = imagehash.phash(img)
                except Exception:
                    continue
                if is_duplicate(phash, recent_hashes, threshold=dedup_threshold):
                    print(f"  [media] 중복(7일 내 사용) 제외: {cand.url[:60]}")
                    _record(cand, width, height)
                    continue
                score = score_candidate(cand, rank, width, height, now)
                scored.append((score, cand, content, width, height, phash))
                _record(cand, width, height, score)

    if not scored:
        return None

    scored.sort(key=lambda t: t[0], reverse=True)
    score, cand, content, width, height, phash = scored[0]

    os.makedirs(img_dir, exist_ok=True)
    image_path = os.path.join(img_dir, f"media_{section_id}.jpg")
    with open(image_path, "wb") as f:
        f.write(content)

    winner_row = rows_by_candidate_id.get(id(cand))
    if winner_row is not None:
        winner_row["selected"] = True
        winner_row["localPath"] = image_path

    return SelectedImage(
        section_id=section_id, keyword=cand.keyword, provider=cand.source,
        url=cand.url, license=cand.license, phash=str(phash),
        width=width, height=height, score=score, image_path=image_path,
        asset_source=cand.asset_source, title=cand.title, credit=cand.credit,
        source_url=cand.source_url, rights_status=cand.rights_status,
        allowed_platforms=cand.allowed_platforms, restrictions=cand.restrictions,
        needs_review=cand.needs_review, search_query=cand.keyword,
    )


def _manifest_row(section_id: str, cand: MediaCandidate, width: Optional[int],
                   height: Optional[int], score: float) -> dict:
    """asset-manifest.json의 assets[] 항목 하나. selected/localPath는 select_best_image()가
    승자를 확정한 뒤 in-place로 갱신한다(초기값은 항상 False/빈 문자열)."""
    asset_id_src = cand.asset_source or cand.source or "unknown"
    url_hash = hashlib.sha1((cand.url or cand.source_url or "").encode("utf-8")).hexdigest()[:8]
    return {
        "assetId":          f"{asset_id_src.lower()}_{section_id}_{url_hash}",
        "sceneId":          section_id,
        "source":           cand.asset_source or cand.source,
        "type":             "image",
        "title":            cand.title,
        "credit":           cand.credit,
        "sourceUrl":        cand.source_url or cand.url,
        "downloadUrl":      cand.download_url or cand.url,
        "localPath":        "",
        "searchQuery":      cand.keyword,
        "rightsStatus":     cand.rights_status,
        "allowedPlatforms": list(cand.allowed_platforms or []),
        "restrictions":     list(cand.restrictions or []),
        "containsPerson":  cand.contains_person,
        "containsLogo":    cand.contains_logo,
        "isForeignAgency": cand.is_foreign_agency,
        "needsReview":      cand.needs_review,
        "selected":         False,
        "width":            width,
        "height":           height,
        "score":            score,
    }


def build_asset_manifest(manifest_rows: List[dict], project: str = "stock-briefing-video") -> dict:
    """select_best_image()가 채운 manifest_rows(assets 항목 리스트)를
    asset-manifest.json 최상위 구조로 감싼다."""
    return {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "project": project,
        "assets": manifest_rows,
    }


def _fallback_sector_for_section(section: dict) -> str:
    for e in section.get("entities") or []:
        if e.get("type") == "섹터":
            return e.get("value", "")
    return ""


def _order_providers(providers: List[MediaProvider], preferred_sources: List[str]) -> List[MediaProvider]:
    """scene_plan 섹션의 preferredSources 순서대로 provider를 정렬한다.
    preferredSources가 없거나 일치하는 provider가 없으면 원래 순서 그대로
    (기존 동작과 100% 동일)."""
    if not preferred_sources:
        return providers
    order_index = {src: i for i, src in enumerate(preferred_sources)}
    return sorted(providers, key=lambda p: order_index.get(p.asset_source, len(preferred_sources)))


def _keywords_for_section(sec: dict, restrict_to_stock_fallback: bool) -> List[str]:
    """1차 작업이 채운 visual_keywords(한국어)/visualKeywordsEn(영어)을 함께
    사용한다. needsDataReview=True(오염 의심 종목명)인 섹션은 종목명 기반
    한국어 키워드로 KBS/연합뉴스를 검색하지 않고, 영어 키워드(스톡 사진/추상
    그래픽용)만 사용한다 — 1차에서 만든 안전장치를 실제로 적용."""
    ko = sec.get("visual_keywords") or []
    en = sec.get("visualKeywordsEn") or []
    if restrict_to_stock_fallback:
        return list(en)
    out = list(ko)
    for kw in en:
        if kw not in out:
            out.append(kw)
    return out


def build_scene_images(scene_plan: dict, img_dir: str, providers: List[MediaProvider],
                        log_path: str, now: Optional[datetime] = None,
                        dedup_window_days: int = DEDUP_WINDOW_DAYS,
                        dedup_threshold: int = DEDUP_HAMMING_THRESHOLD,
                        max_candidates: int = MAX_CANDIDATES_PER_SECTION,
                        cache_dir: Optional[str] = None,
                        manifest_rows: Optional[list] = None) -> dict:
    """scene_plan(dict, scene_plan.json 로드 결과)의 모든 섹션에 대해 이미지를
    선택하고 {section_id: {image_path, source, license, keyword, score}}를
    반환합니다. 검색 실패 섹션은 섹터 fallback(없으면 None)으로 채웁니다.
    manifest_rows가 주어지면 asset-manifest.json용 행을 그 리스트에 채웁니다
    (반환값 자체는 하위호환을 위해 media_map dict 그대로 유지)."""
    now = now or datetime.now()
    log_rows = load_license_log(log_path)
    recent_hashes = _recent_phashes(log_rows, now, days=dedup_window_days)

    media_map = {}
    new_rows = []
    for sec in scene_plan.get("sections") or []:
        section_id = sec.get("id", "")
        needs_data_review = bool(sec.get("needsDataReview"))
        allow_stock_fallback = bool((sec.get("assetRequirements") or {}).get("allowStockFallback", True))
        restrict_to_stock_fallback = needs_data_review and allow_stock_fallback
        keywords = _keywords_for_section(sec, restrict_to_stock_fallback)
        ordered_providers = _order_providers(providers, sec.get("preferredSources") or [])

        selected = None
        if keywords:
            selected = select_best_image(section_id, keywords, ordered_providers, recent_hashes, img_dir, now,
                                          max_candidates=max_candidates, dedup_threshold=dedup_threshold,
                                          cache_dir=cache_dir, manifest_rows=manifest_rows)

        if selected:
            media_map[section_id] = {
                "image_path": selected.image_path,
                "source":     selected.provider,
                "license":    selected.license,
                "keyword":    selected.keyword,
                "score":      selected.score,
                "phash":      selected.phash,
                "credit":     selected.credit,
            }
            new_rows.append({
                "date":       now.strftime("%Y-%m-%d"),
                "section_id": section_id,
                "keyword":    selected.keyword,
                "provider":   selected.provider,
                "url":        selected.url,
                "license":    selected.license,
                "phash":      selected.phash,
                "width":      selected.width,
                "height":     selected.height,
                "score":      selected.score,
            })
            recent_hashes.append(imagehash.hex_to_hash(selected.phash))
        else:
            sector = _fallback_sector_for_section(sec)
            fallback_path = get_sector_fallback_image(sector)
            media_map[section_id] = {
                "image_path": fallback_path,
                "source":     "fallback",
                "license":    "internal",
                "keyword":    "",
                "score":      0.0,
                "phash":      None,
                "credit":     "",
            }
            print(f"  [media] {section_id}: 이미지 검색 실패 → 섹터 폴백({sector or '기타'})")

    append_license_log(log_path, new_rows)
    return media_map
