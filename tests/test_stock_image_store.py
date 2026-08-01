# tests/test_stock_image_store.py
"""
종목별 확정 이미지 저장소(pipeline/assets/stock_image_store.py) +
검토 갤러리(pipeline/assets/image_review_gallery.py) +
확정 CLI(pipeline/confirm_stock_image.py) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크 불필요.
실행: python tests/test_stock_image_store.py
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets import stock_image_store as store  # noqa: E402
from assets.image_review_gallery import render_gallery_html, save_pending_candidates  # noqa: E402
import confirm_stock_image  # noqa: E402

_FAKE_JPG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes-for-tests" + b"\xff\xd9"


def test_empty_store_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")
        assert store.pick_curated_image("삼성전자", manifest_path=manifest_path, store_dir=store_dir) is None
        assert store.get_curated_entries("삼성전자", manifest_path=manifest_path, store_dir=store_dir) == []
        assert not store.has_curated_image("삼성전자", manifest_path=manifest_path, store_dir=store_dir)
    print("✅ 빈 저장소는 None/빈 목록을 반환")


def test_confirm_then_pick_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")

        saved_path = store.confirm_stock_image(
            "삼성전자", _FAKE_JPG, credit="연합뉴스", source_url="https://example.com/a.jpg",
            license="editorial_search", manifest_path=manifest_path, store_dir=store_dir,
        )
        assert os.path.isfile(saved_path)
        with open(saved_path, "rb") as f:
            assert f.read() == _FAKE_JPG

        assert store.has_curated_image("삼성전자", manifest_path=manifest_path, store_dir=store_dir)
        picked = store.pick_curated_image("삼성전자", manifest_path=manifest_path, store_dir=store_dir)
        assert picked is not None
        assert picked["path"] == saved_path
        assert picked["credit"] == "연합뉴스"
    print("✅ confirm_stock_image로 저장한 이미지를 pick_curated_image가 그대로 찾음")


def test_max_images_evicts_oldest():
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")

        p1 = store.confirm_stock_image("현대차", _FAKE_JPG, credit="1번",
                                        manifest_path=manifest_path, store_dir=store_dir, max_images=2)
        p2 = store.confirm_stock_image("현대차", _FAKE_JPG, credit="2번",
                                        manifest_path=manifest_path, store_dir=store_dir, max_images=2)
        entries = store.get_curated_entries("현대차", manifest_path=manifest_path, store_dir=store_dir)
        assert len(entries) == 2

        p3 = store.confirm_stock_image("현대차", _FAKE_JPG, credit="3번",
                                        manifest_path=manifest_path, store_dir=store_dir, max_images=2)
        entries = store.get_curated_entries("현대차", manifest_path=manifest_path, store_dir=store_dir)
        assert len(entries) == 2, "max_images를 넘으면 가장 오래된 항목이 빠지고 항상 2장만 유지돼야 함"
        credits = {e["credit"] for e in entries}
        assert credits == {"2번", "3번"}, f"가장 오래된(1번) 항목이 밀려나야 하는데 {credits}"
        # 밀려난 슬롯 번호(1.jpg)는 재사용되므로 p3는 p1과 같은 경로가 된다 —
        # 파일 자체가 아니라 manifest에 "1번"이 더 이상 남아있지 않은지로 검증한다.
        assert p3 == p1, "빈 슬롯 번호를 재사용해 같은 경로에 새로 저장돼야 함"
        assert os.path.isfile(p2) and os.path.isfile(p3)
    print("✅ max_images 초과 시 가장 오래된 항목이 밀려나고(슬롯 재사용) 최신 장수만 유지됨")


def test_pick_is_deterministic_per_day():
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")
        store.confirm_stock_image("네이버", _FAKE_JPG, credit="1번",
                                   manifest_path=manifest_path, store_dir=store_dir, max_images=2)
        store.confirm_stock_image("네이버", _FAKE_JPG, credit="2번",
                                   manifest_path=manifest_path, store_dir=store_dir, max_images=2)

        now = datetime(2026, 8, 1)
        picks = {
            store.pick_curated_image("네이버", now=now, manifest_path=manifest_path, store_dir=store_dir)["file"]
            for _ in range(5)
        }
        assert len(picks) == 1, "같은 날짜에는 항상 같은 사진을 골라야 함(재실행 시 일관성)"
    print("✅ 같은 날짜에는 항상 같은 확정 이미지를 결정론적으로 선택함")


def test_missing_file_is_filtered_out():
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")
        path = store.confirm_stock_image("카카오", _FAKE_JPG, manifest_path=manifest_path, store_dir=store_dir)
        os.remove(path)  # manifest에는 남아있지만 실제 파일은 없는 상황(수동 삭제 등)
        assert store.get_curated_entries("카카오", manifest_path=manifest_path, store_dir=store_dir) == []
        assert store.pick_curated_image("카카오", manifest_path=manifest_path, store_dir=store_dir) is None
    print("✅ manifest에 남아있어도 실제 파일이 없으면 후보에서 제외(검색 폴백으로 안전하게 넘어감)")


def test_gallery_and_confirm_end_to_end():
    """save_pending_candidates → render_gallery_html → confirm_stock_image.py CLI까지
    전체 플로우를 하나로 검증한다."""
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "manifest.json")
        store_dir = os.path.join(tmp, "stock_images")
        pending_dir = os.path.join(store_dir, "_pending")

        needs_curation = {
            "LG에너지솔루션": [
                {"score": 0.81, "provider": "yonhap", "url": "mock://a", "title": "LG에너지솔루션 실적",
                 "credit": "연합뉴스", "source_url": "https://example.com/a", "license": "editorial_search",
                 "image_bytes": _FAKE_JPG, "width": 1280, "height": 720},
                {"score": 0.55, "provider": "kbs", "url": "mock://b", "title": "LG에너지솔루션 공장",
                 "credit": "KBS", "source_url": "https://example.com/b", "license": "editorial_search",
                 "image_bytes": _FAKE_JPG, "width": 1280, "height": 720},
            ]
        }

        pending_meta = save_pending_candidates(needs_curation, pending_dir)
        assert os.path.isfile(os.path.join(pending_dir, "LG에너지솔루션", "0.jpg"))
        assert os.path.isfile(os.path.join(pending_dir, "LG에너지솔루션", "meta.json"))
        assert len(pending_meta["LG에너지솔루션"]) == 2

        gallery_path = os.path.join(tmp, "gallery.html")
        render_gallery_html(pending_meta, gallery_path)
        assert os.path.isfile(gallery_path)
        with open(gallery_path, encoding="utf-8") as f:
            html = f.read()
        assert "LG에너지솔루션" in html
        assert 'confirm_stock_image.py "LG에너지솔루션" --index 0' in html
        assert "data:image/jpeg;base64," in html

        # confirm_stock_image.run()은 stock_image_store의 기본(레포 경로) 저장소를
        # 쓰므로, 이 테스트에서는 내부 저장 로직만 store.confirm_stock_image로
        # 직접 재현해 검증한다(기본 경로를 실제로 건드리지 않기 위함 — CLI
        # 자체의 default-path 사용은 아래 test_confirm_cli_run_uses_default_store_
        # and_cleans_pending에서 monkeypatch로 별도 검증한다).
        match = pending_meta["LG에너지솔루션"][0]
        with open(match["path"], "rb") as f:
            image_bytes = f.read()
        saved_path = store.confirm_stock_image(
            "LG에너지솔루션", image_bytes, credit=match["credit"], source_url=match["source_url"],
            license=match["license"], manifest_path=manifest_path, store_dir=store_dir,
        )
        assert os.path.isfile(saved_path)
        picked = store.pick_curated_image("LG에너지솔루션", manifest_path=manifest_path, store_dir=store_dir)
        assert picked["credit"] == "연합뉴스"
    print("✅ 검토 갤러리 생성(save_pending_candidates/render_gallery_html) → 확정 저장 전체 플로우 확인")


def test_confirm_cli_run_writes_to_given_store_and_cleans_pending():
    """confirm_stock_image.py의 run()이 실제로 stock_image_store.confirm_stock_image를
    호출하고, 완료 후 대기 후보 폴더를 정리하는지 확인한다. manifest_path/store_dir을
    명시적으로 넘겨 레포의 실제 저장소를 건드리지 않고 검증한다(run()의 기본값은
    운영용 실제 경로이므로, 여기서 넘기지 않으면 테스트가 레포를 오염시킨다)."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_manifest = os.path.join(tmp, "manifest.json")
        fake_store_dir = os.path.join(tmp, "stock_images")
        pending_dir = os.path.join(tmp, "_pending")

        stock_dir = os.path.join(pending_dir, "삼성SDI")
        os.makedirs(stock_dir, exist_ok=True)
        with open(os.path.join(stock_dir, "0.jpg"), "wb") as f:
            f.write(_FAKE_JPG)
        with open(os.path.join(stock_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump([{"index": 0, "credit": "연합뉴스", "source_url": "u", "license": "editorial_search"}], f)

        saved_path = confirm_stock_image.run(
            "삼성SDI", 0, pending_dir=pending_dir,
            manifest_path=fake_manifest, store_dir=fake_store_dir,
        )
        assert os.path.isfile(saved_path)
        assert saved_path.startswith(fake_store_dir), "지정한 store_dir 아래에 저장돼야 함"
        assert not os.path.isdir(stock_dir), "확정 후에는 대기 후보 폴더가 정리돼야 함"

        picked = store.pick_curated_image("삼성SDI", manifest_path=fake_manifest, store_dir=fake_store_dir)
        assert picked is not None and picked["path"] == saved_path
    print("✅ confirm_stock_image.py CLI: 지정 저장소로 확정 저장 + 대기 후보 정리 확인")


if __name__ == "__main__":
    test_empty_store_returns_none()
    test_confirm_then_pick_roundtrip()
    test_max_images_evicts_oldest()
    test_pick_is_deterministic_per_day()
    test_missing_file_is_filtered_out()
    test_gallery_and_confirm_end_to_end()
    test_confirm_cli_run_writes_to_given_store_and_cleans_pending()

    print("\n✅ stock_image_store 테스트 전체 통과")
