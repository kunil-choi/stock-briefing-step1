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
(수동) workflow_dispatch → morning_core.yml
  script(script.json → scene_plan.json → reordered_script.json)
    → voice / assets(reordered_script.json 기준 프레임+오디오 생성, assets는 media_map.json도 생성)
    → video → generate_metadata.py → quality_gate.py
```

과금(OpenAI/TTS) 방지를 위해 `stock-briefing-v3-1`의 자동 dispatch를 제거했습니다.
`stock-briefing-v3-1`의 `docs/index.html`로 데이터가 준비됐는지 사람이 먼저 확인한
뒤, 이 레포 Actions 탭에서 수동으로 `workflow_dispatch`를 실행하세요. 자체 cron도
없습니다.

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
| `pipeline/assets/video_renderer.py` | 정지 화면(기본)/Ken Burns(`ENABLE_KEN_BURNS=true`) + crossfade/push 전환 `VideoRenderer` 인터페이스/구현체 (Phase D, 아래 참고) |
| `pipeline/assets/html_theme.py`의 `lower_third()`/`headline_card()`/`report_card()`/`risk_card()`/`sector_heatmap()`/`autofit_text()` | 방송형 컴포넌트 + 2줄 자동 축소 텍스트 (Phase D, 추가된 함수) |
| `pipeline/assets/render.py`의 autofit 스크린샷 전처리 | `data-autofit` 요소를 실측해 폰트 크기 자동 축소 (Phase D, 추가된 로직) |
| `pipeline/generate_video.py` / `generate_subtitles.py` | 정지 프레임 홀드 → 정지 화면/전환 클립으로 교체, 전환 구간만큼 자막 타임라인 보정, `TARGET_MIN/MAX`를 `config/schedule.yml`에서 로드 (Phase D, 변경) |
| `pipeline/assets/narrative_reorder.py` / `pipeline/generate_reordered_script.py` | "종목 언급 중심" 플롯(훅→채널언급인트로→주요지표→대형주도주→관심종목→AI히든픽→클로징, 5~9분)으로 섹션 재정렬 + `reordered_script.json` 생성 — **실제 음성/영상 생성 파이프라인의 입력으로 사용됨** (Phase E, 아래 참고) |
| `pipeline/assets/builders.py`의 `build_hook()`/`build_conclusion()` | 훅/결론 슬라이드 렌더링(추가된 함수) |
| `pipeline/generate_assets.py` | 고정 순서 렌더링 → `reordered_script.json`의 섹션 순서를 그대로 따라가는 동적 디스패치로 교체 (변경) |
| `pipeline/assets/ranking.py` / `ranking_builders.py` / `shorts_export.py` / `pipeline/generate_ranking.py` | "주도주 랭킹형" 플롯 — TOP5 산정 + 카드 + TOP1~3 쇼츠 export (Phase F, 아래 참고) |
| `pipeline/assets/tts_providers.py` / `config/audio.yml` / `config/pronunciation_ko.yml` / `pipeline/config_audio.py` | 프리미엄 TTS provider 폴백 체인(Azure→ElevenLabs→OpenAI) + 발음 교정 사전 (Phase H, 아래 참고) |
| `pipeline/assets/audio_post.py` | atempo/loudnorm 후처리 + BGM 사이드체인 덕킹 + 과장 표현 탐지 (Phase H, 아래 참고) |
| `pipeline/generate_voice.py` | OpenAI 단일 호출 → provider 폴백 체인 + loudnorm 후처리 + `audio_report.json` 생성으로 교체 (Phase H, 변경) |
| `pipeline/generate_video.py`의 `compute_bgm_bounds()` / BGM 믹싱 단계 | 상수 볼륨 `amix` → intro/body/outro 구간별 볼륨 + 사이드체인 덕킹으로 교체 (Phase H, 변경) |

그 외 `generate_assets.py`/`build_asset_map.py`/
`pipeline/assets/{chart,image_fetch}.py`/`update_voice_id.py`는
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

### AssetSearchService / asset_manifest.json / 권리 검수 (2차 작업)

`pipeline/assets/asset_search_service.py`의 `AssetSearchService`가 `generate_media.py`의
실제 진입점입니다. 기존 `media_pipeline.build_scene_images()`(스코어링/중복방지)를
그대로 재사용하면서, 커넥터 인스턴스화(`config/media.yml`의 `providers` 목록 +
환경변수 존재 여부로 자동 활성/비활성 결정)와 `asset_manifest.json` 생성을 감쌉니다.

- **커넥터 확장**(`pipeline/assets/media_providers.py`): 기존 `YonhapProvider`/`KbsProvider`/
  `MockProvider`에 더해 `KbsInternalConnector`/`KbsBadaConnector`/`PublicAgencyConnector`/
  `OfficialCompanyConnector`(필요한 API 키/내부 접근 정보가 없으면 항상 빈 리스트를
  반환하는 비활성 스켈레톤), `StockPhotoConnector`(Pexels, `PEXELS_API_KEY` 있으면 실제
  동작), `NaverDiscoveryConnector`(네이버 오픈API로 KBS/연합뉴스 원문 URL만 찾는
  discovery 전용 — **이미지를 직접 다운로드하지 않으며 항상 검수 대상**)를 추가했습니다.
  각 커넥터는 `asset_source` 클래스 속성으로 `scene_plan.json`의 `preferredSources`
  8종 표준값(`KBS_INTERNAL`/`KBS_BADA`/`KBS_WEBSITE`/`YONHAP`/`NAVER_DISCOVERY`/
  `PUBLIC_AGENCY`/`OFFICIAL_COMPANY`/`STOCK`/`GENERATED_ABSTRACT`)과 일치시킵니다.
- **권리 분류**(`pipeline/assets/rights_review.py`의 `classify_rights()`): 후보마다
  `rightsStatus`/`needsReview`를 판정합니다. 네이버 discovery와 외신(URL 휴리스틱)은
  예외 없이 항상 검수 대상이지만, 지금처럼 API 키 없이 공개 검색 페이지를 스크래핑하는
  연합뉴스/KBS(`YONHAP`/`KBS_WEBSITE`)는 **기존 동작을 유지**해 `editorial_search`도
  자동 사용 가능(`needsReview=False`)으로 둡니다(실제 이미지 사용량이 줄지 않도록
  하기 위한 의도적 결정).
- **1차 산출물과의 연결**: `build_scene_images()`가 이제 `visual_keywords`(한국어)
  뿐 아니라 `visualKeywordsEn`(영어, 스톡 이미지 검색용), `preferredSources`(이
  순서로 커넥터 우선순위 정렬), `needsDataReview`/`assetRequirements.allowStockFallback`
  (오염 의심 종목명은 한국어로 KBS/연합뉴스 검색을 하지 않고 영어 키워드로만
  스톡/추상 그래픽을 찾음)를 함께 소비합니다.
- **asset_manifest.json**: `output/{lang}/media/asset_manifest.json`에 검토된 모든
  후보(선택된 것 포함)를 `assetId`/`sceneId`/`source`/`credit`/`sourceUrl`/`localPath`/
  `rightsStatus`/`needsReview`/`selected` 등과 함께 기록합니다. `media_map.json`은
  하위호환을 위해 그대로 유지됩니다.
- **다운로드 캐시**: `ASSET_CACHE_DIR`(기본 `assets/cache/`) 아래 `{source}/{source}_{url해시}.jpg`로
  저장해 같은 URL을 재실행마다 다시 받지 않습니다.
- **환경변수**: `.env.example` 참고. 실제 키가 없으면 관련 커넥터는 안전하게 비활성화됩니다.
- **아직 하지 않은 것**: KBS 내부망/KBS 바다/연합뉴스 정식 계약/네이버 오픈API의 실제
  인증·응답 파싱(이 세션에 접근 권한 없음), `builders.py`(렌더링)가 `media_map.json`/
  `asset_manifest.json`을 실제로 읽어 화면에 쓰는 것(3차 작업 범위).

샘플: `tests/test_asset_search_service.py`(권리 분류 규칙, 신규 커넥터 비활성 확인,
캐시 재사용, `AssetSearchService` end-to-end, 전부 오프라인 mock 기반).

## 방송형 렌더링 (Ken Burns / 전환 / lower-third / 자동 텍스트 축소)

기존 `generate_video.py`는 PNG 슬라이드를 `-loop 1`로 그대로 정지 홀드해
"PPT를 넘기는" 느낌이었습니다. Phase D는 이를 방송 그래픽처럼 항상 미세하게
움직이는 화면으로 바꿉니다.

- **renderer interface 분리**: `pipeline/assets/video_renderer.py`의
  `VideoRenderer`(추상클래스, `compose_scene`/`build_transition`/`concat`)를
  `FFmpegVideoRenderer`가 구현합니다. 추후 Remotion 등으로 교체하려면 이
  인터페이스를 만족하는 새 클래스만 추가하면 되고, `generate_video.py` 등
  호출부는 그대로 둘 수 있습니다.
- **Ken Burns(기본 꺼짐)**: `compose_scene()`이 ffmpeg `zoompan` 필터로 각
  장면을 서서히 확대(최대 1.08배)하는 기능이 있지만, 이미지 소스가 연합뉴스/
  KBS 정식 API가 아니라 텍스트가 박힌 카드형 이미지 위주라 확대·팬 중 중요한
  텍스트가 화면 밖으로 밀려나는 역효과가 있었습니다(실사용 피드백). 그래서
  `video_renderer.ENABLE_KEN_BURNS`(기본 `false`, `ENABLE_KEN_BURNS=true`
  환경변수로 켤 수 있음)로 기본은 정지 화면(`scale+pad`로 원본 비율 유지)만
  쓰도록 껐습니다. Yonhap/KBS 정식 이미지를 안정적으로 확보하게 되면
  다시 켤 수 있도록 zoompan 경로 자체는 그대로 남겨뒀습니다.
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
- **이어붙이기(concat) 길이 검증**: 여러 장면/전환 클립을 이어붙인 뒤
  ffprobe로 측정한 길이가 (ffmpeg 버전/환경에 따라) 실제 콘텐츠 길이와 크게
  어긋나는 사례가 실제 운영 중 발견됐습니다(755초 분량이 1300초로 잘못
  측정되어 "영상이 길다"고 오판 → 배속을 줄여 오히려 목표보다 짧은 영상이
  만들어짐). `concat()`을 스트림 카피(`-c copy`) 대신
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

샘플: `tests/test_video_renderer.py`(실제 ffmpeg로 정지 화면 합성(기본값)/
`ENABLE_KEN_BURNS=true`일 때의 zoompan 경로/전환/이어붙이기 검증,
`python tests/test_video_renderer.py`. ffmpeg가 PATH에 없으면 스킵).

### scene_plan.json / media_map.json을 실제 화면에 연결 (3차 작업)

1·2차 작업은 `scene_plan.json`(압축된 화면 텍스트)과 `media_map.json`(선택된
이미지)을 만들었지만, 실제 렌더링(`builders.py`)은 그 어느 것도 읽지 않고
`reordered_script.json` 원본 문장만 그대로 화면에 썼습니다. 3차 작업은 이
연결을 만듭니다.

- **`generate_assets.py`**가 `reordered_script.json`뿐 아니라 `scene_plan.json`/
  `media_map.json`도 로드해 섹션 id로 조인한 `visual` dict(`screenText`/
  `image_path`/`needsDataReview`/`safeDisplayName` 등)를 각 빌더에 전달합니다
  (`_resolve_visual()`). 두 파일이 없거나(1·2차를 안 거쳤거나 실패한 경우)
  섹션이 매칭되지 않으면 빈 값으로 채워져 빌더가 기존 폴백 경로(원본 문장/
  이미지 없음)로 자연스럽게 동작합니다 — 회귀 없음.
- **배경 이미지 + 사진 위 텍스트**: `html_theme.background_layer()`가 전체화면
  배경 이미지와 아래로 갈수록 어두워지는 그라디언트 오버레이를 만듭니다.
  이 코드베이스는 카드/텍스트를 대부분 인라인 style로 작성해 CSS 클래스로
  일괄 색상 오버라이드가 어려우므로, "글자 색을 바꾸는" 대신
  `text_plate()`(반투명 다크 판)로 헤드라인을 감싸 사진의 명암과 무관하게
  항상 대비를 보장합니다. 흰 카드(`class="card"`)류 컴포넌트는 이미
  불투명해 배경 사진 위에서도 별도 처리 없이 안전합니다. 배경 사진이 있으면
  기본 흰색 상단바도 반투명 다크 톤으로 전환해 사진과 한 화면처럼 보이게
  합니다. 적용 대상: `build_hook`(오프닝)/`_build_stock_summary`/
  `build_sector`/`build_market_summary`.
- **오프닝(`build_hook`) 재구성**: 배경 사진이 있으면 `screenText`(예: "AI
  반도체 급락" / "오늘 시장의 방향은?")를 큰 흰 헤드라인으로, 없으면 기존
  원형 그라디언트 폴백을 그대로 씁니다. 오늘의 핵심 이슈 키워드 3개를 칩으로
  추가했습니다. 이 파이프라인은 1개 장면=1개 정지 이미지+1개 오디오
  구간이라(`video_renderer.py`), 오프닝 안에서 "0~1.5초/1.5~4.5초/4.5~8초"
  식 여러 타이밍 비트를 넣는 멀티 비트 애니메이션은 이번 범위가 아닙니다
  (`generate_video.py`의 프레임-오디오 페어링 구조 자체를 바꿔야 함).
- **화면 텍스트 압축 적용**: `corner_summary`/`subtitle` 원문 대신
  `scene_plan.json`의 `screenText`(최대 2줄, 1차 작업의 규칙 기반 압축
  결과)를 우선 사용합니다. `screenText`가 없으면 기존 원문으로 폴백합니다.
- **오염 종목명 안전장치를 화면에 실제 적용**: `needsDataReview=true`
  섹션은 원래 종목명 대신 `safeDisplayName`("관심 종목")을 제목/lower-third에
  표시하고, 그 이름으로 로고를 검색하는 것도(무의미하므로) 건너뜁니다.
- **하단 뉴스 티커**: `html_theme.news_ticker()`. `set_briefing_date()`와
  동일한 전역 상태 패턴(`set_ticker_text()`)으로 구현해 `shell()` 기반
  빌더 전체가 시그니처 변경 없이 자동으로 티커를 받습니다. 이 파이프라인은
  DOM을 정지 스크린샷으로 뜨는 방식(PNG 1장, video 아님)이라 CSS marquee
  애니메이션은 캡처 시점의 임의 프레임만 찍혀 의미가 없어, 스크롤 대신 고정
  텍스트로 표시합니다. `lower_third()`가 이미 `.content` 하단을 차지하는
  종목 카드류는 `suppress_ticker=True`로 겹침을 피합니다. 티커 문구는
  `scene_plan.json`의 `priority_score` 상위 섹션 키워드를 모아 자동 생성하고,
  색조는 `market_summary`의 `dataOverlay.marketMood`를 따릅니다.
- **`review-checklist.md`**(`pipeline/generate_review_checklist.py`):
  렌더링 전 자동 판정 가능한 항목(오프닝 screenText 유무, 2줄 초과 섹션,
  `needsReview`인데 `selected`된 자산이 있는지, 오염 종목명 목록, 외신 자산
  목록)을 정리한 체크리스트를 `output/{lang}/review-checklist.md`로 생성.

이번 범위에서 하지 않은 것: 섹터 타일 하나하나에 개별 이미지를 붙이는 것
(`media_map.json`이 섹션 단위 이미지 1장만 제공), Ken Burns를 오프닝에만
선택 적용하는 것(전역 스위치라 장면별 차등 적용은 별도 작업), `html_theme.py`
전체를 다크 금융뉴스 테마로 재작성하는 것(1차 결정대로 기존 라이트 테마 유지).

샘플: `tests/test_builders_visual.py`(배경 이미지 유무/screenText 우선순위/
티커 전역상태/`_resolve_visual` 조인 검증), `tests/test_review_checklist.py`.

## 종목 언급 중심 플롯 (섹션 재정렬 — 실제 영상 제작에 반영됨)

`generate_reordered_script.py`가 `script.json`을 읽어 재정렬한
`reordered_script.json`을 만들고, **`generate_voice.py`/`generate_assets.py`/
`generate_video.py`/`generate_subtitles.py`/`quality_gate.py`가 전부 이
파일을 실제 입력으로 사용합니다** — 재정렬이 최종 영상에 실제로 반영되는
지점이 여기입니다(과거 버전은 이 파일을 생성만 하고 아무도 읽지 않아서,
재정렬이 완전히 무시되는 상태였습니다 — 실사용 중 발견된 버그).

`narrative_reorder.build_mention_briefing()`이 실제 프로덕션 구성을 만듭니다.
개장 전(07:10~08:20 KST) 방송이라 시장 요약/전망에 쓸 수 있는 데이터가 전부
전일 종가·오늘 새벽 마감된 미국 시장 자료뿐이라 해석성 "시장 해설"이
시의성에 안 맞는다는 판단 하에, v3-1의 핵심 데이터인 "지난 24시간 채널
언급 종목 정리"에 집중합니다:

1. 15초 훅(고정 시그니처 오프닝 멘트 + 종목 섹션 중 importance가 가장 높은
   2~3개 요약 — 시그니처 멘트는 `narrative_reorder.OPENING_HOOK_LINE`에
   호기심 유발형 질문으로 고정돼 있어 매일 동일하게 재생된다. 그 뒤에 이어지는
   요약만 날마다 달라진다)
2. 채널 언급 인트로(고정 — `narrative_reorder.MENTION_INTRO_LINE`. "오늘의
   한 줄 결론" 자리를 대체하며, 시장 방향 해설 대신 이 영상의 핵심을 그대로
   알린다)
3. 주요 지표(market_data가 있을 때만 — 코스피/코스닥/나스닥/S&P500/환율을
   해석·전망 없이 코드에서 직접 "~마감했습니다" 문장으로 낭독한다. LLM
   해설을 거치지 않으므로 "상승세"류 진행형 표현이 섞일 여지가 없다)
4. 대형 주도주(`market_leaders`, 보통 2개 — 첫 종목 앞에 고정 전환 멘트
   "우선 시장을 이끌고 있는 대형 주도주 상황 살펴보겠습니다.")
5. 관심종목(`top_stocks` 개별 상세 + `stock_추가관심종목` 집계 슬라이드 —
   첫 항목 앞에 고정 전환 멘트 "인기 유튜브 채널에서 언급된 관심종목에 대해
   분석해보겠습니다.")
6. AI 히든픽(`stock_오늘의픽`이 있을 때만 — 고정 전환 멘트 "AI가 선정한
   오늘의 히든픽 종목은 무엇인지 알아보겠습니다.")
7. 클로징(투자 유의사항 + `generate_script.py`의 `CLOSING_NARRATION`에 고정된
   "10시 report_update 영상 예고" 프로모 문구)

시장배경 해설(corner_summary/points)·섹터분석·AI 투자전략·리스크 다이제스트는
이 구성에서 전부 제외됩니다. 대형 주도주/관심종목 그룹 분리는 importance
재랭킹이 아니라 `generate_script.py`가 종목 섹션마다 심어두는 `stock_tier`
필드("market_leader"|"top_stock")를 신뢰합니다(예전 TOP3 재랭킹 방식은
`market_leaders`로 분류된 종목이 재랭킹에서 밀려 "대형 주도주" 그룹에 못
들어갈 수 있는 문제가 있었습니다). `stock_tier`가 없는 과거 `script.json`은
원본 순서의 앞 2개를 대형 주도주로 추정하는 폴백이 있습니다.

목표 길이는 `config/schedule.yml`의 `duration.longform`(현재 5~9분 —
시장배경/섹터분석/AI전략이 빠지면서 기존 9~11분보다 짧아질 것으로 예상해
낮춘 잠정치이며, 실제 생성물 길이를 보고 재조정이 필요할 수 있습니다)이며,
`generate_video.py`의 `TARGET_MIN`/`TARGET_MAX`/`TARGET_IDEAL`이 이 값을
그대로 읽습니다(예전엔 여기에 하드코딩된 15분짜리 값이 schedule.yml과
별개로 존재해서, schedule.yml을 바꿔도 실제 영상 길이는 그대로 15분이
나오는 불일치가 있었습니다 — 역시 실사용 중 발견된 버그).

기존 "장전 의사결정형" 8단계 롱폼/하이라이트 구성(`narrative_reorder.
reorder_sections()`, `short_form` 인자 포함 — 훅→결론→TOP3→시장배경→
섹터분석→체크포인트→리스크→체크리스트→클로징)은 코드와 테스트
(`tests/test_narrative_reorder.py`) 모두 그대로 남아 있습니다. 이 레포의
실제 진입점(`generate_reordered_script.py`)은 더 이상 이 함수를 호출하지
않지만, 포맷을 다시 늘리고 싶을 때는 진입점의 호출만 `build_mention_briefing()`
에서 `reorder_sections()`로 바꾸면 됩니다. `generate_assets.py`가 참조하는
`build_sector`/`build_ai_strategy` 빌더들도 `builders.py`에 그대로 남아
있습니다(현재는 미사용).

- **importance/entities**: 새로 만들지 않고 Phase B의
  `scene_plan.build_scene_plan()`을 그대로 재사용합니다(`priority_score`를
  `importance`로 사용). 이 결과로 `scene_plan.json`도 재정렬된 구조 기준으로
  다시 계산해 덮어씁니다.
- **투자 조언체 완화**: `narrative_reorder.soften_advice_language()`가
  "~확대하세요"/"~매수를 추천합니다" 같은 표현을 "~확인할 필요가 있다"/
  "~관전 포인트다" 식으로 치환합니다. 알려진 패턴 기반 치환이라(완전한 자연어
  재작성에는 LLM이 필요해 이 모듈 스코프 밖) 모든 조언체 표현을 잡아내지는
  못할 수 있습니다. 종목 섹션 원문(narration/subtitle)은 손대지 않습니다 —
  TTS 음성이 이미 그 원문 기준으로 생성될 것을 전제하는 narration/subtitle
  문장 수 일치 규칙을 깨지 않기 위해서입니다.
- **`generate_metadata.py`는 여전히 원본 `script.json`을 읽습니다** —
  YouTube 제목/설명/태그는 그날 전체 시장 내용을 요약해야 하므로, 영상에서
  빠진 종목이 있어도 원본 기준으로 생성합니다.
- **`script.json` 자체는 절대 수정되지 않습니다**(`tests/test_mention_briefing.py`가
  원본 불변을 검증) — `build_mention_briefing()`은 항상 새 dict를 반환합니다.
- **한계**: `generate_ranking.py`(TOP5 랭킹형 플롯)는 독립적인 산정 기준
  (거래대금/뉴스/리포트 언급)으로 자체 TOP5를 계산하는데, 이 TOP5가 영상의
  대형 주도주+관심종목(개별 상세 종목)과 겹치지 않으면 그 종목의 프레임/오디오가
  애초에 생성되지 않아 TOP1~3 쇼츠 export가 건너뛰어질 수 있습니다(오류 없이
  경고 로그만 남김 — `generate_ranking.py`의 `_find_summary_frame()` 참고).

샘플: `tests/test_mention_briefing.py`(섹션 구성/제외, 고정 인트로 문구,
주요 지표 결정적 생성, 대형 주도주/관심종목/히든픽 전환 멘트, stock_tier
폴백, 원본 불변을 검증), `tests/test_narrative_reorder.py`(기존 8단계
구성은 계속 정상 동작함을 검증), `tests/test_generate_subtitles.py`
(00_hook/01_conclusion 프레임→오디오ID 매핑, generate_video.py가 중복
구현 없이 재사용하는지 검증), `tests/test_generate_video.py`(TARGET_MIN/MAX가
config/schedule.yml을
실제로 읽는지 검증). `python tests/test_mention_briefing.py`,
`python tests/test_narrative_reorder.py`.

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
  `FFmpegVideoRenderer.compose_scene()`을 그대로 재사용해(`ENABLE_KEN_BURNS`
  설정을 그대로 따름 — 기본은 정지 화면), 해당 종목의 요약 카드 이미지 +
  요약 나레이션 오디오로 클립을 만듭니다.
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

## 프리미엄 TTS 파이프라인 (provider 폴백 + 후처리)

`generate_voice.py`가 더 이상 OpenAI TTS를 직접 호출하지 않고,
`config/audio.yml`의 `provider_priority`(기본 `azure → elevenlabs → openai`)
순서로 provider를 시도합니다. Azure/ElevenLabs Secret이 없으면 자동으로
건너뛰어 결국 OpenAI로 폴백하므로, 이 레포는 현재 실제로는 항상 OpenAI로
동작합니다 — Secret이 등록되는 순간 코드 변경 없이 우선순위대로 켜집니다
(Phase C의 `YonhapProvider`/`KbsProvider`와 동일한 설계 패턴).

- **TTSProvider 인터페이스** (`pipeline/assets/tts_providers.py`):
  `is_configured()`/`synthesize()`만 있는 추상클래스. `OpenAITTSProvider`(기존
  `text_to_speech()` 로직 이관), `AzureTTSProvider`(Speech REST API, SSML로
  `speaking_rate`/`pitch` 조절), `ElevenLabsProvider`(REST API, 이 레포에
  이미 있었지만 쓰이지 않던 `voice_config.py`의 `MODEL_ID`/`VOICE_SETTINGS`/
  `get_voice_id()`를 재사용)가 구현체입니다. `synthesize_with_fallback()`이
  우선순위 순서대로 시도해 첫 성공 provider를 사용합니다.
- **발음 교정 사전 데이터 파일화**: 기존 `voice_config.py`에 파이썬 리스트로
  하드코딩돼 있던 62개 발음 교정 규칙을 `config/pronunciation_ko.yml`로
  옮겼습니다(개발자가 아니어도 이 파일만 고치면 발음이 바뀌도록). `voice_config.
  apply_phoneme_rules()`는 하위 호환을 위해 남겨두고 `config_audio.
  apply_pronunciation_rules()`에 위임합니다 — 두 함수는 바이트 단위로 동일하게
  동작함을 테스트로 확인했습니다. subtitle(화면 자막)에는 절대 적용하지
  않습니다.
- **후처리** (`pipeline/assets/audio_post.py`): 합성된 mp3마다 ffmpeg
  `loudnorm`으로 방송 표준 음량(기본 -16 LUFS, `config/audio.yml`의
  `loudness`)에 맞춥니다. `apply_post_processing()`은 `speed` 인자도 받아
  ffmpeg `atempo`(0.5~2.0배 범위 제한을 체인으로 우회)를 함께 적용할 수 있게
  만들어져 있지만, 현재 `generate_voice.py`는 `speed=1.0`(loudnorm만)으로
  호출합니다 — 영상 전체 배속 조정은 지금까지처럼
  `generate_video.adjust_to_target_duration()`이 최종 병합 영상 단위로
  담당합니다(개별 나레이션 단위로 옮기면 15분 타겟을 계산하기 전에 배속을
  정해야 하는 순환 의존성이 생김).
- **BGM 사이드체인 덕킹**: `mix_bgm_with_ducking()`이 ffmpeg
  `sidechaincompress`로 나레이션이 나올 때 BGM 볼륨을 자동으로 낮추고,
  intro/body/outro 구간별로 기본 볼륨을 다르게 적용합니다(`config/audio.yml`의
  `bgm`). `generate_video.py`의 `compute_bgm_bounds()`가 첫 장면(intro)이
  끝나는 시점과 마지막 장면(outro)이 시작하는 시점을 `frame_audio_pairs`의
  실제 오디오 길이 + 전환 클립 수로 계산하고, 배속 조정이 적용됐다면 자막과
  동일한 `time_scale`(`1/speed_factor`)로 축소해 최종 타임라인 기준 시각을
  맞춥니다. 기존 상수 볼륨 `amix` 방식은 제거했습니다.
- **과장 투자 권유 표현 탐지**: `detect_advice_language()`가 Phase E의
  `narrative_reorder._ADVICE_PATTERNS`(치환용 패턴)를 재사용하되, 여기서는
  원문을 바꾸지 않고 매치된 문구를 경고 목록으로만 남깁니다(요구사항: "과장
  표현은 바꾸지 말고 별도 warnings 로그에 표시" — Phase E가 새로 합성하는
  훅/결론/체크리스트 문구를 치환하는 것과는 다른 처리).
- **`output/KO/audio_report.json`**: 섹션별 `id`/`provider`/
  `duration_seconds`/`speed`/`loudness_lufs`/`warnings`(과장 표현 목록)와
  전체 `providers_used`/`total_advice_language_warnings`를 기록합니다.
  `generate_metadata.py`가 Phase D의 `scene_plan.json`과 동일한 방식으로
  `output/YYYY-MM-DD/audio_report.json`에 사본을 남기고 `metadata.json`의
  `audio_report_path` 필드에 경로를 채웁니다.

설정: `config/audio.yml`(provider 우선순위/설정, atempo 허용 범위, loudness
목표, BGM 구간별 볼륨/덕킹 파라미터), `config/pronunciation_ko.yml`(발음
교정 규칙).
샘플: `tests/test_audio_post.py`(atempo+loudnorm 실측치 검증, BGM 덕킹 믹싱
결과물 검증, 과장 표현 탐지, `audio_report.json` 구조 — 실제 ffmpeg 호출,
없으면 순수 로직 테스트만 실행), `tests/test_generate_video.py`의
`compute_bgm_bounds()` 테스트(순수 계산, ffmpeg 불필요).

## 산출물

```
output/KO/scripts/scene_plan.json   # Phase B: 개체명/priority_score/visual_type/visual_keywords
output/KO/scripts/reordered_script.json  # Phase E: 종목 언급 중심 재정렬 결과(훅→채널언급인트로→주요지표→대형주도주→관심종목→AI히든픽→클로징) — voice/assets/video/subtitles/quality_gate가 실제로 이 파일을 읽음
output/KO/media/media_map.json      # Phase C: 섹션별 선택 이미지 경로/출처/사용권
output/KO/audio_report.json         # Phase H: TTS provider/실측 음량/과장 표현 경고 리포트
output/KO/...                 # 기존과 동일한 중간 산출물(scripts/audio/frames/subtitles/video)
data/media/license_log.csv    # Phase C: 이미지 사용 이력(7일 중복 감지용, 레포에 커밋 유지)
output/YYYY-MM-DD/
  metadata.json                # 아래 스키마
  final.mp4                    # output/KO/video/final.mp4 사본
  thumbnail.png
  script.json                  # output/KO/scripts/script.json 사본
  scene_plan.json              # Phase D: output/KO/scripts/scene_plan.json 사본(렌더링 결과물과 함께 보관)
  audio_report.json            # Phase H: output/KO/audio_report.json 사본
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
  "audio_report_path": "audio_report.json",
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
| `OPENAI_API_KEY` | 스크립트 생성 + TTS 폴백(다른 provider가 없거나 실패하면 최종적으로 사용) | 필수 |
| `YONHAP_API_KEY` | 연합뉴스 이미지 검색 인증(정식 계약 API 연결 시) | 선택 — 없으면 공개 검색 경로로 자동 폴백 |
| `KBS_API_KEY` | KBS 뉴스 이미지 검색 인증(정식 계약 API 연결 시) | 선택 — 없으면 공개 검색 경로로 자동 폴백 |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | Azure TTS(`config/audio.yml`의 `provider_priority` 1순위) | 선택 — 없으면 다음 provider로 자동 폴백 |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | ElevenLabs TTS(2순위, `VOICE_ID`가 없으면 `voice_config.py`의 프리셋/기본값 사용) | 선택 — 없으면 다음 provider로 자동 폴백 |

## 환경변수 (.env, 로컬 실행용)

`YONHAP_API_KEY`/`KBS_API_KEY`/`AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION`/
`ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`는 로컬에서는 `.env`
(`python-dotenv`로 로드하거나 `export`)로 넣을 수 있습니다. `MEDIA_MOCK=1`을
설정하면 `generate_media.py`가 네트워크 요청 없이 `MockProvider`만
사용합니다(오프라인 테스트/CI 드라이런용).

- `SCRIPT_MOCK=1`: `generate_script.py`가 OpenAI를 호출하지 않고, V3_1 원문의
  실제 종목 분류(대형 주도주/관심 종목/오늘의 픽)는 유지한 채 narration/summary
  등 텍스트만 `[MOCK]` 더미로 채운 script.json을 만듭니다.
- `TTS_MOCK=1`: `generate_voice.py`가 실제 TTS provider 대신 텍스트 길이에
  비례한 무음에 가까운 톤 mp3를 ffmpeg로 생성합니다.

두 플래그를 `MEDIA_MOCK=1`과 함께 켜면(`SCRIPT_MOCK=1 TTS_MOCK=1 MEDIA_MOCK=1`)
OpenAI/TTS 비용 없이 재정렬→에셋→미디어→랭킹→자막→영상→메타데이터→
quality_gate까지 파이프라인 전체를 로컬에서 검증할 수 있습니다. GitHub
Actions에서는 `morning_core.yml`의 workflow_dispatch에 있는 **"드라이런
모드" 체크박스**로 동일하게 실행할 수 있습니다(이 경우 `data/media/
license_log.csv` 커밋도 건너뜁니다 — mock 항목으로 실제 중복 감지 로그가
오염되지 않도록).

- `BGM_URL`: `assets/music/bgm.mp3`가 이미 레포에 커밋돼 있어(`stock-briefing-video`와
  동일 음원) 별도 설정 없이 바로 BGM이 적용됩니다. 다른 음원으로 바꾸고
  싶을 때만 이 값을 설정하세요(파일이 이미 있으면 `download_bgm()`이
  캐시로 보고 건너뛰므로, 교체하려면 `assets/music/bgm.mp3`를 먼저
  지우거나 직접 덮어써야 합니다).
- `ENABLE_KEN_BURNS`: 기본 `false`(정지 화면). `true`로 설정하면
  `compose_scene()`이 다시 zoompan 확대/팬 효과를 적용합니다 — 이미지
  소스가 텍스트 카드 위주인 지금은 콘텐츠가 화면 밖으로 밀려나는 역효과가
  있어 기본으로는 꺼져 있습니다.

실행 예시(Azure TTS를 우선 사용하고 싶을 때):

```bash
export OPENAI_API_KEY=sk-...
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=koreacentral
python pipeline/generate_voice.py KO   # config/audio.yml의 provider_priority 순서(기본 azure 1순위)대로 자동 선택
```

## 로컬 실행

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python pipeline/generate_script.py KO
python pipeline/generate_scene_plan.py KO
python pipeline/generate_reordered_script.py KO   # reordered_script.json — 아래 voice/assets/video/subtitles/quality_gate가 전부 이 파일을 읽음
python pipeline/generate_voice.py KO
python pipeline/generate_assets.py KO
MEDIA_MOCK=1 python pipeline/generate_media.py KO   # 실제 검색은 MEDIA_MOCK 없이 실행
python pipeline/generate_ranking.py KO   # TOP1~3 쇼츠는 voice/assets 산출물이 있어야 생성됨(영상 TOP3와 겹칠 때만)
python pipeline/generate_subtitles.py KO
python pipeline/generate_video.py KO
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

테스트(모두 네트워크 없이 실행 가능. `test_video_renderer.py`/`test_ranking.py`/
`test_audio_post.py`의 ffmpeg 관련 테스트는 ffmpeg 필요, 없으면 스킵):

```bash
python tests/test_scene_plan.py
python tests/test_media_pipeline.py
python tests/test_video_renderer.py
python tests/test_mention_briefing.py
python tests/test_narrative_reorder.py
python tests/test_generate_subtitles.py
python tests/test_ranking.py
python tests/test_generate_video.py
python tests/test_audio_post.py
```

## 다음 단계 (이번 범위 아님)

아래는 설계만 논의됐고 이 레포에는 아직 구현되지 않았습니다:

- TOP1~3 쇼츠의 30~45초 트리밍을 LLM 요약 기반으로 개선(현재는 원본 나레이션의
  도입부만 잘라 써서 문장이 중간에 끊길 수 있음)
- `generate_ranking.py`의 TOP5 산정 기준(거래대금/뉴스/리포트 언급)과
  `narrative_reorder.py`의 영상 TOP3 산정 기준(importance/개체명 밀도)이
  서로 달라, 두 TOP-N이 겹치지 않으면 TOP1~3 쇼츠 export가 건너뛰어질 수
  있음(오류는 아니지만 두 기준을 통일하거나 영상 TOP3 외 종목도 프레임/오디오를
  만들도록 확장하는 후속 작업이 필요)
- Ken Burns(`ENABLE_KEN_BURNS=true`)를 연합뉴스/KBS 정식 이미지(API 계약)
  확보 후 다시 켜고, 여백이 넉넉한 보도사진에 맞춰 팬 범위를 재조정하는 작업
- Phase H(프리미엄 TTS 파이프라인)를 `stock-briefing-step2`(report_update)에도
  동일하게 적용하는 작업(이 레포에서 먼저 구현 후 이식 예정)

각각은 별도 계획 수립 후 후속 작업으로 진행합니다.
