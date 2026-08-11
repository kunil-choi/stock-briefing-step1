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
import subprocess
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
from assets.watchlist_pages import build_watchlist_pages

AGGREGATE_STOCK_SECTION_IDS = {"stock_추가관심종목", "stock_증권사리포트"}

# conclusion(영상의 첫 프레임 — 브랜드 타이틀 이미지 + 채널 언급 인트로
# 내레이션) 오디오 맨 앞에 붙이는 무음 길이. 이 구간 동안은 내레이션이
# 없으니 사이드체인 덕킹(assets/audio_post.py)이 BGM을 낮추지 않아 배경
# 음악만 들리는 인트로가 된다(사용자 요청: 영상 시작 5초 정도는 음악만
# 나온 뒤 멘트 시작). Ken Burns 클립 길이는 오디오 길이를 그대로 따라가므로
# (generate_video.py) 화면은 같은 타이틀 이미지를 그 무음 구간 동안 계속
# 보여준다 — 새 프레임을 추가하는 게 아니라 conclusion.mp3 자체를 늘린다.
CONCLUSION_LEAD_SILENCE_SECONDS = 5.0


def _prepend_silence(mp3_path: str, seconds: float) -> bool:
    """mp3_path 오디오 맨 앞에 seconds초 무음을 붙인다(원본을 대체). ffmpeg의
    adelay 필터로 파형 시작 지점을 뒤로 미루는 방식이라(모든 채널을 같은
    양만큼 지연), concat용 별도 무음 파일을 만들 필요가 없다."""
    if seconds <= 0:
        return True
    delay_ms = int(seconds * 1000)
    padded_path = mp3_path + ".padded.mp3"
    cmd = [
        "ffmpeg", "-y", "-i", mp3_path,
        "-af", f"adelay={delay_ms}|{delay_ms}",
        "-c:a", "libmp3lame", "-b:a", "192k",
        padded_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.isfile(padded_path):
        print(f"    ⚠️ 무음 인트로 추가 실패 → 원본 길이 그대로 사용")
        return False
    os.replace(padded_path, mp3_path)
    return True


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
        elif sid == "hook":
            # 훅 타이틀 화면은 제목 카드처럼 텍스트만 보여주고 내레이션은 넣지
            # 않는다(narrative_reorder._build_hook_section 참고) — 오디오를
            # 합성하지 않으며, generate_video.py가 무음 프레임으로 처리한다.
            continue
        elif sid == "stock_추가관심종목":
            # 종목 1개당 화면 1페이지(builders.build_extra_watchlist)이므로
            # 오디오도 페이지마다 하나씩 따로 합성한다 — assets.watchlist_pages가
            # builders.py와 페이지 목록(순서·텍스트)을 공유해 프레임/오디오가
            # 어긋나지 않는다.
            for p, page in enumerate(build_watchlist_pages(section)):
                text = page["text"]
                if text:
                    jobs.append((text, f"{audio_base}/{sid}_{p:02d}.mp3", f"{label} [{page['name']}]"))
        elif sid == "ai_strategy_brief":
            # 화면 3장(핵심 시나리오/포인트/애널리스트)마다 오디오를 하나씩
            # 따로 합성한다(narrative_reorder._build_ai_strategy_brief_section,
            # builders.build_ai_strategy_brief 참고).
            for key, audio_name in (
                ("core_narration", "ai_strategy_core"),
                ("points_narration", "ai_strategy_points"),
                ("analyst_narration", "ai_strategy_analyst"),
            ):
                text = section.get(key, "")
                if text:
                    jobs.append((text, f"{audio_base}/{audio_name}.mp3", f"{label} [{audio_name}]"))
        else:
            narration = section.get("narration", "")
            if narration:
                jobs.append((narration, f"{audio_base}/{sid}.mp3", label))

    return jobs


def _synthesize_job(providers, text: str, out_path: str, job_id: str,
                     lead_silence: float = 0.0) -> dict:
    """provider 폴백 체인으로 합성 → loudnorm 후처리 → 실측치/경고를 담은
    audio_report 엔트리를 반환한다. 원문(text)에 대해 과장 표현을 탐지하되
    치환은 하지 않는다(원문은 그대로 provider에 전달). lead_silence는
    loudnorm까지 끝난 뒤에 붙인다 — loudnorm이 무음까지 포함해 음량을
    재계산하면 실제 목소리 음량이 왜곡되기 때문이다."""
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

    if lead_silence > 0:
        _prepend_silence(out_path, lead_silence)

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

    script_path = f"output/{lang}/scripts/reordered_script.json"
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
        lead_silence = CONCLUSION_LEAD_SILENCE_SECONDS if job_id == "conclusion" else 0.0
        entry = _synthesize_job(providers, text, out_path, job_id, lead_silence=lead_silence)
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
