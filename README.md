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
| `pipeline/assets/video_renderer.py` | Ken Burns 합성 + crossfade/push 전환 `VideoRenderer` 인터페이스/구현체 (Phase D, 아래 참고) |
| `pipeline/assets/html_theme.py`의 `lower_third()`/`headline_card()`/`report_card()`/`risk_card()`/`sector_heatmap()`/`autofit_text()` | 방송형 컴포넌트 + 2줄 자동 축소 텍스트 (Phase D, 추가된 함수) |
| `pipeline/assets/render.py`의 autofit 스크린샷 전처리 | `data-autofit` 요소를 실측해 폰트 크기 자동 축소 (Phase D, 추가된 로직) |
| `pipeline/generate_video.py` / `generate_subtitles.py` | 정지 프레임 홀드 → Ken Burns/전환 클립으로 교체, 전환 구간만큼 자막 타임라인 보정 (Phase D, 변경) |
| `pipeline/assets/narrative_reorder.py` / `pipeline/generate_reordered_script.py` | "장전 의사결정형" 플롯으로 섹션 재정렬 + `reordered_script.json` 생성 (Phase E, 아래 참고) |
| `pipeline/assets/ranking.py` / `ranking_builders.py` / `shorts_export.py` / `pipeline/generate_ranking.py` | "주도주 랭킹형" 플롯 — TOP5 산정 + 카드 + TOP1~3 쇼츠 export (Phase F, 아래 참고) |

그 외 `generate_voice.py`/`generate_assets.py`/`build_asset_map.py`/
`pipeline/assets/{chart,image_fetch}.py`/`voice_config.py`/`update_voice_id.py`는
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

## 방송형 렌더링 (Ken Burns / 전환 / lower-third / 자동 텍스트 축소)

기존 `generate_video.py`는 PNG 슬라이드를 `-loop 1`로 그대로 정지 홀드해
"PPT를 넘기는" 느낌이었습니다. Phase D는 이를 방송 그래픽처럼 항상 미세하게
움직이는 화면으로 바꿉니다.

- **renderer interface 분리**: `pipeline/assets/video_renderer.py`의
  `VideoRenderer`(추상클래스, `compose_scene`/`build_transition`/`concat`)를
  `FFmpegVideoRenderer`가 구현합니다. 추후 Remotion 등으로 교체하려면 이
  인터페이스를 만족하는 새 클래스만 추가하면 되고, `generate_video.py` 등
  호출부는 그대로 둘 수 있습니다.
- **Ken Burns**: `compose_scene()`이 ffmpeg `zoompan` 필터로 각 장면을 서서히
  확대(최대 1.08배)합니다. 팬(pan) 중심은 장면 인덱스에 따라 4가지 패턴을
  순환해 매번 같은 방식으로 확대되는 단조로움을 피합니다.
- **crossfade/push 전환**: `build_transition()`이 ffmpeg `xfade` 필터로
  `fade`(crossfade)와 `slideleft`/`slideright`(push)를 번갈아 적용한
  0.4초짜리 짧은 전환 클립을 만들어 장면 사이에 **삽입**합니다. 실제로
  겹쳐서(overlap) 이어붙이면 오디오 타임라인이 전환 길이만큼 줄어들어
  자막 동기화 로직(`generate_subtitles.py`)이 촘촘히 튜닝된 누적-합산 방식과
  충돌하기 때문에, 대신 오디오 없는 짧은 세그먼트를 별도로 끼워 넣는 방식을
  택했습니다 — 그 결과 자막 타임라인은 전환 구간만큼 "더하기"만 하면 되고
  (`generate_ass()`의 `transition_duration` 인자), 각 장면 자체의 오디오
  길이는 전혀 바뀌지 않습니다. `build_transition()`은 xfade가 실패해도
  정지 프레임 홀드 → 검정 화면 순으로 폴백해 **항상** 정확히 지정된 길이의
  클립을 반환합니다(호출부의 누적 시간 계산이 조건 분기 없이 단순해지도록).
- **이어붙이기(concat) 길이 검증**: 여러 Ken Burns/전환 클립을 이어붙인 뒤
  ffprobe로 측정한 길이가 (ffmpeg 버전/환경에 따라) 실제 콘텐츠 길이와 크게
  어긋나는 사례가 실제 운영 중 발견됐습니다(755초 분량이 1300초로 잘못
  측정되어 "영상이 길다"고 오판 → 배속을 줄여 오히려 목표(14분30초~15분30초)
  보다 짧은 영상이 만들어짐). `concat()`을 스트림 카피(`-c copy`) 대신
  재인코딩(`+genpts`로 타임스탬프 재생성)으로 바꾸고, `generate_video.py`의
  `resolve_merged_duration()`이 이미 아는 입력값(오디오 총합 + 전환 클립
  수 × 전환 길이)으로 계산한 기대 길이와 ffprobe 측정값을 대조해 20% 넘게
  어긋나면 계산값으로 대체하는 안전장치를 추가했습니다.
- **lower-third**: `html_theme.lower_third()`가 종목명/코드/등락률/섹터를
  하단 바로 표시합니다(`builders._build_stock_summary()`에 통합, 코드는
  `STOCK_CODES`, 섹터는 Phase B의 `get_stock_sector()`를 재사용). 상승=빨강,
  하락=파랑 한국 증권가 관행은 기존 `PALETTE["up"]`/`PALETTE["down"]`을 그대로
  사용합니다.
- **신규 템플릿**: `headline_card()`(시장 요약 헤드라인), `sector_heatmap()`
  (업종 슬라이드, momentum 3단계를 타일 색으로 표현), `report_card()`(증권사
  리포트 카드 — `opinion`/`target_price` 필드는 있을 때만 표시, 없으면
  `BROKERAGE_FIRMS` 사전으로 본문에서 증권사명을 역추출), `risk_card()`
  (리스크 강조 카드).
- **2줄 자동 축소**: `html_theme.autofit_text()`로 만든 요소는 `render.py`가
  스크린샷 직전 Playwright로 실제 렌더링 높이를 측정해 2줄에 맞을 때까지
  폰트 크기를 줄입니다(`-webkit-line-clamp`을 안전망으로 병행 적용).

샘플: `tests/test_video_renderer.py`(실제 ffmpeg로 Ken Burns/전환/이어붙이기
검증, `python tests/test_video_renderer.py`. ffmpeg가 PATH에 없으면 스킵).

## 장전 의사결정형 플롯 (섹션 재정렬)

`generate_reordered_script.py`가 `script.json`을 읽어 아래 8단계 구성 +
컴플라이언스 클로징으로 재정렬한 `reordered_script.json`을 만듭니다.

1. 15초 훅(전체 브리핑에서 importance가 가장 높은 2~3개 이슈 요약)
2. 오늘의 한 줄 결론(시장 요약 헤드라인)
3. 주도주 후보 TOP3(importance 상위 3개 종목)
4. 시장 배경 5. 섹터별 분석 6. 종목별 체크포인트(TOP3에 들지 못한 나머지 종목 + 집계 섹션)
7. 리스크(모든 종목의 risks를 모아 중복 제거) 8. 오늘 장 체크리스트(AI 전략을 조언체 완화해 재구성)
9. 클로징(투자 유의사항 — 8단계엔 없지만 컴플라이언스 문구라 그대로 유지)

- **importance/entities**: 새로 만들지 않고 Phase B의
  `scene_plan.build_scene_plan()`을 그대로 재사용합니다(`priority_score`를
  `importance`로 사용). 이 결과로 `scene_plan.json`도 재정렬된 구조 기준으로
  다시 계산해 덮어씁니다.
- **투자 조언체 완화**: `narrative_reorder.soften_advice_language()`가
  "~확대하세요"/"~매수를 추천합니다" 같은 표현을 "~확인할 필요가 있다"/
  "~관전 포인트다" 식으로 치환합니다. 알려진 패턴 기반 치환이라(완전한 자연어
  재작성에는 LLM이 필요해 이 모듈 스코프 밖) 모든 조언체 표현을 잡아내지는
  못할 수 있습니다. 새로 합성하는 훅/결론/리스크/체크리스트 문구에만
  적용하고, 종목 섹션 원문(narration/subtitle)은 손대지 않습니다 — TTS
  음성이 이미 그 원문 기준으로 생성될 것을 전제하는 narration/subtitle
  문장 수 일치 규칙을 깨지 않기 위해서입니다.
- **기존 렌더링 파이프라인과의 호환성**: 이 모듈은 `script.json`을 읽기만
  하고 절대 수정하지 않습니다(`tests/test_narrative_reorder.py`가 원본
  불변을 검증). `generate_assets.py`/`generate_video.py`는 지금까지와
  동일하게 `script.json`을 그대로 소비하므로 기존 영상 제작 경로는 전혀
  바뀌지 않습니다. `reordered_script.json`을 실제 영상 제작 순서(음성 생성
  ID, 프레임 파일명 규칙 등)에 반영하는 것은 더 큰 범위의 후속 통합
  작업입니다.

샘플: `tests/test_narrative_reorder.py`(8단계 순서, TOP3 선정, importance
일치, 조언체 완화, 원본 불변을 검증. `python tests/test_narrative_reorder.py`).

## 주도주 랭킹형 플롯 (TOP5 + 쇼츠)

`generate_ranking.py`가 script.json에서 오늘의 주도주 TOP5를 선정해
`output/YYYY-MM-DD/ranking/`에 저장합니다: 1) 오늘의 주도주 TOP5 공개
2) 5→1위 빠른 요약(TOP5 overview 카드) 3~6) 순위별 상세(종목 이슈/섹터/
거래대금·수급·뉴스 근거/추격 매수 리스크) 7) 관심종목 체크리스트(각 상세
카드에 이미 포함).

- **companies/themes/volume_score/news_score/report_score**: script.json에는
  이 값들을 직접 나타내는 숫자 필드가 없어 기존 데이터로 근사합니다.
  - `companies`: 종목명(정규화), `themes`: Phase B의 `get_stock_sector()`가
    반환하는 섹터명을 그대로 사용
  - `volume_score`: `chart.py`의 `fetch_ohlcv()`(pykrx→네이버 폴백, 이미
    검증된 소스)로 가져온 최근 OHLCV의 거래량 추세(최근 절반 vs 이전 절반
    평균 비율)를 0~1로 정규화. 데이터가 없으면 중립값 0.5
  - `news_score`/`report_score`: 종목 섹션의 `channel_summaries`에서
    유튜브·경제방송/증권사 카테고리 등장 횟수와 출처 수를 0~1로 정규화
- **ranking_score 산식**: `ranking.compute_ranking_score(volume_score,
  news_score, report_score, weights=(0.4, 0.3, 0.3))`로 별도 함수 분리(요구사항).
  가중치를 인자로 받으므로 산식 자체를 건드리지 않고도 조정/테스트 가능합니다.
- **TOP5 카드**: `ranking_card()`(순위 배지 + 종목명/코드/테마 + 점수
  breakdown 바)로 overview 슬라이드 1장 + 상세 슬라이드 5장을 렌더링합니다
  (`ranking_builders.py`).
- **TOP1~3 쇼츠(30~45초)**: `shorts_export.export_shorts_clip()`이 Phase D의
  `FFmpegVideoRenderer.compose_scene()`(Ken Burns 포함)을 그대로 재사용해,
  해당 종목의 요약 카드 이미지 + 요약 나레이션 오디오로 클립을 만듭니다.
  오디오가 45초보다 길면 앞부분만 잘라 쓰고(별도 요약 없이 도입부만 사용 —
  문장이 중간에 끊길 수 있는 한계가 있음), 45초 이하면 그대로 사용합니다.
  이 스텝은 `voice`/`assets` 잡 산출물(mp3/png)이 이미 있어야 쇼츠를 만들
  수 있으므로, 아직 없으면 경고만 남기고 건너뜁니다(`ranking.json`/카드는
  정상 생성).

설정 필요 없음(가중치는 `compute_ranking_score()` 호출 시 인자로 전달).
샘플: `tests/test_ranking.py`(ranking_score 산식, volume/news/report 점수,
TOP5 선정 + 집계 섹션 제외, 쇼츠 45초 상한 적용을 검증 — OHLCV는
`fetch_ohlcv_fn` 의존성 주입으로 네트워크 없이 테스트. 쇼츠 테스트는 ffmpeg
필요, 없으면 스킵. `python tests/test_ranking.py`).

## 산출물

```
output/KO/scripts/scene_plan.json   # Phase B: 개체명/priority_score/visual_type/visual_keywords
output/KO/scripts/reordered_script.json  # Phase E: 장전 의사결정형 8단계 재정렬 결과
output/KO/media/media_map.json      # Phase C: 섹션별 선택 이미지 경로/출처/사용권
output/KO/...                 # 기존과 동일한 중간 산출물(scripts/audio/frames/subtitles/video)
data/media/license_log.csv    # Phase C: 이미지 사용 이력(7일 중복 감지용, 레포에 커밋 유지)
output/YYYY-MM-DD/
  metadata.json                # 아래 스키마
  final.mp4                    # output/KO/video/final.mp4 사본
  thumbnail.png
  script.json                  # output/KO/scripts/script.json 사본
  scene_plan.json              # Phase D: output/KO/scripts/scene_plan.json 사본(렌더링 결과물과 함께 보관)
  ranking/                     # Phase F: 주도주 랭킹형 플롯
    ranking.json                #   TOP5 companies/themes/volume·news·report_score/ranking_score
    00_ranking_top5.png         #   TOP5 overview 카드
    0N_rank_종목명.png          #   순위별 상세 카드(N=1~5)
    shorts/topN_종목명.mp4      #   TOP1~3, 30~45초 쇼츠(voice/assets 산출물 있을 때만 생성)
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
  "scene_plan_path": "scene_plan.json",
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
python pipeline/generate_reordered_script.py KO   # scene_plan.json을 재정렬 구조 기준으로 재계산
python pipeline/generate_voice.py KO
python pipeline/generate_assets.py KO
MEDIA_MOCK=1 python pipeline/generate_media.py KO   # 실제 검색은 MEDIA_MOCK 없이 실행
python pipeline/generate_ranking.py KO   # TOP1~3 쇼츠는 voice/assets 산출물이 있어야 생성됨
python pipeline/generate_subtitles.py KO
python pipeline/generate_video.py KO
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

테스트(모두 네트워크 없이 실행 가능. `test_video_renderer.py`/`test_ranking.py`의
쇼츠 관련 테스트는 ffmpeg 필요, 없으면 스킵):

```bash
python tests/test_scene_plan.py
python tests/test_media_pipeline.py
python tests/test_video_renderer.py
python tests/test_narrative_reorder.py
python tests/test_ranking.py
python tests/test_generate_video.py
```

## 다음 단계 (이번 범위 아님)

아래는 설계만 논의됐고 이 레포에는 아직 구현되지 않았습니다:

- `reordered_script.json`을 실제 음성 생성/프레임 렌더링 순서에 반영하는 통합 작업
  (현재는 별도 산출물로만 생성되며 기존 영상 제작 경로는 바뀌지 않음)
- TOP1~3 쇼츠의 30~45초 트리밍을 LLM 요약 기반으로 개선(현재는 원본 나레이션의
  도입부만 잘라 써서 문장이 중간에 끊길 수 있음)
- 프리미엄 TTS(Azure/ElevenLabs) + 발음사전 + BGM ducking + loudness normalization

각각은 별도 계획 수립 후 후속 작업으로 진행합니다.
