# stock-briefing-step1 — morning_core

📺 **[stock-briefing-video](https://github.com/kunil-choi/stock-briefing-video)**를
1일 2개 영상 파이프라인(morning_core / report_update)으로 분리한 것 중
**morning_core**(장전, 07:10~08:20 KST, 증권사 리포트 제외) 담당 레포입니다.

## 데이터 소스

기존 `stock-briefing-video`는 `stock-briefing-v3`의 라이브 공개 사이트를 Playwright로
스크래핑했지만, 이 레포는 공개 사이트가 없는
**[stock-briefing-v3-1](https://github.com/kunil-choi/stock-briefing-v3-1)**의
`data/briefing_data.json`을 `raw.githubusercontent.com`으로 직접 소비합니다
(`pipeline/generate_script.py`의 `fetch_briefing_data()`/`build_briefing_text()`).
V3_1에는 증권사 리포트 데이터가 애초에 없으므로, 이 레포에서 별도로 필터링할
필요 없이 자연히 증권사 리포트가 빠진 영상이 만들어집니다.

## 트리거 체인

```
stock-briefing-v3-1 완료 → workflow_dispatch → morning_core.yml
  script → voice / assets → video → generate_metadata.py → quality_gate.py
```

자체 cron은 없습니다(V3_1이 끝나기 전에 실행되면 날짜 불일치 위험 —
`stock-briefing-video`의 `daily_broadcast.yml`과 동일한 설계 원칙).

## 신규 구성 요소 (`stock-briefing-video` 대비 추가/변경)

| 파일 | 역할 |
|---|---|
| `config/schedule.yml` | `briefing_type: morning_core`, 실행 창(07:10~08:20), longform 길이 목표 |
| `pipeline/config_schedule.py` | 위 yaml 로더 |
| `pipeline/generate_script.py` | Playwright 스크래핑 제거 → V3_1 JSON 직접 소비로 변경 |
| `pipeline/generate_metadata.py` | 제목/설명/태그/썸네일 생성 + `output/YYYY-MM-DD/metadata.json` 작성 |
| `pipeline/assets/builders.py`의 `build_thumbnail()` | 1920x1080 YouTube 썸네일 렌더링(추가된 함수) |
| `pipeline/quality_gate.py`의 `check_metadata()` | metadata.json 필수 필드 + 길이 범위 검증(추가된 함수) |
| `.github/workflows/morning_core.yml` | `daily_broadcast.yml` 대체, `workflow_dispatch`만 사용 |

그 외 `generate_voice.py`/`generate_assets.py`/`generate_subtitles.py`/
`generate_video.py`/`build_asset_map.py`/`pipeline/assets/{chart,html_theme,
image_fetch,render,config}.py`/`voice_config.py`/`update_voice_id.py`는
`stock-briefing-video`에서 무수정 복사했습니다.

## 산출물

```
output/KO/...                 # 기존과 동일한 중간 산출물(scripts/audio/frames/subtitles/video)
output/YYYY-MM-DD/
  metadata.json                # 아래 스키마
  final.mp4                    # output/KO/video/final.mp4 사본
  thumbnail.png
  script.json                  # output/KO/scripts/script.json 사본
```

`metadata.json` 스키마:

```json
{
  "briefing_type": "morning_core",
  "video_format": "longform",
  "briefing_date": "2026-07-09",
  "generated_at": "2026-07-09T07:45:00+09:00",
  "status": "success | partial | failed",
  "warnings": ["..."],
  "title": "...", "description": "...", "tags": ["..."],
  "thumbnail_path": "thumbnail.png",
  "video_path": "final.mp4",
  "script_path": "script.json",
  "duration_seconds": 905.2,
  "core_stock_count": 5
}
```

## 실패 시 fallback

- `stock-briefing-v3-1`의 `briefing_data.json`을 가져오지 못하면 `generate_script.py`가
  즉시 종료(exit 1)합니다 — 잘못된/오래된 데이터로 영상을 만들지 않기 위함입니다.
- `generate_metadata.py`는 `script.json`이 없으면 `status:"failed"`인 최소
  `metadata.json`만 남기고 종료합니다(빈 산출물 폴더 대신 실패 원인을 남김).
- `final.mp4`가 아직 없는데 `generate_metadata.py`가 실행되면 `status:"partial"`로
  표시하고 `warnings`에 원인을 기록합니다.
- `quality_gate.py`가 `metadata.json`의 필수 필드/길이 범위/`status`를 검증해
  실패 시 워크플로우를 중단시킵니다.

## 필요 Secrets

| Secret | 용도 |
|---|---|
| `OPENAI_API_KEY` | 스크립트/TTS 생성 |

## 로컬 실행

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python pipeline/generate_script.py KO
python pipeline/generate_voice.py KO
python pipeline/generate_assets.py KO
python pipeline/generate_subtitles.py KO
python pipeline/generate_video.py KO
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

## 다음 단계 (이번 범위 아님)

아래는 설계만 논의됐고 이 레포에는 아직 구현되지 않았습니다:

- 개체명 추출 + `scene_plan.json` (KRX/pykrx 정규화, 별칭 매핑, priority_score/
  visual_type/visual_keywords)
- 연합뉴스/KBS 이미지 검색 미디어 파이프라인(`MediaProvider` 추상클래스, mock provider,
  imagehash 중복 감지, `license_log.csv`)
- 방송형 렌더러 고도화(Ken Burns, crossfade/push transition, lower-third, renderer
  interface 분리)
- "장전 의사결정형"/"주도주 랭킹형" 내러티브 플롯 알고리즘(`reordered_script.json`,
  `ranking_score`)
- 프리미엄 TTS(Azure/ElevenLabs) + 발음사전 + BGM ducking + loudness normalization

각각은 별도 계획 수립 후 후속 작업으로 진행합니다.
