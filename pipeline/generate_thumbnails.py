# pipeline/generate_thumbnails.py
"""
YouTube 업로드용 썸네일 후보 2장 생성 (발언형 + 뉴스형).

기존 generate_metadata.py의 build_thumbnail()(제목 그대로 보여주는 기본형)과
별개로, 사람이 업로드 시 고를 수 있는 클릭 유발형 후보를 추가로 만든다:
  1. 발언형: "OOO가 왜 OOO라고 말했나?" — script.json의 raw_stock_quotes
     (generate_script.py가 THUMBNAIL-QUOTE-1로 보존한 화자명/발언 원문)에서
     가장 궁금증을 유발할 만한 발언 1개를 고른다.
  2. 뉴스형: 오늘의 화제 종목 1개 — ranking.json(generate_ranking.py 산출물)의
     TOP1을 쓰고, 발언형과 겹치면 다음 순위로 넘어간다.

generate_ranking.py 이후, generate_metadata.py와 무관하게(순서 상관없이)
독립적으로 실행 가능하다 — 워크플로우에서는 ranking.json이 이미 있어야
뉴스형 선정에 랭킹 점수를 쓸 수 있으므로 generate_ranking.py 다음에 둔다.

배경 이미지는 assets.thumbnail_bg.build_thumbnail_background()가 각 후보 종목의
2주 캔들차트(generate_ranking.py/generate_assets.py가 이미 쓰는 것과 동일한
pykrx→네이버 폴백 OHLCV 소스)와 거래소 분위기를 내는 장식 요소(격자·티커
텍스트·방향 워터마크)를 합성해 그 자리에서 새로 그려서 쓴다. video 잡은
assets 잡의 output/{lang}/images/ 캐시를 내려받지 않으므로(최종 프레임에는
이미 차트가 구워져 있어 원본 PNG는 artifact로 안 올림) 매번 다시 그리게
되지만, 유료 API가 아니라 비용 문제는 없다. 시세 조회가 실패하면(상장폐지/
코드 매핑 실패 등) 캔들 없이 장식 요소만으로 배경을 구성하고, 그마저도
실패하면 chart_path=None으로 넘어가 builders.py가 기존 단색 배경으로
자동 폴백한다.

script.json에 오늘 패널 발언이 없으면(raw_stock_quotes가 비어있으면) 발언형은
건너뛰고 뉴스형만 만든다 — 부분 실패를 전체 실패로 만들지 않는다
(generate_metadata.py의 기존 fallback 원칙과 동일).

출력 파일명: output/{date}/thumbnails/{YYMMDD}_1.png(발언형), _2.png(뉴스형).

ADMIN-THUMBNAIL-EDIT-1: 위 출력과 별도로, docs/thumbnails/latest_{1,2}.png +
latest_meta.json(선정된 candidate 원본 + 현재 문구)을 함께 커밋해둔다.
GitHub Pages 관리자 페이지(stock-briefing-v3-1/docs/admin)가 이 PNG를 그대로
보여주고, 문구를 고쳐 "재생성"을 누르면 apply_thumbnail_edit.py가 이 meta.json의
candidate를 그대로 재사용해 script.json/ranking.json 없이도(즉 OpenAI 재호출
없이) 새 문구로 다시 그려 같은 경로에 덮어쓴다 — pipeline/regenerate_thumbnail.py
(로컬 CLI, script.json 기준 재선정)와는 별개의, 관리자 페이지 전용 경량 경로.
"""
import json
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from generate_metadata import _kdate_to_iso  # noqa: E402


def run(lang: str = "KO"):
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")

    if not os.path.exists(script_path):
        print(f"❌ {script_path} 없음 — 썸네일 생성 건너뜀")
        return {"quote_thumbnail": None, "news_thumbnail": None}

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
    else:
        print(f"⚠️ {ranking_path} 없음 — 랭킹 점수 없이 진행(뉴스형은 sections 순서로 폴백)")

    from assets.builders import build_thumbnail_news, build_thumbnail_quote
    from assets.thumbnail_bg import build_thumbnail_background
    from assets.thumbnail_select import (
        build_news_title, build_quote_title, select_news_candidate,
        select_quote_candidate,
    )

    img_dir = os.path.join(root, "output", lang, "images")
    os.makedirs(img_dir, exist_ok=True)

    def _chart_for(stock_name: str, is_bullish: bool):
        try:
            return build_thumbnail_background(stock_name, img_dir, is_bullish=is_bullish)
        except Exception as e:
            print(f"⚠️ {stock_name} 썸네일 배경 생성 실패(단색 배경으로 폴백): {e}")
            return None

    date_str = script.get("date", date_iso)
    result = {"quote_thumbnail": None, "news_thumbnail": None}

    meta = {"date": date_str, "date_iso": date_iso}

    quote_candidate = select_quote_candidate(script, ranking_entries)
    if quote_candidate:
        quote_title = build_quote_title(quote_candidate)
        out_path = os.path.join(out_dir, f"{yymmdd}_1.png")
        chart_path = _chart_for(quote_candidate["stock_name"], quote_candidate.get("change_positive", True))
        try:
            build_thumbnail_quote(quote_candidate, quote_title, date_str, out_path, chart_path=chart_path)
            result["quote_thumbnail"] = out_path
            meta["quote"] = {"candidate": quote_candidate, "title": quote_title}
            print(f"✅ 발언형 썸네일 → {out_path}\n   제목: {quote_title}")
        except Exception as e:
            print(f"⚠️ 발언형 썸네일 렌더링 실패: {e}")
    else:
        print("⚠️ 오늘 패널 발언 데이터(raw_stock_quotes) 없음 — 발언형 썸네일 건너뜀")

    exclude_stock = quote_candidate["stock_name"] if quote_candidate else None
    news_candidate = select_news_candidate(script, ranking_entries, exclude_stock=exclude_stock)
    if news_candidate:
        news_title = build_news_title(news_candidate)
        out_path = os.path.join(out_dir, f"{yymmdd}_2.png")
        chart_path = _chart_for(news_candidate["stock_name"], news_candidate.get("change_positive", True))
        try:
            build_thumbnail_news(news_candidate, news_title, date_str, out_path, chart_path=chart_path)
            result["news_thumbnail"] = out_path
            meta["news"] = {"candidate": news_candidate, "title": news_title}
            print(f"✅ 뉴스형 썸네일 → {out_path}\n   제목: {news_title}")
        except Exception as e:
            print(f"⚠️ 뉴스형 썸네일 렌더링 실패: {e}")
    else:
        print("⚠️ 뉴스형 썸네일에 쓸 종목 후보 없음 — 건너뜀")

    # ADMIN-THUMBNAIL-EDIT-1: 관리자 페이지가 읽는 고정 경로. 후보가 하나도
    # 없으면(둘 다 스킵) 이전 날짜의 낡은 PNG/메타가 남아 오해를 부르지 않도록
    # 아예 쓰지 않는다.
    if "quote" in meta or "news" in meta:
        docs_dir = os.path.join(root, "docs", "thumbnails")
        os.makedirs(docs_dir, exist_ok=True)
        if result["quote_thumbnail"]:
            shutil.copyfile(result["quote_thumbnail"], os.path.join(docs_dir, "latest_1.png"))
        if result["news_thumbnail"]:
            shutil.copyfile(result["news_thumbnail"], os.path.join(docs_dir, "latest_2.png"))
        with open(os.path.join(docs_dir, "latest_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"✅ 관리자 페이지용 썸네일 메타 → {docs_dir}/latest_meta.json")

    return result


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
