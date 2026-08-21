# pipeline/generate_motion_plan.py
"""
motion_plan.json 생성 진입점 (Phase 2 — LLM 연출 감독)
사용법: python pipeline/generate_motion_plan.py [KO|ko|en]

입력: output/{lang}/scripts/reordered_script.json
  (scene_plan.json의 visual_type/priority_score/entities는 narrative_reorder.
   build_mention_briefing()이 이미 각 섹션에 병합해 두므로 별도로 다시 읽지
   않는다 — generate_subtitles.py/generate_video.py와 동일한 관례.)
출력: output/{lang}/scripts/motion_plan.json

LLM의 역할은 "무엇을 강조할지"(template/emphasis/camera/tone) 판단까지만이고,
각 emphasis가 몇 초에 뜰지(at)는 이 파일이 코드로 계산한다(P2-2, 아래 참고).

emphasis[].text 검증 기준: 화면에 실제로 표시되는 subtitle 텍스트.
narration은 TTS 낭독용으로 숫자를 완전히 한글로 풀어쓴 텍스트("십이조원")라
"12조원" 같은 화면 표기가 애초에 등장하지 않는다(config/pronunciation_ko.yml
참고). 아래 P2-2 타이밍 계산과 P2-3이 화면에서 감싸는 텍스트도 전부 subtitle
쪽 표기 기준이므로 여기서도 같은 기준으로 검증해야 앞뒤가 맞는다.

★ P2-2 타이밍 산출 — 실제 오디오 대신 글자 수 기반 추정치를 쓴다(사용자 결정,
2026-08-21): generate_assets.py(이 파일의 출력을 읽는 쪽)가 voice 잡과 병렬로
실행되므로 이 시점엔 아직 mp3가 없다. assets 잡을 voice 잡 뒤로 순차 실행하면
정확한 실제 음성 길이를 쓸 수 있지만 파이프라인 총 소요 시간이 늘어나(SLA
영향) 병렬 구조를 그대로 유지하기로 했다 — 강조 팝은 장식적 연출 효과라
수백ms 오차는 육안으로 거의 구분되지 않는다는 판단. narration은 이미 한글로
완전히 풀어 쓴 텍스트라 그 글자 수 자체가 발화 길이에 근접하므로
(generate_subtitles._speech_weight 주석 참고), generate_script.py가 대본
분량을 산정할 때 쓰는 320자/분 페이스와 동일한 기준으로 추정 duration을 만들고
generate_subtitles._compute_dialogue_segments()(ASS 생성과 동일한 함수, 로직
중복 없음)로 각 emphasis 문구가 등장하는 청크의 시작 시각을 찾는다.
"""
import os
import re
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from openai import OpenAI

from generate_subtitles import _compute_dialogue_segments, AGGREGATE_STOCK_SECTION_IDS

# generate_script.py가 대본 분량("320자/분 기준 15분 분량")을 산정할 때 쓰는
# 페이스와 동일 — narration 글자 수만으로 발화 길이를 추정하는 데 재사용한다.
NARRATION_CHARS_PER_SECOND = 320 / 60

MOTION_LEAD_SECONDS = float(os.environ.get("MOTION_LEAD_SECONDS", "3.0"))
MOTION_MAX_LEAD_SECONDS = float(os.environ.get("MOTION_MAX_LEAD_SECONDS", "8.0"))

# MOTION_PLAN_MOCK=1: LLM을 호출하지 않고 정규식 기반 규칙으로 emphasis를
# 뽑는다. CI 드라이런/오프라인 테스트에 사용(문서 지시).
MOTION_PLAN_MOCK = os.environ.get("MOTION_PLAN_MOCK") == "1"

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key and not MOTION_PLAN_MOCK:
    raise EnvironmentError("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
client = OpenAI(api_key=_api_key or "sk-mock-dry-run")

_VALID_TEMPLATES = {"big_number", "compare_bar", "chart_focus", "quote", "timeline"}
_VALID_CAMERAS = {"static", "slow_push"}
_VALID_TONES = {"bullish", "bearish", "neutral"}
_MAX_EMPHASIS_PER_SECTION = 3


def _is_stock_section(section: dict) -> bool:
    """generate_subtitles._build_subtitle_map()의 is_stock 판정과 동일 기준
    (summary+chart+mention 개별 카드가 아니라 집계 슬라이드 한 장으로 렌더되는
    stock_추가관심종목/stock_증권사리포트는 제외)."""
    sid = section.get("id", "")
    return (sid.startswith("stock_") or sid.startswith("hidden_")) and sid not in AGGREGATE_STOCK_SECTION_IDS


def _display_text(section: dict) -> str:
    """섹션의 화면 표시 텍스트(숫자가 실제 자릿수로 적힌 쪽)를 반환한다.

    종목 섹션은 builders._build_stock_summary()가 화면 큰 헤드라인으로
    corner_summary(~25자 한줄 요약)를 쓰지, 바닥 자막(subtitle_summary, 훨씬
    긴 문단)을 쓰지 않는다 — 그 둘은 표현이 달라 문자열이 일치하지 않으므로
    emphasis 검증·타이밍 기준을 실제 화면에 뜨는 corner_summary로 맞춘다
    (사용자 결정, 2026-08-21). 일반 섹션은 subtitle이 곧 화면 텍스트라
    기존 기준을 그대로 쓴다."""
    if _is_stock_section(section) and section.get("corner_summary"):
        return section["corner_summary"]
    return (
        section.get("subtitle_summary")
        or section.get("subtitle")
        or section.get("narration_summary")
        or section.get("narration")
        or ""
    )


def _narration_text(section: dict) -> str:
    """_display_text()와 짝을 이루는 나레이션(발화) 텍스트.

    종목 섹션은 corner_summary 자체를 그대로 쓴다 — corner_summary는 실제
    나레이션 문장이 아니라 화면용 한줄 요약이지만, 정밀한 실제 음성 동기화
    대신 글자 수 추정 방식을 쓰기로 한 이상(P2-2 주석 참고) narration/subtitle을
    동일 텍스트로 맞추는 게(ai_strategy_brief가 이미 쓰는 방식과 동일) at 계산과
    검증 기준을 일치시키는 가장 단순한 방법이다."""
    if _is_stock_section(section) and section.get("corner_summary"):
        return section["corner_summary"]
    return section.get("narration_summary") or section.get("narration") or ""


def _emphasis_timing(narration_text: str, subtitle_text: str, phrases: list) -> dict:
    """P2-2: narration 글자 수 기반 추정 duration으로 _compute_dialogue_segments()를
    돌려, 각 phrase가 등장하는 첫 청크의 시작 시각(장면 상대, 초)을 찾는다.
    못 찾으면 0.0(장면 시작과 동시에 팝)으로 폴백한다 — 화면 표기(subtitle)
    기준 문구라 narration 청크가 아니라 subtitle 청크(_compute_dialogue_segments가
    함께 반환하는 화면 표출 문구)에서 찾아야 한다."""
    duration = len(narration_text) / NARRATION_CHARS_PER_SECOND
    if duration <= 0:
        return {p: 0.0 for p in phrases}
    segments = _compute_dialogue_segments(narration_text, subtitle_text, 0.0, duration)
    at_by_phrase = {}
    for phrase in phrases:
        at = 0.0
        for chunk, t_start, _t_end in segments:
            if phrase in chunk:
                at = round(max(0.0, t_start), 2)
                break
        at_by_phrase[phrase] = at
    return at_by_phrase


def _lead_seconds_for(emphasis: list) -> float:
    """emphasis 중 가장 늦게 뜨는 at이 MOTION_LEAD_SECONDS를 넘으면 그 시각
    +1.0초까지 장면 lead를 연장한다(팝이 정지 홀드 구간에 걸려 안 보이는 것
    방지). 상한은 MOTION_MAX_LEAD_SECONDS."""
    if not emphasis:
        return MOTION_LEAD_SECONDS
    max_at = max(e["at"] for e in emphasis)
    if max_at + 1.0 <= MOTION_LEAD_SECONDS:
        return MOTION_LEAD_SECONDS
    return min(max_at + 1.0, MOTION_MAX_LEAD_SECONDS)


# ── MOTION_PLAN_MOCK 규칙 기반 폴백 ───────────────────────────────────────
_MOCK_PATTERNS = [
    re.compile(r'\d[\d,]*\.?\d*\s*(?:조|억|만)?\s*원'),
    re.compile(r'\d+\.?\d*\s*%'),
    re.compile(r'\d[\d,]*\s*포인트'),
]


def _mock_emphasis(text: str) -> list:
    found = []
    for pat in _MOCK_PATTERNS:
        for m in pat.finditer(text):
            phrase = m.group(0).strip()
            if phrase and phrase not in found:
                found.append(phrase)
    return [{"text": p, "style": "pop_highlight"} for p in found[:_MAX_EMPHASIS_PER_SECTION]]


def _mock_plan_for_section(section_id: str, text: str) -> dict:
    emphasis = _mock_emphasis(text)
    return {
        "id": section_id,
        "template": "big_number" if emphasis else "chart_focus",
        "emphasis": emphasis,
        "camera": "static",
        "tone": "neutral",
    }


# ── LLM 호출 ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "너는 한국어 경제 뉴스 영상의 모션그래픽 연출 감독이다. 입력으로 주는 "
    "섹션(id, text)마다 화면 연출을 결정한다.\n"
    "- template: big_number(핵심 수치 하나를 크게) / compare_bar(비교 막대) / "
    "chart_focus(차트 중심) / quote(발언 인용) / timeline(시간 흐름) 중 가장 "
    "어울리는 것 하나.\n"
    "- emphasis: 화면에서 확대·하이라이트할 문구 목록(최대 3개, 핵심 수치/비율/"
    "고유명사 위주). 반드시 그 섹션 text 필드에 글자 하나 다르지 않게 그대로 "
    "등장하는 부분 문자열만 골라라. 지어내지 마라 — 없으면 빈 배열로 둔다.\n"
    "- camera: static(고정) / slow_push(서서히 확대) 중 하나. 임팩트가 큰 "
    "섹션에만 slow_push.\n"
    "- tone: bullish(긍정) / bearish(부정) / neutral(중립) 중 하나.\n\n"
    "다음 형식의 JSON 객체로만 답하라. 입력에 있는 모든 id에 대해 정확히 "
    "하나씩 반환하라:\n"
    '{"sections": [{"id": "...", "template": "...", '
    '"emphasis": [{"text": "...", "style": "pop_highlight"}], '
    '"camera": "...", "tone": "..."}]}'
)


def _call_llm(candidates: list) -> dict:
    user_content = json.dumps(candidates, ensure_ascii=False)
    last_err = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=6000,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            last_err = e
            print(f"  ⚠️ motion_plan API 호출 실패(시도 {attempt + 1}/2): {e}")
    print(f"  ❌ motion_plan API 호출 최종 실패: {last_err}")
    return {"sections": []}


# ── 검증 ──────────────────────────────────────────────────────────────────
def _validate_plan(raw_sections: list, source_by_id: dict) -> list:
    """LLM(혹은 목업)이 반환한 섹션별 계획을 검증하고 P2-2 타이밍(at/lead_seconds)을
    채운다.
    - 모르는 id는 버린다.
    - emphasis[].text가 해당 섹션 표시 텍스트에 그대로 없으면 그 항목만 버린다
      (LLM이 지어낸 수치가 화면에 강조되는 사고 방지 — 방송 신뢰도 문제라 타협 불가).
    - template/camera/tone이 허용값이 아니면 안전한 기본값으로 대체한다.
    source_by_id[sid]는 {"display": 화면표시텍스트, "narration": 나레이션텍스트}."""
    validated = []
    for item in raw_sections:
        sid = item.get("id", "")
        if sid not in source_by_id:
            continue
        text = source_by_id[sid]["display"]
        narration = source_by_id[sid]["narration"]

        template = item.get("template")
        if template not in _VALID_TEMPLATES:
            template = "chart_focus"

        camera = item.get("camera")
        if camera not in _VALID_CAMERAS:
            camera = "static"

        tone = item.get("tone")
        if tone not in _VALID_TONES:
            tone = "neutral"

        phrases = []
        styles = {}
        for e in (item.get("emphasis") or [])[:_MAX_EMPHASIS_PER_SECTION]:
            phrase = (e.get("text") or "").strip()
            if phrase and phrase in text and phrase not in styles:
                phrases.append(phrase)
                styles[phrase] = e.get("style") or "pop_highlight"

        at_by_phrase = _emphasis_timing(narration, text, phrases)
        emphasis = [
            {"text": p, "style": styles[p], "at": at_by_phrase[p]}
            for p in phrases
        ]

        validated.append({
            "id": sid,
            "template": template,
            "emphasis": emphasis,
            "camera": camera,
            "tone": tone,
            "lead_seconds": _lead_seconds_for(emphasis),
        })
    return validated


def build_motion_plan(reordered_script: dict) -> dict:
    sections = reordered_script.get("sections", [])
    candidates = []
    source_by_id = {}
    for s in sections:
        sid = s.get("id", "")
        if not sid:
            continue
        text = _display_text(s).strip()
        if not text:
            continue
        candidates.append({"id": sid, "text": text})
        source_by_id[sid] = {"display": text, "narration": _narration_text(s)}

    if not candidates:
        return {"sections": []}

    if MOTION_PLAN_MOCK:
        raw_sections = [_mock_plan_for_section(c["id"], c["text"]) for c in candidates]
    else:
        raw_sections = _call_llm(candidates).get("sections", [])

    return {"sections": _validate_plan(raw_sections, source_by_id)}


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "reordered_script.json")
    out_path = os.path.join(root, "output", lang, "scripts", "motion_plan.json")

    if not os.path.isfile(script_path):
        print(f"❌ reordered_script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        reordered = json.load(f)

    motion_plan = build_motion_plan(reordered)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(motion_plan, f, ensure_ascii=False, indent=2)

    total_emphasis = sum(len(s["emphasis"]) for s in motion_plan["sections"])
    print(
        f"✅ motion_plan 생성 완료! 섹션 수: {len(motion_plan['sections'])}개, "
        f"강조 항목: {total_emphasis}개 → {out_path}"
    )
    return motion_plan


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
