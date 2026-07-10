"""
pipeline/generate_voice.py
TTS 생성 모듈 — 프리미엄 TTS 파이프라인(Phase H)

provider_priority(config/audio.yml, 기본 azure→elevenlabs→openai) 순서로
합성을 시도하고, 키가 없는 provider는 자동으로 건너뛴다(이 레포는 아직
AZURE_SPEECH_KEY/ELEVENLABS_API_KEY가 없어 실제로는 항상 OpenAI로 동작한다).
합성 후에는 loudnorm으로 방송 표준 음량(기본 -16 LUFS)에 맞추고, 원문에서
투자 권유처럼 들리는 과장 표현을 탐지(치환 없이 경고만)해 output/{lang}/
audio_report.json에 기록한다.
"""
import os
import json
import shutil
import time
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config_audio import (
    apply_pronunciation_rules, build_providers,
    LOUDNESS_TARGET_LUFS, LOUDNESS_TRUE_PEAK, LOUDNESS_RANGE,
)
from assets.tts_providers import synthesize_with_fallback
from assets.audio_post import (
    apply_post_processing, measure_duration, measure_loudness,
    detect_advice_language, build_audio_report,
)

AGGREGATE_STOCK_SECTION_IDS = {"stock_추가관심종목", "stock_오늘의픽", "stock_증권사리포트"}


def _build_jobs(sections: list, lang: str) -> list:
    jobs = []
    audio_base = f"output/{lang}/audio"

    for section in sections:
        sid   = section.get("id", "")
        label = section.get("label", sid)
        if not sid:
            continue

        is_stock = (
            (sid.startswith("stock_") or sid.startswith("hidden_"))
            and sid not in AGGREGATE_STOCK_SECTION_IDS
        )

        if is_stock:
            text = section.get("narration_summary", section.get("narration", ""))
            if text:
                jobs.append((text, f"{audio_base}/{sid}_summary.mp3", f"{label} [summary]"))

            # channel_summaries: 종목당 최대 3개(유튜브/경제방송/증권사) 카테고리별
            # 종합 분석 요약 — 한 항목당 오디오 1개(페이지 인덱스 = 배열 인덱스)
            for p, cs in enumerate(section.get("channel_summaries", [])):
                text = cs.get("narration", "")
                if text:
                    label_suffix = cs.get("channel_type", f"mention_page{p}")
                    jobs.append((text, f"{audio_base}/{sid}_mention_{p:02d}.mp3", f"{label} [{label_suffix}]"))
        else:
            narration = section.get("narration", "")
            if narration:
                jobs.append((narration, f"{audio_base}/{sid}.mp3", label))

    return jobs


def _synthesize_job(providers, text: str, out_path: str, job_id: str) -> dict:
    """provider 폴백 체인으로 합성 → loudnorm 후처리 → 실측치/경고를 담은
    audio_report 엔트리를 반환한다. 원문(text)에 대해 과장 표현을 탐지하되
    치환은 하지 않는다(원문은 그대로 provider에 전달)."""
    warnings = detect_advice_language(text)
    processed_text = apply_pronunciation_rules(text)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    raw_path = out_path + ".raw.mp3"
    ok, provider_name = synthesize_with_fallback(providers, processed_text, raw_path)

    if not ok:
        return {
            "id": job_id, "provider": "", "duration_seconds": 0.0,
            "speed": 1.0, "loudness_lufs": None, "warnings": warnings, "success": False,
        }

    post_ok = apply_post_processing(
        raw_path, out_path, speed=1.0,
        target_lufs=LOUDNESS_TARGET_LUFS, true_peak=LOUDNESS_TRUE_PEAK,
        loudness_range=LOUDNESS_RANGE,
    )
    if not post_ok:
        print("    ⚠️ 후처리(loudnorm) 실패 → 원본 합성 파일 그대로 사용")
        shutil.move(raw_path, out_path)
    elif os.path.isfile(raw_path):
        os.remove(raw_path)

    duration = measure_duration(out_path)
    loudness = measure_loudness(out_path)
    return {
        "id": job_id, "provider": provider_name, "duration_seconds": round(duration, 2),
        "speed": 1.0, "loudness_lufs": loudness, "warnings": warnings, "success": True,
    }


def run(lang: str = "KO"):
    lang = lang.upper()

    providers = build_providers()
    configured = [p.name for p in providers if p.is_configured()]
    if not configured:
        raise EnvironmentError(
            "❌ 사용 가능한 TTS provider가 없습니다. OPENAI_API_KEY(또는 "
            "AZURE_SPEECH_KEY/AZURE_SPEECH_REGION, ELEVENLABS_API_KEY) 환경변수를 "
            "설정하세요."
        )

    print(f"🎙️ TTS provider 우선순위: {[p.name for p in providers]} (사용 가능: {configured})")
    print(f"📁 출력 언어: {lang}")

    script_path = f"output/{lang}/scripts/script.json"
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    sections = script.get("sections", [])
    jobs     = _build_jobs(sections, lang)
    total    = len(jobs)
    print(f"\n🎙️ TTS 생성 시작 — 총 {total}개 작업\n")

    success_count = 0
    audio_files   = []
    report_entries = []

    for i, (text, out_path, label) in enumerate(jobs, 1):
        print(f"  [{i}/{total}] {label}")
        print(f"    내용: {text[:60]}...")

        job_id = os.path.splitext(os.path.basename(out_path))[0]
        entry = _synthesize_job(providers, text, out_path, job_id)
        success = entry.pop("success")

        if success:
            print(f"    ✅ 완료 → {out_path} (provider={entry['provider']}, "
                  f"{entry['duration_seconds']:.1f}s, {entry['loudness_lufs']}LUFS)")
            success_count += 1
            audio_files.append({"label": label, "path": out_path})
        else:
            print(f"    ❌ 실패 → {out_path}")

        report_entries.append(entry)
        time.sleep(0.3)  # rate limit 여유

    summary = {
        "total":   total,
        "success": success_count,
        "failed":  total - success_count,
        "files":   audio_files
    }
    summary_path = f"output/{lang}/audio/summary.json"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    audio_report = build_audio_report(report_entries)
    report_path = f"output/{lang}/audio_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audio_report, f, ensure_ascii=False, indent=2)
    print(f"📄 오디오 리포트 저장: {report_path} "
          f"(과장 표현 경고 {audio_report['total_advice_language_warnings']}건)")

    print(f"\n{'='*40}")
    print(f"🎉 TTS 완료! 성공: {success_count}/{total}개")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
