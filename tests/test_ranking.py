# tests/test_ranking.py
"""
ranking.py("주도주 랭킹형" 플롯) 검증 스크립트. pytest 미사용, 다른
tests/*.py와 동일하게 순수 assert 기반. OHLCV는 fetch_ohlcv_fn 의존성 주입으로
합성 데이터를 사용하므로 네트워크가 필요 없다.
실행: python tests/test_ranking.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from assets.ranking import (  # noqa: E402
    build_ranking, compute_news_score, compute_ranking_score, compute_report_score,
    compute_volume_score,
)


class _FakeVolumeSeries:
    """pandas 없이도 compute_volume_score를 검증할 수 있도록 최소 인터페이스만
    흉내 내는 더미. 실제로는 pandas.DataFrame을 쓰지만(ranking.py는 .astype(float)/
    .iloc를 호출), 여기서는 pandas가 설치돼 있다고 가정하고 진짜 DataFrame을 만든다."""


def _make_df(volumes):
    import pandas as pd
    n = len(volumes)
    return pd.DataFrame({
        "Open": [1] * n, "High": [1] * n, "Low": [1] * n, "Close": [1] * n,
        "Volume": volumes,
    })


def test_compute_ranking_score_is_pure_weighted_sum():
    assert compute_ranking_score(1.0, 1.0, 1.0) == 1.0
    assert compute_ranking_score(0.0, 0.0, 0.0) == 0.0
    # 기본 가중치 (0.4, 0.3, 0.3) 확인
    assert compute_ranking_score(1.0, 0.0, 0.0) == 0.4
    assert compute_ranking_score(0.0, 1.0, 0.0) == 0.3
    # 가중치를 바꿔서 호출 가능해야 함(별도 함수로 분리된 요구사항 확인)
    assert compute_ranking_score(1.0, 0.0, 0.0, weights=(1.0, 0.0, 0.0)) == 1.0
    print("✅ compute_ranking_score: 가중합 산식 및 가중치 커스터마이즈 확인")


def test_compute_volume_score_increasing_vs_decreasing():
    increasing = compute_volume_score(_make_df([100, 100, 100, 400, 400, 400]))
    decreasing = compute_volume_score(_make_df([400, 400, 400, 100, 100, 100]))
    flat = compute_volume_score(_make_df([200, 200, 200, 200, 200, 200]))
    none_case = compute_volume_score(None)

    assert increasing > flat > decreasing, (increasing, flat, decreasing)
    assert abs(flat - 0.5) < 0.01
    assert none_case == 0.5  # 데이터 없음 → 중립값
    print(f"✅ compute_volume_score: 증가={increasing} 평탄={flat} 감소={decreasing} 없음={none_case}")


def test_compute_news_and_report_score():
    section_rich = {
        "channel_summaries": [
            {"channel_type": "유튜브", "sources": ["채널A", "채널B"]},
            {"channel_type": "경제방송", "sources": ["방송C"]},
            {"channel_type": "증권사", "sources": ["미래에셋증권", "키움증권"]},
        ]
    }
    section_empty = {"channel_summaries": []}

    news_rich = compute_news_score(section_rich)
    news_empty = compute_news_score(section_empty)
    report_rich = compute_report_score(section_rich)
    report_empty = compute_report_score(section_empty)

    assert news_rich > news_empty == 0.0
    assert report_rich > report_empty == 0.0
    assert 0.0 <= news_rich <= 1.0 and 0.0 <= report_rich <= 1.0
    print(f"✅ news_score: {news_rich} vs {news_empty} / report_score: {report_rich} vs {report_empty}")


def test_build_ranking_top5_and_aggregate_exclusion():
    def fake_ohlcv(name):
        # 종목명 길이가 길수록 거래량 증가 추세를 크게 부여해 순위 차이를 만든다
        n = len(name)
        return _make_df([1000] * 3 + [1000 + n * 800] * 3)

    script_data = {
        "title": "t", "date": "2026년 07월 10일",
        "sections": [
            {"id": "opening"},
            {"id": "stock_가장중요종목", "price": "1", "change": "+1%", "change_positive": True,
             "channel_summaries": [{"channel_type": "유튜브", "sources": ["a", "b"]},
                                    {"channel_type": "증권사", "sources": ["c"]}]},
            {"id": "stock_두번째", "price": "1", "change": "+1%", "change_positive": True,
             "channel_summaries": [{"channel_type": "경제방송", "sources": ["d"]}]},
            {"id": "hidden_세번째", "price": "1", "change": "-1%", "change_positive": False,
             "channel_summaries": []},
            {"id": "stock_추가관심종목", "items": []},   # 집계 섹션 → 후보 제외돼야 함
            {"id": "stock_오늘의픽", "items": []},        # 집계 섹션 → 후보 제외돼야 함
            {"id": "ai_strategy"},
            {"id": "closing"},
        ],
    }

    result = build_ranking(script_data, top_n=5, fetch_ohlcv_fn=fake_ohlcv)
    ranking = result["ranking"]

    ids = [r["id"] for r in ranking]
    assert "stock_추가관심종목" not in ids and "stock_오늘의픽" not in ids, "집계 섹션이 랭킹 후보에 포함됨"
    assert len(ranking) == 3  # 후보가 3개뿐이므로 top_n=5여도 3개만 나와야 함

    scores = [r["ranking_score"] for r in ranking]
    assert scores == sorted(scores, reverse=True), "ranking_score 내림차순 정렬이 깨짐"
    assert [r["rank"] for r in ranking] == [1, 2, 3]

    top1 = ranking[0]
    assert top1["companies"] == "가장중요종목"
    assert top1["ranking_score"] == compute_ranking_score(
        top1["volume_score"], top1["news_score"], top1["report_score"]
    )
    print(f"✅ build_ranking: TOP{len(ranking)} 선정 및 집계 섹션 제외 확인 — 1위 {top1['companies']}")


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _probe_duration(path: str) -> float:
    import re
    result = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    assert m, f"ffmpeg -i 출력에서 Duration을 찾지 못함: {path}"
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def test_export_shorts_clip_caps_at_max_duration():
    if not _ffmpeg_available():
        print("⚠️  ffmpeg가 PATH에 없어 shorts export 테스트를 스킵합니다.")
        return

    from assets.shorts_export import export_shorts_clip, SHORTS_MAX_SECONDS

    tmp_dir = tempfile.mkdtemp()
    try:
        frame = os.path.join(tmp_dir, "frame.png")
        audio = os.path.join(tmp_dir, "audio.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360",
                         "-frames:v", "1", frame], capture_output=True, check=True)
        # 60초짜리 오디오(45초 상한을 넘음)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                         "-t", "60", "-q:a", "9", audio], capture_output=True, check=True)

        out_path = os.path.join(tmp_dir, "shorts.mp4")
        result = export_shorts_clip(frame, audio, out_path, audio_duration=60.0, scene_index=0)
        assert result == out_path
        dur = _probe_duration(out_path)
        assert dur <= SHORTS_MAX_SECONDS + 0.5, f"쇼츠 클립이 상한을 넘음: {dur}"
        assert dur >= SHORTS_MAX_SECONDS - 0.5, f"60초 오디오인데 45초 상한까지 채우지 못함: {dur}"
        print(f"✅ export_shorts_clip: 60초 오디오 → {dur:.1f}초로 상한(45초) 적용 확인")
    finally:
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    test_compute_ranking_score_is_pure_weighted_sum()
    test_compute_volume_score_increasing_vs_decreasing()
    test_compute_news_and_report_score()
    test_build_ranking_top5_and_aggregate_exclusion()
    test_export_shorts_clip_caps_at_max_duration()
    print("\n✅ ranking 테스트 전체 통과")
