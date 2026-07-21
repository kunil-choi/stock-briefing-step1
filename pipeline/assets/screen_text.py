"""
화면 표시용 텍스트(screenText) 압축.

corner_summary/subtitle처럼 이미 "한 줄 요약"으로 설계된 필드를 추가로
문장형 → 키워드형으로 다듬어 최대 2줄 이내로 만든다. LLM을 재호출하지 않는
규칙 기반 처리이며, narrative_reorder.soften_advice_language()와 마찬가지로
관찰된 패턴만 치환하는 경량 처리다(완벽한 요약이 아님). 시그니처를 안정적으로
유지해 향후 LLM 기반 압축으로 교체할 수 있게 한다.
"""
import re
from typing import List, Optional

# 길이 내림차순 — 짧은 접미사가 긴 접미사의 부분집합이면 먼저 매칭돼 꼬리가 남는다
_SENTENCE_ENDINGS = [
    "제안드립니다", "마치겠습니다", "전해드립니다",
    "마감했습니다", "전망됩니다", "기록했습니다", "달했습니다", "보입니다",
    "제안합니다", "드립니다", "됩니다", "했습니다", "였습니다", "합니다", "입니다",
]
_LEADING_FILLERS = ["오늘 ", "다음은 ", "이제 ", "지금부터 ", "우선 ", "그리고 ", "이상으로 "]
_TRAILING_PUNCT_RE = re.compile(r"[.!?~…\"'“”·]+$")
_RAW_PRICE_RE = re.compile(r"\d{1,3}(?:,\d{3})+")  # "85,400"류 — price 필드로 이미 별도 노출됨
# \b를 쓰지 않는 이유: 뒤에 "원/에" 같은 한글 조사가 바로 붙으면(예: "85,400원")
# 숫자↔한글 경계가 정규식 \b(단어-비단어 경계) 조건을 만족하지 못해 매칭이 실패한다.
_CLAUSE_SPLIT_RE = re.compile(r"(?:[.!?]\s+|,\s+)")


def strip_sentence_ending(text: str) -> str:
    t = _TRAILING_PUNCT_RE.sub("", text.strip())
    for _ in range(2):  # "~했습니다." 처럼 종결어+마침표가 중첩된 경우 대비
        matched = False
        for suf in _SENTENCE_ENDINGS:
            if t.endswith(suf):
                t = t[: -len(suf)].strip()
                matched = True
                break
        t = _TRAILING_PUNCT_RE.sub("", t)
        if not matched:
            break
    return t


def drop_leading_filler(text: str) -> str:
    for f in _LEADING_FILLERS:
        if text.startswith(f):
            return text[len(f):]
    return text


def to_keyword_form(text: str, drop_prices: bool = True) -> str:
    t = drop_leading_filler(text.strip())
    t = strip_sentence_ending(t)
    if drop_prices:
        t = _RAW_PRICE_RE.sub("", t).strip()
        t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def compress_line(text: str, max_chars: int = 18) -> str:
    t = to_keyword_form(text)
    if len(t) <= max_chars:
        return t
    # 단어 경계에서 자르되, 경계가 없으면(한국어 특성상 흔함) 하드 컷 —
    # 렌더링 단계의 html_theme.autofit_text()가 폰트 축소로 오버플로를 추가 처리한다
    cut = t[:max_chars]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.strip()


def compress_to_screen_text(
    headline_base: str,
    narration: str = "",
    entities: Optional[List[str]] = None,
    max_lines: int = 2,
    max_chars: int = 18,
) -> List[str]:
    """corner_summary/subtitle(headline_base)을 우선 압축한다. narration과
    동일해지면(짧은 narration을 corner_summary가 그대로 복붙한 경우) entity
    기반 키워드로 폴백한다."""
    entities = entities or []
    if not headline_base:
        return []

    clauses = [c for c in _CLAUSE_SPLIT_RE.split(headline_base) if c.strip()]
    lines = [compress_line(c, max_chars) for c in clauses[:max_lines]]
    lines = [l for l in lines if l]

    narration_norm = to_keyword_form(narration) if narration else ""
    joined = " ".join(lines)
    if not lines or (narration_norm and joined == narration_norm):
        fallback = " · ".join(dict.fromkeys(entities[:2]))
        lines = [compress_line(fallback, max_chars)] if fallback else lines

    out: List[str] = []
    for l in lines[:max_lines]:
        if l and l not in out:
            out.append(l)
    return out
