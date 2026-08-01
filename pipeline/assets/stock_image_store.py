# pipeline/assets/stock_image_store.py
"""
종목별 "확정 이미지" 저장소 (연합뉴스/KBS 실시간 검색 대신 쓰는 캐시).

배경: 실시간 뉴스 사진 검색은 얼굴이 크게 나온 사진이나 종목과 무관한 사진이
섞여 나오는 문제가 있었다(사용자 보고). 매번 자동으로 좋은 사진을 골라내는
대신, 사람이 한 번 확인해서 확정한 사진을 종목당 최대 몇 장 저장해두고
재사용하는 쪽이 훨씬 안전하다.

저장 구조:
  assets/stock_images/manifest.json                — {종목명: [항목, ...]}
  assets/stock_images/{종목명}/{1,2,...}.jpg        — 실제 이미지 파일

이 모듈은 그 저장소를 읽고(pick_curated_image), 검토 갤러리에서 사용자가
고른 이미지를 저장하는(confirm_stock_image) 역할만 한다 — 실제 검색/스코어링은
media_pipeline.py가 그대로 담당하고, 이 모듈은 그 결과를 "영구 저장할지"만
다룬다.
"""
import hashlib
import json
import os
from datetime import datetime
from typing import List, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pipeline/
STOCK_IMAGE_DIR = os.path.join(_BASE, "..", "assets", "stock_images")
STOCK_IMAGE_MANIFEST = os.path.join(STOCK_IMAGE_DIR, "manifest.json")

# 종목당 저장해두는 확정 이미지 장수. 이 이상 새로 확정하면 가장 오래된
# 항목부터 밀어낸다(선입선출로 최신 2장만 유지).
MAX_IMAGES_PER_STOCK = 2


def load_manifest(manifest_path: str = STOCK_IMAGE_MANIFEST) -> dict:
    if not os.path.isfile(manifest_path):
        return {}
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: dict, manifest_path: str = STOCK_IMAGE_MANIFEST) -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def get_curated_entries(stock_name: str, manifest_path: str = STOCK_IMAGE_MANIFEST,
                         store_dir: str = STOCK_IMAGE_DIR) -> List[dict]:
    """stock_name에 확정 저장된 이미지 항목만(파일이 실제로 존재하는 것만)
    반환한다. 각 항목에 실제 파일 절대경로("path")를 채워 넣는다."""
    manifest = load_manifest(manifest_path)
    entries = manifest.get(stock_name, [])
    out = []
    for entry in entries:
        path = os.path.join(store_dir, stock_name, entry["file"])
        if os.path.isfile(path):
            out.append({**entry, "path": path})
    return out


def pick_curated_image(stock_name: str, now: Optional[datetime] = None,
                        manifest_path: str = STOCK_IMAGE_MANIFEST,
                        store_dir: str = STOCK_IMAGE_DIR) -> Optional[dict]:
    """확정 저장된 이미지가 있으면 하나를 골라 반환하고, 없으면 None을
    반환한다(호출부가 실시간 검색으로 폴백해야 함을 알 수 있도록).

    완전 무작위 대신 (날짜, 종목명)을 시드로 결정론적으로 고른다 — 같은 날
    파이프라인을 여러 번 재실행해도 매번 다른 사진이 나오면(예: 오류로 재시도)
    최종 결과물이 실행마다 달라져 디버깅이 어려워진다."""
    entries = get_curated_entries(stock_name, manifest_path, store_dir)
    if not entries:
        return None
    now = now or datetime.now()
    seed = f"{now.strftime('%Y-%m-%d')}:{stock_name}"
    idx = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(entries)
    return entries[idx]


def confirm_stock_image(stock_name: str, image_bytes: bytes, *,
                         credit: str = "", source_url: str = "",
                         license: str = "unknown",
                         manifest_path: str = STOCK_IMAGE_MANIFEST,
                         store_dir: str = STOCK_IMAGE_DIR,
                         max_images: int = MAX_IMAGES_PER_STOCK) -> str:
    """검토 갤러리에서 확정한 이미지를 종목 폴더에 저장하고 manifest에
    기록한다. 이미 max_images장이 저장돼 있으면 가장 오래된 항목을 밀어내고
    교체한다(선입선출로 항상 최신 max_images장만 유지).

    반환값: 저장된 이미지의 절대경로."""
    manifest = load_manifest(manifest_path)
    entries = manifest.get(stock_name, [])

    stock_dir = os.path.join(store_dir, stock_name)
    os.makedirs(stock_dir, exist_ok=True)

    if len(entries) >= max_images:
        oldest = entries.pop(0)
        old_path = os.path.join(stock_dir, oldest["file"])
        if os.path.isfile(old_path):
            os.remove(old_path)

    used_numbers = {
        int(os.path.splitext(e["file"])[0])
        for e in entries
        if os.path.splitext(e["file"])[0].isdigit()
    }
    n = 1
    while n in used_numbers:
        n += 1
    filename = f"{n}.jpg"
    path = os.path.join(stock_dir, filename)
    with open(path, "wb") as f:
        f.write(image_bytes)

    entries.append({
        "file": filename,
        "credit": credit,
        "source_url": source_url,
        "license": license,
        "confirmed_at": datetime.now().strftime("%Y-%m-%d"),
    })
    manifest[stock_name] = entries
    save_manifest(manifest, manifest_path)
    return path


def has_curated_image(stock_name: str, manifest_path: str = STOCK_IMAGE_MANIFEST,
                       store_dir: str = STOCK_IMAGE_DIR) -> bool:
    return bool(get_curated_entries(stock_name, manifest_path, store_dir))
