"""
pipeline/generate_subtitles.py
================================
ASS(Advanced SubStation Alpha) 자막 파일 생성 모듈

- 각 슬라이드의 오디오 길이에 맞춰 자막 타임라인을 자동 생성합니다.
- 나레이션이 나오는 타이밍에 동시에 자막이 화면 하단에 표출됩니다.
- 자막은 한글 맞춤법 준수, 숫자/영어 원문 표기, 뜻을 () 안에 병기합니다.
- 긴 자막은 적절한 길이로 자동 분할합니다.

프레임 파일명 → 오디오 ID 매핑 규칙:
  00_hook.png                → hook.mp3
  01_conclusion.png          → conclusion.mp3
  10_삼성전자_1_summary.png  → stock_삼성전자_summary.mp3
  10_삼성전자_3_mention.png  → stock_삼성전자_mention.mp3
  10_삼성전자_3_mention_00.png → stock_삼성전자_mention_00.mp3
  99_closing.png             → closing.mp3

(구 8단계/롱폼 구성에서만 쓰이던 00_opening/01_market_00/02_sector/
90_extra_watchlist/91_today_pick/92_brokerage_report/98_ai_strategy 패턴도
하위 호환을 위해 계속 지원한다 — narrative_reorder.reorder_sections()의
short_form=False 경로를 다시 쓰게 되면 그대로 동작한다.)
"""
import os
import sys
import json
import re
import subprocess
import math

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.video_renderer import TRANSITION_DURATION

# ── ASS 스타일 정의 ────────────────────────────────────────────────────────

ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
Title: KBS 머니올라 자막

; MarginV=40 는 슬라이드 하단 190px 고정 자막 영역(pipeline/assets/config.py의
; SUBTITLE_ZONE_TOP)과 맞춰 카드/차트 등 콘텐츠와 겹치지 않도록 배치한 값입니다.
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,NotoSansCJK,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1
Style: Highlight,NotoSansCJK,42,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1
Style: Warning,NotoSansCJK,36,&H004040FF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

CHARS_PER_LINE = 45   # 자막 한 줄 최대 글자 수
MAX_LINES      = 2    # 자막 최대 줄 수
SILENT_DURATION = 3.0 # 오디오 없을 때 기본 슬라이드 길이

# summary+chart+mention 개별 카드가 아니라 단일 슬라이드로 렌더링되는 집계형 종목 섹션
AGGREGATE_STOCK_SECTION_IDS = {"stock_추가관심종목", "stock_증권사리포트"}


def _ts(seconds: float) -> str:
    """초를 ASS 타임코드 형식(H:MM:SS.CC)으로 변환합니다."""
    total = max(0.0, seconds)
    h     = int(total // 3600)
    m     = int((total % 3600) // 60)
    s     = int(total % 60)
    cs    = int((total - int(total)) * 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _get_audio_duration(mp3_path: str) -> float:
    """ffprobe로 MP3 파일 길이를 가져옵니다."""
    if not mp3_path or not os.path.isfile(mp3_path):
        return SILENT_DURATION
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            mp3_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        dur = float(result.stdout.strip())
        return dur if dur > 0 else SILENT_DURATION
    except Exception:
        return SILENT_DURATION


def _frame_stem_to_audio_id(stem: str, sections: list) -> str:
    """
    프레임 파일 스템(확장자 없는 파일명)을 오디오 ID로 변환합니다.

    매핑 규칙:
      00_hook                → hook
      01_conclusion          → conclusion
      NN_종목명_1_summary    → stock_종목명_summary
      NN_종목명_2_chart      → stock_종목명_chart
      NN_종목명_3_mention    → stock_종목명_mention
      NN_종목명_3_mention_MM → stock_종목명_mention_MM
      99_closing             → closing

      (하위 호환) 00_opening/01_market_00/02_sector/90_extra_watchlist/
      91_today_pick/92_brokerage_report/98_ai_strategy — short_form=False
      (구 8단계 롱폼) 구성에서만 나타남.
    """
    # 고정 패턴 (정확한 매핑)
    fixed_patterns = [
        (r'^00_hook$',              'hook'),
        (r'^01_conclusion$',        'conclusion'),
        (r'^00_opening$',           'opening'),
        (r'^01_market',             'market_summary'),
        (r'^02_sector',             'sectors'),
        (r'^90_extra_watchlist$',   'stock_추가관심종목'),
        (r'^91_today_pick$',        'stock_오늘의픽'),
        (r'^92_brokerage_report$',  'stock_증권사리포트'),
        (r'^98_ai_strategy',        'ai_strategy'),
        (r'^99_closing',            'closing'),
    ]
    for pattern, audio_id in fixed_patterns:
        if re.match(pattern, stem):
            return audio_id

    # 종목 슬라이드 패턴: NN_종목명_1_summary / _2_chart / _3_mention / _3_mention_MM
    # 형식: {숫자2자리}_{종목명}_{슬라이드번호}_{타입}[_{페이지번호}]

    # mention 페이지 있음: NN_종목명_3_mention_MM
    m = re.match(r'^\d{2}_(.+)_3_mention_(\d{2})$', stem)
    if m:
        stock_name = m.group(1)
        page_num   = m.group(2)
        # sections에서 실제 ID 찾기
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_mention_{page_num}"

    # mention 단일 페이지: NN_종목명_3_mention
    # builders.py는 항상 _3_mention_{p:02d}.png 형식으로 생성하므로
    # 이 패턴은 실제로 도달 불가능하나, 방어적으로 _mention_00 반환
    m = re.match(r'^\d{2}_(.+)_3_mention$', stem)
    if m:
        stock_name = m.group(1)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_mention_00"

    # chart: NN_종목명_2_chart
    m = re.match(r'^\d{2}_(.+)_2_chart$', stem)
    if m:
        stock_name = m.group(1)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_chart"

    # summary: NN_종목명_1_summary
    m = re.match(r'^\d{2}_(.+)_1_summary$', stem)
    if m:
        stock_name = m.group(1)
        sid = _find_stock_section_id(stock_name, sections)
        return f"{sid}_summary"

    # fallback: 스템 그대로 반환
    print(f"  [subtitle] ⚠️ 매핑 실패 — 스템: {stem}")
    return stem


def _find_stock_section_id(stock_name: str, sections: list) -> str:
    """
    종목명으로 sections에서 실제 section ID를 찾습니다.
    예: '삼성전자' → 'stock_삼성전자' 또는 'hidden_삼성전자'
    """
    # 정확히 일치하는 section 찾기
    for sec in sections:
        sid = sec.get("id", "")
        if sid in (f"stock_{stock_name}", f"hidden_{stock_name}"):
            return sid

    # 부분 일치 (종목명이 section ID에 포함되는 경우)
    for sec in sections:
        sid = sec.get("id", "")
        if stock_name in sid:
            return sid

    # 못 찾으면 기본값
    return f"stock_{stock_name}"


def _build_subtitle_map(sections: list, lang: str):
    """
    섹션 ID → (narration_text, subtitle_text) 매핑 딕셔너리를 생성합니다.
    오디오 ID와 동일한 키를 사용합니다.

    narration_text를 함께 반환하는 이유: 자막 표출 시간은 실제로 낭독되는
    narration의 길이에 비례해야 정확한데, 화면에는 표기가 다른 subtitle
    텍스트를 보여줘야 하기 때문입니다 (숫자/영문 표기 차이). 두 텍스트를
    같은 키로 짝지어 반환해 _make_dialogue_events()가 문장 단위로 정렬할
    수 있게 합니다.

    반환: {
        'opening': (narration, subtitle),
        'market_summary': (narration, subtitle),
        ...
        'stock_삼성전자_mention_00': (narration, subtitle),
        ...
    }
    """
    subtitle_map = {}
    audio_base = f"output/{lang}/audio"

    for section in sections:
        sid   = section.get("id", "")
        if not sid:
            continue

        is_stock = (
            (sid.startswith("stock_") or sid.startswith("hidden_"))
            and sid not in AGGREGATE_STOCK_SECTION_IDS
        )

        if is_stock:
            # summary
            narr = section.get("narration_summary", section.get("narration", ""))
            sub  = section.get("subtitle_summary", section.get("subtitle", ""))
            if sub:
                subtitle_map[f"{sid}_summary"] = (narr, sub)

            # channel_summaries: 종목당 최대 3개(유튜브/경제방송/증권사) 카테고리별
            # 종합 분석 요약 — builders.py/voice.py와 동일하게 배열 인덱스를 그대로
            # _mention_{p:02d} 페이지 번호로 사용한다.
            for p, cs in enumerate(section.get("channel_summaries", [])):
                sub  = cs.get("subtitle", "")
                narr = cs.get("narration", "")
                if sub:
                    subtitle_map[f"{sid}_mention_{p:02d}"] = (narr, sub)

        elif sid == "closing":
            # 클로징 슬라이드는 투자 유의사항 전문을 화면에 이미 글자로 표시하므로
            # (builders.build_closing 참고) 하단 자막을 중복으로 넣지 않는다.
            continue

        else:
            # 일반 섹션
            narr = section.get("narration", "")
            sub  = section.get("subtitle", "")
            if sub:
                subtitle_map[sid] = (narr, sub)

    return subtitle_map


# 문장 종결부호([.!?。]) 뒤에 공백이 오는 경우에만 문장을 분리한다. 숫자 사이의
# 소수점(예: "8302.5")은 마침표 바로 뒤에 숫자가 오므로 (?!\d)에 의해 분리되지
# 않는다 — "8302."와 "5"로 잘못 쪼개지는 것을 방지.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?。])(?!\d)\s*')


def _split_into_sentences(text: str) -> list:
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _split_sentences(text: str) -> list:
    """문장 단위로만 분할합니다 (화면 표출용 줄바꿈/청크 병합 없이 순수 분리)."""
    return _split_into_sentences(text)


def _wrap_words(text: str, width: int) -> list:
    """단어(공백) 경계에서만 줄바꿈해 길이 width 이하의 조각으로 나눕니다. 문장/단어
    중간이 잘리지 않도록 문자 수 기준 강제 절단 대신 항상 공백에서만 끊습니다.
    단어 하나가 그 자체로 width보다 길 때만 부득이하게 강제로 자릅니다."""
    words = [w for w in text.split(" ") if w]
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if len(word) <= width:
            current = word
        else:
            # 단어 자체가 width보다 긴 극단적인 경우에만 강제 분할
            for i in range(0, len(word), width):
                piece = word[i:i + width]
                if len(piece) == width:
                    lines.append(piece)
                else:
                    current = piece
    if current:
        lines.append(current)
    return lines


# 자막 표기는 숫자를 아라비아 숫자로 짧게 쓰지만(예: "85,400"), 실제 내레이션은
# 이걸 한글로 풀어 읽는다("팔만오천사백원") — 표기 글자 수보다 훨씬 길게
# 발음된다. 청크 단위로 화면 시간을 배분할 때 이 차이를 무시하고 자막 글자
# 수만 쓰면, 숫자가 많은 청크는 실제 발화 시간보다 짧게, 문구 위주 청크는
# 길게 배정돼 내레이션과 자막이 어긋나 보인다(사용자 보고 버그).
_DIGIT_GROUP_RE = re.compile(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?%?')


def _speech_weight(text: str) -> float:
    """자막 텍스트 조각의 상대적 발화 길이를 추정합니다. 완벽한 한글 숫자
    변환기를 만드는 대신, 숫자 구간만 분해해 가벼운 보정 계수를 적용합니다:
    - 정수부(콤마 제외 자릿수)는 1.3배 — "85400"(5자리)→"팔만오천사백"(6음절)처럼
      만/천/백 등 자릿값 단위가 끼어들어 원래 자릿수보다 길게 발음되는 것의 근사치.
    - 소수점은 "쩜"(1음절), 소수부는 자릿수 그대로(한 자리씩 그대로 읽음 — 예:
      ".2"→"쩜이", 자릿값 단위가 끼지 않으므로 확장 배율을 적용하지 않음).
    - "%"는 "퍼센트"(3음절: 퍼/센/트)로 확장.
    narration 텍스트(이미 한글로 풀어 쓴 상태)에는 적용하지 않습니다 — 그건
    그 자체로 이미 발화 길이에 가까운 글자 수입니다."""
    weight = 0.0
    pos = 0
    for m in _DIGIT_GROUP_RE.finditer(text):
        weight += len(text[pos:m.start()])
        raw = m.group()
        has_percent = raw.endswith('%')
        core = raw[:-1] if has_percent else raw
        int_part, _, frac_part = core.partition('.')
        int_digits = int_part.replace(',', '')
        weight += len(int_digits) * 1.3
        if frac_part:
            weight += 1 + len(frac_part)  # "쩜" + 소수부 자릿수
        if has_percent:
            weight += 3  # "퍼센트"
        pos = m.end()
    weight += len(text[pos:])
    return max(weight, 1.0)


def _split_subtitle_text(text: str) -> list:
    """
    자막 텍스트를 화면 표출 단위로 분할합니다.
    반환: 자막 청크 리스트
    """
    if not text:
        return []

    sentences = _split_into_sentences(text)

    chunks  = []
    current = ""

    for sent in sentences:
        test = (current + " " + sent).strip()
        lines_needed = math.ceil(len(test) / CHARS_PER_LINE)
        if lines_needed > MAX_LINES and current:
            chunks.append(current)
            current = sent
        else:
            current = test

    if current:
        chunks.append(current)

    # 최대 길이 초과 청크는 단어 경계에서만 강제 분할(문자 중간 절단 금지)
    final = []
    max_len = CHARS_PER_LINE * MAX_LINES
    for chunk in chunks:
        if len(chunk) <= max_len:
            final.append(chunk)
        else:
            final.extend(_wrap_words(chunk, max_len))

    return final if final else _wrap_words(text, max_len)


def _format_ass_text(text: str) -> str:
    """ASS 텍스트: 긴 줄을 단어 경계에서 \\N 으로 분리합니다(단어 중간 절단 금지)."""
    lines = _wrap_words(text, CHARS_PER_LINE)
    return r"\N".join(lines[:MAX_LINES])


def _make_dialogue_events(narration_text: str, subtitle_text: str,
                           start_time: float,
                           duration: float,
                           style: str = "Default") -> list:
    """
    자막 텍스트를 duration에 맞게 분할하여 ASS Dialogue 이벤트 리스트를 반환합니다.

    자막 표출 시간은 subtitle 문장 길이가 아니라 실제로 낭독되는 narration 문장의
    길이에 비례해 배분합니다. narration/subtitle은 표기만 다를 뿐(숫자·영문 표기 차이)
    같은 내용을 담고 있어야 하므로, 문장 수가 일치하면 문장 단위로 1:1 짝지어 각
    narration 문장 길이만큼 시간을 배분하고 그 구간에 대응하는 subtitle 문장을 표시합니다.
    문장 수가 다르면(LLM이 형식을 못 지킨 경우) subtitle 자체의 발화 가중치
    (_speech_weight) 비례로 대체합니다.

    ★ 한 문장이 길어 여러 화면 청크로 쪼개질 때(_split_subtitle_text), 청크별
    시간 배분은 narration 기준 분할점을 알 수 없어 부득이 subtitle 텍스트로
    추정해야 합니다 — 이때 단순 글자 수 대신 _speech_weight()로 숫자 구간의
    실제 발화 길이를 보정합니다(자막은 "85,400"처럼 짧게 쓰지만 내레이션은
    "팔만오천사백원"으로 길게 읽어, 글자 수만 쓰면 숫자 많은 청크가 실제보다
    짧게 배정돼 내레이션과 어긋나 보이는 문제가 있었습니다).
    """
    if not subtitle_text or duration <= 0:
        return []

    narr_sentences = _split_sentences(narration_text)
    sub_sentences  = _split_sentences(subtitle_text)

    if narr_sentences and sub_sentences and len(narr_sentences) == len(sub_sentences):
        pairs = list(zip((len(s) for s in narr_sentences), sub_sentences))
    else:
        # narration과 subtitle 문장 수가 다르면 subtitle 발화 가중치 비례로 대체
        pairs = [(_speech_weight(s), s) for s in (sub_sentences or [subtitle_text])]

    total_weight = sum(w for w, _ in pairs) or 1
    events = []
    t_cursor = start_time

    for weight, sub_sentence in pairs:
        seg_duration = duration * (weight / total_weight)
        chunks = _split_subtitle_text(sub_sentence)
        if not chunks:
            t_cursor += seg_duration
            continue
        chunk_total_len = sum(_speech_weight(c) for c in chunks) or 1
        for chunk in chunks:
            chunk_duration = seg_duration * (_speech_weight(chunk) / chunk_total_len)
            t_start  = t_cursor
            t_end    = t_start + chunk_duration - 0.08
            ass_text = _format_ass_text(chunk)
            events.append(
                f"Dialogue: 0,{_ts(t_start)},{_ts(t_end)},{style},,0,0,0,,{ass_text}"
            )
            t_cursor += chunk_duration

    return events


def generate_ass(sections: list, lang: str, out_path: str,
                 frame_order: list = None, time_scale: float = 1.0,
                 transition_duration: float = 0.0):
    """
    ASS 자막 파일을 생성합니다.

    Args:
        sections:    script.json의 섹션 목록
        lang:        언어 코드 (KO)
        out_path:    출력 ASS 파일 경로
        frame_order: asset_map.json의 frames 순서 (프레임 파일 절대/상대 경로 목록)
        time_scale:  최종 영상이 배속 조정(atempo/setpts)된 경우의 보정 계수.
                     예) 영상을 1.05배속으로 줄였다면 1/1.05를 전달해 자막
                     타임라인도 동일 비율로 줄여야 나레이션과 어긋나지 않습니다.
        transition_duration: 장면 사이에 삽입되는 crossfade/push 전환 클립의
                     길이(초, generate_video.py의 video_renderer.TRANSITION_DURATION과
                     동일한 값을 전달해야 함). video_renderer는 전환을 겹치지
                     않고 "삽입"하므로(오디오 타임라인 불변), 자막 누적 시간도
                     장면과 장면 "사이"마다 이 값만큼만 더해주면 정확히 맞는다
                     (뺄셈 보정이 필요 없다 — video_renderer.py 모듈 docstring 참고).
    """
    subtitle_map = _build_subtitle_map(sections, lang)
    audio_base   = os.path.join("output", lang, "audio")

    print(f"\n  [subtitle] 자막 맵 키 수: {len(subtitle_map)}")
    for k in list(subtitle_map.keys())[:5]:
        print(f"    · {k}: {subtitle_map[k][1][:30]}...")
    if time_scale != 1.0:
        print(f"  [subtitle] 배속 보정 적용: time_scale={time_scale:.4f}")

    events       = []
    current_time = 0.0

    trans_offset = transition_duration * time_scale

    if not frame_order:
        # frame_order 없으면 subtitle_map 순서대로 처리
        print("  [subtitle] ⚠️ frame_order 없음 — subtitle_map 순서로 처리")
        for i, (audio_id, (narration_text, subtitle_text)) in enumerate(subtitle_map.items()):
            if i > 0:
                current_time += trans_offset
            mp3_path = os.path.join(audio_base, f"{audio_id}.mp3")
            duration = _get_audio_duration(mp3_path) * time_scale
            style    = "Warning" if "closing" in audio_id else "Default"
            slide_events = _make_dialogue_events(narration_text, subtitle_text, current_time, duration, style)
            events.extend(slide_events)
            print(f"    {audio_id}: {duration:.1f}s, {len(slide_events)}개 이벤트")
            current_time += duration
    else:
        for i, frame_path in enumerate(frame_order):
            if i > 0:
                current_time += trans_offset
            stem     = os.path.splitext(os.path.basename(frame_path))[0]
            audio_id = _frame_stem_to_audio_id(stem, sections)
            mp3_path = os.path.join(audio_base, f"{audio_id}.mp3")
            duration = _get_audio_duration(mp3_path) * time_scale

            narration_text, subtitle_text = subtitle_map.get(audio_id, ("", ""))

            style = "Warning" if "closing" in audio_id else "Default"

            if subtitle_text:
                slide_events = _make_dialogue_events(narration_text, subtitle_text, current_time, duration, style)
                events.extend(slide_events)
                print(f"  [subtitle] {stem} → {audio_id}: {duration:.1f}s, {len(slide_events)}개 이벤트")
            else:
                print(f"  [subtitle] {stem} → {audio_id}: {duration:.1f}s, 자막 없음")

            current_time += duration

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(ASS_HEADER)
        f.write("\n".join(events))
        f.write("\n")

    mins = int(current_time // 60)
    secs = int(current_time % 60)
    print(f"\n✅ ASS 자막 생성 완료: {out_path}")
    print(f"   이벤트: {len(events)}개 | 총 길이: {mins}분 {secs}초")
    return out_path


def run(lang: str = "KO"):
    lang = lang.upper()

    script_path    = f"output/{lang}/scripts/reordered_script.json"
    asset_map_path = f"output/{lang}/asset_map.json"
    out_path       = f"output/{lang}/subtitles/subtitle.ass"

    if not os.path.isfile(script_path):
        print(f"❌ reordered_script.json 없음: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    sections = script.get("sections", [])

    frame_order = None
    if os.path.isfile(asset_map_path):
        with open(asset_map_path, encoding="utf-8") as f:
            asset_map = json.load(f)
        frame_order = asset_map.get("frames", [])
        print(f"📋 asset_map 로드: {len(frame_order)}개 프레임")
    else:
        print(f"⚠️ asset_map.json 없음: {asset_map_path} — 섹션 순서로 처리")

    generate_ass(sections, lang, out_path, frame_order, transition_duration=TRANSITION_DURATION)


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
