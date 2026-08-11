# pipeline/regenerate_thumbnail.py
"""
발언형/뉴스형 썸네일 문구를 사람이 다듬어서 다시 렌더링하는 CLI.

generate_thumbnails.py가 자동으로 고른 후보(발언 또는 종목)와 배경 차트는
그대로 재사용하고, 화면에 들어갈 제목 문구만 --title로 교체해서
output/{date}/thumbnails/의 같은 파일을 다시 그린다. 후보 자체를 바꾸고
싶다면(예: 다른 발언/다른 종목을 쓰고 싶다) generate_thumbnails.py를
다시 실행해야 한다 — 이 스크립트는 "추천 문구 다듬기" 전용이다.

사용법:
  # 1) --title 없이 실행하면 지금 추천되는 문구만 보여주고 끝난다(재렌더 X)
  python pipeline/regenerate_thumbnail.py KO quote
  python pipeline/regenerate_thumbnail.py KO news

  # 2) 그 문구를 일부 고쳐서 --title로 넘기면 같은 파일을 그 문구로 다시 그린다
  python pipeline/regenerate_thumbnail.py KO quote --title '고친 문구'
  python pipeline/regenerate_thumbnail.py KO news --title '고친 문구'

  # 3) 줄바꿈도 직접 정하고 싶으면 --title 안에 \n을 그대로 타이핑하면 된다
  #    (셸에서 실제 개행을 넣기 번거로우니 두 글자 "\n"을 줄바꿈으로 해석한다)
  python pipeline/regenerate_thumbnail.py KO news --title '코스피 폭락,\n진범은 따로 있었다'
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from generate_metadata import _kdate_to_iso  # noqa: E402


def _load_context(lang: str):
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")
    if not os.path.exists(script_path):
        raise SystemExit(f"❌ {script_path} 없음 — generate_script.py를 먼저 실행하세요")
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    date_iso = _kdate_to_iso(script.get("date", ""))
    yymmdd = date_iso.replace("-", "")[2:]
    out_dir = os.path.join(root, "output", date_iso, "thumbnails")
    os.makedirs(out_dir, exist_ok=True)

    ranking_path = os.path.join(root, "output", date_iso, "ranking", "ranking.json")
    ranking_entries = []
    if os.path.isfile(ranking_path):
        with open(ranking_path, "r", encoding="utf-8") as f:
            ranking_entries = (json.load(f) or {}).get("ranking", [])

    return root, script, date_iso, yymmdd, out_dir, ranking_entries


def main():
    parser = argparse.ArgumentParser(description="썸네일 문구를 사람이 고쳐서 다시 렌더링")
    parser.add_argument("lang", nargs="?", default="KO")
    parser.add_argument("which", choices=["quote", "news"], help="발언형(quote) 또는 뉴스형(news)")
    parser.add_argument("--title", help="이 문구로 바꿔서 다시 렌더링(생략하면 추천 문구만 보여주고 종료). "
                                         "문자 그대로의 \\n은 줄바꿈으로 해석한다")
    args = parser.parse_args()

    root, script, date_iso, yymmdd, out_dir, ranking_entries = _load_context(args.lang)

    from assets.builders import build_thumbnail_news, build_thumbnail_quote
    from assets.thumbnail_bg import build_thumbnail_background
    from assets.thumbnail_select import (
        build_news_title, build_quote_title, select_news_candidate,
        select_quote_candidate,
    )

    img_dir = os.path.join(root, "output", args.lang, "images")
    os.makedirs(img_dir, exist_ok=True)
    date_str = script.get("date", date_iso)

    # 뉴스형 후보는 발언형과 같은 종목이면 다음 순위로 넘어가야 하므로
    # (generate_thumbnails.py와 동일 로직), which 값과 무관하게 발언형 후보를
    # 먼저 계산해둔다.
    quote_candidate = select_quote_candidate(script, ranking_entries)

    if args.which == "quote":
        candidate = quote_candidate
        if not candidate:
            raise SystemExit("⚠️ 오늘 패널 발언 데이터 없음 — 발언형 후보가 없습니다")
        default_title = build_quote_title(candidate)
        out_path = os.path.join(out_dir, f"{yymmdd}_1.png")
        build_fn = build_thumbnail_quote
    else:
        exclude_stock = quote_candidate["stock_name"] if quote_candidate else None
        candidate = select_news_candidate(script, ranking_entries, exclude_stock=exclude_stock)
        if not candidate:
            raise SystemExit("⚠️ 뉴스형에 쓸 종목 후보가 없습니다")
        default_title = build_news_title(candidate)
        out_path = os.path.join(out_dir, f"{yymmdd}_2.png")
        build_fn = build_thumbnail_news

    print(f"추천 문구: {default_title}")

    if not args.title:
        print('→ --title "고친 문구" 를 붙여서 다시 실행하면 그 문구로 재렌더링합니다.')
        return

    chart_path = None
    try:
        chart_path = build_thumbnail_background(
            candidate["stock_name"], img_dir,
            is_bullish=candidate.get("change_positive", True),
        )
    except Exception as e:
        print(f"⚠️ {candidate['stock_name']} 썸네일 배경 생성 실패(단색 배경으로 폴백): {e}")

    title = args.title.replace("\\n", "\n")
    build_fn(candidate, title, date_str, out_path, chart_path=chart_path)
    print(f"✅ 재렌더링 완료 → {out_path}\n   문구: {title}")


if __name__ == "__main__":
    main()
