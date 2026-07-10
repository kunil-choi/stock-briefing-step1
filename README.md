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
  script(script.json → scene_plan.json)
    → voice / assets(asset 프레임 → media_map.json)
    → video → generate_metadata.py → quality_gate.py
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
| `pipeline/assets/scene_plan.py` / `pipeline/generate_scene_plan.py` | 개체명 추출 + `scene_plan.json` 생성 (Phase B, 아래 참고) |
| `pipeline/assets/media_providers.py` / `media_pipeline.py` / `generate_media.py` / `config/media.yml` | 연합뉴스/KBS 이미지 검색 + `media_map.json` 생성 (Phase C, 아래 참고) |

그 외 `generate_voice.py`/`generate_assets.py`/`generate_subtitles.py`/
`generate_video.py`/`build_asset_map.py`/`pipeline/assets/{chart,html_theme,
image_fetch,render,config}.py`/`voice_config.py`/`update_voice_id.py`는
`stock-briefing-video`에서 무수정 복사했습니다.

## scene_plan.json (개체명 추출 + 비주얼 우선순위)

`generate_script.py`가 만든 `script.json`을 `generate_scene_plan.py`가 읽어
섹션마다 기업명/종목코드/섹터/뉴스키워드/인물/지역/증권사명 7종 개체명을 추출하고,
`priority_score`(0~1, 비주얼 비중)·`visual_type`(오프닝/시장차트/섹터그리드/
종목차트/리스트카드/전략카드/클로징)·`visual_keywords`(기업명>섹터>인물>증권사>
지역>뉴스키워드 우선순위로 최대 8개)를 계산해 `output/KO/scripts/scene_plan.json`
으로 저장합니다. 출력 스키마는 `pipeline/assets/scene_plan.py`의 pydantic
`ScenePlan`/`ScenePlanSection`/`Entity` 모델로 정의됩니다.

기업명 정규화는 이 레포의 기존 `STOCK_CODES`(수동 등록)를 1순위로, `pykrx`
실시간 KRX 전종목 조회를 보조로 사용합니다(`chart.py`의 OHLCV 폴백과 동일하게,
KRX 인증 문제로 실패하면 조용히 수동 목록으로 대체). 별도 파일로만 출력되므로
`script.json`/`asset_map.json`을 소비하는 기존 렌더링 파이프라인은 전혀
변경하지 않습니다(하위 호환).

샘플: `tests/fixtures/sample_script.json` + `tests/test_scene_plan.py`
(`python tests/test_scene_plan.py`로 실행).

## media_map.json (연합뉴스/KBS 이미지 검색)

`generate_media.py`가 `scene_plan.json`의 `visual_keywords`로 연합뉴스/KBS를
검색해 섹션별 최적 이미지를 고르고 `output/KO/media/`에 저장, 매핑을
`output/KO/media/media_map.json`으로 남깁니다.

- **MediaProvider 추상클래스** (`pipeline/assets/media_providers.py`): `YonhapProvider`,
  `KbsProvider`(공개 검색 페이지 스크래핑 기반, `YONHAP_API_KEY`/`KBS_API_KEY`가
  있으면 인증 헤더를 실어 보내는 플러그인 지점을 갖고 있음 — 문서화된 정식 계약
  API가 아직 없어 현재는 항상 공개 검색 경로로 동작), `MockProvider`(네트워크 없이
  결정적 합성 이미지를 생성, `MEDIA_MOCK=1`로 활성화).
- **선택 기준** (`pipeline/assets/media_pipeline.py`의 `score_candidate()`): 관련도
  (visual_keywords 우선순위 근사) + 최근성 + 가로형 여부 + 사용권(`api_licensed` >
  `editorial_search` > `mock`)을 합산 점수로 비교.
- **중복 사용 방지**: 선택된 이미지마다 `imagehash.phash()`를 계산해
  `data/media/license_log.csv`에 기록하고, 다음 실행 시 최근 7일(`config/media.yml`의
  `dedup.window_days`) 내 해밍 거리 6 이하인 이미지는 후보에서 제외합니다. 이
  로그는 실행 간에 유지돼야 하므로 `assets` 잡이 워크플로우에서 직접 레포에
  커밋합니다.
- **섹터 fallback**: 모든 후보가 실패/중복이면 `pipeline/assets/config.py`의
  `SECTOR_FALLBACK_IMAGES`(Phase B의 `STOCK_SECTORS`를 재사용)에서 섹터별
  로컬 이미지를 찾습니다. `assets/sector_fallback/{섹터명}.jpg`는 아직 빈
  placeholder이므로(`assets/fonts`, `assets/music`과 동일한 관례) 실제 파일을
  채워 넣기 전까지는 `image_path: null`로 남고, 다운스트림(렌더러)이 이를
  건너뛰도록 처리해야 합니다.

설정: `config/media.yml`(provider 목록, dedup 기간/임계값, 후보 상한, mock_mode).
샘플: `tests/test_media_pipeline.py`(`MockProvider`만 사용, 네트워크 없이 실행,
`python tests/test_media_pipeline.py`).

## 산출물

```
output/KO/scripts/scene_plan.json   # Phase B: 개체명/priority_score/visual_type/visual_keywords
output/KO/media/media_map.json      # Phase C: 섹션별 선택 이미지 경로/출처/사용권
output/KO/...                 # 기존과 동일한 중간 산출물(scripts/audio/frames/subtitles/video)
data/media/license_log.csv    # Phase C: 이미지 사용 이력(7일 중복 감지용, 레포에 커밋 유지)
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
- `generate_media.py`는 연합뉴스/KBS 검색이 모두 실패하거나(네트워크 오류,
  검색 결과 없음) 후보가 전부 7일 내 중복이면 예외를 던지지 않고 섹터 fallback
  이미지로 대체합니다. fallback 이미지 파일조차 없으면(`assets/sector_fallback/`
  placeholder 미채움) 해당 섹션은 `image_path: null`로 남깁니다 — 워크플로우를
  중단시키지 않고 다음 단계(렌더러)가 그 섹션의 이미지를 건너뛰도록 위임합니다.

## 필요 Secrets

| Secret | 용도 | 필수 여부 |
|---|---|---|
| `OPENAI_API_KEY` | 스크립트/TTS 생성 | 필수 |
| `YONHAP_API_KEY` | 연합뉴스 이미지 검색 인증(정식 계약 API 연결 시) | 선택 — 없으면 공개 검색 경로로 자동 폴백 |
| `KBS_API_KEY` | KBS 뉴스 이미지 검색 인증(정식 계약 API 연결 시) | 선택 — 없으면 공개 검색 경로로 자동 폴백 |

## 환경변수 (.env, 로컬 실행용)

`YONHAP_API_KEY`/`KBS_API_KEY`는 로컬에서는 `.env`(`python-dotenv`로 로드하거나
`export`)로 넣을 수 있습니다. `MEDIA_MOCK=1`을 설정하면 `generate_media.py`가
네트워크 요청 없이 `MockProvider`만 사용합니다(오프라인 테스트/CI 드라이런용).

## 로컬 실행

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python pipeline/generate_script.py KO
python pipeline/generate_scene_plan.py KO
python pipeline/generate_voice.py KO
python pipeline/generate_assets.py KO
MEDIA_MOCK=1 python pipeline/generate_media.py KO   # 실제 검색은 MEDIA_MOCK 없이 실행
python pipeline/generate_subtitles.py KO
python pipeline/generate_video.py KO
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

테스트(둘 다 네트워크 없이 실행 가능):

```bash
python tests/test_scene_plan.py
python tests/test_media_pipeline.py
```

## 다음 단계 (이번 범위 아님)

아래는 설계만 논의됐고 이 레포에는 아직 구현되지 않았습니다:

- 방송형 렌더러 고도화(Ken Burns, crossfade/push transition, lower-third, renderer
  interface 분리)
- "장전 의사결정형"/"주도주 랭킹형" 내러티브 플롯 알고리즘(`reordered_script.json`,
  `ranking_score`)
- 프리미엄 TTS(Azure/ElevenLabs) + 발음사전 + BGM ducking + loudness normalization

각각은 별도 계획 수립 후 후속 작업으로 진행합니다.
