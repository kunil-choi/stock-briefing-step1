# pipeline/generate_reordered_script.py
"""
reordered_script.json 생성 진입점

script.json을 읽어 "종목 언급 중심" 구성(훅 → 채널 언급 인트로(고정) → 주요
지표(있으면) → 대형 주도주 → 관심종목 → AI 히든픽(있으면) → 컴플라이언스
클로징)으로 재정렬한 reordered_script.json을 만든다.

개장 전(07:10~08:20 KST) 방송이라 시장 요약/전망에 쓸 수 있는 데이터가 전부
전일 종가·오늘 새벽 마감된 미국 시장 자료뿐이라 "시장 해설"이 시의성에 안
맞는다는 판단 하에, v3-1의 핵심 데이터인 "지난 24시간 채널 언급 종목 정리"에
집중한다. market_summary의 해설(corner_summary/points)·섹터분석·AI 투자전략·
리스크 다이제스트는 이 구성에서 전부 제외한다(narrative_reorder.
build_mention_briefing() 참고). 그리고 이 새 구조를 기준으로 scene_plan.json도
다시 계산해 저장한다(섹션 id/순서가 바뀌었으므로 개체명·priority_score도 그에
맞춰 갱신되어야 함).

★ script.json 자체는 건드리지 않으므로(읽기 전용) generate_metadata.py의
제목/설명/태그 생성은 계속 원본 script.json을 그대로 쓴다. 하지만
generate_voice.py/generate_assets.py/generate_video.py/generate_subtitles.py/
quality_gate.py는 이 reordered_script.json을 실제 영상 제작 입력으로
사용한다 — 재정렬이 최종 영상에 실제로 반영되는 지점이 바로 여기다.

★ 기존 8단계 "장전 의사결정형" 구성(narrative_reorder.reorder_sections(),
short_form 포함)은 그대로 남아 있다 — 이 진입점이 build_mention_briefing()으로
바뀌었을 뿐, reorder_sections()과 그 테스트(tests/test_narrative_reorder.py)는
전혀 건드리지 않았다. 나중에 다시 필요해지면 언제든 이 파일의 호출만 바꾸면
된다.
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.narrative_reorder import build_mention_briefing
from assets.scene_plan import build_scene_plan


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

    reordered = build_mention_briefing(script_data)
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
