# pipeline/assets/media_pipeline.py
"""
scene_plan.json의 visual_keywords를 입력으로 받아 MediaProvider들에서 이미지
후보를 모으고, 관련도/최근성/가로형 여부/사용권/중복 사용 여부로 점수를 매겨
장면별 최적 이미지를 선택한다. 선택 근거는 license_log.csv에 남기고, 7일 내
재사용된 이미지는 imagehash 기반 perceptual hash로 걸러낸다. 모든 후보가
실패하면 섹터 fallback 이미지로 대체한다.
"""
import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Optional

import imagehash
from PIL import Image

from .config import get_sector_fallback_image
from .media_providers import MediaCandidate, MediaProvider

LICENSE_LOG_FIELDS = [
    "date", "section_id", "keyword", "provider", "url",
    "license", "phash", "width", "height", "score",
]

_PROVIDER_TRUST = {"yonhap": 0.3, "kbs": 0.3, "mock": 0.15}
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

def score_candidate(candidate: MediaCandidate, keyword_rank: int,
                     width: int, height: int, now: datetime) -> float:
    """관련도(키워드 우선순위) + 최근성 + 가로형 여부 + 사용권을 합산한
    0에 가까운 음수부터 1을 넘길 수 있는 점수(정규화하지 않음, 상대 비교용)."""
    score = _PROVIDER_TRUST.get(candidate.source, 0.15)
    # 관련도: visual_keywords는 이미 우선순위(기업명>섹터>인물>증권사>지역>뉴스키워드)
    # 순서이므로, 몇 번째 키워드로 찾았는지를 관련도의 근사치로 사용한다.
    score += max(0.0, 0.3 - 0.06 * keyword_rank)
    if candidate.published_at:
        days = max(0, (now - candidate.published_at).days)
        score += max(0.0, 0.2 - 0.02 * days)
    else:
        score += 0.1  # 게시일 정보 없음 → 중립
    if width and height:
        score += 0.2 if width >= height else -0.1
    score += _LICENSE_SCORE.get(candidate.license, 0.0)
    return round(score, 3)


# ─────────────────────────────────────────────────────────────────────────────
# 선택 파이프라인
# ─────────────────────────────────────────────────────────────────────────────

def select_best_image(section_id: str, keywords: List[str], providers: List[MediaProvider],
                       recent_hashes: List[imagehash.ImageHash], img_dir: str,
                       now: Optional[datetime] = None,
                       max_candidates: int = MAX_CANDIDATES_PER_SECTION,
                       dedup_threshold: int = DEDUP_HAMMING_THRESHOLD) -> Optional[SelectedImage]:
    now = now or datetime.now()
    scored = []
    probed = 0

    for rank, keyword in enumerate(keywords):
        if probed >= max_candidates:
            break
        for provider in providers:
            if probed >= max_candidates:
                break
            for cand in provider.search(keyword, count=3):
                if probed >= max_candidates:
                    break
                content = provider.download(cand)
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
                    continue
                score = score_candidate(cand, rank, width, height, now)
                scored.append((score, cand, content, width, height, phash))

    if not scored:
        return None

    scored.sort(key=lambda t: t[0], reverse=True)
    score, cand, content, width, height, phash = scored[0]

    os.makedirs(img_dir, exist_ok=True)
    image_path = os.path.join(img_dir, f"media_{section_id}.jpg")
    with open(image_path, "wb") as f:
        f.write(content)

    return SelectedImage(
        section_id=section_id, keyword=cand.keyword, provider=cand.source,
        url=cand.url, license=cand.license, phash=str(phash),
        width=width, height=height, score=score, image_path=image_path,
    )


def _fallback_sector_for_section(section: dict) -> str:
    for e in section.get("entities") or []:
        if e.get("type") == "섹터":
            return e.get("value", "")
    return ""


def build_scene_images(scene_plan: dict, img_dir: str, providers: List[MediaProvider],
                        log_path: str, now: Optional[datetime] = None,
                        dedup_window_days: int = DEDUP_WINDOW_DAYS,
                        dedup_threshold: int = DEDUP_HAMMING_THRESHOLD,
                        max_candidates: int = MAX_CANDIDATES_PER_SECTION) -> dict:
    """scene_plan(dict, scene_plan.json 로드 결과)의 모든 섹션에 대해 이미지를
    선택하고 {section_id: {image_path, source, license, keyword, score}}를
    반환합니다. 검색 실패 섹션은 섹터 fallback(없으면 None)으로 채웁니다."""
    now = now or datetime.now()
    log_rows = load_license_log(log_path)
    recent_hashes = _recent_phashes(log_rows, now, days=dedup_window_days)

    media_map = {}
    new_rows = []
    for sec in scene_plan.get("sections") or []:
        section_id = sec.get("id", "")
        keywords = sec.get("visual_keywords") or []
        selected = None
        if keywords:
            selected = select_best_image(section_id, keywords, providers, recent_hashes, img_dir, now,
                                          max_candidates=max_candidates, dedup_threshold=dedup_threshold)

        if selected:
            media_map[section_id] = {
                "image_path": selected.image_path,
                "source":     selected.provider,
                "license":    selected.license,
                "keyword":    selected.keyword,
                "score":      selected.score,
                "phash":      selected.phash,
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
            }
            print(f"  [media] {section_id}: 이미지 검색 실패 → 섹터 폴백({sector or '기타'})")

    append_license_log(log_path, new_rows)
    return media_map
