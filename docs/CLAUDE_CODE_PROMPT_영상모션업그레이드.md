# 작업 지시: stock-briefing-step1 영상 모션그래픽 업그레이드 (Phase 0~2)

## 배경

이 레포는 KBS 머니올라의 일일 주식 브리핑 영상을 자동 생성한다. 나레이션(TTS)과 원고 품질은
만족스러우나, **영상이 사실상 "PPT 캡처 슬라이드쇼"** 라서 시청 경험이 나쁘다. 원인은 코드에서
확인되었다:

- `pipeline/assets/render.py` — HTML을 `page.screenshot()`으로 **정지 PNG 1장**만 렌더링
- `pipeline/assets/video_renderer.py` — `ENABLE_KEN_BURNS` 기본값이 `false`라서
  `compose_scene()`이 만드는 클립은 **나레이션 15~30초 동안 완전 정지 화면**
- 같은 파일 — `_TRANSITION_CYCLE = ["slideleft"]` 하나뿐이라 화면 변화는 장면 사이 0.4초가 전부
- `pipeline/assets/chart.py` — 차트도 matplotlib 정지 PNG

**해결 방향은 생성형 AI 영상(Veo/Sora)이 아니라 "데이터 모션그래픽"이다.** 생성형 영상 모델은
한글 텍스트와 숫자를 정확히 렌더링하지 못하고, 수치 신뢰성이 핵심인 경제 방송에서는 리스크다.
대신 이미 잘 만들어진 `html_theme.py`(651줄) / `builders.py`(670줄) 디자인 시스템을
**시간축으로 펼치는** 방식으로 해결한다.

## 목표 (Phase 0 + 1 + 2를 한 번에)

| Phase | 내용 | 비용 |
|---|---|---|
| 0 | ffmpeg 레이어 개선 (미세 Ken Burns, 전환 위계) | 0 |
| 1 | 정지 스크린샷 → 애니메이션 프레임 시퀀스 (카운트업/바 성장/차트 드로잉) | 0 |
| 2 | LLM 연출 감독(`motion_plan.json`) + 나레이션 싱크 강조 | 기존 OPENAI_API_KEY 재사용, 하루 1회 소액 |
| — | 자막 스타일 수정 | 0 |

**시각적 목표물**: 첨부한 `motion_mockup_reference.py`를 실행하면 목표하는 최종 프레임 7장이
나온다. 이 스크립트는 레포의 `PALETTE`와 `assets/fonts`를 그대로 써서 만든 **디자인 검증용
목업**이며, 각 애니메이션 시점(t)의 상태를 파이썬에서 계산해 정적 HTML로 구운 것이다.
**이 목업의 픽셀 결과물을 재현하는 것이 이번 작업의 합격 기준**이다. 다만 목업의 구현 방식
(t마다 HTML 재생성)은 성능상 그대로 쓰면 안 된다 — 아래 P1-1의 방식을 따를 것.

---

## 🚨 절대 규칙 (위반 시 작업 실패)

1. **자막 타임라인 불변식을 깨지 말 것.**
   `video_renderer.py` 상단 설계 노트에 명시된 대로, "장면 N개 사이에 항상 N-1개의 정확히
   `TRANSITION_DURATION`초짜리 전환이 삽입된다"는 전제 위에서 `generate_subtitles.py`가
   동작한다. 프레임 시퀀스를 도입해도 **각 장면 클립의 길이는 반드시 오디오 길이와 정확히
   같아야** 한다. 프레임 수 반올림(`int(duration*fps)`)에서 몇 프레임씩 어긋나기 쉬우니
   최종 인코딩에 `-t {duration:.3f}`를 반드시 명시해 강제 절단할 것.

2. **모든 신규 경로는 실패 시 기존 정지 프레임 경로로 폴백할 것.** 어떤 이유로든 애니메이션
   렌더링이 실패하면 지금과 동일한 결과물이 나와야 한다. 회귀는 절대 불가.

3. **종목 개수를 줄이지 말 것.** `generate_video.py`의 `trim_to_fit_budget()` 우선순위
   로직은 그대로 유지한다.

4. **새 유료 API를 도입하지 말 것.** 생성형 이미지/영상 API(Veo, Sora, Nano Banana, Imagen 등)
   호출 코드를 추가하지 마라. Phase 2의 LLM 호출은 기존 `OPENAI_API_KEY`만 재사용한다.

5. **Remotion을 도입하지 말 것.** React 스택 이탈 문제도 있지만, 무엇보다 Remotion은
   4인 이상 영리법인에 유료 회사 라이선스를 요구한다(KBS는 해당). Playwright + HTML/CSS를
   확장하는 현재 방식을 유지한다.

6. **다음 파일은 건드리지 말 것**: `media_providers.py`, `media_pipeline.py`,
   `generate_script.py`, `generate_ranking.py`, `narrative_reorder.py`.
   (미디어 수급/원고 생성/종목 선정 로직은 이번 작업 범위 밖)

7. **모든 신규 기능에 환경변수 킬스위치를 둘 것.** 문제 발생 시 즉시 되돌릴 수 있어야 한다.

---

## Phase 0 — ffmpeg 레이어 (파일: `pipeline/assets/video_renderer.py`)

### P0-1. 슬라이드 타입별 Ken Burns 분기
현재 `ENABLE_KEN_BURNS` 불리언 하나로 전역 on/off 하고 있고, 기본값이 `false`인 이유는
코드 주석대로 "카드 텍스트가 확대·팬으로 잘려나가서"다. 이 판단은 옳았고, 해법은 끄는 게
아니라 **슬라이드 종류별로 강도를 다르게 주는 것**이다.

- `compose_scene()`에 `motion: str = "subtle"` 인자를 추가한다.
  - `"none"` — 완전 정지 (현재 동작). 폴백용.
  - `"subtle"` — zoom 1.0 → **1.02**, 중심 고정(팬 없음). 텍스트 카드용 기본값.
  - `"photo"` — zoom 1.0 → 1.08 + `_PAN_CYCLE` 팬. 배경 사진 슬라이드 전용.
- 호출부(`generate_video.py`)에서 `_resolve_visual()`이 이미 넘기고 있는
  `backgroundType`을 근거로 `photo` / `subtle`을 결정한다.
- 기존 `ENABLE_KEN_BURNS` 환경변수는 하위호환으로 남기되, `false`여도 `subtle`은 적용되게
  한다(=`"none"`은 새 환경변수 `MOTION_DISABLE=true`일 때만).

### P0-2. 전환 위계
지금은 모든 장면 전환이 `slideleft` 하나라 영상의 구조가 읽히지 않는다.

- 섹션 경계(시장요약 → 종목 → AI전략 → 클로징처럼 `section_type`이 바뀌는 지점)에서만
  `wipeleft`, 같은 섹션 내부 페이지 전환은 기존 `slideleft` 유지.
- `build_transition()`에 `kind` 인자를 명시적으로 받도록 하고, 호출부가 경계 여부를 판정한다.
- **반환 클립 길이는 어떤 경우에도 정확히 `duration`초여야 한다**(기존 불변식).

### P0-3. (선택, 시간이 남으면) 배경 미세 모션
전체화면 배경에 은은한 그라디언트 드리프트 레이어를 깔면 정지감이 더 줄어든다. 다만 이건
있으면 좋은 정도이므로 P1/P2를 먼저 완성한 뒤에 착수할 것. 외부 에셋 다운로드는 금지하고,
필요하면 ffmpeg `lavfi`로 생성한다.

---

## Phase 1 — 애니메이션 프레임 시퀀스 ★핵심

### P1-1. `render.py`에 프레임 시퀀스 렌더러 추가

**성능이 이 작업의 최대 리스크다.** GitHub Actions `ubuntu-latest`는 2코어이고, 15분 영상을
30fps 전체 캡처하면 27,000장이 되어 절대 완주할 수 없다. 다음 두 가지로 해결한다:

1. **모션은 각 장면 앞 `MOTION_LEAD_SECONDS = 3.0`초만 캡처**하고, 나머지 구간은 마지막
   프레임을 정지 홀드한다. 이건 성능 타협이 아니라 실제 방송 그래픽 문법이기도 하다 —
   그래픽은 등장할 때 움직이고 그 다음엔 멈춰 있어야 읽힌다.
2. **프레임마다 `set_content()`를 다시 호출하지 말 것.** HTML 파싱과 폰트 로딩이 매번
   반복되어 수십 배 느려진다. 대신 페이지를 **한 번만** 로드하고, 페이지 내 JS 함수를
   호출해 상태만 갱신한 뒤 스크린샷을 찍는다.

```python
# pipeline/assets/render.py 에 추가
MOTION_LEAD_SECONDS = float(os.environ.get("MOTION_LEAD_SECONDS", "3.0"))
MOTION_FPS = int(os.environ.get("MOTION_FPS", "24"))  # 30보다 24가 러너에 유리

def render_html_to_frames(html: str, out_dir: str, lead: float = None,
                          fps: int = None) -> list:
    """애니메이션 HTML을 프레임 시퀀스로 캡처한다.

    HTML 안에 window.__setT(t) 함수가 정의되어 있어야 한다(html_theme.MOTION_JS).
    페이지는 한 번만 로드하고, __setT(t)로 상태만 바꿔가며 스크린샷을 찍는다.
    __setT가 없으면(=애니메이션 없는 기존 슬라이드) 1장만 찍고 반환한다.
    실패 시 빈 리스트를 반환해 호출부가 기존 정지 경로로 폴백할 수 있게 한다.
    """
```

- 반환값은 캡처된 PNG 경로 리스트(정렬된 `f_00000.png` 형식).
- 렌더링 완료 후 `page.close()`는 반드시 `finally`에서.
- 총 캡처 프레임 수를 로그로 출력할 것(성능 회귀 감시용).

### P1-2. `html_theme.py`에 애니메이션 런타임 추가

`BASE_CSS` 옆에 `MOTION_JS` 상수를 추가한다. 목업(`motion_mockup_reference.py`)의
`ease()` 함수와 동일한 easeOutCubic을 JS로 구현하고, `data-anim` 속성이 붙은 요소를
일괄 갱신하는 `window.__setT(t)`를 정의한다.

지원할 애니메이션 타입(요소의 `data-anim` 값):

| 타입 | 동작 | 추가 data 속성 |
|---|---|---|
| `count` | 숫자를 0 → 목표값으로 카운트업 (천단위 콤마, 소수 자리 유지) | `data-to`, `data-decimals`, `data-suffix`, `data-delay`, `data-dur` |
| `grow` | `width`를 0% → 목표%로 성장 | `data-to`, `data-delay`, `data-dur` |
| `fadeup` | opacity 0→1 + translateY 26px→0 | `data-delay`, `data-dur` |
| `pop` | scale 0.6→1 + opacity, 늦은 딜레이로 배지 등장 | `data-delay`, `data-dur` |
| `draw` | SVG path `stroke-dashoffset`을 length→0으로 | `data-delay`, `data-dur` |

- **숫자는 반드시 `font-variant-numeric: tabular-nums`를 적용할 것.** 안 그러면 카운트업
  도중 글자폭이 흔들려서 숫자가 덜덜 떨린다.
- `__setT(t)`는 **순수 함수여야 한다** — 같은 t를 두 번 넣으면 같은 화면이 나와야 하고,
  내부에 `setInterval`/`requestAnimationFrame` 같은 자체 타이머를 두면 안 된다.
- 이 JS는 `shell()`과 `centered_shell()`이 반환하는 HTML의 `</body>` 직전에 삽입한다.

### P1-3. 적용 대상 3종 (이번 작업 범위는 여기까지만)

목업 프레임과 1:1로 대응한다.

**(a) 시장 지표 카운트업** — `builders.build_market_summary()`
목업 프레임 `01/02/03` 참조. 기존 `stat_table()`(표 형태)을 **3분할 카드**로 교체한다.
지수명 / 큰 숫자(count) / 게이지 바(grow) / 등락률 배지(pop), 카드마다 0.18초씩 딜레이.
그 아래에 투자자별 순매수 스트립(grow 3줄)을 추가하고, 마지막에 헤드라인이 fadeup 한다.
**기존 `stat_table()` 함수는 지우지 말 것** — 다른 빌더가 쓸 수 있으므로 남겨둔다.

**(b) 섹터 랭킹 바 성장** — `html_theme.ranking_card()` / `sector_heatmap()`
목업 프레임 `04` 참조. 이미 있는 `_score_bar()`에 `data-anim="grow"`와 순차 딜레이(0.12초)만
얹으면 되므로 변경량이 가장 적다. **여기부터 먼저 구현해서 파이프라인 전체를 한 번 통과시켜
보고**, 검증된 다음 (a)와 (c)로 넘어갈 것.

**(c) 차트 드로잉** — `html_theme.py`에 `svg_line_chart()` 신규 추가
목업 프레임 `05` 참조. `chart.py`의 `fetch_ohlcv()`가 가져온 종가 시계열을 받아 SVG
`<path>`로 그리고, `data-anim="draw"`로 선이 그려지게 한다. 선 끝에 광점(circle 2개 겹침)을
두고, 영역 그라디언트는 `clipPath`의 `width`를 진행률에 맞춰 늘려 따라 차오르게 한다.
**`chart.py`의 matplotlib 경로를 제거하지 말 것** — 캔들 차트는 그대로 두고, 라인 차트는
SVG로 병행 제공한다.

### P1-4. `video_renderer.py`의 `compose_scene()` 확장

이미지 경로 대신 **프레임 디렉토리**를 받을 수 있게 오버로드한다.

- 프레임 시퀀스 → `-framerate {MOTION_FPS} -i f_%05d.png`로 lead 구간 클립 생성
- 나머지 구간 → 마지막 프레임 정지 홀드 클립 생성
- 두 클립을 concat하고 **오디오를 입힌 뒤 `-t {duration:.3f}`로 절단**
- 오디오 스펙은 기존 `AUDIO_SAMPLE_RATE` / `AUDIO_CHANNELS` 상수를 반드시 그대로 사용할 것
  (파일 주석에 있는 "전환 직후 지지직 잡음" 회귀 방지)
- `duration <= MOTION_LEAD_SECONDS`인 짧은 장면은 홀드 없이 프레임 시퀀스만 사용

---

## Phase 2 — LLM 연출 감독 + 나레이션 싱크

### P2-1. `pipeline/generate_motion_plan.py` 신규 생성

- **입력**: `output/{lang}/scripts/reordered_script.json`, `scene_plan.json`
- **출력**: `output/{lang}/scripts/motion_plan.json`
- **LLM 역할은 "무엇을 강조할지" 판단까지만.** 타이밍 계산은 절대 LLM에 맡기지 마라.

LLM이 섹션별로 반환할 JSON 스키마:

```json
{
  "id": "stock_삼성전자",
  "template": "big_number | compare_bar | chart_focus | quote | timeline",
  "emphasis": [{"text": "12조원", "style": "pop_highlight"}],
  "camera": "static | slow_push",
  "tone": "bullish | bearish | neutral"
}
```

- `emphasis[].text`는 **반드시 해당 섹션 나레이션 원문에 그대로 등장하는 문자열**이어야 한다.
  검증에 실패한 항목은 조용히 버린다(LLM이 지어낸 수치가 화면에 강조되는 사고 방지 —
  이건 방송 신뢰도 문제라 타협 불가).
- `MOTION_PLAN_MOCK=1`이면 LLM을 호출하지 않고 규칙 기반 폴백을 쓴다
  (예: 정규식으로 `\d+(조|억|만)?원`, `\d+(\.\d+)?%` 패턴을 뽑아 emphasis로 삼음).
  CI 드라이런과 오프라인 테스트에 필요하다.
- 워크플로우에서는 `generate_scene_plan.py` 직후에 실행한다.

### P2-2. 타이밍 산출 (코드가 계산)

`generate_subtitles.py`가 이미 각 자막 이벤트의 시작/종료 시각을 정밀하게 계산하고 있다.
이 타임라인에서 `emphasis[].text`가 포함된 자막 이벤트를 찾아 그 시작 시각을 `at`으로 넣는다.

- `generate_subtitles.py`에 자막 이벤트 타임라인을 **JSON으로도 내보내는 함수**를 추가한다
  (`export_subtitle_timeline(...)` 정도). 기존 ASS 생성 로직은 그대로 두고 부산물만 추가.
- 장면 시작 기준 상대 시각(`at`)으로 변환해 `motion_plan.json`에 기록한다.
- 이 `at`이 `MOTION_LEAD_SECONDS`(3초)를 넘으면 **그 장면의 lead를 `at + 1.0`초까지
  연장**한다. 강조 팝이 정지 홀드 구간에 걸리면 아예 안 보이기 때문이다.
  단 상한 `MOTION_MAX_LEAD_SECONDS = 8.0`을 두어 성능이 폭주하지 않게 한다.

### P2-3. 빌더에 강조 반영

`builders.py`가 `motion_plan.json`을 읽어(없으면 조용히 무시), `emphasis`에 해당하는 텍스트를
`data-anim="pop"` + `data-delay="{at}"`로 감싼다. 목업 프레임 `06`의 "12조원"처럼 해당
단어가 발화되는 순간 확대되고 하이라이트 배경이 씌워지는 결과가 나와야 한다.

---

## 자막 스타일 수정 (사용자 명시 요청)

목업의 자막 스타일을 그대로 적용한다. 대상: `pipeline/generate_subtitles.py`의 `ASS_HEADER`,
`pipeline/generate_video.py`의 `burn_subtitles()`.

### 1. 폰트명 수정 (버그)
현재 `Fontname`이 `NotoSansCJK`인데, 레포에 번들된 `assets/fonts/NotoSansKR-Bold.ttf`의
**실제 폰트 패밀리명은 `Noto Sans KR`**이다(fontTools로 확인함). 러너에 `NotoSansCJK`가
설치돼 있지 않으면 libass가 조용히 기본 폰트로 폴백하므로, 지금 나오는 자막이 의도한 서체가
아닐 가능성이 높다.

- 세 스타일 모두 `Fontname`을 `Noto Sans KR`로 변경.
- **`burn_subtitles()`의 필터를 `ass=`에서 `subtitles=`로 교체할 것.** `ass` 필터는
  `fontsdir` 옵션을 지원하지 않아 번들 폰트를 못 찾는다.
  ```
  -vf "subtitles={ass_escaped}:fontsdir={assets/fonts 절대경로}"
  ```
  경로 이스케이프(`:` → `\:`)는 기존 로직을 유지하되 `fontsdir`에도 동일하게 적용한다.
- 변경 후 반드시 **렌더된 영상에서 한글 자막이 깨지지 않는지 눈으로 확인**할 것.

### 2. 색상 수정
- `Default` — 흰색 `&H00FFFFFF` 유지.
- `Highlight` — 현재 순노랑 `&H0000FFFF`(#FFFF00)를 목업의 `#FFE066`으로 변경.
  ASS는 AABBGGRR 순서이므로 → **`&H0066E0FF`**
  (`html_theme.PALETTE["highlight"]`와 동일한 값이라 화면 그래픽의 하이라이트와 톤이 맞는다.)
- `Warning` — 현행 유지.

### 3. 외곽선/그림자
목업은 딱딱한 외곽선 없이 부드러운 그림자만 쓴다. libass는 블러 그림자를 지원하지 않으므로
가독성을 위해 최소한의 외곽선은 남긴다.
- `Outline` 2 → **1**, `Shadow` 1 → **2**, `BorderStyle` 1 유지.
- 배경 사진 슬라이드 위에서 가독성이 떨어지면 `Outline`을 1.5로 되돌릴 것.

### 4. 문장 내 부분 강조 (Phase 2 연동)
현재 `Highlight`는 자막 **한 줄 전체**에 적용되는 스타일이다. 목업처럼 한 문장 안에서
특정 단어만 노랑으로 만들려면 인라인 오버라이드 태그를 써야 한다.

- `_format_ass_text()`가 `motion_plan.json`의 `emphasis[].text`를 받아, 해당 부분만
  `{\c&H0066E0FF&}강조어{\c&H00FFFFFF&}`로 감싸도록 확장한다.
- 줄바꿈 계산(`_wrap_words`, `CHARS_PER_LINE`)은 **태그를 제외한 실제 글자 수 기준**으로
  해야 한다. 태그 문자를 길이에 포함시키면 줄바꿈이 엉뚱한 곳에서 일어난다. 이 부분은
  버그가 나기 쉬우니 단위 테스트를 반드시 작성할 것.

---

## 성능 가드

- `.github/workflows/morning_core.yml`의 assets/video 잡 `timeout-minutes`를 넉넉히 올린다.
- `MOTION_MAX_SCENES` 환경변수로 애니메이션을 적용할 장면 수 상한을 둔다(기본 999).
  초과분은 기존 정지 프레임으로 렌더링한다.
- 파이프라인 종료 시 **총 캡처 프레임 수와 단계별 소요 시간을 로그로 출력**한다.
- 프레임 PNG는 장면 클립 인코딩 직후 삭제해 디스크를 아낀다(러너 용량 제한).

## 환경변수 정리 (모두 `.env.example`에 문서화할 것)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MOTION_DISABLE` | `false` | `true`면 모든 신규 모션을 끄고 기존 동작으로 완전 복귀 |
| `MOTION_LEAD_SECONDS` | `3.0` | 장면당 애니메이션 캡처 길이 |
| `MOTION_MAX_LEAD_SECONDS` | `8.0` | 강조 싱크로 연장될 수 있는 상한 |
| `MOTION_FPS` | `24` | 프레임 시퀀스 캡처 fps |
| `MOTION_MAX_SCENES` | `999` | 애니메이션 적용 장면 수 상한 |
| `MOTION_PLAN_MOCK` | `` | `1`이면 LLM 없이 규칙 기반 motion_plan 생성 |

---

## 검증 (완료 보고 전 반드시 수행)

1. `python -m pytest tests/ -v` — 기존 테스트 전부 통과.
2. 신규 테스트 추가:
   - `tests/test_video_renderer.py` — **프레임 시퀀스로 만든 클립의 실제 길이가 오디오
     길이와 ±0.05초 이내로 일치**하는지 (가장 중요한 회귀 테스트)
   - `tests/test_motion_runtime.py` — `__setT(t)` 멱등성, t=0/중간/끝 상태 검증
   - `tests/test_subtitles_emphasis.py` — 인라인 강조 태그가 들어가도 줄바꿈이
     실제 글자 수 기준으로 정확한지
   - `tests/test_motion_plan.py` — 원문에 없는 `emphasis.text`가 버려지는지
3. 전체 드라이런:
   `SCRIPT_MOCK=1 TTS_MOCK=1 MEDIA_MOCK=1 MOTION_PLAN_MOCK=1` 로 파이프라인 전체 실행.
   최종 mp4가 생성되고 길이가 `config/schedule.yml`의 목표 범위 안에 드는지 확인.
4. `MOTION_DISABLE=true`로 한 번 더 실행해 **기존 동작과 동일한 결과**가 나오는지 확인.
5. 최종 mp4에서 임의 프레임 몇 장을 뽑아, 목업 프레임과 육안 비교한 결과를 보고할 것.

---

## 작업 순서 (커밋 단위로 나눌 것)

한 번에 다 하지 말고 아래 순서로 커밋하며 진행한다. 각 커밋마다 파이프라인이 깨지지 않아야 한다.

1. `feat: 자막 폰트/색상 수정 + subtitles 필터 전환` — 독립적이고 검증이 쉬우니 먼저.
2. `feat(P0): 슬라이드 타입별 Ken Burns 분기 + 전환 위계`
3. `feat(P1): 프레임 시퀀스 렌더러 + MOTION_JS 런타임 (섹터 랭킹 바에만 우선 적용)`
   → 여기서 파이프라인 전체를 한 번 통과시키고 성능 실측치를 보고할 것.
4. `feat(P1): 시장 지표 카운트업 + SVG 차트 드로잉 적용`
5. `feat(P2): motion_plan.json 생성 + 나레이션 싱크 강조`

---

## 시작 전에

먼저 레포 구조와 위에 언급된 파일들을 읽고, **구현 계획과 예상 리스크를 요약해서 보고**해줘.
특히 P1-4(프레임 시퀀스 클립 길이를 오디오 길이와 정확히 맞추는 부분)를 어떻게 구현할지
구체적으로 설명해줘. 내가 확인한 뒤에 코드 작성을 시작해줘.

애매한 부분이 있으면 추측해서 진행하지 말고 물어봐줘.
