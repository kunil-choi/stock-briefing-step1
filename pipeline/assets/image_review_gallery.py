# pipeline/assets/image_review_gallery.py
"""
확정 이미지가 없는 종목의 검색 후보를 사람이 검토할 수 있는 정적 HTML
갤러리로 만든다. media_pipeline.build_scene_images()가 채운
needs_curation({종목명: [후보, ...]}, 후보는 image_bytes 포함)을 입력으로 받아:

  1. save_pending_candidates() — 후보 이미지를 assets/stock_images/_pending/
     {종목명}/{index}.jpg + meta.json으로 디스크에 저장한다(리뷰 대기열).
  2. render_gallery_html() — 그 후보들을 data URI로 임베드한 자체완결(self-
     contained) HTML 한 장으로 렌더링한다(외부 리소스 로딩 없음 — 사내망/오프라인
     에서도, 어떤 뷰어로 열어도 그대로 보인다).

검토 후 확정은 pipeline/confirm_stock_image.py가 이 대기열(meta.json)을 읽어
처리한다.
"""
import base64
import html
import json
import os
from typing import Dict, List


def save_pending_candidates(needs_curation: Dict[str, List[dict]], pending_dir: str) -> Dict[str, List[dict]]:
    """needs_curation의 각 후보(image_bytes 포함)를 pending_dir/{종목명}/{index}.jpg로
    저장하고, meta.json(같은 폴더)에 image_bytes를 뺀 메타데이터를 기록한다.
    렌더링/확정 양쪽에서 쓸 수 있도록 메타데이터 dict를 그대로 반환한다."""
    result: Dict[str, List[dict]] = {}
    for stock_name, candidates in needs_curation.items():
        stock_dir = os.path.join(pending_dir, stock_name)
        os.makedirs(stock_dir, exist_ok=True)

        meta = []
        for i, cand in enumerate(candidates):
            img_path = os.path.join(stock_dir, f"{i}.jpg")
            with open(img_path, "wb") as f:
                f.write(cand["image_bytes"])
            entry = {k: v for k, v in cand.items() if k != "image_bytes"}
            entry["index"] = i
            entry["path"] = img_path
            meta.append(entry)

        meta_path = os.path.join(stock_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        result[stock_name] = meta
    return result


def _data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _card_html(stock_name: str, cand: dict) -> str:
    uri = _data_uri(cand["path"])
    confirm_cmd = f'python pipeline/confirm_stock_image.py "{stock_name}" --index {cand["index"]}'
    score = cand.get("score")
    score_txt = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
    return f"""
      <figure class="card">
        <img src="{uri}" alt="{html.escape(stock_name)} 후보 {cand['index']}" loading="lazy">
        <figcaption>
          <div class="meta">#{cand['index']} · {html.escape(cand.get('provider', ''))} · score {score_txt}</div>
          <div class="title">{html.escape(cand.get('title', '') or '(제목 없음)')}</div>
          <div class="credit">ⓒ {html.escape(cand.get('credit', '') or '출처 미상')}</div>
          <code class="cmd">{html.escape(confirm_cmd, quote=False)}</code>
        </figcaption>
      </figure>
    """


def render_gallery_html(candidates_meta: Dict[str, List[dict]], out_path: str) -> str:
    """candidates_meta({종목명: [메타 dict, ...]}, save_pending_candidates()의
    반환값과 동일한 형식)를 받아 자체완결 HTML 갤러리 파일을 만든다."""
    sections = []
    for stock_name in sorted(candidates_meta.keys()):
        candidates = candidates_meta[stock_name]
        cards = "".join(_card_html(stock_name, c) for c in candidates)
        sections.append(f"""
          <section class="stock">
            <h2>{html.escape(stock_name)}</h2>
            <p class="hint">마음에 드는 사진 아래 명령어를 서버/로컬에서 실행하면 그 사진이
              앞으로 이 종목의 확정 이미지로 저장됩니다(최신 2장까지 유지).</p>
            <div class="grid">{cards}</div>
          </section>
        """)

    body = "".join(sections) if sections else "<p>검토가 필요한 종목이 없습니다.</p>"

    doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>종목 이미지 검토 갤러리</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, "Noto Sans KR", sans-serif;
    max-width: 1100px; margin: 0 auto; padding: 24px 16px 80px;
    background: #f7f7f8; color: #1a1a1a;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #15161a; color: #e8e8ea; }}
    .card {{ background: #202126 !important; border-color: #34353c !important; }}
    .cmd {{ background: #0c0d10 !important; color: #9fe39f !important; }}
  }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-top: 40px; }}
  .hint {{ color: #666; font-size: 13px; margin: 4px 0 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }}
  .card {{
    background: #fff; border: 1px solid #e2e2e5; border-radius: 10px;
    overflow: hidden; display: flex; flex-direction: column;
  }}
  .card img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
  .card figcaption {{ padding: 10px 12px 12px; font-size: 13px; }}
  .meta {{ color: #888; margin-bottom: 4px; }}
  .title {{ font-weight: 600; margin-bottom: 4px; line-height: 1.35; }}
  .credit {{ color: #888; margin-bottom: 8px; }}
  .cmd {{
    display: block; background: #f0f0f2; padding: 6px 8px; border-radius: 6px;
    font-size: 11px; overflow-x: auto; white-space: pre;
  }}
</style>
</head>
<body>
  <h1>종목 이미지 검토 갤러리</h1>
  <p class="hint">확정 저장소(assets/stock_images/)에 사진이 없는 종목만 표시됩니다.
    오늘은 아래 후보 중 점수가 가장 높은 사진이 임시로 사용됐습니다.</p>
  {body}
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
