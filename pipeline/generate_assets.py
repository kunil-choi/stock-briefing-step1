# pipeline/generate_assets.py
"""
AI 주식 브리핑 — 에셋 생성 진입점
사용법: python pipeline/generate_assets.py [KO|ko|en]

reordered_script.json(전체 구성: 훅 → 결론 → 주도주 TOP → 시장배경 →
섹터분석 → 나머지 종목 체크포인트 → AI 투자 전략 → 클로징)을 입력으로 받아,
각 섹션의 id/section_type에 따라 알맞은 빌더로 프레임을 렌더링한다. 정해진
순서로 고정 섹션들을 호출하는 대신 reordered_script.json의 실제 순서를 그대로
따라간다 — 재정렬 결과(훅 오프닝 등)가 실제 영상에 반영되려면 이 파일이
reordered_script.json을 읽어야 한다(script.json만 읽으면 재정렬이 무시된다).
"""
import os, re, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.builders import (
    build_hook,
    build_conclusion,
    build_market_summary,
    build_sector,
    build_stock_cards,
    build_extra_watchlist,
    build_brokerage_report,
    build_ai_strategy,
    build_closing,
)

# id 기준으로 전용 빌더를 호출해야 하는 집계/코너 섹션 — 제네릭 stock_ 카드
# 디스패치(build_stock_cards)보다 먼저 걸러야 한다. build_stock_cards는
# 종목 하나짜리(price/channel_summaries) 구조를 기대하므로, items 리스트
# 구조인 이 집계 섹션들을 잘못 넘기면 빈 카드가 렌더링된다.
_AGGREGATE_BUILDERS = {
    "stock_추가관심종목": build_extra_watchlist,
    "stock_증권사리포트": build_brokerage_report,
}
from assets.render import close_renderer
from assets.html_theme import set_briefing_date, set_ticker_text


def _kdate_to_dotted(date_str: str) -> str:
    """'2026년 07월 08일' → '2026.07.08'. 매칭 실패 시 빈 문자열."""
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}.{int(mo):02d}.{int(d):02d}"


def _load_json_or_default(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_visual(section_id: str, scene_by_id: dict, media_map: dict) -> dict:
    """scene_plan.json(screenText/키워드/needsDataReview)과 media_map.json
    (선택된 이미지)을 섹션 id로 조인해 빌더에 넘길 visual dict를 만든다.
    scene_plan.json/media_map.json이 없거나(1·2차 단계를 안 거쳤거나 실패한
    경우) 해당 섹션이 없으면 빈 값들로 채워, 빌더가 기존 폴백 경로(원본 문장/
    이미지 없음)로 자연스럽게 동작하도록 한다 — 회귀 없음."""
    scene = scene_by_id.get(section_id, {})
    media = media_map.get(section_id, {})
    image_path = media.get("image_path")
    # media_map.json의 image_path는 media_pipeline.select_best_image()가 이미
    # needsReview=False인 것만 selected로 기록하지만(2차 작업), 렌더링 단계에서도
    # 파일이 실제 존재하는지 한 번 더 방어적으로 확인한다.
    if image_path and not os.path.isfile(image_path):
        image_path = None
    return {
        "screenText": scene.get("screenText") or [],
        "backgroundType": scene.get("backgroundType", "image"),
        "visualKeywordsKo": scene.get("visualKeywordsKo") or scene.get("visual_keywords") or [],
        "needsDataReview": bool(scene.get("needsDataReview")),
        "safeDisplayName": scene.get("safeDisplayName"),
        "image_path": image_path,
    }


_TICKER_AGGREGATE_IDS = {"stock_추가관심종목", "stock_증권사리포트"}


def _compute_ticker(scene_sections: list, max_items: int = 6):
    """오늘 영상이 다루는 종목명을 priority_score 상위 섹션에서 모아 하단
    티커 텍스트로 만든다. 시장 전반 분위기(dataOverlay.marketMood)로 색조를
    정한다.

    FIX-TICKER-1: 예전에는 섹션 종류를 가리지 않고 visualKeywordsKo[0]을
    그대로 모았다 — 그 결과 "삼성전자 · 삼성SDI · KB금융 · HD현대중공업 ·
    LG화학 · 금융"처럼 실제 종목명과 섹터/키워드("금융")가 뒤섞여 무엇을
    나열한 목록인지 애매했다. 이제는 개별 종목 섹션(stock_/hidden_, 집계
    섹션 제외)의 종목명만 모으고 "오늘의 주요 관심종목: " 라벨을 붙여
    이 영상이 다루는 종목 목록임을 명확히 한다."""
    ranked = sorted(scene_sections, key=lambda s: s.get("priority_score", 0), reverse=True)
    names = []
    for s in ranked:
        sid = s.get("id", "")
        if sid in _TICKER_AGGREGATE_IDS:
            continue
        if not (sid.startswith("stock_") or sid.startswith("hidden_")):
            continue
        name = sid.replace("stock_", "").replace("hidden_", "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= max_items:
            break
    text = f"오늘의 주요 관심종목: {' · '.join(names)}" if names else ""

    tone = "neutral"
    for s in scene_sections:
        if s.get("id") == "market_summary":
            mood = (s.get("dataOverlay") or {}).get("marketMood")
            if mood in ("bullish", "bearish"):
                tone = mood
            break
    return text, tone


def run(lang: str = "KO"):
    lang = lang.upper()

    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "reordered_script.json")
    scene_plan_path = os.path.join(root, "output", lang, "scripts", "scene_plan.json")
    media_map_path = os.path.join(root, "output", lang, "media", "media_map.json")
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

    scene_plan = _load_json_or_default(scene_plan_path, {"sections": []})
    scene_sections = scene_plan.get("sections") or []
    scene_by_id = {s.get("id", ""): s for s in scene_sections}
    if scene_by_id:
        print(f"🎬 scene_plan.json 로드 완료 (섹션 수: {len(scene_by_id)})")
    else:
        print("  ⚠️ scene_plan.json 없음 — 화면 텍스트/배경 이미지 없이 기존 방식으로 렌더링")

    media_map = _load_json_or_default(media_map_path, {})
    if media_map:
        resolved = sum(1 for v in media_map.values() if v.get("source") != "fallback")
        print(f"🖼️ media_map.json 로드 완료 (이미지 확보 {resolved}/{len(media_map)}개 섹션)")
    else:
        print("  ⚠️ media_map.json 없음 — 배경 이미지 없이 기존 방식으로 렌더링")

    # 모든 슬라이드 상단바 날짜를 실제 브리핑 날짜로 고정 (렌더링 시점의 시스템
    # 날짜로 폴백하면 워크플로우가 전날 데이터로 실행됐을 때 날짜가 어긋난다)
    briefing_date = _kdate_to_dotted(data.get("date", ""))
    if briefing_date:
        set_briefing_date(briefing_date)
        print(f"📅 슬라이드 날짜 고정: {briefing_date}")

    ticker_text, ticker_tone = _compute_ticker(scene_sections)
    if ticker_text:
        set_ticker_text(ticker_text, ticker_tone)
        print(f"📰 하단 티커: {ticker_text}")

    asset_map = {"frames": [], "lang": lang}

    try:
        stock_idx = 0
        for sec in sections:
            sid = sec.get("id", "")
            section_type = sec.get("section_type", "")
            visual = _resolve_visual(sid, scene_by_id, media_map)

            if sid == "hook":
                asset_map["frames"].extend(build_hook(sec, out_dir, visual=visual))
            elif sid == "conclusion":
                asset_map["frames"].append(build_conclusion(sec, out_dir))
            elif sid == "closing":
                asset_map["frames"].append(build_closing(data, out_dir))
            elif sid == "market_summary":
                asset_map["frames"].extend(build_market_summary(data, out_dir, visual=visual))
            elif sid == "sectors":
                asset_map["frames"].append(build_sector(data, out_dir, visual=visual))
            elif sid == "ai_strategy":
                asset_map["frames"].append(build_ai_strategy(data, out_dir))
            elif sid in _AGGREGATE_BUILDERS:
                frame = _AGGREGATE_BUILDERS[sid](data, out_dir, img_dir)
                if frame:
                    asset_map["frames"].append(frame)
            elif section_type == "top_mover" or sid.startswith("stock_") or sid.startswith("hidden_"):
                name = sid.replace("stock_", "").replace("hidden_", "")
                prefix = f"{10 + stock_idx:02d}_{name}"
                stock_idx += 1
                asset_map["frames"].extend(build_stock_cards(sec, out_dir, img_dir, prefix, visual=visual))
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
