# pipeline/assets/tts_providers.py
"""
프리미엄 TTS 파이프라인(Phase H) — TTSProvider 추상클래스 + 구현체.

OpenAITTSProvider가 이 레포에서 실제로 동작 중인 유일한 provider다(기존
generate_voice.py의 text_to_speech() 로직을 그대로 옮김). AzureTTSProvider/
ElevenLabsProvider는 REST API를 직접 호출하도록(무거운 SDK 의존성 추가 없이)
완전히 구현돼 있지만, 이 레포에는 아직 AZURE_SPEECH_KEY/ELEVENLABS_API_KEY가
등록돼 있지 않아 실제로는 항상 OpenAI로 폴백한다 — Phase C의 YonhapProvider/
KbsProvider와 같은 패턴(키가 없어도 안전하게 대체 경로로 동작, 키가 들어오면
바로 켜짐).

ElevenLabsProvider는 이 레포에 이미 있던(죽어있던) voice_config.py의
MODEL_ID/VOICE_SETTINGS/get_voice_id()를 그대로 재사용한다.
"""
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import requests


class TTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """실제로 호출 가능한 상태인지(API 키 등) 반환합니다."""
        ...

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> bool:
        """텍스트를 output_path(mp3)로 합성합니다. 성공하면 True."""
        ...


class OpenAITTSProvider(TTSProvider):
    """기존 generate_voice.py의 text_to_speech() 로직을 그대로 옮긴 provider.
    이 레포에서 현재 실제로 동작하는 유일한 경로(OPENAI_API_KEY는 이미
    workflow secret으로 설정돼 있음).

    speed는 OpenAI TTS API가 합성 단계에서 자체적으로 낭독 속도를 조절하는
    파라미터(0.25~4.0)다 — 다 만들어진 오디오를 ffmpeg atempo로 재생속도만
    올리는 것과 달리, 음높이 왜곡이나 "기계음" 느낌 없이 자연스러운 속도
    조절이 가능하다(요구사항: 빠르지만 정상적인 목소리)."""
    name = "openai"

    def __init__(self, voice: str = "nova", model: str = "tts-1-hd", speed: float = 1.0):
        self.voice = voice
        self.model = model
        self.speed = speed

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def synthesize(self, text: str, output_path: str) -> bool:
        try:
            from openai import OpenAI
        except ImportError:
            print("  ❌ [tts:openai] openai 패키지가 없습니다. pip install openai")
            return False

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("  ❌ [tts:openai] OPENAI_API_KEY 환경변수가 없습니다.")
            return False

        try:
            client = OpenAI(api_key=api_key)
            response = client.audio.speech.create(
                model=self.model, voice=self.voice, input=text,
                response_format="mp3", speed=self.speed,
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"  ❌ [tts:openai] 합성 실패: {e}")
            return False


class AzureTTSProvider(TTSProvider):
    """Azure Cognitive Services Speech REST API(무거운 SDK 없이 requests로
    직접 호출). AZURE_SPEECH_KEY/AZURE_SPEECH_REGION이 없으면 is_configured()가
    False를 반환해 폴백 체인이 자동으로 다음 provider로 넘어간다."""
    name = "azure"

    def __init__(self, voice_id: str = "ko-KR-SunHiNeural",
                 speaking_rate: float = 1.0, pitch: float = 0.0):
        self.voice_id = voice_id
        self.speaking_rate = speaking_rate
        self.pitch = pitch

    def is_configured(self) -> bool:
        return bool(os.environ.get("AZURE_SPEECH_KEY")) and bool(os.environ.get("AZURE_SPEECH_REGION"))

    def synthesize(self, text: str, output_path: str) -> bool:
        key = os.environ.get("AZURE_SPEECH_KEY", "")
        region = os.environ.get("AZURE_SPEECH_REGION", "")
        if not key or not region:
            print("  ❌ [tts:azure] AZURE_SPEECH_KEY/AZURE_SPEECH_REGION 없음")
            return False

        rate_pct = f"{(self.speaking_rate - 1.0) * 100:+.0f}%"
        pitch_pct = f"{self.pitch:+.0f}%"
        ssml = (
            f'<speak version="1.0" xml:lang="ko-KR">'
            f'<voice name="{self.voice_id}">'
            f'<prosody rate="{rate_pct}" pitch="{pitch_pct}">{_xml_escape(text)}</prosody>'
            f'</voice></speak>'
        )
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
        }
        try:
            r = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=30)
            if r.status_code != 200:
                print(f"  ❌ [tts:azure] HTTP {r.status_code}: {r.text[:200]}")
                return False
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            print(f"  ❌ [tts:azure] 합성 실패: {e}")
            return False


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs REST API. 이 레포에 이미 있던(그러나 쓰이지 않던)
    voice_config.py의 MODEL_ID/VOICE_SETTINGS/get_voice_id()를 그대로
    재사용한다 — stock-briefing-video에서 넘어올 때 ElevenLabs 설정만 남고
    실제 호출부는 OpenAI TTS로 바뀌어 죽어있던 설정이었다."""
    name = "elevenlabs"

    def __init__(self, voice_id: str = "", model_id: str = "",
                 voice_settings: Optional[dict] = None, output_format: str = "mp3_44100_128"):
        self._voice_id = voice_id
        self._model_id = model_id
        self._voice_settings = voice_settings
        self.output_format = output_format

    def _resolve_voice_id(self) -> str:
        if self._voice_id:
            return self._voice_id
        try:
            from voice_config import get_voice_id
            return get_voice_id()
        except Exception:
            return ""

    def _resolve_model_id(self) -> str:
        if self._model_id:
            return self._model_id
        try:
            from voice_config import MODEL_ID
            return MODEL_ID
        except Exception:
            return "eleven_multilingual_v2"

    def _resolve_voice_settings(self) -> dict:
        if self._voice_settings:
            return self._voice_settings
        try:
            from voice_config import VOICE_SETTINGS
            return VOICE_SETTINGS
        except Exception:
            return {"stability": 0.72, "similarity_boost": 0.88}

    # NOTE: ElevenLabs v2/turbo 모델은 voice_settings.speed(0.7~1.2)로
    # 낭독 속도를 조절할 수 있다. config/audio.yml에 speed가 설정돼 있으면
    # 여기서 채워 넣는다(호출부인 config_audio.build_providers()가 처리).

    def is_configured(self) -> bool:
        return bool(os.environ.get("ELEVENLABS_API_KEY")) and bool(self._resolve_voice_id())

    def synthesize(self, text: str, output_path: str) -> bool:
        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        voice_id = self._resolve_voice_id()
        if not api_key or not voice_id:
            print("  ❌ [tts:elevenlabs] ELEVENLABS_API_KEY 또는 voice_id 없음")
            return False

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={self.output_format}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": self._resolve_model_id(),
            "voice_settings": self._resolve_voice_settings(),
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code != 200:
                print(f"  ❌ [tts:elevenlabs] HTTP {r.status_code}: {r.text[:200]}")
                return False
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            print(f"  ❌ [tts:elevenlabs] 합성 실패: {e}")
            return False


class MockTTSProvider(TTSProvider):
    """TTS_MOCK=1 드라이런 전용. 실제 TTS provider를 전혀 호출하지 않고,
    텍스트 길이에 비례한 길이의 무음에 가까운 저음량 톤 mp3를 ffmpeg로 만든다.
    실제 음성 품질은 검증할 수 없지만, 후속 단계(loudnorm 후처리/영상 길이
    계산/BGM 덕킹/자막 타이밍/quality_gate)를 진짜 오디오 파일로 — TTS 비용
    없이 — 끝까지 실행해볼 수 있게 해준다."""
    name = "mock"

    def __init__(self, chars_per_second: float = 5.5):
        self.chars_per_second = chars_per_second

    def is_configured(self) -> bool:
        return True

    def synthesize(self, text: str, output_path: str) -> bool:
        import subprocess
        duration = max(1.0, len(text) / self.chars_per_second)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=220:duration={duration:.2f}",
            "-af", "volume=0.05",
            "-c:a", "libmp3lame", "-b:a", "128k",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ❌ [tts:mock] 더미 오디오 생성 실패: {result.stderr[-300:]}")
            return False
        return True


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


def synthesize_with_fallback(providers: List[TTSProvider], text: str,
                              output_path: str) -> Tuple[bool, str]:
    """providers를 우선순위 순서대로 시도해 처음 성공하는 provider로 합성한다.
    is_configured()가 False인 provider는 호출 자체를 건너뛴다(불필요한 실패
    로그 방지). 반환: (성공 여부, 실제로 사용된 provider.name 또는 "").
    """
    for provider in providers:
        if not provider.is_configured():
            continue
        if provider.synthesize(text, output_path):
            return True, provider.name
        print(f"  ⚠️ [tts] {provider.name} 실패 → 다음 provider로 폴백")
    return False, ""
