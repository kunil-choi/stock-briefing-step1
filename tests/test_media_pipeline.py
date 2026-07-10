# tests/test_media_pipeline.py
"""
media_pipeline 검증 스크립트 (pytest 미사용, tests/test_scene_plan.py와 동일하게
순수 assert 기반). MockProvider만 사용하므로 네트워크 없이 실행됩니다.
실행: python tests/test_media_pipeline.py
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.media_providers import MockProvider  # noqa: E402
from assets.media_pipeline import (  # noqa: E402
    append_license_log, build_scene_images, is_duplicate, load_license_log,
    score_candidate,
)
from assets.media_providers import MediaCandidate  # noqa: E402
from assets.scene_plan import build_scene_plan  # noqa: E402


def _load_scene_plan():
    path = os.path.join(_HERE, "fixtures", "sample_script.json")
    with open(path, encoding="utf-8") as f:
        script_data = json.load(f)
    return build_scene_plan(script_data).model_dump()


def test_score_prefers_landscape_and_recent():
    now = datetime(2026, 7, 9)
    landscape = MediaCandidate(url="a", source="yonhap", license="editorial_search",
                                published_at=now)
    portrait = MediaCandidate(url="b", source="yonhap", license="editorial_search",
                               published_at=now)
    s_landscape = score_candidate(landscape, keyword_rank=0, width=1280, height=720, now=now)
    s_portrait = score_candidate(portrait, keyword_rank=0, width=720, height=1280, now=now)
    assert s_landscape > s_portrait, "가로형이 세로형보다 높은 점수를 받아야 함"

    old = MediaCandidate(url="c", source="yonhap", license="editorial_search",
                          published_at=now - timedelta(days=20))
    s_old = score_candidate(old, keyword_rank=0, width=1280, height=720, now=now)
    assert s_landscape > s_old, "최근 이미지가 오래된 이미지보다 높은 점수를 받아야 함"

    later_keyword = score_candidate(landscape, keyword_rank=3, width=1280, height=720, now=now)
    assert s_landscape > later_keyword, "우선순위가 높은 키워드로 찾은 후보가 더 높은 점수를 받아야 함"
    print("✅ score_candidate: 가로형/최근성/키워드 우선순위 반영 확인")


def test_license_log_roundtrip():
    tmp_dir = tempfile.mkdtemp()
    try:
        log_path = os.path.join(tmp_dir, "license_log.csv")
        assert load_license_log(log_path) == []

        rows = [{
            "date": "2026-07-09", "section_id": "stock_삼성전자", "keyword": "삼성전자",
            "provider": "mock", "url": "mock://x", "license": "mock",
            "phash": "0" * 16, "width": 1280, "height": 720, "score": 0.5,
        }]
        append_license_log(log_path, rows)
        loaded = load_license_log(log_path)
        assert len(loaded) == 1
        assert loaded[0]["section_id"] == "stock_삼성전자"
        print("✅ license_log.csv 왕복 읽기/쓰기 확인")
    finally:
        shutil.rmtree(tmp_dir)


def test_build_scene_images_with_mock_and_dedup():
    tmp_dir = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp_dir, "media")
        log_path = os.path.join(tmp_dir, "data", "media", "license_log.csv")
        scene_plan = _load_scene_plan()
        providers = [MockProvider()]
        now = datetime(2026, 7, 9)

        media_map_1 = build_scene_images(scene_plan, img_dir, providers, log_path, now=now)
        assert len(media_map_1) == len(scene_plan["sections"])
        # visual_keywords가 있는 섹션은 MockProvider가 항상 성공하므로 fallback이 없어야 함
        keyworded_ids = {s["id"] for s in scene_plan["sections"] if s.get("visual_keywords")}
        for sid in keyworded_ids:
            entry = media_map_1[sid]
            assert entry["source"] == "mock", f"{sid}: mock provider가 있으면 fallback이면 안 됨"
            assert os.path.isfile(entry["image_path"]), f"{sid}: 선택된 이미지 파일이 실제로 저장돼야 함"

        log_rows_after_1 = load_license_log(log_path)
        assert len(log_rows_after_1) == len(keyworded_ids)

        # 같은 날 같은 scene_plan으로 재실행 → 1회차에서 고른 이미지는 7일 내
        # 중복이므로 모든 섹션이 다른 이미지(다른 phash)를 골라야 한다. media_map의
        # image_path는 섹션당 고정 파일명이라 실행마다 덮어써지므로, 디스크 파일이
        # 아니라 선택 시점에 기록한 phash 필드로 비교한다.
        media_map_2 = build_scene_images(scene_plan, img_dir, providers, log_path, now=now)
        changed = [
            sid for sid in keyworded_ids
            if media_map_2[sid]["source"] == "mock"
            and media_map_1[sid]["phash"] != media_map_2[sid]["phash"]
        ]
        assert set(changed) == keyworded_ids, \
            "7일 내 중복 이미지는 재사용하지 않고 모든 섹션이 다른 후보를 골라야 함"
        print(f"✅ 7일 중복 감지 확인 (재실행 시 {len(changed)}/{len(keyworded_ids)}개 섹션에서 다른 이미지 선택)")
    finally:
        shutil.rmtree(tmp_dir)


def test_sector_fallback_when_no_keywords():
    tmp_dir = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp_dir, "media")
        log_path = os.path.join(tmp_dir, "data", "media", "license_log.csv")
        scene_plan = {
            "title": "t", "date": "d",
            "sections": [{
                "id": "closing", "label": "클로징",
                "visual_keywords": [],
                "entities": [],
            }],
        }
        media_map = build_scene_images(scene_plan, img_dir, [MockProvider()], log_path)
        assert media_map["closing"]["source"] == "fallback"
        print("✅ visual_keywords가 없는 섹션은 fallback 경로로 처리됨")
    finally:
        shutil.rmtree(tmp_dir)


def _textured_image(seed: int):
    """단색 이미지는 pHash가 저주파 성분만 봐서 색이 달라도 거의 같은 해시가
    나온다(MockProvider에서 실제로 부딪힌 문제). 실제 공간 주파수 차이가 있는
    격자 패턴으로 테스트 이미지를 만든다."""
    import random
    from PIL import Image

    rng = random.Random(seed)
    grid = 8
    small = Image.new("RGB", (grid, grid))
    px = small.load()
    for y in range(grid):
        for x in range(grid):
            px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    return small.resize((100, 100), Image.NEAREST)


def test_is_duplicate_threshold():
    import imagehash

    img1 = _textured_image(seed=1)
    img2 = _textured_image(seed=1)   # 동일 시드 → 동일 이미지
    img3 = _textured_image(seed=2)   # 다른 시드 → 확연히 다른 이미지
    h1, h2, h3 = imagehash.phash(img1), imagehash.phash(img2), imagehash.phash(img3)
    assert is_duplicate(h1, [h2]) is True
    assert is_duplicate(h1, [h3]) is False
    print("✅ is_duplicate: 동일/상이 이미지 판별 확인")


if __name__ == "__main__":
    test_score_prefers_landscape_and_recent()
    test_license_log_roundtrip()
    test_build_scene_images_with_mock_and_dedup()
    test_sector_fallback_when_no_keywords()
    test_is_duplicate_threshold()
    print("\n✅ media_pipeline 테스트 전체 통과")
