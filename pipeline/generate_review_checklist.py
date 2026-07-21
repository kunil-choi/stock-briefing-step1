# pipeline/generate_review_checklist.py
"""
review-checklist.md 생성 진입점
사용법: python pipeline/generate_review_checklist.py [KO|ko|en]

scene_plan.json / asset_manifest.json / reordered_script.json을 읽어, 렌더링
전에 사람이 빠르게 훑어볼 수 있는 체크리스트를 만든다. 자동으로 판정 가능한
항목만 담는다(오프닝 screenText 존재 여부, 화면 텍스트 2줄 초과 섹션,
needsReview인데 selected된 자산이 있는지 — 있으면 안 됨, 오염 종목명 목록,
외신 자산 목록).
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _load_json_or_default(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_checklist(scene_plan: dict, asset_manifest: dict, reordered_script: dict) -> str:
    sections = scene_plan.get("sections") or []
    by_id = {s.get("id", ""): s for s in sections}
    assets = asset_manifest.get("assets") or []

    lines = ["# 렌더링 전 검수 체크리스트", ""]

    # 1) 오프닝 screenText 존재 여부
    hook = by_id.get("hook") or by_id.get("opening") or {}
    ok = bool(hook.get("screenText"))
    lines.append(f"- [{'x' if ok else ' '}] 오프닝 화면 텍스트(screenText)가 준비돼 있는가"
                 + ("" if ok else " — ⚠️ 없음, 원본 문장으로 폴백됨"))

    # 2) 화면 텍스트 2줄 초과 섹션
    over = [s["id"] for s in sections if len(s.get("screenText") or []) > 2]
    lines.append(f"- [{'x' if not over else ' '}] 모든 섹션의 화면 텍스트가 2줄 이내인가"
                 + ("" if not over else f" — ⚠️ 초과: {', '.join(over)}"))

    # 3) needsReview인데 selected=True인 자산(있으면 버그)
    bad = [a["assetId"] for a in assets if a.get("needsReview") and a.get("selected")]
    lines.append(f"- [{'x' if not bad else ' '}] 권리 미확인(needsReview) 자산이 자동 렌더링에 쓰이지 않았는가"
                 + ("" if not bad else f" — ❌ 발견: {', '.join(bad)} (렌더링 파이프라인 점검 필요)"))

    # 4) 오염 의심 종목명
    dirty = [s["id"] for s in sections if s.get("needsDataReview")]
    lines.append(f"- [{'x' if not dirty else ' '}] 종목명이 오염되지 않았는가"
                 + ("" if not dirty else f" — ⚠️ 검수 필요: {', '.join(dirty)} (안전 표시명으로 대체됨)"))

    # 5) 외신 자산(수동 검수 대상)
    foreign = [a["assetId"] for a in assets if a.get("isForeignAgency")]
    lines.append(f"- [{'x' if not foreign else ' '}] 외신 자산이 없는가(있으면 수동 검수 필요)"
                 + ("" if not foreign else f" — ℹ️ 수동 검수 대상: {', '.join(foreign)}"))

    # 6) 자산 개요
    selected = [a for a in assets if a.get("selected")]
    review_pending = [a for a in assets if a.get("needsReview")]
    lines += [
        "",
        "## 자산 개요",
        f"- 검토된 후보: {len(assets)}개",
        f"- 실제 선택(selected): {len(selected)}개",
        f"- 검수 대기(needsReview): {len(review_pending)}개",
    ]

    return "\n".join(lines) + "\n"


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    scene_plan = _load_json_or_default(os.path.join(root, "output", lang, "scripts", "scene_plan.json"), {"sections": []})
    asset_manifest = _load_json_or_default(os.path.join(root, "output", lang, "media", "asset_manifest.json"), {"assets": []})
    reordered_script = _load_json_or_default(os.path.join(root, "output", lang, "scripts", "reordered_script.json"), {"sections": []})

    checklist = build_checklist(scene_plan, asset_manifest, reordered_script)
    out_path = os.path.join(root, "output", lang, "review-checklist.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(checklist)
    print(f"✅ review-checklist.md 생성 완료 → {out_path}")
    return checklist


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
