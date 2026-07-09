"""
pipeline/generate_voice.py
TTS 생성 모듈 — OpenAI TTS (nova, 여성)
"""
import os
import json
import time
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from voice_config import apply_phoneme_rules

OPENAI_VOICE = "nova"       # nova(여성) / onyx(남성) / alloy / echo / fable / shimmer
OPENAI_MODEL = "tts-1-hd"  # tts-1(빠름) / tts-1-hd(고품질)


def text_to_speech(text: str, output_path: str) -> bool:
    """OpenAI TTS로 텍스트를 MP3로 변환합니다."""
    try:
        from openai import OpenAI
    except ImportError:
        print("  ❌ openai 패키지가 없습니다. pip install openai")
        return False

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  ❌ OPENAI_API_KEY 환경변수가 없습니다.")
        return False

    client = OpenAI(api_key=api_key)
    processed_text = apply_phoneme_rules(text)

    try:
        response = client.audio.speech.create(
            model=OPENAI_MODEL,
            voice=OPENAI_VOICE,
            input=processed_text,
            response_format="mp3",
            speed=1.0,
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  ❌ OpenAI TTS 실패: {e}")
        return False


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


def run(lang: str = "KO"):
    lang = lang.upper()

    if not os.environ.get("OPENAI_API_KEY"):
        raise EnvironmentError("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    print(f"🎙️ TTS 엔진: OpenAI TTS ({OPENAI_MODEL} / {OPENAI_VOICE})")
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

    for i, (text, out_path, label) in enumerate(jobs, 1):
        print(f"  [{i}/{total}] {label}")
        print(f"    내용: {text[:60]}...")

        success = text_to_speech(text, out_path)

        if success:
            print(f"    ✅ 완료 → {out_path}")
            success_count += 1
            audio_files.append({"label": label, "path": out_path})
        else:
            print(f"    ❌ 실패 → {out_path}")

        time.sleep(0.3)  # OpenAI는 rate limit 여유 있음

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

    print(f"\n{'='*40}")
    print(f"🎉 TTS 완료! 성공: {success_count}/{total}개")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
