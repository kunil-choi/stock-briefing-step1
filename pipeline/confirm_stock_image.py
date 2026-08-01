# pipeline/confirm_stock_image.py
"""
output/{lang}/media/image_review_gallery.html에서 고른 후보 이미지를 종목
확정 저장소(assets/stock_images/)에 저장합니다. 확정 저장소에 그 종목의
사진이 있으면, 다음 파이프라인 실행부터는 실시간 검색 없이 그 사진을 바로
씁니다(pipeline/assets/media_pipeline.py의 pick_curated_image).

사용법:
    python pipeline/confirm_stock_image.py "삼성전자" --index 0

갤러리 카드마다 이 명령어가 그대로 적혀 있습니다(종목명 + 후보 번호만
다름). 확정하면 그 종목의 대기 후보(assets/stock_images/_pending/{종목명}/)는
정리됩니다 — 다음에 그 종목이 다시 확정 이미지 없이 나오면 새로 검토
갤러리에 올라옵니다.
"""
import argparse
import json
import os
import shutil
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.stock_image_store import confirm_stock_image, STOCK_IMAGE_DIR  # noqa: E402

PENDING_DIR = os.path.join(STOCK_IMAGE_DIR, "_pending")


def run(stock_name: str, index: int, pending_dir: str = PENDING_DIR,
        manifest_path: Optional[str] = None, store_dir: Optional[str] = None) -> str:
    """manifest_path/store_dir을 넘기지 않으면 stock_image_store.confirm_stock_image()의
    기본(레포 assets/stock_images/) 경로를 그대로 쓴다 — 테스트에서만 임시
    경로로 오버라이드한다(운영 시에는 항상 기본 경로)."""
    stock_dir = os.path.join(pending_dir, stock_name)
    meta_path = os.path.join(stock_dir, "meta.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"검토 대기 후보를 찾을 수 없습니다: {meta_path}\n"
            f"(image_review_gallery.html이 최신인지, 종목명 철자가 맞는지 확인하세요)"
        )
    with open(meta_path, encoding="utf-8") as f:
        candidates = json.load(f)

    match = next((c for c in candidates if c.get("index") == index), None)
    if match is None:
        raise ValueError(f"index={index}인 후보가 없습니다 ({stock_name}, 후보 {len(candidates)}개)")

    img_path = os.path.join(stock_dir, f"{index}.jpg")
    with open(img_path, "rb") as f:
        image_bytes = f.read()

    kwargs = {}
    if manifest_path is not None:
        kwargs["manifest_path"] = manifest_path
    if store_dir is not None:
        kwargs["store_dir"] = store_dir

    saved_path = confirm_stock_image(
        stock_name, image_bytes,
        credit=match.get("credit", ""),
        source_url=match.get("source_url", ""),
        license=match.get("license", "unknown"),
        **kwargs,
    )
    print(f"✅ 확정 저장: {stock_name} → {saved_path}")

    shutil.rmtree(stock_dir, ignore_errors=True)
    return saved_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="검토 갤러리에서 고른 후보 이미지를 종목 확정 저장소에 저장합니다."
    )
    parser.add_argument("stock_name", help="종목명 (예: 삼성전자)")
    parser.add_argument("--index", type=int, required=True, help="갤러리 카드에 적힌 후보 번호(#N)")
    parser.add_argument("--pending-dir", default=PENDING_DIR)
    args = parser.parse_args()
    run(args.stock_name, args.index, args.pending_dir)
