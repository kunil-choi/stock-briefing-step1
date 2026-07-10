# pipeline/generate_media.py
"""
media_map.json 생성 진입점
사용법: python pipeline/generate_media.py [KO|ko|en]
scene_plan.json의 visual_keywords로 연합뉴스/KBS에서 장면별 최적 이미지를
검색·선택해 output/{lang}/media/에 저장하고, media_map.json으로 매핑을
남긴다. 사용한 이미지는 data/media/license_log.csv에 근거와 함께 기록된다
(7일 내 재사용 방지를 위해 이 파일은 레포에 커밋되어 실행 간에 유지되어야 함).

MEDIA_MOCK=1 환경변수(또는 config/media.yml의 mock_mode: true)를 설정하면
실제 네트워크 요청 없이 MockProvider로 동작한다.
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config_media
from assets.media_providers import YonhapProvider, KbsProvider, MockProvider
from assets.media_pipeline import build_scene_images

_PROVIDER_REGISTRY = {"yonhap": YonhapProvider, "kbs": KbsProvider}


def build_providers():
    if config_media.MOCK_MODE:
        print("  [media] MOCK_MODE=on → MockProvider만 사용")
        return [MockProvider()]

    providers = []
    for name in config_media.PROVIDER_NAMES:
        cls = _PROVIDER_REGISTRY.get(name)
        if cls:
            providers.append(cls())
        else:
            print(f"  [media] 알 수 없는 provider 설정 무시: {name}")
    return providers or [MockProvider()]


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    scene_plan_path = os.path.join(root, "output", lang, "scripts", "scene_plan.json")
    img_dir = os.path.join(root, "output", lang, "media")
    map_path = os.path.join(img_dir, "media_map.json")
    log_path = os.path.join(root, "data", "media", "license_log.csv")

    if not os.path.isfile(scene_plan_path):
        print(f"❌ scene_plan.json을 찾을 수 없습니다: {scene_plan_path}")
        sys.exit(1)

    with open(scene_plan_path, encoding="utf-8") as f:
        scene_plan = json.load(f)

    providers = build_providers()
    media_map = build_scene_images(
        scene_plan, img_dir, providers, log_path,
        dedup_window_days=config_media.DEDUP_WINDOW_DAYS,
        dedup_threshold=config_media.DEDUP_HAMMING_THRESHOLD,
        max_candidates=config_media.MAX_CANDIDATES_PER_SECTION,
    )

    os.makedirs(img_dir, exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(media_map, f, ensure_ascii=False, indent=2)

    resolved = sum(1 for v in media_map.values() if v.get("source") != "fallback")
    fallback = len(media_map) - resolved
    print(f"✅ media_map 생성 완료! 총 {len(media_map)}개 섹션 (검색 성공 {resolved} / 폴백 {fallback}) → {map_path}")
    return media_map


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
