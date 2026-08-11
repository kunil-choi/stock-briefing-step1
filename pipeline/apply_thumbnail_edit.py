# pipeline/apply_thumbnail_edit.py
"""
관리자 페이지(stock-briefing-v3-1/docs/admin) 전용 — 저장된 썸네일 후보에
새 문구만 입혀 다시 그리는 경량 CLI.

generate_thumbnails.py가 매 실행마다 docs/thumbnails/latest_meta.json에 남겨둔
candidate(선정된 발언/종목 원본 데이터)를 그대로 재사용하므로, script.json/
ranking.json이 없어도(즉 OpenAI를 다시 부르지 않고) 문구만 바꿔 1~2분 안에
재렌더링할 수 있다. regenerate_thumbnail.py(로컬 CLI, script.json 기준으로
후보를 다시 선정)와 달리 이미 확정된 후보의 "문구만" 바꾸는 용도라 별도로
분리했다 — 관리자 페이지가 트리거하는 .github/workflows/regenerate_thumbnail.yml이
이 스크립트를 부른다.
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main():
    parser = argparse.ArgumentParser(description="저장된 썸네일 후보에 새 문구를 입혀 재생성")
    parser.add_argument("which", choices=["quote", "news"], help="발언형(quote) 또는 뉴스형(news)")
    parser.add_argument("--title", required=True, help="새 문구. 리터럴 \\n은 줄바꿈으로 해석한다")
    parser.add_argument("--meta", default="docs/thumbnails/latest_meta.json")
    args = parser.parse_args()

    root = os.path.join(_HERE, "..")
    meta_path = os.path.join(root, args.meta)
    if not os.path.isfile(meta_path):
        raise SystemExit(f"❌ {meta_path} 없음 — 오늘의 브리핑 워크플로우가 먼저 실행돼야 합니다")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    entry = meta.get(args.which)
    if not entry or not entry.get("candidate"):
        raise SystemExit(f"❌ meta.json에 '{args.which}' 후보가 없습니다")

    candidate = entry["candidate"]
    title = args.title.replace("\\n", "\n")

    from assets.builders import build_thumbnail_news, build_thumbnail_quote
    from assets.thumbnail_bg import build_thumbnail_background

    img_dir = os.path.join(root, "output", "KO", "images")
    os.makedirs(img_dir, exist_ok=True)

    chart_path = None
    try:
        chart_path = build_thumbnail_background(
            candidate["stock_name"], img_dir,
            is_bullish=candidate.get("change_positive", True),
        )
    except Exception as e:
        print(f"⚠️ {candidate['stock_name']} 썸네일 배경 생성 실패(단색 배경으로 폴백): {e}")

    docs_dir = os.path.join(root, "docs", "thumbnails")
    out_name = "latest_1.png" if args.which == "quote" else "latest_2.png"
    out_path = os.path.join(docs_dir, out_name)
    build_fn = build_thumbnail_quote if args.which == "quote" else build_thumbnail_news

    build_fn(candidate, title, meta.get("date", meta.get("date_iso", "")), out_path, chart_path=chart_path)

    entry["title"] = title
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"✅ 재생성 완료 → {out_path}\n   문구: {title}")


if __name__ == "__main__":
    main()
