# pipeline/generate_script.py
"""
AI 주식 브리핑 — 스크립트 생성 모듈 (morning_core / stock-briefing-step1)
- 데이터 소스: stock-briefing-v3-1의 data/briefing_data.json
  (raw.githubusercontent.com, Playwright 라이브 사이트 스크래핑 대체 — 이
  레포는 공개 사이트가 없는 V3_1을 소비하므로 스크래핑 자체가 불가능함)
- 목표 영상 길이: 정확히 15분 내외
- 오프닝: 'KBS 머니올라' 멘트
- 발음 교정 / 나레이션·자막 완전 분리
- 목소리 관리: pipeline/voice_config.py 에서 통합 관리
"""

import os
import re
import sys
import json
import urllib.request
from datetime import datetime
from openai import OpenAI

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.config import (
    STOCK_CODES, normalize_stock_name, classify_channel_type, resolve_channel_identity,
)

# SCRIPT_MOCK=1: OpenAI를 실제로 호출하지 않고 구조만 맞는 더미 데이터로
# 대체한다 — 실제 영상 생성 전에 파이프라인 전체(재정렬/에셋/오디오/영상/자막/
# quality_gate)를 토큰 소비 없이 로컬에서 먼저 검증하기 위함
# (`SCRIPT_MOCK=1 TTS_MOCK=1 python pipeline/generate_script.py KO`처럼 사용).
SCRIPT_MOCK = os.environ.get("SCRIPT_MOCK") == "1"

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key and not SCRIPT_MOCK:
    raise EnvironmentError("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
client = OpenAI(api_key=_api_key or "sk-mock-dry-run")

# morning_core는 stock-briefing-v3-1(증권사 리포트 제외 이른 스냅샷)을 소비한다.
UPSTREAM_REPO = "kunil-choi/stock-briefing-v3-1"

TODAY       = datetime.now().strftime("%Y년 %m월 %d일")
TODAY_MONTH = datetime.now().strftime("%-m")
TODAY_DAY   = datetime.now().strftime("%-d")

STOCK_NAME_LIST = "\n".join(f"- {name}" for name in STOCK_CODES.keys())

# ─────────────────────────────────────────────────────────────────────────────
# 오프닝 / 클로징 멘트
# ─────────────────────────────────────────────────────────────────────────────

OPENING_NARRATION = (
    "오늘 주식시장, 어떤 종목이 가장 뜨거울까요? "
    "많은 투자자들이 어젯밤 찾아본 그 유튜브 영상 속에 답이 있습니다. "
    "머니올라가 최근 24시간 내 업로드된 최고 조회수 영상들을 샅샅이 분석해, "
    "대중의 관심이 쏠린 종목들을 찾아냈습니다. "
    "여기에 핵심 뉴스, 경제방송, 증권사 리포트까지 종합해 완벽하게 요약해 드립니다. "
    "오늘 하루 투자의 나침반이 되어줄 머니올라 브리핑, 시작하겠습니다."
)

OPENING_SUBTITLE = (
    "오늘 주식시장, 어떤 종목이 가장 뜨거울까요? "
    "많은 투자자들이 어젯밤 찾아본 그 유튜브 영상 속에 답이 있습니다. "
    "머니올라가 최근 24시간 내 업로드된 최고 조회수 영상들을 샅샅이 분석해, "
    "대중의 관심이 쏠린 종목들을 찾아냈습니다. "
    "여기에 핵심 뉴스, 경제방송, 증권사 리포트까지 종합해 완벽하게 요약해 드립니다. "
    "오늘 하루 투자의 나침반이 되어줄 머니올라 브리핑, 시작하겠습니다."
)

# ─────────────────────────────────────────────────────────────────────────────
# 투자 경고 클로징 (요구사항 8번: 경고문 강화)
# ─────────────────────────────────────────────────────────────────────────────

CLOSING_NARRATION = (
    "오늘 오전 발행된 주요 증권사의 애널리스트 보고서를 종합 분석한 영상은 "
    "잠시 후 10시에 업로드됩니다. 많은 시청 바랍니다. "
    "이상으로 케이비에스 머니올라의 오늘의 주식시장 브리핑을 마치겠습니다. "
    "오늘도 함께해 주셔서 감사합니다. "
    "마지막으로 꼭 당부드릴 말씀이 있습니다. "
    "본 브리핑은 에이아이가 뉴스, 유튜브, 증권사 리포트 등 공개 데이터를 분석하여 제작한 참고용 정보입니다. "
    "특정 종목의 매수 또는 매도를 권유하는 것이 아니며, 수익을 보장하지 않습니다. "
    "주식 투자는 원금 손실의 위험이 있으므로 반드시 본인의 판단과 책임 하에 신중하게 결정하시기 바랍니다. "
    "투자의 최종 결정과 그에 따른 모든 책임은 전적으로 투자자 본인에게 있습니다. "
    "구독과 좋아요는 저희에게 큰 힘이 됩니다. 내일도 유익한 브리핑으로 찾아뵙겠습니다. 감사합니다."
)

CLOSING_SUBTITLE = (
    "오늘 오전 발행된 주요 증권사의 애널리스트 보고서를 종합 분석한 영상은 "
    "잠시 후 10시에 업로드됩니다. 많은 시청 바랍니다. "
    "이상으로 KBS 머니올라의 오늘의 주식시장 브리핑을 마치겠습니다. "
    "오늘도 함께해 주셔서 감사합니다. "
    "마지막으로 꼭 당부드릴 말씀이 있습니다. "
    "본 브리핑은 AI가 뉴스, 유튜브, 증권사 리포트 등 공개 데이터를 분석하여 제작한 참고용 정보입니다. "
    "특정 종목의 매수 또는 매도를 권유하는 것이 아니며, 수익을 보장하지 않습니다. "
    "주식 투자는 원금 손실의 위험이 있으므로 반드시 본인의 판단과 책임 하에 신중하게 결정하시기 바랍니다. "
    "투자의 최종 결정과 그에 따른 모든 책임은 전적으로 투자자 본인에게 있습니다. "
    "구독과 좋아요는 저희에게 큰 힘이 됩니다. 내일도 유익한 브리핑으로 찾아뵙겠습니다. 감사합니다."
)

DISCLAIMER = (
    "⚠️ 투자 유의사항 | 본 브리핑은 AI 분석 참고자료이며 투자 권유가 아닙니다. "
    "주식 투자는 원금 손실 위험이 있습니다. 투자 책임은 전적으로 본인에게 있습니다."
)


# ─────────────────────────────────────────────────────────────────────────────
# 자막 표기 안전망 — narration용 한글 발음/숫자 표기가 subtitle 필드에 잘못
# 섞여 들어온 경우 자동으로 원래 표기(숫자/로마자)로 되돌립니다.
# LLM이 프롬프트 지시를 놓쳤을 때의 최종 방어선이며, narration 필드에는
# 절대 적용하지 않습니다.
# ─────────────────────────────────────────────────────────────────────────────

# narration에서만 쓰이는 필드 — 자막 안전망을 적용하지 않음
_NARRATION_ONLY_KEYS = {"narration", "narration_summary", "id", "title", "date"}

# 영문 약어의 한글 발음 표기 → 원래 로마자 표기 (긴 복합어 먼저)
_ACRONYM_SUBTITLE_FIXES = [
    ("에이치디현대중공업", "HD현대중공업"),
    ("에이치디현대일렉트릭", "HD현대일렉트릭"),
    ("에이치디현대", "HD현대"),
    ("에스케이하이닉스", "SK하이닉스"),
    ("엘지에너지솔루션", "LG에너지솔루션"),
    ("엘지화학", "LG화학"),
    ("케이비금융", "KB금융"),
    ("에이치비엠", "HBM"),
    ("에이아이", "AI"),
    ("이티에프", "ETF"),
    ("이에스에스", "ESS"),
    ("피씨이", "PCE"),
    ("디에스알", "DSR"),
    ("오티티", "OTT"),
    ("에이디알", "ADR"),
    ("엠오유", "MOU"),
    ("비피에스", "BPS"),
    ("이피에스", "EPS"),
    ("피이알", "PER"),
    ("알오이", "ROE"),
    ("아이피오", "IPO"),
    ("엠앤에이", "M&A"),
    ("알앤디", "R&D"),
    ("와이오와이", "YoY"),
    ("큐오큐", "QoQ"),
    ("에스케이", "SK"),
    ("엘지", "LG"),
    ("케이비", "KB"),
]

_KR_DIGIT = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
             "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
_KR_SMALL_UNIT = {"십": 10, "백": 100, "천": 1000}
_KR_BIG_UNITS = "조억만"
_KR_NUM_CHARS = "".join(_KR_DIGIT) + "".join(_KR_SMALL_UNIT) + _KR_BIG_UNITS


def _parse_kr_number_group(chars: str):
    """4자리 미만 그룹(예: '이천사백')을 정수로 변환. 실패하면 None."""
    if not chars:
        return 0
    total = 0
    pending = None
    for ch in chars:
        if ch in _KR_DIGIT:
            pending = _KR_DIGIT[ch]
        elif ch in _KR_SMALL_UNIT:
            total += (pending if pending is not None else 1) * _KR_SMALL_UNIT[ch]
            pending = None
        else:
            return None
    if pending is not None:
        total += pending
    return total


def _korean_number_run_to_digits(run: str):
    """'십이조이천사백억' → '12조2400억' 처럼 조/억/만 단위는 유지한 채 각 자릿수
    구간만 아라비아 숫자로 변환합니다. 파싱 실패 시 None을 반환합니다."""
    parts = re.split(r"([조억만])", run)
    out, i = [], 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and parts[i + 1] in "조억만":
            val = _parse_kr_number_group(seg)
            if val is None:
                return None
            out.append(f"{val}{parts[i + 1]}")
            i += 2
        else:
            if seg:
                val = _parse_kr_number_group(seg)
                if val is None:
                    return None
                out.append(str(val))
            i += 1
    return "".join(out) if out else None


_DECIMAL_PERCENT_RE = re.compile(
    r"([영일이삼사오육륙칠팔구]+)쩜([영일이삼사오육륙칠팔구]+)퍼센트"
)


def _fix_decimal_percent(text: str) -> str:
    """'십이쩜오퍼센트' → '12.5%' / '영쩜팔퍼센트' → '0.8%'"""
    def repl(m):
        int_val = _parse_kr_number_group(m.group(1))
        dec_str = "".join(str(_KR_DIGIT[c]) for c in m.group(2))
        if int_val is None or not dec_str:
            return m.group(0)
        return f"{int_val}.{dec_str}%"
    return _DECIMAL_PERCENT_RE.sub(repl, text)


_PLAIN_NUMBER_RE = re.compile(
    f"([{_KR_NUM_CHARS}]+)(원|퍼센트|포인트|배)?"
)


# 숫자처럼 보이지만 실제로는 일반 어휘인 경우 (오탐 확인된 단어만 등록).
# 예: "구조"(9+조) → 구조적/구조원 등 실제 단어와 충돌하므로 절대 숫자로 변환하지 않음.
_NUMBER_RUN_DENYLIST = {"구조"}


def _fix_plain_numbers(text: str) -> str:
    """'삼천오백원' → '3500원' 처럼 뒤에 원/퍼센트/포인트/배 단위가 붙는 경우,
    또는 '십이조이천사백억'처럼 조/억/만 단위가 두 번 이상 나와 명백히 복합
    숫자 표기로 판단되는 경우만 변환합니다.

    한글에는 숫자 음절(일이삼사...구/십백천만억조)이 우연히 들어간 일반 단어가
    매우 많습니다 (구조, 오만, 천만에요, 구천 등). 그래서 "조/억/만으로 끝나기만
    하면 숫자"로 간주하던 이전 방식은 "구조적" → "9조적" 같은 오탐을 냈습니다.
    이제는 반드시 (1) 뒤에 명시적 단위 앵커가 붙거나 (2) 조/억/만이 한 런에서
    2회 이상 나타나 복합 숫자임이 명백한 경우에만 변환합니다.
    """
    def repl(m):
        run, trailing = m.group(1), m.group(2) or ""
        if len(run) < 2 or not any(c in "십백천만억조" for c in run):
            return m.group(0)
        if run in _NUMBER_RUN_DENYLIST:
            return m.group(0)
        big_unit_count = sum(run.count(u) for u in _KR_BIG_UNITS)
        if not trailing and big_unit_count < 2:
            return m.group(0)
        converted = _korean_number_run_to_digits(run)
        if converted is None:
            return m.group(0)
        trailing_out = "%" if trailing == "퍼센트" else trailing
        return converted + trailing_out
    return _PLAIN_NUMBER_RE.sub(repl, text)


def fix_subtitle_text(text: str) -> str:
    """자막(subtitle) 필드에 섞여 들어온 narration용 한글 발음/숫자 표기를
    원래의 숫자·로마자 표기로 되돌립니다. narration 필드에는 절대 호출하지 마세요."""
    if not text or not isinstance(text, str):
        return text
    try:
        fixed = text
        for src, dst in _ACRONYM_SUBTITLE_FIXES:
            fixed = fixed.replace(src, dst)
        fixed = _fix_decimal_percent(fixed)
        fixed = _fix_plain_numbers(fixed)
        return fixed
    except Exception:
        return text


def fix_subtitle_fields(obj, key: str = None):
    """script.json 트리를 순회하며 narration 계열이 아닌 모든 문자열 필드에
    fix_subtitle_text()를 적용합니다."""
    if isinstance(obj, dict):
        return {k: fix_subtitle_fields(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_subtitle_fields(v, key) for v in obj]
    if isinstance(obj, str):
        if key in _NARRATION_ONLY_KEYS:
            return obj
        return fix_subtitle_text(obj)
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# 브리핑 데이터 수집 (v3 URL)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_briefing_data() -> dict:
    """UPSTREAM_REPO(stock-briefing-v3-1/-2)의 data/briefing_data.json을 가져온다.
    이 레포는 공개 GitHub Pages 사이트가 없으므로(v3와 달리 데이터 전용 백엔드),
    기존의 Playwright 라이브 사이트 스크래핑을 raw.githubusercontent.com 직접
    소비로 대체했다."""
    url = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/data/briefing_data.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ {UPSTREAM_REPO} briefing_data.json 로드 실패: {e}")
        return {}


def _kdate_to_iso(date_str: str) -> str:
    """'2026년 07월 06일' → '2026-07-06'. 매칭 실패 시 빈 문자열."""
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def build_briefing_text(data: dict) -> str:
    """briefing_data.json을 기존 Playwright 스크래핑 텍스트와 동등한 형태의
    평문으로 변환한다. _generate_core() 등 기존 LLM 프롬프트 파이프라인은 이
    텍스트를 그대로 소비하므로 프롬프트 자체는 수정이 필요 없다. 종목별
    구획 표시(### [종목 구획 시작/끝])는 기존 스크래핑 텍스트의 형식을 그대로
    유지해, 사명이 비슷한 계열사끼리 내용이 섞이는 걸 막는 기존 안전장치가
    계속 동작하도록 한다."""
    lines = []
    market_summary = data.get("market_summary", "")
    if market_summary:
        lines.append(f"## 시장 개요\n{market_summary}")

    hot_sectors = data.get("hot_sectors") or []
    if hot_sectors:
        lines.append("## 주목 섹터\n" + "\n".join(
            f"- {s.get('name', '')}: {s.get('reason', '')}" for s in hot_sectors
        ))

    ai_strategy = data.get("ai_strategy") or ""
    if ai_strategy:
        lines.append(f"## AI 투자 전략\n{ai_strategy}")

    def _stock_block(stock: dict, tag: str) -> str:
        parts = [
            f"### [종목 구획 시작] ({tag})",
            f"종목명: {stock.get('name', '')} ({stock.get('code', '')})",
            f"신호: {stock.get('signal', '')}",
            f"요약: {stock.get('summary', '')}",
            f"촉매: {stock.get('catalyst', '')}",
            f"리스크: {stock.get('risk', '')}",
        ]
        # PANELIST-QUOTE-1: 검증된 패널 발언(panelist_quotes, Gemini 영상
        # 직접분석)이 있으면 그것만 쓴다. 영상 제작은 시간 제약이 있어
        # 종목당 한 가지 소스만 골라야 하는데, 검증된 실제 발언이 있는데도
        # 자막 재구성 텍스트(channel_mentions)를 같이 넣으면 정작 중요한
        # 발언이 묻힌다. panelist_quotes가 없는 종목만 channel_mentions로
        # 폴백한다.
        panelist_quotes = stock.get("panelist_quotes") or []
        if panelist_quotes:
            for pq in panelist_quotes:
                body = pq.get("quote") or pq.get("fact", "")
                parts.append(f"[패널발언/{pq.get('speaker_name', '')}] {body}")
        else:
            for cm in stock.get("channel_mentions") or []:
                parts.append(
                    f"[{cm.get('source_type', '')}/{cm.get('source_name', '')}] {cm.get('content', '')}"
                )
        parts.append("### [종목 구획 끝]")
        return "\n".join(parts)

    for s in data.get("market_leaders") or []:
        lines.append(_stock_block(s, "대형 주도주"))
    for s in data.get("stocks") or []:
        lines.append(_stock_block(s, "관심 종목"))

    return "\n\n".join(lines)


def build_synthetic_mentions(data: dict, briefing_date_iso: str) -> list:
    """market_leaders/stocks의 channel_mentions을 기존 build_stock_quotes()가
    기대하는 mentions 리스트 형태로 변환한다(기존에는 youtube_mentions.json에서
    이 형태로 직접 가져왔음).

    ★ source_type=="증권사"(증권사가 직접 운영하는 유튜브 채널의 실시간
    코멘트 — channels.json의 securities 카테고리에서 24h 이내 수집된 것)는
    애널리스트 PDF 리포트(build_stock_brokerage_mentions()가 별도로 처리하는
    brokerage_reports)와 전혀 다른 소스인데, 예전에는 "증권사 리포트"로
    착각해 여기서 통째로 걸러내고 있었다. brokerage_reports는 오전엔 항상
    비어 있으므로 그 결과 "증권사" 카테고리 콘텐츠가 1차 영상에서 조용히
    사라지는 문제가 있었다 — 이제 원본 source_type을 그대로 실어 보내
    build_stock_quotes()가 channel_type="증권사"로 분류하도록 한다.

    HIDDEN-PICK-REMOVE: "오늘의 픽"은 V3-1에서 제거됐다(관심종목 후보 풀이
    얇아서 항상 0개로 나오는 구조적 문제 — 대신 증권사 리포트가 있는
    V3-2/STEP-2 쪽으로 이전됨). market_leaders/stocks만 순회한다."""
    mentions = []
    for bucket in ("market_leaders", "stocks"):
        for stock in data.get(bucket) or []:
            name = (stock.get("name") or "").strip()
            if not name:
                continue
            # PANELIST-QUOTE-1: panelist_quotes(검증된 발언)가 있으면 그것만
            # 쓰고, 없는 종목만 channel_mentions(자막 재구성 텍스트)로 폴백.
            panelist_quotes = stock.get("panelist_quotes") or []
            if panelist_quotes:
                for pq in panelist_quotes:
                    mentions.append({
                        "date":          briefing_date_iso,
                        "stock_name":    name,
                        "channel":       pq.get("source_name", ""),
                        "source_type":   "유튜브",
                        "speaker":       pq.get("speaker_name", ""),
                        "quote":         pq.get("quote") or pq.get("fact", ""),
                        "timestamp_url": pq.get("source_url", ""),
                        "sentiment":     pq.get("sentiment", ""),
                    })
                continue
            for cm in stock.get("channel_mentions") or []:
                mentions.append({
                    "date":          briefing_date_iso,
                    "stock_name":    name,
                    "channel":       cm.get("source_name", ""),
                    "source_type":   cm.get("source_type", ""),
                    "speaker":       "",
                    "quote":         cm.get("content", ""),
                    "timestamp_url": cm.get("url", ""),
                    "sentiment":     "",
                })
    return mentions


def build_stock_market_data(data: dict) -> dict:
    """market_leaders/stocks의 실제 price/change_pct/code를 종목명 기준으로
    모은다. LLM에게 가격을 지어내게 하는 대신(과거 이 값이 프롬프트
    예시("000,000"/"+0.00%")를 그대로 베껴 화면에 노출되는 사고가 있었다)
    market_summary의 지수 데이터와 동일하게 코드에서 실측치를 주입하기
    위함이다."""
    result = {}
    for bucket in ("market_leaders", "stocks"):
        for stock in data.get(bucket) or []:
            name = (stock.get("name") or "").strip()
            if not name:
                continue
            price = stock.get("price")
            change_pct = stock.get("change_pct")
            result[normalize_stock_name(name)] = {
                "price":        f"{price:,.0f}" if isinstance(price, (int, float)) else "",
                "change":       f"{change_pct:+.2f}%" if isinstance(change_pct, (int, float)) else "",
                "change_positive": bool(change_pct is not None and change_pct >= 0),
                "price_label":  stock.get("price_label", ""),
                "code":         stock.get("code", ""),
            }
    return result


# 원본 소스 데이터의 source_type → 이 방송의 channel_summaries 카테고리(channel_type).
# "뉴스"(온라인 기사)는 별도 카테고리를 두지 않고 기존 "경제방송"에 합친다
# (classify_channel_type()도 "매일경제" 같은 언론사명을 이미 경제방송으로 묶고
# 있어 일관성이 있다). "증권사"는 증권사가 직접 운영하는 유튜브 채널의 실시간
# 코멘트를 가리키며, channel_type을 채널명 추정(classify_channel_type)에
# 맡기지 않고 원본 source_type을 그대로 신뢰한다.
_SOURCE_TYPE_TO_CHANNEL_TYPE = {
    "증권사":   "증권사",
    "경제방송": "경제방송",
    "뉴스":     "경제방송",
    "유튜브":   "유튜브",
}


def _merge_quotes_by_speaker(items: list) -> list:
    """같은 채널·화자의 발언 조각을 하나의 항목으로 묶는다. quote는 등장 순서
    그대로의 리스트로 유지한다(임의로 한 문자열로 이어붙이면 문장 경계가
    뭉개질 수 있어, LLM이 조각들을 이어지는 맥락으로 스스로 종합하게 한다).
    V3-1 원본 데이터에서 같은 화자의 발언이 여러 조각으로 나뉘어 반복
    등장하는 문제를 이 소비 지점에서 흡수한다(V3-1 저장소 자체는 별도
    스코프라 수정 대상이 아님)."""
    order = []
    grouped: dict = {}
    for it in items:
        key = (it.get("channel", ""), it.get("speaker", ""))
        if key not in grouped:
            grouped[key] = {**it, "quote": []}
            order.append(key)
        q = (it.get("quote") or "").strip()
        if q:
            grouped[key]["quote"].append(q)
    return [grouped[k] for k in order if grouped[k]["quote"]]


def build_stock_quotes(mentions: list, briefing_date_iso: str) -> dict:
    """
    종목명을 정규화해 stock_name → [{speaker, channel, channel_type, quote, timestamp_url, sentiment}] 로 그룹핑.
    briefing_date_iso가 있으면 같은 날짜의 발언만 사용 (V3 브리핑과 날짜 어긋남 방지).
    같은 채널·화자의 발언 조각은 _merge_quotes_by_speaker()로 먼저 하나로 묶은 뒤,
    화자·채널 단위로 최대 9명까지 유지해 출연진의 발언을 최대한 폭넓게 다룬다
    (요구사항: 방송/유튜브 전문가 발언 종합이 이 영상의 핵심 목적 — 한 화자가
    조각을 여러 번 남겨도 슬롯을 독점하지 않도록 병합 후에 자른다).
    """
    grouped: dict = {}
    for m in mentions:
        if briefing_date_iso and m.get("date") and m.get("date") != briefing_date_iso:
            continue
        raw_name = (m.get("stock_name") or "").strip()
        if not raw_name:
            continue
        name = normalize_stock_name(raw_name)
        raw_channel = m.get("channel", "")
        raw_speaker = m.get("speaker") or m.get("main_speaker", "")
        channel, speaker = resolve_channel_identity(raw_channel, raw_speaker)
        channel_type = _SOURCE_TYPE_TO_CHANNEL_TYPE.get((m.get("source_type") or "").strip())
        if not channel_type:
            channel_type = classify_channel_type(channel)
        grouped.setdefault(name, []).append({
            "speaker":       speaker,
            "channel":       channel,
            "channel_type":  channel_type,
            "quote":         m.get("quote", ""),
            "timestamp_url": m.get("timestamp_url") or m.get("video_url", ""),
            "sentiment":     m.get("sentiment", ""),
        })
    return {name: _merge_quotes_by_speaker(items)[:9] for name, items in grouped.items()}


def build_stock_brokerage_mentions(brokerage_reports: dict) -> dict:
    """
    brokerage_reports(simultaneous/new_coverage/single_significant)를 종목명 기준으로
    재그룹핑합니다: stock_name → [{brokers, title, opinion, target_price, ai_summary}].
    종목별 mention 종합 요약("증권사" 카테고리)의 근거 데이터로 사용됩니다.
    """
    grouped: dict = {}
    if not brokerage_reports:
        return grouped
    for bucket in ("simultaneous", "new_coverage", "single_significant"):
        for r in brokerage_reports.get(bucket, []) or []:
            raw_name = (r.get("stock_name") or "").strip()
            if not raw_name:
                continue
            name = normalize_stock_name(raw_name)
            grouped.setdefault(name, []).append({
                "brokers":      r.get("brokers", []),
                "title":        r.get("title", ""),
                "opinion":      r.get("opinion", ""),
                "target_price": r.get("target_price", ""),
                "ai_summary":   r.get("ai_summary", ""),
            })
    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# 스크립트 생성
#
# ★ 설계 노트 (다중 호출 아키텍처): gpt-4o의 출력 토큰 상한은 16,384개로 고정돼
# 있습니다. 15분 분량(시장요약+업종분석+AI전략+대형주도주/상위종목 5개(종목당 최대
# 9개 발언 인용 포함)+집계 섹션)을 narration+subtitle 이중 표기로 모두 채우려면
# 실측상 25,000~55,000 토큰이 필요해, 한 번의 API 호출로는 절대 다 채울 수
# 없습니다. 프롬프트 글자 수 목표를 아무리 올려도 이 하드 리밋 때문에 실제로는
# 전혀 개선되지 않았던 것이 바로 이 문제입니다.
# 그래서 하나의 거대한 호출 대신, 섹션별로 여러 번의 작은 호출로 나눠 생성한 뒤
# 병합합니다. 각 호출은 개별적으로 16,384 토큰 상한에 여유 있게 들어갑니다.
# ─────────────────────────────────────────────────────────────────────────────

_NARRATION_SUBTITLE_RULES = """
## ★ narration vs subtitle 핵심 차이 (반드시 준수)

### narration/subtitle 문장 수 일치 (자막 동기화를 위해 반드시 준수)
- narration과 subtitle(및 narration_summary/subtitle_summary 등 모든 쌍)은 반드시 문장
  수가 동일해야 하고, 같은 순서로 같은 내용을 담아야 합니다. 표기(숫자/영문)만 다를 뿐
  내용과 문장 경계는 1:1로 대응해야 자막이 나레이션과 정확히 동기화됩니다.
- 문장 수를 맞추기 위해 임의로 문장을 합치거나 쪼개지 말고, 애초에 같은 문장 구조로
  narration과 subtitle을 나란히 작성하세요.

### [narration — TTS 낭독용]
- 모든 숫자를 한글로 풀어서 읽습니다:
  · 6,700 → 육천칠백  |  133만 → 백삼십삼만  |  12조2400억 → 십이조 이천사백억
  · 85,400원 → 팔만오천사백원  |  +1.2% → 플러스 일쩜이퍼센트
- 소수점은 반드시 **"쩜"** (절대 "점" 금지):
  · 12.5% → 십이쩜오퍼센트  |  0.8% → 영쩜팔퍼센트
- 영문 약어를 한글 발음으로:
  · SK→에스케이 | LG→엘지 | KB→케이비 | AI→에이아이 | HBM→에이치비엠
  · ETF→이티에프 | ESS→이에스에스 | PCE→피씨이 | DSR→디에스알 | OTT→오티티
  · KOSPI→코스피 | KOSDAQ→코스닥 | MOU→엠오유 | ADR→에이디알
- 경음화 규칙:
  · 주가→주까 | 목표주가→목표주까 | 유가→유까 | 고유가→고유까
  · 실적→실쩍 | 적자→적짜 | 특징→특찡 | 격차→격짜
  · 국채→국째 | 역대→역때 | 발전→발쩐 | 결정→결쩡 | 절감→절깜
  · 신고가→신고까 | 최고가→최고까 | 할 것→할 껏 | 볼 수→볼 쑤
- 삼성전기 → "삼성 전기" (TTS 오독 방지, 자막은 원래대로)
- 숫자+단위 붙여 읽기: 170만원→백칠십만원 (절대 "백칠십만 원" 금지)

### [subtitle — 화면 자막용] — 절대 규칙 (narration을 그대로 베끼지 말 것)
- 숫자는 반드시 아라비아 숫자 그대로 표기:
  · 6,700 (❌ 육천칠백)  |  3,500원 (❌ 삼천오백원)  |  1.2% (❌ 일쩜이퍼센트)
  · 12조2400억 (❌ 십이조 이천사백억)
- 영문 약어·기업명은 반드시 원래 로마자 표기 그대로:
  · SK (❌ 에스케이)  |  AI (❌ 에이아이)  |  OTT (❌ 오티티)  |  LG (❌ 엘지)
  · KB (❌ 케이비)  |  HBM (❌ 에이치비엠)  |  ETF (❌ 이티에프)
- narration 필드를 작성한 뒤 숫자·영문 부분을 한글 발음으로 바꿔 놓았다면, subtitle
  필드에는 그 발음 표기를 절대 복사하지 말고 반드시 원래 숫자·로마자로 다시 바꿔서 쓰세요.
- 뜻이 생소한 용어는 **(뜻)** 을 괄호 안에 병기:
  · HBM(고대역폭 메모리) | PER(주가수익비율) | DSR(총부채원리금상환비율)
  · MOU(업무협약) | ADR(미국주식예탁증서) | PCE(개인소비지출) | ESS(에너지저장장치) | OTT(온라인 동영상 서비스)
"""

_MENTION_RULES = """
## ★ channel_summaries 항목 규칙 — 이 방송의 핵심 목적
이 방송은 유튜브·경제방송에 출연한 전문가들과 증권사 리포트가 각 종목에 대해 실제로
어떻게 평가하고 있는지 "정확하게 분석해 짧게 정리"해 전달하는 것이 목적입니다.
발언·리포트 원문을 그대로 나열하거나 인용하지 말고, 핵심 논지·수치·전망을 종합적으로
이해한 뒤 자연스러운 문장으로 다시 써서 정리하세요. 추임새·군더더기·반복되는 잡담은
모두 제거하고 투자 판단에 실제로 도움이 되는 내용만 남기세요.

### 카테고리 3종 (해당 데이터가 있는 카테고리만 작성)
- 아래 별도 제공되는 stock_quotes(JSON)는 각 항목에 channel_type이 "유튜브"/
  "경제방송"/"증권사" 중 하나로 표시돼 있습니다("증권사"는 증권사가 직접 운영하는
  유튜브 채널에서 최근 24시간 내 나온 실시간 코멘트입니다). channel_type별로
  묶어서 각각 하나의 종합 요약을 작성하세요(유튜브 종합 1개, 경제방송 종합 1개,
  stock_quotes 안의 증권사 발언 종합 1개).
- 별도 제공되는 stock_brokerage(JSON)가 있으면(애널리스트가 작성한 정식 리포트),
  그 안의 브로커·투자의견·목표주가·ai_summary도 "증권사" 카테고리에 함께 종합하세요
  — stock_quotes의 증권사 유튜브 발언과 stock_brokerage의 리포트가 둘 다 있으면
  하나의 "증권사" 요약 안에 함께 녹여내세요.
- 해당 카테고리에 데이터가 전혀 없으면 그 카테고리는 channel_summaries 배열에서
  완전히 생략하세요(빈 요약을 지어내지 마세요).

### 분석·요약 원칙 (반드시 준수)
- 없는 내용을 지어내지 말고, 제공된 데이터에 실제로 나온 의견·수치·근거만 사용하세요.
- 단순 나열이 아니라 "종합 분석"이어야 합니다: 여러 발언/리포트의 공통된 시각이나
  차이점을 짚고, 목표주가·투자의견·구체적 근거·전망을 포함하세요.
- 채널명/증권사명은 자연스럽게 문장 안에 녹여 언급하세요(예: "삼프로TV와 한국경제TV
  양쪽에서 모두...", "미래에셋증권과 키움증권은 목표주가를...").
- ★ 특정 인물(stock_quotes의 speaker)의 발언을 인용할 때는 이름만 말하지 말고
  "[채널명]에 출연한 [소속/직책] [이름]은" 형식으로 어느 방송에 나온 누구인지
  구체적으로 밝히세요(예: "이데일리TV에 출연한 권소현 이데일리 마켓in센터장은...",
  "KBS 1라디오에 출연한 이인철 참좋은경제연구소 소장은..."). 소속/직책 정보가
  stock_quotes에 없으면 이름과 채널명만이라도 반드시 함께 밝히고, 채널명 없이
  이름만 단독으로 언급하지 마세요.
- 분량: 카테고리별 narration 500~640자 내외(공백 포함, 기존 대비 약 2배 —
  짧은 headline이 아니라 배경·근거·전망까지 충분히 담은 완결된 분석 문단으로
  작성하세요). 근거가 부족하다고 없는 내용을 지어내 채우지 말고, 실제 제공된
  내용의 배경과 함의를 충분히 풀어써서 분량을 채우세요.
- 같은 채널·화자의 stock_quotes 항목은 이미 quote 필드가 발언 조각 리스트로
  묶여 있습니다. 이를 하나의 이어지는 코멘트로 이해하고 종합하되, 조각별로
  같은 논지를 반복해서 다시 쓰지 마세요.
- 발언 중 이 종목과 무관한 다른 종목·일반적인 시장 이야기만 담긴 부분은
  제외하고, 이 종목에 실제로 해당하는 내용만 사용하세요.

### ★ 역할 분리 (매우 중요 — corner_summary/summary/catalysts/risks와 중복 금지)
- corner_summary/summary/catalysts/risks는 가격 흐름·실적·업종 이슈 등
  브리핑 원문 기반의 "개요"만 담당합니다. channel_summaries는 "누가 어떻게
  평가했는지"를 자세히 푸는 "심층 설명"입니다.
- 개요(corner_summary/summary/catalysts/risks)에서 이미 쓴 문장이나 특정
  발언자의 구체적 논리를 channel_summaries에서 그대로 반복하지 마세요.
  channel_summaries는 그 개요의 배경이 되는 구체적 근거·수치·전망을 채널별로
  새롭게 풀어 설명해야 합니다.

### narration (TTS 낭독용)
- "[채널 종류] 쪽에서는" 또는 "증권사 리포트에서는" 식으로 자연스럽게 시작하세요.
- 종결어미 다양화 (같은 어미 2회 연속 금지):
  "~라고 분석했습니다" | "~다고 평가했습니다" | "~라고 진단했습니다" | "~고 내다봤습니다"
  "~다고 전망했습니다" | "~라고 짚었습니다" | "~고 설명했습니다" | "~다고 판단했습니다"

### subtitle (화면 카드 본문)
- narration과 문장 수·순서를 동일하게 맞추되, 숫자·영문은 subtitle 표기 규칙(아라비아
  숫자/로마자 원표기)을 따르세요.

## 출력 JSON의 channel_summaries 배열 형식
"channel_summaries": [
  {"channel_type": "유튜브", "sources": ["채널명1", "채널명2"],
   "narration": "...(250~320자)", "subtitle": "..."},
  {"channel_type": "경제방송", "sources": [...], "narration": "...", "subtitle": "..."},
  {"channel_type": "증권사", "sources": ["증권사명1", "증권사명2"], "narration": "...", "subtitle": "..."}
]
"""


# ─────────────────────────────────────────────────────────────────────────────
# SCRIPT_MOCK=1 더미 생성기 — 실제 LLM 없이 스키마만 맞춘 응답을 만든다.
# 각 함수는 실제 호출부가 이미 갖고 있는 입력값만 사용해, 다운스트림 파이프라인
# (재정렬/에셋/오디오/영상/자막/quality_gate)을 토큰 소비 없이 검증할 수 있게 한다.
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_STOCK_BLOCK_RE = re.compile(r"### \[종목 구획 시작\] \((.*?)\)\n종목명: (.*?) \(")


def _mock_core_response(briefing_text: str) -> dict:
    """build_briefing_text()가 남긴 "(대형 주도주)/(관심 종목)" 태그를 그대로
    파싱해 실제 종목 분류를 재사용한다(LLM 호출 없이도 실제 종목명으로
    다운스트림을 검증하기 위함)."""
    tag_to_bucket = {"대형 주도주": "market_leaders", "관심 종목": "stocks"}
    buckets = {"market_leaders": [], "stocks": []}
    for m in _MOCK_STOCK_BLOCK_RE.finditer(briefing_text):
        bucket = tag_to_bucket.get(m.group(1))
        name = m.group(2).strip()
        if bucket and name and name not in buckets[bucket]:
            buckets[bucket].append(name)
    return {
        "keywords": ["[MOCK]키워드1", "[MOCK]키워드2", "[MOCK]키워드3"],
        "market_summary": {
            "corner_summary": "[MOCK] 오늘 시장 한줄 요약",
            "narration": "[MOCK] 오늘의 시장 흐름을 요약한 더미 문장입니다. " * 6,
            "subtitle": "[MOCK] 오늘의 시장 흐름을 요약한 더미 문장입니다. " * 6,
            "points": ["[MOCK] 포인트1", "[MOCK] 포인트2", "[MOCK] 포인트3"],
        },
        "sectors": {
            "corner_summary": "[MOCK] 핵심 섹터 한줄 요약",
            "narration": "[MOCK] 업종 분석 더미 문장입니다. " * 8,
            "subtitle": "[MOCK] 업종 분석 더미 문장입니다. " * 8,
            "sector_list": [
                {"name": "반도체", "desc": "[MOCK] 더미 설명", "momentum": "상승"},
                {"name": "2차전지", "desc": "[MOCK] 더미 설명", "momentum": "보합"},
            ],
        },
        "ai_strategy": {
            "corner_summary": "[MOCK] AI 전략 한줄 요약",
            "narration": "[MOCK] 투자 전략 더미 문장입니다. " * 8,
            "subtitle": "[MOCK] 투자 전략 더미 문장입니다. " * 8,
            "bullet_points": ["[MOCK] 전략1", "[MOCK] 전략2", "[MOCK] 전략3"],
        },
        "market_leaders":   buckets["market_leaders"][:2],
        "top_stocks":       buckets["stocks"][:3],
        "remaining_stocks": buckets["stocks"][3:],
    }


def _mock_stock_section(stock_name: str, quotes: list, brokerage_mentions: list) -> dict:
    """실제 quotes의 channel_type 분포를 그대로 반영해(유튜브/경제방송/증권사)
    channel_summaries 개수·오디오 job 수가 실제 실행과 비슷하게 나오도록 한다."""
    types_present = {q.get("channel_type") for q in (quotes or [])}
    channel_summaries = []
    for ctype in ("유튜브", "경제방송", "증권사"):
        if ctype not in types_present:
            continue
        sources = list({q["channel"] for q in quotes if q.get("channel_type") == ctype})[:3] or ["[MOCK]채널"]
        channel_summaries.append({
            "channel_type": ctype, "sources": sources,
            "narration": f"[MOCK] {ctype} 종합: {stock_name} 관련 더미 분석 문장입니다. " * 6,
            "subtitle":  f"[MOCK] {ctype} 종합: {stock_name} 관련 더미 분석 문장입니다. " * 6,
        })
    if brokerage_mentions and "증권사" not in types_present:
        channel_summaries.append({
            "channel_type": "증권사", "sources": ["[MOCK]증권사"],
            "narration": f"[MOCK] 증권사 리포트 종합: {stock_name} 더미 분석입니다.",
            "subtitle":  f"[MOCK] 증권사 리포트 종합: {stock_name} 더미 분석입니다.",
        })
    return {
        "corner_summary": f"[MOCK] {stock_name} 오늘 상황 요약",
        "narration_summary": f"다음은 {stock_name} 분석입니다. [MOCK] 더미 분석 문장입니다. " * 4,
        "subtitle_summary":  f"다음은 {stock_name} 분석입니다. [MOCK] 더미 분석 문장입니다. " * 4,
        "summary": f"[MOCK] {stock_name} 한 문장 요약",
        "catalysts": ["[MOCK] 촉매1", "[MOCK] 촉매2"],
        "risks": ["[MOCK] 리스크1"],
        "channel_summaries": channel_summaries,
    }


def _mock_aggregate_sections(remaining_stocks: list,
                              brokerage_reports: dict) -> dict:
    result = {}
    if remaining_stocks:
        result["stock_추가관심종목"] = {
            "corner_summary": "[MOCK] 추가 관심 종목 한줄 요약",
            "narration": "다음은 오늘의 추가 관심 종목입니다. " + " ".join(f"[MOCK] {n} 더미 설명." for n in remaining_stocks),
            "subtitle": "다음은 오늘의 추가 관심 종목입니다. " + " ".join(f"[MOCK] {n} 더미 설명." for n in remaining_stocks),
            "items": [{"name": n, "text": f"[MOCK] {n}에 대한 더미 설명입니다."} for n in remaining_stocks],
        }
    if brokerage_reports:
        names = [
            r.get("stock_name", "")
            for bucket in ("simultaneous", "new_coverage", "single_significant")
            for r in (brokerage_reports.get(bucket) or [])
        ]
        names = [n for n in names if n]
        if names:
            result["stock_증권사리포트"] = {
                "corner_summary": "[MOCK] 증권사 리포트 한줄 요약",
                "narration": "증권사 리포트에서 주목한 종목을 살펴보겠습니다. " + " ".join(f"[MOCK] {n} 더미." for n in names),
                "subtitle": "증권사 리포트에서 주목한 종목을 살펴보겠습니다. " + " ".join(f"[MOCK] {n} 더미." for n in names),
                "items": [{"name": n, "text": f"[MOCK] {n} 증권사 리포트 더미."} for n in names],
            }
    return result


def _call_json(system_prompt: str, user_content: str, max_tokens: int,
               temperature: float = 0.7, retries: int = 1, mock: dict = None) -> dict:
    """OpenAI Chat Completions를 호출해 JSON 객체를 반환합니다. 실패 시 1회 재시도.
    SCRIPT_MOCK=1이고 mock이 주어지면 API를 호출하지 않고 그 값을 그대로 반환한다."""
    if SCRIPT_MOCK and mock is not None:
        return mock
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            last_err = e
            print(f"  ⚠️ API 호출 실패(시도 {attempt + 1}/{retries + 1}): {e}")
    print(f"  ❌ API 호출 최종 실패: {last_err}")
    return {}


def _generate_core(briefing_text: str, market_data: dict) -> dict:
    """시장요약/업종분석/AI전략 코너와 종목 분류 목록을 생성하는 1차 호출.
    종목별 상세 섹션(mentions 포함)은 여기서 만들지 않아 토큰 상한에 여유가 큽니다."""
    system_prompt = f"""
너는 KBS 머니올라 주식 방송 스크립트 작성 전문가입니다. 오늘 방송의 '시장 요약',
'업종 분석', 'AI 투자 전략' 코너와, 이후 종목별 섹션을 만들기 위한 종목 분류 목록을
JSON으로 작성하세요. 이 호출에서는 개별 종목의 상세 설명은 작성하지 마세요.
작성일: {TODAY}

{_NARRATION_SUBTITLE_RULES}

## ★ 섹션별 요구사항 (narration 글자 수, 공백 포함)
- market_summary: 480~600자 (목표 1분 30초~2분, 600자를 크게 넘기지 말 것).
  KOSPI·KOSDAQ·해외지수·환율의 등락과 핵심 원인 1~2가지만 짚고, 업종·개별 종목 상세
  설명은 하지 마세요(다음 코너에서 다룸). "먼저 오늘의 주식시장 전체 흐름을 요약해
  드리겠습니다."로 시작. points는 3~4개.
  ★ 이 코너는 장 시작 전(개장 전) 방송이므로 여기 담긴 KOSPI·KOSDAQ은 전일 종가,
  해외지수는 오늘 새벽에 이미 마감된 미국 시장 자료입니다 — 전부 이미 끝난
  거래입니다. corner_summary와 narration 모두 반드시 완료형 표현("~로 마감했습니다",
  "~마감", "~마감했다")을 쓰고, 진행형/추세 표현("~상승세", "~강세를 보이고 있다",
  "~하는 중")은 절대 쓰지 마세요. 방향(상승/하락/보합)과 무관하게 이 규칙을
  지키세요.
- sectors: 900자 이상. sector_list는 최소 4개, 각 섹터마다 narration에서 최소 150자
  이상 분량으로(주도 종목, 상승/하락 배경, 수급 근거, 전망까지) 충분히 설명하고,
  market_summary와 중복되는 지수·환율 코멘트는 반복하지 마세요. "오늘 시장에서
  주목받는 핵심 업종들을 살펴보겠습니다."로 시작. sector_list는 최대 6개.
- ai_strategy: 700자 이상. bullet_points는 최소 4개, 각 bullet을 narration에서 최소
  120자 이상 분량으로 구체적 근거·수치와 함께 서술. "에이아이가 제안하는 오늘의
  투자 전략입니다."로 시작. bullet_points는 최대 6개.
- 위 세 섹션 모두 목표 글자 수 미달을 절대 허용하지 마세요. 미달 시 배경 설명, 수치,
  전망을 추가해서 채우세요. "간략히", "요약하면" 같은 축약 표현은 쓰지 마세요.

## ★ 종목 분류 (브리핑 원문에서 추출 — 본문 작성 없이 목록만)
- market_leaders: 브리핑에서 가장 비중 있게 다뤄진 대형 주도주 정확히 2개.
- top_stocks: market_leaders를 제외하고 weighted_score(또는 언급 비중)가 높은 상위 3개.
- remaining_stocks: 브리핑에 등장하는 나머지 관심 종목 전부 (생략 없이 모두 나열).
- 종목명은 아래 목록의 정확한 표기를 사용하세요.

## ★ 종목 목록 매핑
{STOCK_NAME_LIST}

## 출력 JSON 구조
{{
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "market_summary": {{
    "corner_summary": "오늘 시장의 핵심 한줄 요약",
    "narration": "...", "subtitle": "...",
    "points": ["포인트1", "포인트2", "포인트3"]
  }},
  "sectors": {{
    "corner_summary": "오늘의 핵심 섹터 한줄 요약",
    "narration": "...", "subtitle": "...",
    "sector_list": [{{"name": "섹터명", "desc": "설명", "momentum": "상승/보합/하락"}}]
  }},
  "ai_strategy": {{
    "corner_summary": "오늘의 AI 전략 핵심 요약",
    "narration": "...", "subtitle": "...",
    "bullet_points": ["전략1", "전략2"]
  }},
  "market_leaders": ["종목명", "종목명"],
  "top_stocks": ["종목명", "종목명", "종목명"],
  "remaining_stocks": ["종목명"]
}}
"""
    user_content = (
        (f"## 실시간 시장 지표 (참고만 하고 narration/subtitle 서술에 반영하세요. "
         f"이 수치 필드를 JSON에 다시 출력할 필요는 없습니다)\n"
         f"{json.dumps(market_data, ensure_ascii=False, indent=2)}\n\n"
         if market_data else "")
        + briefing_text
    )
    data = _call_json(system_prompt, user_content, max_tokens=6000, temperature=0.7,
                       mock=_mock_core_response(briefing_text) if SCRIPT_MOCK else None)

    market_summary = data.get("market_summary") or {}
    if market_data:
        market_summary = {**market_summary, **market_data}

    return {
        "keywords":          (data.get("keywords") or [])[:4],
        "market_summary":    market_summary,
        "sectors":           data.get("sectors") or {},
        "ai_strategy":       data.get("ai_strategy") or {},
        "market_leaders":    data.get("market_leaders") or [],
        "top_stocks":        data.get("top_stocks") or [],
        "remaining_stocks":  data.get("remaining_stocks") or [],
    }


def _is_unfilled_stock_section(data: dict, stock_name: str) -> bool:
    """예시로 보여준 placeholder 문구가 실제 값인 것처럼 그대로 출력에 남았는지
    검사한다 — 과거 "000,000"/"한줄 요약"이 화면에 그대로 노출된 사고
    (LLM이 스키마 예시를 실제 값으로 착각해 베낀 것)의 재발 방지용 안전망."""
    corner = (data.get("corner_summary") or "").strip()
    summary = (data.get("summary") or "").strip()
    return (
        corner in ("", f"{stock_name} 한줄 요약", "한줄 요약")
        or summary in ("", "한줄 요약")
    )


def _generate_stock_section(stock_name: str, briefing_text: str,
                             quotes: list, is_hidden: bool = False,
                             brokerage_mentions: list = None,
                             market_data: dict = None,
                             stock_tier: str = "top_stock") -> dict:
    """종목 하나에 대한 완전한 섹션(summary+channel_summaries)을 생성하는 호출.
    market_leaders/top_stocks 종목마다 별도로 호출해, 근거 데이터가 많아도 토큰
    상한에 안전하게 들어갑니다. stock_tier("market_leader"|"top_stock")는
    narrative_reorder.build_mention_briefing()이 "대형 주도주"/"관심종목"
    그룹을 importance 재랭킹 없이 정확히 나누기 위해 심어두는 태그입니다."""
    brokerage_mentions = brokerage_mentions or []
    market_data = market_data or {}
    system_prompt = f"""
너는 KBS 머니올라 주식 방송 스크립트 작성 전문가입니다. 아래 종목 '{stock_name}' 하나에
대한 종목 분석 섹션만 작성하세요. 다른 종목은 절대 다루지 마세요.
작성일: {TODAY}

{_NARRATION_SUBTITLE_RULES}

{_MENTION_RULES}

## ★ 분량 요구사항 (요구사항: 종목별 설명을 더 자세히)
- narration_summary 400자 이상.
- channel_summaries의 각 항목 narration은 500~640자 내외.
- 목표 미달을 절대 허용하지 마세요. "간략히", "요약하면" 표현 금지.

## ★ 코너 멘트
- narration_summary 시작: "다음은 {stock_name} 분석입니다."

## ★ 반드시 실제 값으로 채울 것 (아래 출력 JSON 구조의 값은 형식 예시일 뿐,
그대로 복사해서 출력하면 안 됩니다 — corner_summary/summary는 매번 이 종목의
실제 상황을 반영한 새 문장이어야 합니다)
- corner_summary: 이 종목의 오늘 상황을 25자 내외 한 문장으로 직접 요약.
- summary: 이 종목 분석의 핵심을 한 문장으로 직접 요약.
- ★ corner_summary/summary/catalysts/risks에는 특정 발언자 이름("OOO 대표는",
  "OOO 연구원은" 등)이나 그 사람의 발언을 절대 넣지 마세요 — 이 필드들은 화면에
  일반 텍스트로 그대로 노출되어(카드 없이) 화자 발언처럼 보이면서도 출처 카드가
  없는 문제가 생깁니다. 특정 인물의 견해·발언은 반드시 channel_summaries
  안에서만 다루고(quote_bubble 카드로 렌더링됨), corner_summary/summary/
  catalysts/risks는 "시장 전반에서는", "업계에서는"처럼 익명화된 사실/개요
  서술만 담으세요.
- 가격/등락률은 이 호출에서 다루지 않습니다(별도 실제 시세 데이터로 채워집니다) —
  price/change 필드는 출력하지 마세요.

## 출력 JSON 구조
{{
  "corner_summary": "(예: 반도체 수출 호조로 외국인 매수 집중)",
  "narration_summary": "...", "subtitle_summary": "...",
  "summary": "(예: 반도체 수출 호조와 외국인 매수세로 긍정적 전망)",
  "catalysts": ["촉매1", "촉매2"], "risks": ["리스크1"],
  "channel_summaries": [
    {{"channel_type": "유튜브", "sources": ["채널명1", "채널명2"],
      "narration": "...(250~320자)", "subtitle": "..."}},
    {{"channel_type": "경제방송", "sources": [...], "narration": "...", "subtitle": "..."}},
    {{"channel_type": "증권사", "sources": ["증권사명1"], "narration": "...", "subtitle": "..."}}
  ]
}}

stock_quotes/stock_brokerage 둘 다 비어 있으면 channel_summaries는 빈 배열로 두세요.
"""
    user_content = (
        (f"## 이 종목의 유튜브·경제방송·증권사 발언 원본 (channel_type별로 묶어 종합 분석)\n"
         f"{json.dumps(quotes, ensure_ascii=False, indent=2)}\n\n"
         if quotes else "이 종목에 대한 유튜브·경제방송·증권사 발언 데이터가 없습니다.\n\n")
        + (f"## 이 종목의 증권사 리포트 원본 (종합해 '증권사' 카테고리로 분석)\n"
           f"{json.dumps(brokerage_mentions, ensure_ascii=False, indent=2)}\n\n"
           if brokerage_mentions else "이 종목에 대한 증권사 리포트 데이터가 없습니다.\n\n")
        + f"## 브리핑 원문 (이 중 '{stock_name}' 관련 내용만 참고하세요)\n{briefing_text}"
    )
    data = _call_json(system_prompt, user_content, max_tokens=6000, temperature=0.7,
                       mock=_mock_stock_section(stock_name, quotes, brokerage_mentions) if SCRIPT_MOCK else None)
    if data and _is_unfilled_stock_section(data, stock_name):
        print(f"  ⚠️ {stock_name}: corner_summary/summary가 예시 placeholder 그대로 반환됨 — 재시도")
        data = _call_json(system_prompt, user_content, max_tokens=6000, temperature=0.9)
        if data and _is_unfilled_stock_section(data, stock_name):
            print(f"  ❌ {stock_name}: 재시도 후에도 placeholder — 화면에 빈 요약이 노출될 수 있음")
    if not data:
        return {}
    data["id"] = f"{'hidden_' if is_hidden else 'stock_'}{stock_name}"
    data["label"] = f"{'숨은 ' if is_hidden else ''}종목 분석 - {stock_name}"
    data["stock_tier"] = stock_tier
    # 가격/등락률은 LLM이 지어내지 않고 V3_1 원본 시세로 항상 덮어쓴다
    # (market_summary의 지수 데이터를 코드에서 주입하는 것과 동일한 패턴).
    data["price"] = market_data.get("price", "")
    data["change"] = market_data.get("change", "")
    data["change_positive"] = market_data.get("change_positive", True)
    return data


def _generate_aggregate_sections(remaining_stocks: list,
                                  brokerage_reports: dict, briefing_text: str) -> list:
    """추가 관심 종목 / 증권사 리포트 집계 섹션을 생성하는 호출."""
    if not remaining_stocks and not brokerage_reports:
        return []

    system_prompt = f"""
너는 KBS 머니올라 주식 방송 스크립트 작성 전문가입니다. 아래 세 집계형 코너를 JSON으로
작성하세요. 해당 데이터가 없는 코너는 결과 JSON에서 필드 자체를 생략하세요.
작성일: {TODAY}

{_NARRATION_SUBTITLE_RULES}

## ★ 종목 혼동 금지 (매우 중요)
- 브리핑 원문에는 사명이 비슷한 계열사(예: 삼성SDI ↔ 삼성전기, 포스코홀딩스 ↔
  포스코퓨처엠 등)가 함께 언급될 수 있습니다. items의 각 "text"는 반드시 해당
  "name"으로 명시된 종목에 대한 내용만 담아야 하며, 원문에서 그 종목명이 실제로
  등장한 문장·문단만 근거로 사용하세요.
- 다른 종목(사명이 비슷하거나 같은 섹터라도)의 실적, 수요, 제품(예: MLCC, 배터리 등)
  관련 내용을 해당 종목의 설명에 섞어 쓰지 마세요. 확실하지 않으면 그 내용은 생략하세요.

## ★ stock_추가관심종목 (remaining_stocks 목록에 있는 종목이 있을 때만 작성)
- narration/subtitle: "다음은 오늘의 추가 관심 종목입니다."로 시작, 종목 수에 비례해
  종목당 최소 100자, 전체 400자 이상. 각 종목: 등락 방향+핵심 이유+전망까지 2문장 이상.
- items: remaining_stocks의 종목을 전부(생략 없이) 다루고, 종목 1개당 items 배열 원소
  1개. [{{"name": "종목명", "text": "이 종목 1개에 대한 2~3문장 설명"}}, ...]
  items 순서·개수는 narration에서 언급한 순서·개수와 반드시 일치해야 합니다.

## ★ stock_증권사리포트 (brokerage_reports 데이터가 있을 때만 작성)
- narration/subtitle: "증권사 리포트에서 주목한 종목을 살펴보겠습니다."로 시작, 전체
  300자 이상.
  · simultaneous(동시언급): "여러 증권사에서 동시에 주목한 [종목명]입니다."로 소개
  · new_coverage(신규 커버리지 개시): "[증권사]가 [종목명]에 대한 커버리지를 새로
    시작했습니다."로 소개
  · single_significant(유의미한 단독 언급): "[증권사]는 [종목명]에 대해 [의견/목표주가
    요지]를 제시했습니다."로 소개
- items: 위 세 카테고리에 등장한 종목 1개당 원소 1개, 위와 동일한 형식.

## 문장마다 번호를 매기지 말고, 반드시 종목(items 원소)마다 번호가 매겨지도록 items를
작성하세요 (화면에 items 배열 순서대로 번호가 표시됩니다).

## 출력 JSON 구조 (해당 데이터 없는 코너는 키 자체를 생략)
{{
  "stock_추가관심종목": {{
    "corner_summary": "추가 관심 종목 한줄 요약",
    "narration": "...", "subtitle": "...",
    "items": [{{"name": "종목명", "text": "..."}}]
  }},
  "stock_증권사리포트": {{
    "corner_summary": "증권사 리포트 한줄 요약",
    "narration": "...", "subtitle": "...",
    "items": [{{"name": "종목명", "text": "..."}}]
  }}
}}
"""
    user_content = (
        f"## 추가 관심 종목 목록\n{json.dumps(remaining_stocks, ensure_ascii=False)}\n\n"
        + (f"## 증권사 리포트 데이터\n{json.dumps(brokerage_reports, ensure_ascii=False, indent=2)}\n\n"
           if brokerage_reports else "")
        + f"## 브리핑 원문\n{briefing_text}"
    )
    data = _call_json(system_prompt, user_content, max_tokens=8000, temperature=0.7,
                       mock=_mock_aggregate_sections(remaining_stocks, brokerage_reports)
                       if SCRIPT_MOCK else None)

    sections = []
    for sid, title in (
        ("stock_추가관심종목", "추가 관심 종목"),
        ("stock_증권사리포트", "증권사 리포트"),
    ):
        sec = data.get(sid)
        if sec:
            sec["id"] = sid
            sec["label"] = title
            sections.append(sec)
    return sections


def _warn_cross_stock_contamination(aggregate_sections: list) -> None:
    """items[].text에 다른 화이트리스트 종목명이 섞여 있는지 가벼운 검사만 수행하고
    경고만 출력합니다(생성 파이프라인을 막지 않음). 종목명이 비슷한 계열사끼리 내용이
    혼입되는 사고(예: 삼성SDI 설명에 삼성전기 언급)를 조기에 발견하기 위한 안전망입니다."""
    all_names = list(STOCK_CODES.keys())
    for sec in aggregate_sections:
        for item in sec.get("items", []):
            name = item.get("name", "")
            text = item.get("text", "")
            if not name or not text:
                continue
            own = normalize_stock_name(name)
            for other in all_names:
                if other == own or other in own or own in other:
                    continue
                if other in text:
                    print(f"  ⚠️  종목 혼동 의심: '{name}' 설명에 다른 종목명 '{other}'가 "
                          f"포함되어 있습니다 — {sec.get('id', '')} 섹션을 확인하세요.")


def generate_script(
    briefing_text: str,
    market_data: dict = None,
    brokerage_reports: dict = None,
    stock_quotes: dict = None,
    stock_market_data: dict = None,
) -> dict:
    stock_quotes = stock_quotes or {}
    stock_market_data = stock_market_data or {}
    stock_brokerage = build_stock_brokerage_mentions(brokerage_reports)

    print("\n🧩 1/3 — 시장요약/업종분석/AI전략 + 종목 분류 생성 중...")
    core = _generate_core(briefing_text, market_data)
    print(f"   대형 주도주: {core['market_leaders']}")
    print(f"   상위 관심종목: {core['top_stocks']}")
    print(f"   추가 관심종목: {len(core['remaining_stocks'])}개")

    # 개별 섹션으로 다룰 종목 목록 (대형 주도주 + 상위 관심종목, 중복 제거).
    # tier_by_name은 narrative_reorder.build_mention_briefing()이 "대형 주도주"
    # 그룹을 importance 재랭킹 없이 정확히 골라내도록 종목별로 심어주는 태그다.
    seen = set()
    major_stocks = []
    tier_by_name = {}
    for name in core["market_leaders"]:
        norm = normalize_stock_name(name)
        if norm and norm not in seen:
            seen.add(norm)
            major_stocks.append(norm)
            tier_by_name[norm] = "market_leader"
    for name in core["top_stocks"]:
        norm = normalize_stock_name(name)
        if norm and norm not in seen:
            seen.add(norm)
            major_stocks.append(norm)
            tier_by_name[norm] = "top_stock"

    print(f"\n🧩 2/3 — 종목별 상세 섹션 생성 중... ({len(major_stocks)}개)")
    stock_sections = []
    for i, stock_name in enumerate(major_stocks, 1):
        print(f"   [{i}/{len(major_stocks)}] {stock_name}")
        sec = _generate_stock_section(stock_name, briefing_text, stock_quotes.get(stock_name, []),
                                       brokerage_mentions=stock_brokerage.get(stock_name, []),
                                       market_data=stock_market_data.get(stock_name, {}),
                                       stock_tier=tier_by_name.get(stock_name, "top_stock"))
        if sec:
            stock_sections.append(sec)
        else:
            print(f"   ⚠️ {stock_name} 섹션 생성 실패 — 건너뜁니다")

    # 개별 섹션에서 다룬 종목은 추가 관심 종목 목록에서 제외
    covered = set(major_stocks)
    remaining_stocks = [
        normalize_stock_name(n) for n in core["remaining_stocks"]
        if normalize_stock_name(n) not in covered
    ]

    print(f"\n🧩 3/3 — 집계 섹션(추가 관심종목/증권사리포트) 생성 중...")
    aggregate_sections = _generate_aggregate_sections(
        remaining_stocks, brokerage_reports, briefing_text
    )
    _warn_cross_stock_contamination(aggregate_sections)

    opening_section = {
        "id": "opening", "label": "오프닝",
        "narration": "__OPENING__", "subtitle": "__OPENING_SUBTITLE__",
        "keywords": core["keywords"],
    }
    market_summary_section = {"id": "market_summary", "label": "시장 요약", **core["market_summary"]}
    sectors_section = {"id": "sectors", "label": "업종 분석", **core["sectors"]}
    ai_strategy_section = {"id": "ai_strategy", "label": "AI 투자 전략", **core["ai_strategy"]}
    closing_section = {
        "id": "closing", "label": "클로징",
        "narration": "__CLOSING__", "subtitle": "__CLOSING_SUBTITLE__",
        "disclaimer": DISCLAIMER,
    }

    sections = (
        [opening_section, market_summary_section, sectors_section]
        + stock_sections
        + aggregate_sections
        + [ai_strategy_section, closing_section]
    )
    data = {"title": f"{TODAY} KBS 머니올라 주식 브리핑", "date": TODAY, "sections": sections}

    def _replace(obj):
        if isinstance(obj, str):
            return (obj
                    .replace("__OPENING__",          OPENING_NARRATION)
                    .replace("__OPENING_SUBTITLE__",  OPENING_SUBTITLE)
                    .replace("__CLOSING__",           CLOSING_NARRATION)
                    .replace("__CLOSING_SUBTITLE__",  CLOSING_SUBTITLE))
        if isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace(v) for v in obj]
        return obj

    data = _replace(data)
    data = fix_subtitle_fields(data)

    # ── 분량 검증 로그 ──────────────────────────────────────────────────────
    sections = data.get("sections", [])
    total_chars = 0
    print("\n📏 섹션별 narration 글자 수:")
    for sec in sections:
        sid = sec.get("id", "")
        # narration 필드가 여러 이름으로 존재할 수 있음 (종목 섹션은 summary +
        # channel_summaries 각 항목의 narration을 전부 합산)
        if sec.get("narration"):
            narr = sec["narration"]
        else:
            cs_texts = "".join(cs.get("narration", "") for cs in sec.get("channel_summaries", []))
            narr = sec.get("narration_summary", "") + cs_texts
        chars = len(narr) if narr else 0
        total_chars += chars
        print(f"  {sid}: {chars:,}자")
    print(f"  ─────────────────")
    print(f"  합계: {total_chars:,}자  (목표: 5,800자 이상, 약 320자/분 기준 15분 분량)")
    if total_chars < 5800:
        print(f"  ⚠️  분량 부족! {5800 - total_chars:,}자 미달 — 영상 후반부가 무음 패딩으로 "
              f"채워질 위험이 있습니다")
    else:
        print(f"  ✅ 분량 목표 달성")

    market_sec = next((s for s in sections if s.get("id") == "market_summary"), None)
    if market_sec:
        ms_chars = len(market_sec.get("narration", "") or "")
        if ms_chars > 600:
            print(f"  ⚠️  market_summary가 목표(480~600자)를 초과했습니다: {ms_chars:,}자 "
                  f"(약 {ms_chars / 320 * 60:.0f}초 분량 — 2분 목표 초과)")

    return data


# ─────────────────────────────────────────────────────────────────────────────

def run(lang: str = "KO"):
    global TODAY
    lang = lang.upper()

    briefing_data = fetch_briefing_data()
    if not briefing_data:
        print(f"❌ {UPSTREAM_REPO}의 briefing_data.json을 가져오지 못했습니다. 종료합니다.")
        sys.exit(1)

    briefing_text = build_briefing_text(briefing_data)
    if not briefing_text.strip():
        print("❌ 브리핑 텍스트가 비어 있습니다(종목/시장 데이터 없음). 종료합니다.")
        sys.exit(1)
    print(f"✅ 브리핑 텍스트 생성 완료 ({len(briefing_text):,}자, {UPSTREAM_REPO} JSON 기반)")

    briefing_date_str = briefing_data.get("briefing_date", "")
    briefing_date_iso = _kdate_to_iso(briefing_date_str)
    if briefing_date_str:
        # 시스템 실행 시각(TODAY) 대신 실제 브리핑이 다루는 날짜를 사용 — 워크플로우가
        # 조기 실행되어 전날 데이터로 생성되더라도 영상에는 데이터 기준 날짜가 정확히 표시된다.
        TODAY = briefing_date_str
        print(f"📅 브리핑 날짜: {TODAY} (실제 브리핑 데이터 기준)")

    # market_data 파싱 (기존 v3 스키마와 동일 — 소스만 UPSTREAM_REPO로 변경)
    market_data = None
    md = briefing_data.get("market_data") or {}
    if md:
        def _fmt_value(v):
            if v is None: return ""
            return f"{v:,.2f}" if isinstance(v, float) else str(v)

        def _fmt_change(pct, direction):
            if pct is None: return ""
            sign = "+" if direction == "up" else ("-" if direction == "down" else "")
            return f"{sign}{abs(pct):.2f}%"

        market_data = {
            "kospi_value":        _fmt_value(md.get("kospi", {}).get("value")),
            "kospi_change":       _fmt_change(md.get("kospi", {}).get("change_pct"), md.get("kospi", {}).get("direction")),
            "kospi_change_positive": md.get("kospi", {}).get("direction") == "up",
            "kosdaq_value":       _fmt_value(md.get("kosdaq", {}).get("value")),
            "kosdaq_change":      _fmt_change(md.get("kosdaq", {}).get("change_pct"), md.get("kosdaq", {}).get("direction")),
            "kosdaq_change_positive": md.get("kosdaq", {}).get("direction") == "up",
            "nasdaq_value":       _fmt_value(md.get("nasdaq", {}).get("value")),
            "nasdaq_change":      _fmt_change(md.get("nasdaq", {}).get("change_pct"), md.get("nasdaq", {}).get("direction")),
            "nasdaq_positive":    md.get("nasdaq", {}).get("direction") == "up",
            "sp500_value":        _fmt_value(md.get("sp500", {}).get("value")),
            "sp500_change":       _fmt_change(md.get("sp500", {}).get("change_pct"), md.get("sp500", {}).get("direction")),
            "sp500_positive":     md.get("sp500", {}).get("direction") == "up",
            "usdkrw_value":       _fmt_value(md.get("usd_krw", {}).get("value")),
            "usdkrw_change":      _fmt_change(md.get("usd_krw", {}).get("change_pct"), md.get("usd_krw", {}).get("direction")),
            "usdkrw_positive":    md.get("usd_krw", {}).get("direction") == "up",
        }
        print(f"✅ market_data 로드 완료: KOSPI {market_data['kospi_value']} / NASDAQ {market_data['nasdaq_value']} / USD/KRW {market_data['usdkrw_value']}")
    else:
        print("⚠️ market_data 없음 → 수치 없이 진행")

    # morning_core는 증권사 리포트를 다루지 않는다 — V3_1의 briefing_data.json에는
    # brokerage_reports가 애초에 비어있으므로 여기서 별도 처리가 필요 없다.
    brokerage_reports = briefing_data.get("brokerage_reports") or None
    if brokerage_reports and not any(
        brokerage_reports.get(k) for k in ("simultaneous", "new_coverage", "single_significant")
    ):
        brokerage_reports = None

    # 종목별 실제 발언 인용 (channel_mentions에서 추출 — 기존 build_stock_quotes()는 그대로 재사용)
    stock_quotes = None
    synthetic_mentions = build_synthetic_mentions(briefing_data, briefing_date_iso)
    if synthetic_mentions:
        grouped = build_stock_quotes(synthetic_mentions, briefing_date_iso)
        if grouped:
            stock_quotes = grouped
            total_quotes = sum(len(v) for v in grouped.values())
            print(f"✅ 종목별 실제 발언 로드 완료: {len(grouped)}개 종목 / {total_quotes}건")
    if not stock_quotes:
        print("⚠️ channel_mentions 없음 → mentions는 생략될 수 있음")

    stock_market_data = build_stock_market_data(briefing_data)

    script = generate_script(briefing_text, market_data, brokerage_reports, stock_quotes,
                              stock_market_data)

    root     = os.path.join(_HERE, "..")
    out_dir  = os.path.join(root, "output", lang, "scripts")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "script.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    sections = script.get("sections", [])
    print(f"\n✅ 스크립트 생성 완료! 섹션 수: {len(sections)}개 → {out_path}")
    return script


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)

