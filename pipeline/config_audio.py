# pipeline/config_audio.py
"""config/audio.yml + config/pronunciation_ko.yml 로더.
프리미엄 TTS 파이프라인(Phase H)의 provider 우선순위/설정, 오디오 후처리
(atempo/loudnorm/BGM 덕킹) 파라미터, 발음 교정 사전을 노출한다."""
import os
import sys
from typing import List

import yaml

_HERE_DIR = os.path.dirname(os.path.abspath(__file__))
if _HERE_DIR not in sys.path:
    sys.path.insert(0, _HERE_DIR)
from assets.korean_numbers import read_decimal_numbers_ko

_HERE = os.path.dirname(os.path.abspath(__file__))
_AUDIO_PATH = os.path.join(_HERE, "..", "config", "audio.yml")
_PRONUNCIATION_PATH = os.path.join(_HERE, "..", "config", "pronunciation_ko.yml")

with open(_AUDIO_PATH, "r", encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f) or {}

with open(_PRONUNCIATION_PATH, "r", encoding="utf-8") as _f:
    _PRONUNCIATION_CFG = yaml.safe_load(_f) or {}

PROVIDER_PRIORITY = _CFG.get("provider_priority") or ["openai"]
PROVIDER_SETTINGS = _CFG.get("providers") or {}

_ATEMPO = _CFG.get("atempo") or {}
ATEMPO_MIN_SPEED = _ATEMPO.get("min_speed", 0.85)
ATEMPO_MAX_SPEED = _ATEMPO.get("max_speed", 1.15)

_LOUDNESS = _CFG.get("loudness") or {}
LOUDNESS_TARGET_LUFS = _LOUDNESS.get("target_lufs", -16.0)
LOUDNESS_TRUE_PEAK = _LOUDNESS.get("true_peak", -1.5)
LOUDNESS_RANGE = _LOUDNESS.get("loudness_range", 11.0)

_BGM = _CFG.get("bgm") or {}
BGM_INTRO_VOLUME = _BGM.get("intro_volume", 0.08)
BGM_BODY_VOLUME = _BGM.get("body_volume", 0.045)
BGM_OUTRO_VOLUME = _BGM.get("outro_volume", 0.08)
BGM_DUCKING_THRESHOLD_DB = _BGM.get("ducking_threshold_db", -25)
BGM_DUCKING_RATIO = _BGM.get("ducking_ratio", 8)

PRONUNCIATION_RULES: List[List[str]] = _PRONUNCIATION_CFG.get("rules") or []


def apply_pronunciation_rules(text: str) -> str:
    """narration 텍스트에 config/pronunciation_ko.yml의 발음 교정 규칙과
    소수점 숫자 완전 한글 변환을 적용합니다. subtitle(화면 자막)에는 절대
    사용하지 마세요.

    FIX-NUM-READ-1: 예전에는 "(\\d+)\\.(\\d+)" 자리에 "쩜"만 끼워 넣고 숫자
    자체는 아라비아 숫자 그대로 TTS에 넘겼다 — 그 결과 소수부(예: ".27")를
    TTS가 자릿수 단위가 있는 두 자리 수("이십칠")로 읽어버려, 한국어 표준
    발음(소수부는 한 자리씩: "이칠")과 어긋났다. read_decimal_numbers_ko()가
    정수부/소수부/부호/퍼센트까지 통째로 한글 발음으로 풀어써 이 문제를
    근본적으로 해결한다(assets/korean_numbers.py 참고)."""
    if not text:
        return text
    result = text
    for src, dst in PRONUNCIATION_RULES:
        result = result.replace(src, dst)
    result = read_decimal_numbers_ko(result)
    return result


_PROVIDER_CLASS_NAMES = {"openai": "OpenAITTSProvider", "azure": "AzureTTSProvider",
                          "elevenlabs": "ElevenLabsProvider"}


def build_providers():
    """provider_priority 순서대로 TTSProvider 인스턴스 목록을 만든다.
    TTS_MOCK=1이면 실제 provider는 전혀 만들지 않고 MockTTSProvider만 반환한다
    (SCRIPT_MOCK과 짝을 이루는 드라이런 스위치 — 토큰/TTS 비용 없이 파이프라인
    전체를 로컬에서 먼저 검증하기 위함)."""
    from assets.tts_providers import (
        AzureTTSProvider, ElevenLabsProvider, OpenAITTSProvider, MockTTSProvider,
    )

    if os.environ.get("TTS_MOCK") == "1":
        return [MockTTSProvider()]

    registry = {
        "openai": lambda cfg: OpenAITTSProvider(
            voice=cfg.get("voice", "nova"), model=cfg.get("model", "tts-1-hd"),
            speed=cfg.get("speaking_rate", 1.0),
        ),
        "azure": lambda cfg: AzureTTSProvider(
            voice_id=cfg.get("voice_id", "ko-KR-SunHiNeural"),
            speaking_rate=cfg.get("speaking_rate", 1.0), pitch=cfg.get("pitch", 0.0),
        ),
        "elevenlabs": lambda cfg: ElevenLabsProvider(
            voice_id=cfg.get("voice_id", ""), model_id=cfg.get("model_id", ""),
            voice_settings={
                "stability": cfg.get("stability", 0.72),
                "similarity_boost": cfg.get("similarity_boost", 0.88),
                "speed": cfg.get("speaking_rate", 1.0),
            } if cfg.get("stability") is not None else None,
            output_format=cfg.get("output_format", "mp3_44100_128"),
        ),
    }

    providers = []
    for name in PROVIDER_PRIORITY:
        factory = registry.get(name)
        if not factory:
            print(f"  [config_audio] 알 수 없는 provider 설정 무시: {name}")
            continue
        providers.append(factory(PROVIDER_SETTINGS.get(name, {})))
    return providers


if __name__ == "__main__":
    print(f"PROVIDER_PRIORITY = {PROVIDER_PRIORITY}")
    print(f"ATEMPO = {ATEMPO_MIN_SPEED}~{ATEMPO_MAX_SPEED}")
    print(f"LOUDNESS_TARGET_LUFS = {LOUDNESS_TARGET_LUFS}")
    print(f"BGM = intro:{BGM_INTRO_VOLUME} body:{BGM_BODY_VOLUME} outro:{BGM_OUTRO_VOLUME}")
    print(f"PRONUNCIATION_RULES = {len(PRONUNCIATION_RULES)}개")
