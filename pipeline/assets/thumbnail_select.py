# pipeline/assets/thumbnail_select.py
"""
YouTube 썸네일 후보 선정 (발언형 + 뉴스형, 각 1개).

- 발언형: "OOO가 왜 OOO라고 말했나?" 포맷. script.json의 raw_stock_quotes
  (generate_script.py가 THUMBNAIL-QUOTE-1로 보존한 화자명/발언 원문/sentiment)에서
  가장 궁금증을 유발할 만한 발언 1개를 고른다.
- 뉴스형: 오늘의 화제 종목 1개(ranking.json TOP1, 발언형과 겹치면 다음 순위).

generate_metadata.py의 build_title()과 같은 원칙으로 LLM 호출 없이 규칙+템플릿
기반으로만 만든다(비용/복잡도 최소화, 필요시 후속 단계에서 LLM으로 문구만
다듬는 방향으로 고도화 가능 — 선정 로직과 렌더링은 그대로 재사용 가능하게
분리해뒀다).
"""
import re

from .config import normalize_stock_name
from .korean_numbers import pick_i_ga
from .screen_text import drop_leading_filler, strip_sentence_ending

# sentiment 필드 값의 형식(enum인지 자유 텍스트인지)이 원본 데이터 소스
# (stock-briefing-v3-1)에 따라 달라질 수 있어 안전하게 키워드 매칭만 한다.
_POSITIVE_WORDS = ["긍정", "매수", "상승", "호재", "상향", "기대", "추천", "비중확대", "저가매수"]
_NEGATIVE_WORDS = ["부정", "매도", "하락", "악재", "하향", "우려", "리스크", "주의", "비중축소", "차익실현"]

_AGGREGATE_STOCK_PREFIXES = ("stock_추가", "stock_오늘", "stock_증권사")


def _is_core_stock_section(sid: str) -> bool:
    if not (sid.startswith("stock_") or sid.startswith("hidden_")):
        return False
    return not sid.startswith(_AGGREGATE_STOCK_PREFIXES)


def _section_by_normalized_name(sections: list) -> dict:
    out = {}
    for sec in sections:
        sid = sec.get("id", "")
        if not _is_core_stock_section(sid):
            continue
        name = normalize_stock_name(sid.replace("stock_", "").replace("hidden_", ""))
        out[name] = sec
    return out


def _quote_sentiment_sign(sentiment: str, quote: str) -> int:
    text = f"{sentiment or ''} {quote or ''}"
    pos = any(w in text for w in _POSITIVE_WORDS)
    neg = any(w in text for w in _NEGATIVE_WORDS)
    if pos and not neg:
        return 1
    if neg and not pos:
        return -1
    return 0


def _specificity_bonus(quote: str) -> float:
    """목표주가/구체적 수치가 있으면 제목화하기 쉬워 가산점."""
    return 0.3 if re.search(r"\d", quote or "") else 0.0


def clean_quote_for_display(quote: str, max_len: int = 42) -> str:
    t = drop_leading_filler((quote or "").strip())
    t = strip_sentence_ending(t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "…"
    return t


def _ranking_score_for(stock_name: str, ranking_entries: list) -> float:
    for e in ranking_entries or []:
        if e.get("companies") == stock_name:
            return e.get("ranking_score", 0.0)
    return 0.15  # 랭킹 TOP5 밖 종목의 기본값(약간의 관심도는 있다고 가정)


def select_quote_candidate(script_data: dict, ranking_entries: list = None) -> dict:
    """raw_stock_quotes에서 발언형 썸네일에 쓸 발언 1개를 고른다. 없으면 None.

    스코어 = 종목 랭킹 점수(ranking.json 재사용) + 역발상 보너스(발언 정서가
    그날 등락 방향과 반대일 때 — "빠졌는데 왜 매수라고 했지?" 궁금증이 가장 큼)
    + 구체성 보너스(수치 포함) + 채널 보너스(증권사보다 유튜브/경제방송이
    말투가 더 생생해 제목화하기 쉬움).
    """
    raw_quotes = script_data.get("raw_stock_quotes") or {}
    section_by_name = _section_by_normalized_name(script_data.get("sections") or [])

    best = None
    for stock_name, quotes in raw_quotes.items():
        sec = section_by_name.get(stock_name)
        change_positive = sec.get("change_positive", True) if sec else True
        rscore = _ranking_score_for(stock_name, ranking_entries)

        for q in quotes or []:
            raw_quote = q.get("quote")
            if isinstance(raw_quote, list):
                # _merge_quotes_by_speaker()(generate_script.py)가 quote를 발언
                # 조각 리스트로 남겨두므로, 표시용으로는 조각들을 이어붙인다.
                quote_text = " ".join(part.strip() for part in raw_quote if part and part.strip())
            else:
                quote_text = (raw_quote or "").strip()
            speaker = (q.get("speaker") or "").strip()
            if not quote_text or not speaker:
                continue

            sentiment_sign = _quote_sentiment_sign(q.get("sentiment", ""), quote_text)
            contrarian_bonus = 0.0
            if sentiment_sign != 0:
                stock_up = 1 if change_positive else -1
                if sentiment_sign != stock_up:
                    contrarian_bonus = 0.5

            channel_bonus = 0.0 if q.get("channel_type") == "증권사" else 0.1
            score = rscore + contrarian_bonus + _specificity_bonus(quote_text) + channel_bonus

            if best is None or score > best["score"]:
                best = {
                    "stock_name":      stock_name,
                    "speaker":         speaker,
                    "channel":         q.get("channel", ""),
                    "quote":           quote_text,
                    "quote_display":   clean_quote_for_display(quote_text),
                    "change_positive": change_positive,
                    "score":           score,
                }
    return best


def select_news_candidate(script_data: dict, ranking_entries: list = None,
                           exclude_stock: str = None) -> dict:
    """오늘의 화제 종목 1개를 고른다. ranking_entries(ranking.json의 "ranking"
    리스트)가 있으면 그 순위를 따르고, 없으면(예: ranking 스텝을 안 거친
    실행) sections 등장 순서로 폴백한다. exclude_stock을 주면 발언형과 같은
    종목이 중복 선택되지 않게 건너뛴다."""
    section_by_name = _section_by_normalized_name(script_data.get("sections") or [])

    ordered_names = [
        e["companies"] for e in sorted(ranking_entries or [], key=lambda e: e.get("rank", 999))
    ]
    if not ordered_names:
        ordered_names = list(section_by_name.keys())

    for name in ordered_names:
        if name == exclude_stock:
            continue
        sec = section_by_name.get(name)
        if not sec:
            continue
        catalysts = sec.get("catalysts") or []
        return {
            "stock_name":      name,
            "change":          sec.get("change", ""),
            "change_positive": sec.get("change_positive", True),
            "catalyst":        catalysts[0] if catalysts else sec.get("summary", ""),
        }
    return None


def build_quote_title(candidate: dict) -> str:
    speaker = candidate["speaker"]
    josa = pick_i_ga(speaker)
    return f'{speaker}{josa} "{candidate["quote_display"]}"라고 말한 까닭은?'


_SURGE_THRESHOLD_PCT = 3.0  # 이 이상이어야 "급등/급락", 아니면 "상승/하락"(과장 방지)


def build_news_title(candidate: dict) -> str:
    change = candidate.get("change", "")
    is_up = candidate.get("change_positive", True)
    m = re.search(r"[\d.]+", change)
    magnitude = float(m.group()) if m else 0.0
    if magnitude >= _SURGE_THRESHOLD_PCT:
        direction = "급등" if is_up else "급락"
    else:
        direction = "상승" if is_up else "하락"
    change_part = f"{change} " if change else ""
    return f'{candidate["stock_name"]} {change_part}{direction}, 무슨 일?'
