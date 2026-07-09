# pipeline/generate_scene_plan.py
"""
scene_plan.json 생성 진입점
사용법: python pipeline/generate_scene_plan.py [KO|ko|en]
script.json을 읽어 개체명 추출 + priority_score/visual_type/visual_keywords가
포함된 scene_plan.json을 같은 output/{lang}/scripts/ 폴더에 씁니다.
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.scene_plan import build_scene_plan


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")
    out_path = os.path.join(root, "output", lang, "scripts", "scene_plan.json")

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    scene_plan = build_scene_plan(script_data)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scene_plan.model_dump(), f, ensure_ascii=False, indent=2)

    print(f"✅ scene_plan 생성 완료! 섹션 수: {len(scene_plan.sections)}개 → {out_path}")
    return scene_plan


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
