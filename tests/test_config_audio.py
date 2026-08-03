# tests/test_config_audio.py
"""
config_audio.build_providers()의 ElevenLabs voice_settings 구성 검증.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. 네트워크 불필요
(provider 객체만 만들고 실제 API는 호출하지 않음).

실제 사고 재현: config/audio.yml에 stability/similarity_boost만 넣어두면
build_providers()가 만드는 voice_settings dict에 style/use_speaker_boost가
통째로 빠졌다. ElevenLabsProvider._resolve_voice_settings()는 voice_settings가
주어지면(넘어온 dict가 비어있지 않으면) voice_config.VOICE_SETTINGS로 폴백하지
않고 그 dict를 그대로 쓰므로, 실제 API 호출에서 style/use_speaker_boost가
빠진 채로 나갔다. use_speaker_boost 누락은 특히 원본(사용자가 학습시킨) 목소리
유사도 보정이 적용되지 않는다는 뜻이라, 사용자가 "내 목소리보다 더 굵고 느리게
나온다"고 보고한 버그의 핵심 원인이었다.

실행: python tests/test_config_audio.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

os.environ.pop("TTS_MOCK", None)

from config_audio import build_providers  # noqa: E402


def test_elevenlabs_voice_settings_includes_style_and_speaker_boost():
    providers = build_providers()
    eleven = next(p for p in providers if p.name == "elevenlabs")
    settings = eleven._voice_settings

    assert settings is not None, "config/audio.yml에 stability가 있으면 voice_settings가 채워져야 함"
    assert "style" in settings, "style이 빠지면 ElevenLabs API 호출에서 통째로 누락됨(실제 사고)"
    assert "use_speaker_boost" in settings, "use_speaker_boost 누락 시 원본 목소리 유사도 보정이 안 됨"
    assert settings["use_speaker_boost"] is True
    assert 0.0 <= settings["style"] <= 1.0
    assert 0.0 <= settings["stability"] <= 1.0
    assert 0.7 <= settings["speed"] <= 1.2, "ElevenLabs speed는 0.7~1.2 범위여야 함"
    print(f"✅ elevenlabs voice_settings에 style/use_speaker_boost 포함 확인: {settings}")


def test_elevenlabs_stability_lowered_from_old_monotone_default():
    """예전 stability=0.72(뉴스 앵커처럼 과도하게 균일한 톤)보다 낮아져
    원본의 억양 변화가 더 살아있어야 한다(사용자 보고: 너무 굵고 개성 없음)."""
    providers = build_providers()
    eleven = next(p for p in providers if p.name == "elevenlabs")
    assert eleven._voice_settings["stability"] < 0.72
    print(f"✅ stability={eleven._voice_settings['stability']} (< 0.72, 더 자연스러운 억양 허용)")


if __name__ == "__main__":
    test_elevenlabs_voice_settings_includes_style_and_speaker_boost()
    test_elevenlabs_stability_lowered_from_old_monotone_default()
    print("\n✅ config_audio 테스트 전체 통과")
