# pipeline/assets/korean_numbers.py
"""
소수점 숫자를 한국어 표준 발음 규칙에 맞게 완전히 풀어 쓰는 유틸리티.

문제: TTS에 "6,516.27"을 그대로 넘기면 정수부는 대체로 올바르게(육천오백
십육) 읽지만, 소수부는 하나의 두 자리 수(이십칠)로 읽어버린다. 한국어에서
소수부는 항상 자릿수 단위 없이 숫자를 하나씩 읽는다("이칠", 이십칠 아님).
등락률(%)의 "-" 부호도 "마이너스"로 명시적으로 읽어야 하는데 그냥 두면
TTS가 부호를 무시하거나 이상하게 읽을 수 있다.

이 모듈은 텍스트 안에서 "-?정수(,구분)?\\.소수(%)?" 패턴만 찾아 그 부분만
완전한 한글 발음으로 치환한다. 소수점이 없는 순수 정수(가격 "259,000원",
날짜 "7월 22일" 등)는 건드리지 않는다 — 그 경우는 기존에도 TTS가 올바르게
읽고 있어(사용자 보고 버그 없음) 손댈 필요가 없고, 자칫 "3개"처럼 고유어
수사(하나/둘/셋)를 써야 하는 문맥까지 한자어 수사로 잘못 바꿔버릴 위험만
커진다 — 그래서 의도적으로 소수점이 있는 패턴으로만 범위를 좁혔다.
"""
import re

_DIGIT_WORDS = "영일이삼사오육칠팔구"
_SMALL_UNITS = ["", "십", "백", "천"]
_BIG_UNITS = ["", "만", "억", "조"]


def _read_four_digit_group(n: int) -> str:
    """0~9999 범위의 정수를 4자리 단위(천/백/십/일) 한글로 읽는다."""
    s = ""
    digits = [int(d) for d in str(n).zfill(4)]
    for i, d in enumerate(digits):
        if d == 0:
            continue
        unit = _SMALL_UNITS[3 - i]
        # "일십"→"십", "일백"→"백"처럼 단위 앞의 "일"은 관용적으로 생략하되,
        # 일의 자리(단위 없음)는 "일" 그대로 남긴다.
        s += (unit if (d == 1 and unit) else _DIGIT_WORDS[d] + unit)
    return s


def read_integer_ko(num: int) -> str:
    """정수를 한글 자릿값 표기(만/억/조)로 읽는다. 예: 6516 → 육천오백십육."""
    if num == 0:
        return "영"
    groups = []
    n = num
    while n > 0:
        groups.append(n % 10000)
        n //= 10000
    parts = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        group_str = _read_four_digit_group(g)
        if i == 1 and group_str == "일":  # "일만"→"만" (관용 표현, 억/조는 유지)
            group_str = ""
        parts.append(group_str + _BIG_UNITS[i])
    return "".join(parts) if parts else "영"


def read_decimal_digits_ko(digits: str) -> str:
    """소수부 문자열("27")을 자릿수 단위 없이 한 글자씩 읽는다("이칠")."""
    return "".join(_DIGIT_WORDS[int(d)] for d in digits if d.isdigit())


# -?  : 음수 부호(있으면 "마이너스"로 읽음)
# \d{1,3}(?:,\d{3})*|\d+ : 콤마로 묶인 정수부 또는 그냥 숫자열
# \.(\d+) : 소수부(필수 — 이 패턴은 소수점이 있는 숫자만 대상으로 함)
# %? : 퍼센트 기호(있으면 "퍼센트"로 읽음)
_DECIMAL_NUMBER_RE = re.compile(
    r"([+-])?(\d{1,3}(?:,\d{3})*|\d+)\.(\d+)(%)?"
)


def _replace_match(m: re.Match) -> str:
    sign_ch, int_part, dec_part, percent_ch = m.groups()
    sign = "마이너스 " if sign_ch == "-" else ""  # "+"는 굳이 소리내 읽지 않음(자연스러운 한국어 관행)
    int_word = read_integer_ko(int(int_part.replace(",", "")))
    dec_word = read_decimal_digits_ko(dec_part)
    percent_word = "퍼센트" if percent_ch else ""
    return f"{sign}{int_word}쩜{dec_word}{percent_word}"


def read_decimal_numbers_ko(text: str) -> str:
    """텍스트 안의 모든 "정수.소수(%)" 패턴을 한글 완전 발음으로 치환한다."""
    if not text:
        return text
    return _DECIMAL_NUMBER_RE.sub(_replace_match, text)


# ── 은/는 조사 선택 ──────────────────────────────────────────────────────

def pick_eun_neun(word: str) -> str:
    """단어 마지막 글자의 받침 유무로 "은"/"는"을 고른다.
    한글 음절이 아닌 문자(영문/숫자)로 끝나면(예: "S&P500") 일반화된 유니코드
    규칙을 적용할 수 없어, 이 프로젝트에서 실제로 쓰이는 시장 지표 이름
    기준으로 알려진 예외만 처리한다."""
    word = (word or "").strip()
    if not word:
        return "는"
    last = word[-1]
    if "가" <= last <= "힣":
        jong = (ord(last) - 0xAC00) % 28
        return "는" if jong == 0 else "은"
    if last.isdigit():
        # "500"→"오백"(받침 ㄱ) 같은 실제 발음 기준 — 이 리포의 지표 이름은
        # 전부 숫자로 끝나면 받침 있는 발음이라(예: S&P500→"오백") "은"을 쓴다.
        return "은"
    return "는"
