# pipeline/assets/ranking_builders.py
"""
"주도주 랭킹형" 플롯 — ranking.build_ranking()의 결과를 TOP5 카드형 장면으로
렌더링한다. 기존 builders.py와 동일한 HTML/CSS + Playwright 렌더링 경로
(render_html_to_png)를 재사용한다.
"""
import os

from .html_theme import shell, ranking_card, bullet_column, risk_card, PALETTE
from .render import render_html_to_png


def build_ranking_overview(ranking_data: dict, out_dir: str) -> str:
    """오늘의 주도주 TOP5를 한 화면에 공개하는 슬라이드(구성 1~2단계)."""
    cards = "".join(
        ranking_card(
            c["rank"], c["companies"], c["code"], c["themes"], c["ranking_score"],
            c["volume_score"], c["news_score"], c["report_score"],
            c.get("change", ""), c.get("change_positive", True),
        )
        for c in ranking_data.get("ranking", [])
    )
    content = f'<div style="display:flex;flex-direction:column;gap:14px;">{cards}</div>'
    html = shell("오늘의 주도주 TOP5", content)
    return render_html_to_png(html, os.path.join(out_dir, "00_ranking_top5.png"))


def build_ranking_detail(entry: dict, script_sections_by_id: dict, out_dir: str) -> str:
    """개별 순위 상세 슬라이드(구성 3~6단계: 종목 상세/근거/리스크).
    script.json의 원본 종목 섹션(catalysts/risks)을 그대로 재사용한다."""
    sec = script_sections_by_id.get(entry["id"], {})
    card_html = ranking_card(
        entry["rank"], entry["companies"], entry["code"], entry["themes"],
        entry["ranking_score"], entry["volume_score"], entry["news_score"],
        entry["report_score"], entry.get("change", ""), entry.get("change_positive", True),
    )

    catalysts = sec.get("catalysts") or []
    risks = sec.get("risks") or []
    lower_html = ""
    if catalysts or risks:
        cols = ""
        if catalysts:
            cols += bullet_column("거래대금/수급/뉴스 근거", catalysts, PALETTE["up"])
        if risks:
            cols += f'<div style="flex:1;">{risk_card(risks, "추격 매수 리스크")}</div>'
        lower_html = f'<div style="display:flex;gap:24px;margin-top:24px;">{cols}</div>'

    content = f"{card_html}{lower_html}"
    html = shell(f"TOP{entry['rank']} 상세: {entry['companies']}", content)
    filename = f"{entry['rank']:02d}_rank_{entry['companies']}.png"
    return render_html_to_png(html, os.path.join(out_dir, filename))


def build_ranking_cards(ranking_data: dict, script_data: dict, out_dir: str) -> list:
    """TOP5 overview 1장 + 개별 상세 카드(TOP5개)를 렌더링해 경로 목록을 반환한다."""
    os.makedirs(out_dir, exist_ok=True)
    sections_by_id = {s.get("id", ""): s for s in script_data.get("sections") or []}

    paths = [build_ranking_overview(ranking_data, out_dir)]
    for entry in ranking_data.get("ranking", []):
        paths.append(build_ranking_detail(entry, sections_by_id, out_dir))
    return paths
