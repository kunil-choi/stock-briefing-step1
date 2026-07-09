"""
pipeline/voice_config.py
========================
목소리(TTS) 설정 관리 모듈.

관리자가 이 파일 한 곳에서 TTS 모델, 목소리 ID, 발음 교정 사전을 모두 변경할 수 있습니다.

사용법:
    from pipeline.voice_config import VOICE_ID, MODEL_ID, VOICE_SETTINGS, apply_phoneme_rules
"""

# ──────────────────────────────────────────────────────────────────────────────
# 1. TTS 서비스 설정 (ElevenLabs)
#    ELEVENLABS_VOICE_ID 환경변수가 없을 경우 여기서 기본값 사용
# ──────────────────────────────────────────────────────────────────────────────

# 사용할 TTS 모델
#   · eleven_multilingual_v2  → 한국어 포함 다국어 고품질 (권장)
#   · eleven_monolingual_v1   → 영어 전용 (한국어 불가)
#   · eleven_turbo_v2_5       → 빠른 속도, 약간 낮은 품질
MODEL_ID = "eleven_multilingual_v2"

# 기본 Voice ID (환경변수 ELEVENLABS_VOICE_ID 로 덮어쓸 수 있음)
# 변경하려면 ElevenLabs 콘솔에서 원하는 voice_id 를 복사해 아래에 붙여넣으세요.
DEFAULT_VOICE_ID = ""   # 기본값 비움: GitHub Secret ELEVENLABS_VOICE_ID 사용 권장

# 목소리 파라미터
VOICE_SETTINGS = {
    "stability":         0.72,   # 0.0~1.0: 높을수록 일관된 톤 (뉴스 앵커 느낌)
    "similarity_boost":  0.88,   # 0.0~1.0: 원본 목소리 유사도
    "style":             0.10,   # 0.0~1.0: 표현력 (낮을수록 안정적)
    "use_speaker_boost": True,   # True 권장
}

# 출력 오디오 포맷
AUDIO_FORMAT = "mp3_44100_128"   # mp3_44100_128 | mp3_44100_192 | pcm_22050

# ──────────────────────────────────────────────────────────────────────────────
# 2. 목소리 후보 프리셋 (자유롭게 전환하세요)
#    아래 딕셔너리에서 원하는 프리셋 이름을 DEFAULT_VOICE_PRESET 에 지정하면 됩니다.
# ──────────────────────────────────────────────────────────────────────────────

VOICE_PRESETS = {
    "matilda":   "XrExE9yKIg1WjnnlVkGX",   # Matilda — 안정적인 여성 앵커
    "rachel":    "21m00Tcm4TlvDq8ikWAM",   # Rachel — 영어/한국어 혼용
    "charlie":   "IKne3meq5aSn9XLyUdCD",   # Charlie — 남성 딥보이스
    "daniel":    "onwK4e9ZLuTAKqWW03F9",   # Daniel — 영국식 남성
    "custom":    "",                         # 커스텀 클론 목소리 ID (보통 Secret으로 주입)
}

# 현재 사용할 프리셋 (VOICE_PRESETS 키 중 하나)
DEFAULT_VOICE_PRESET = "custom"


def get_voice_id() -> str:
    """환경변수 → 프리셋 → 기본값 순으로 Voice ID 를 반환합니다."""
    import os
    env_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if env_id:
        return env_id
    preset_id = VOICE_PRESETS.get(DEFAULT_VOICE_PRESET, "").strip()
    if preset_id:
        return preset_id
    return DEFAULT_VOICE_ID


# ──────────────────────────────────────────────────────────────────────────────
# 3. 발음 교정 사전 (TTS narration 전처리)
#    key: 원문 텍스트 (정규식 또는 고정 문자열)
#    value: TTS 에 전달할 발음 표기
#
#    관리자가 여기서 발음을 추가·수정하면 모든 TTS 출력에 자동 반영됩니다.
# ──────────────────────────────────────────────────────────────────────────────

# (주의) 순서가 중요합니다 — 더 긴 패턴을 위에 배치하세요.
PHONEME_RULES = [
    # ── 영문 약어 → 한글 발음 ─────────────────────────────────────────────
    ("SK하이닉스",       "에스케이하이닉스"),
    ("SK ",              "에스케이 "),
    ("LG에너지솔루션",   "엘지에너지솔루션"),
    ("LG화학",           "엘지화학"),
    ("LG ",              "엘지 "),
    ("KB금융",           "케이비금융"),
    ("KB ",              "케이비 "),
    ("HD현대중공업",     "에이치디현대중공업"),
    ("HD현대일렉트릭",   "에이치디현대일렉트릭"),
    ("HD현대",           "에이치디현대"),
    ("HBM",              "에이치비엠"),
    ("OTT",              "오티티"),
    ("AI",               "에이아이"),
    ("ETF",              "이티에프"),
    ("ESS",              "이에스에스"),
    ("PCE",              "피씨이"),
    ("DSR",              "디에스알"),
    ("MOU",              "엠오유"),
    ("ADR",              "에이디알"),
    ("BPS",              "비피에스"),
    ("EPS",              "이피에스"),
    ("PER",              "피이알"),
    ("ROE",              "알오이"),
    ("POSCO",            "포스코"),
    ("KOSPI",            "코스피"),
    ("KOSDAQ",           "코스닥"),
    ("KrF",              "케이알에프"),
    ("ArF",              "에이알에프"),
    ("EUV",              "이유브이"),
    ("IPO",              "아이피오"),
    ("M&A",              "엠앤에이"),
    ("R&D",              "알앤디"),
    ("YoY",              "와이오와이"),
    ("QoQ",              "큐오큐"),
    ("BUY",              "바이"),
    ("Buy",              "바이"),
    ("MASH",             "마쉬"),
    ("CNS",              "씨엔에스"),
    ("RNAi",             "알엔에이아이"),

    # ── 경음화 / 발음 교정 ───────────────────────────────────────────────
    ("목표주가",          "목표주까"),
    ("주가",              "주까"),
    ("유가",              "유까"),
    ("고유가",            "고유까"),
    ("저유가",            "저유까"),
    ("국채",              "국째"),
    ("역대",              "역때"),
    ("격차",              "격짜"),
    ("적자",              "적짜"),
    ("특징",              "특찡"),
    ("실적",              "실쩍"),
    ("실쩍보다",          "실적보다"),   # 역방향 예외 방지
    ("발전",              "발쩐"),
    ("결정",              "결쩡"),
    ("절감",              "절깜"),
    ("신고가",            "신고까"),
    ("최고가",            "최고까"),
    ("최저가",            "최저까"),
    ("할 것",             "할 껏"),
    ("볼 수",             "볼 쑤"),
    ("될 것",             "될 껏"),
    ("있을",              "이쓸"),

    # ── 소수점 "쩜" 변환 (정규식으로 처리 — apply_phoneme_rules 참조) ──────
    # 정규식 패턴은 아래 apply_phoneme_rules() 에서 처리합니다.

    # ── 숫자 표기 보조 ───────────────────────────────────────────────────
    ("삼성전기",          "삼성 전기"),   # TTS 오독 방지 (자막에는 원래대로)

    # ── 기타 방송 표현 ───────────────────────────────────────────────────
    ("증권사",            "증권사"),
    ("수익률",            "수익률"),
]


def apply_phoneme_rules(text: str) -> str:
    """
    narration 텍스트에 발음 교정 규칙을 적용합니다.
    자막(subtitle)에는 사용하지 마세요.
    """
    import re

    result = text

    # 고정 문자열 치환
    for src, dst in PHONEME_RULES:
        result = result.replace(src, dst)

    # 소수점 "점" → "쩜" (숫자.숫자 패턴)
    result = re.sub(
        r'(\d+)\.(\d+)',
        lambda m: m.group(1) + "쩜" + m.group(2),
        result
    )

    # 숫자+단위 발음 교정: 172만원 → 백칠십이만원 (간단 변환은 GPT가 처리)
    # 여기서는 "%"  앞의 소수점 처리만 추가 보완
    result = re.sub(
        r'(\d+)쩜(\d+)퍼센트',
        lambda m: m.group(0),   # 이미 올바른 형태
        result
    )

    return result
