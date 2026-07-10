# pipeline/generate_ranking.py
"""
"주도주 랭킹형" 플롯 생성 진입점 (Phase F)
사용법: python pipeline/generate_ranking.py [KO|ko|en]

script.json에서 오늘의 주도주 TOP5를 선정해 ranking.json + TOP5 카드 이미지를
output/YYYY-MM-DD/ranking/에 저장한다. TOP1~3은 voice/assets 잡 산출물(mp3/png)이
이미 있으면 30~45초 쇼츠 클립도 함께 만든다(없으면 경고만 남기고 건너뜀 —
이 스텝이 voice/assets보다 먼저 실행되는 워크플로우 구성이면 자연히 스킵됨).
"""
import os
import re
import sys
import json
import subprocess
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.ranking import build_ranking
from assets.ranking_builders import build_ranking_cards
from assets.shorts_export import export_shorts_clip

KST = timezone(timedelta(hours=9))


def _kdate_to_iso(date_str: str) -> str:
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return datetime.now(KST).strftime("%Y-%m-%d")
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _get_audio_duration(mp3_path: str) -> float:
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", mp3_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        dur = float(result.stdout.strip())
        return dur if dur > 0 else 0.0
    except Exception:
        return 0.0


def _find_summary_frame(frames_dir: str, stock_name: str) -> str:
    if not os.path.isdir(frames_dir):
        return ""
    for f in os.listdir(frames_dir):
        if stock_name in f and f.endswith("_1_summary.png"):
            return os.path.join(frames_dir, f)
    return ""


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    date_iso = _kdate_to_iso(script_data.get("date", ""))
    out_dir = os.path.join(root, "output", date_iso, "ranking")
    os.makedirs(out_dir, exist_ok=True)

    print("🏆 주도주 랭킹 계산 중 (거래량/뉴스·방송/증권사 점수)...")
    ranking_data = build_ranking(script_data, top_n=5)
    if not ranking_data["ranking"]:
        print("⚠️ 랭킹에 포함할 종목 후보가 없습니다(집계 섹션 제외 종목 없음) — ranking.json만 빈 목록으로 저장합니다.")

    for entry in ranking_data["ranking"]:
        print(f"  {entry['rank']}위 {entry['companies']} — ranking_score={entry['ranking_score']} "
              f"(거래량 {entry['volume_score']} / 뉴스 {entry['news_score']} / 증권사 {entry['report_score']})")

    ranking_json_path = os.path.join(out_dir, "ranking.json")
    with open(ranking_json_path, "w", encoding="utf-8") as f:
        json.dump(ranking_data, f, ensure_ascii=False, indent=2)
    print(f"✅ ranking.json 저장 → {ranking_json_path}")

    if ranking_data["ranking"]:
        print("\n🎴 TOP5 카드 렌더링 중...")
        from assets.render import close_renderer
        try:
            card_paths = build_ranking_cards(ranking_data, script_data, out_dir)
            print(f"✅ 카드 {len(card_paths)}개 생성 완료")
        finally:
            close_renderer()

    print("\n🎬 TOP1~3 쇼츠 클립 export 중...")
    audio_dir = os.path.join(root, "output", lang, "audio")
    frames_dir = os.path.join(root, "output", lang, "frames")
    shorts_dir = os.path.join(out_dir, "shorts")
    os.makedirs(shorts_dir, exist_ok=True)

    for entry in ranking_data["ranking"][:3]:
        stock_name = entry["companies"]
        mp3_path = os.path.join(audio_dir, f"{entry['id']}_summary.mp3")
        frame_path = _find_summary_frame(frames_dir, stock_name)

        if not frame_path or not os.path.isfile(mp3_path):
            print(f"  ⚠️ TOP{entry['rank']} {stock_name}: 프레임/오디오 자산이 아직 없어 쇼츠 생성을 "
                  f"건너뜁니다(voice/assets 잡이 먼저 완료돼야 함)")
            continue

        duration = _get_audio_duration(mp3_path)
        if duration <= 0:
            print(f"  ⚠️ TOP{entry['rank']} {stock_name}: 오디오 길이를 확인할 수 없어 건너뜁니다")
            continue

        clip_out = os.path.join(shorts_dir, f"top{entry['rank']}_{stock_name}.mp4")
        clip = export_shorts_clip(frame_path, mp3_path, clip_out, duration, scene_index=entry["rank"])
        if clip:
            print(f"  ✅ TOP{entry['rank']} {stock_name} 쇼츠 → {clip}")

    return ranking_data


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
