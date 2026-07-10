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
#
#    Phase H부터는 config/pronunciation_ko.yml이 원본이다(개발자가 아니어도
#    이 yaml만 고치면 발음이 바뀌도록 데이터 파일로 분리). 이 함수는
#    하위 호환을 위해 남겨두고 pipeline/config_audio.py의 구현에 위임한다.
# ──────────────────────────────────────────────────────────────────────────────

def apply_phoneme_rules(text: str) -> str:
    """
    narration 텍스트에 발음 교정 규칙을 적용합니다.
    자막(subtitle)에는 사용하지 마세요.
    """
    from config_audio import apply_pronunciation_rules
    return apply_pronunciation_rules(text)
