# pipeline/generate_assets.py
"""
AI 주식 브리핑 — 에셋 생성 진입점
사용법: python pipeline/generate_assets.py [KO|ko|en]

reordered_script.json(짧은 하이라이트 구성: 훅 → 결론 → TOP3(핵심 멘션) →
클로징)을 입력으로 받아, 각 섹션의 id/section_type에 따라 알맞은 빌더로
프레임을 렌더링한다. 예전처럼 정해진 순서로 고정 섹션들을 호출하는 대신
reordered_script.json의 실제 순서를 그대로 따라간다 — Phase E의 재정렬
결과(훅 오프닝 등)가 실제 영상에 반영되려면 이 파일이 reordered_script.json을
읽어야 한다(예전에는 script.json만 읽어서 재정렬이 무시됐었다).
"""
import os, re, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.builders import (
    build_hook,
    build_conclusion,
    build_stock_cards,
    build_closing,
)
from assets.render import close_renderer
from assets.html_theme import set_briefing_date


def _kdate_to_dotted(date_str: str) -> str:
    """'2026년 07월 08일' → '2026.07.08'. 매칭 실패 시 빈 문자열."""
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}.{int(mo):02d}.{int(d):02d}"


def run(lang: str = "KO"):
    lang = lang.upper()

    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "reordered_script.json")
    out_dir = os.path.join(root, "output", lang, "frames")
    img_dir = os.path.join(root, "output", lang, "images")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    if not os.path.isfile(script_path):
        print(f"❌ reordered_script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    sections = data.get("sections", [])
    print(f"📂 reordered_script.json 로드 완료 (섹션 수: {len(sections)})")

    # 모든 슬라이드 상단바 날짜를 실제 브리핑 날짜로 고정 (렌더링 시점의 시스템
    # 날짜로 폴백하면 워크플로우가 전날 데이터로 실행됐을 때 날짜가 어긋난다)
    briefing_date = _kdate_to_dotted(data.get("date", ""))
    if briefing_date:
        set_briefing_date(briefing_date)
        print(f"📅 슬라이드 날짜 고정: {briefing_date}")

    asset_map = {"frames": [], "lang": lang}

    try:
        stock_idx = 0
        for sec in sections:
            sid = sec.get("id", "")
            section_type = sec.get("section_type", "")

            if sid == "hook":
                asset_map["frames"].append(build_hook(sec, out_dir))
            elif sid == "conclusion":
                asset_map["frames"].append(build_conclusion(sec, out_dir))
            elif sid == "closing":
                asset_map["frames"].append(build_closing(data, out_dir))
            elif section_type == "top_mover" or sid.startswith("stock_") or sid.startswith("hidden_"):
                name = sid.replace("stock_", "").replace("hidden_", "")
                prefix = f"{10 + stock_idx:02d}_{name}"
                stock_idx += 1
                asset_map["frames"].extend(build_stock_cards(sec, out_dir, img_dir, prefix))
            else:
                print(f"  ⚠️ 알 수 없는 섹션 — 건너뜀: id={sid} section_type={section_type}")
    finally:
        close_renderer()

    map_path = os.path.join(root, "output", lang, "asset_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(asset_map, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료: {len(asset_map['frames'])}개 프레임 → {out_dir}")
    return asset_map


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
