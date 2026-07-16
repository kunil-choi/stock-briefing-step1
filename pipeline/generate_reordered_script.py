# pipeline/generate_reordered_script.py
"""
reordered_script.json 생성 진입점

script.json을 읽어 전체 구성(훅 → 오늘의 한 줄 결론 → 주도주 TOP → 시장배경 →
섹터분석 → 나머지 종목 체크포인트 → AI 투자 전략 → 컴플라이언스 클로징,
short_form=False)으로 재정렬한 reordered_script.json을 만든다. V3(증권사
리포트 제외)와 동등한 전체 콘텐츠를 유지하면서 훅으로 시작하는 영상 구성만
입히는 것이 목적이다 — 종목 3개짜리로 잘라내는 하이라이트 축약판이 아니다.
목표 길이는 config/schedule.yml의 duration.longform(기본 약 10분)이다.
그리고 이 새 구조를 기준으로 scene_plan.json도 다시 계산해 저장한다(섹션
id/순서가 바뀌었으므로 개체명·priority_score도 그에 맞춰 갱신되어야 함).

★ script.json 자체는 건드리지 않으므로(읽기 전용) generate_metadata.py의
제목/설명/태그 생성은 계속 원본 script.json을 그대로 쓴다. 하지만
generate_voice.py/generate_assets.py/generate_video.py/generate_subtitles.py/
quality_gate.py는 이 reordered_script.json을 실제 영상 제작 입력으로
사용한다 — 훅/재정렬이 최종 영상에 실제로 반영되는 지점이 바로 여기다.

★ narrative_reorder.reorder_sections(short_form=False)는 ai_strategy 섹션을
"체크리스트"로 재합성해(원문 대신 softened 문구로 재구성) 담는다. 이는 V3에
없는 별도 다이제스트라서, 아래에서 risks 다이제스트는 제거하고 checklist는
원본 ai_strategy 섹션(요약 왜곡 없는 실제 콘텐츠)으로 되돌려 V3와 동일한
"AI 투자 전략" 섹션이 그대로 영상에 실리도록 한다(narrative_reorder.py 자체와
그 테스트는 건드리지 않고 이 진입점에서만 후처리한다).
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.narrative_reorder import reorder_sections
from assets.scene_plan import build_scene_plan


def _restore_full_content(reordered: dict, script_data: dict) -> dict:
    """risks 다이제스트(각 종목 카드에 이미 있는 리스크의 중복 요약)는 제거하고,
    checklist(ai_strategy를 조언체 완화해 재합성한 것)는 원본 ai_strategy
    섹션으로 교체해 V3와 동일한 "AI 투자 전략" 콘텐츠를 그대로 보존한다."""
    orig_ai_strategy = next(
        (s for s in script_data.get("sections", []) if s.get("id") == "ai_strategy"), None
    )
    sections = []
    for s in reordered.get("sections", []):
        if s.get("id") == "risks":
            continue
        if s.get("id") == "checklist":
            if orig_ai_strategy:
                sections.append({
                    **orig_ai_strategy,
                    "section_type": "ai_strategy",
                    "importance": s.get("importance", 0.5),
                    "entities": s.get("entities", []),
                })
            continue
        sections.append(s)
    return {**reordered, "sections": sections}


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")
    reordered_path = os.path.join(root, "output", lang, "scripts", "reordered_script.json")
    scene_plan_path = os.path.join(root, "output", lang, "scripts", "scene_plan.json")

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    reordered = reorder_sections(script_data, short_form=False)
    reordered = _restore_full_content(reordered, script_data)
    with open(reordered_path, "w", encoding="utf-8") as f:
        json.dump(reordered, f, ensure_ascii=False, indent=2)
    print(f"✅ reordered_script.json 생성 완료! 섹션 수: {len(reordered['sections'])}개 → {reordered_path}")

    # scene_plan.json은 재정렬된 구조(hook/conclusion/top_mover 등 새 id)를
    # 기준으로 다시 계산해 덮어쓴다 — Phase B의 generate_scene_plan.py가 만든
    # (script.json 기준) 버전을 대체한다.
    scene_plan = build_scene_plan(reordered)
    with open(scene_plan_path, "w", encoding="utf-8") as f:
        json.dump(scene_plan.model_dump(), f, ensure_ascii=False, indent=2)
    print(f"✅ scene_plan.json을 재정렬된 구조 기준으로 갱신 완료 → {scene_plan_path}")

    return reordered


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
