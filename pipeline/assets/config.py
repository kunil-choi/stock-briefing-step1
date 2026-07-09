# pipeline/assets/config.py
import os
import re

W, H = 1920, 1080

SUBTITLE_ZONE_TOP = 890  # 자막 전용 영역 시작 Y좌표(하단 190px 고정 여백). 콘텐츠(카드/차트/표)는
                          # 이 Y좌표 아래로 내려가면 안 되고, 자막은 이 영역 안에서만 표출됨.

# FIX-PPT-THEME: 다크 방송그래픽 팔레트 → 밝은 슬라이드(PPT) 팔레트로 교체.
# 한국 증권 관행(상승=빨강/하락=파랑)은 그대로 유지하고, 배경만 라이트 테마로 전환.
C = {
    "bg":             (250, 249, 246),
    "gold":           (14,  159, 142),   # 기존 "gold" 강조색 → 틸/민트 액센트로 재사용
    "white":          (22,  24,  29),    # 라이트 테마이므로 "white"는 기본 잉크(텍스트)색
    "green":          (14,  159, 142),
    "red":            (224,  57,  62),   # 상승
    "blue":           ( 47, 111, 237),   # 하락
    "card":           (255, 255, 255),
    "border":         (232, 230, 223),
    "tag_bg":         (227, 247, 243),
    "hidden_accent":  (255, 224, 102),
    "chart_bg":       (255, 255, 255),
    "chart_up":       (224,  57,  62),
    "chart_down":     ( 47, 111, 237),
    "chart_grid":     (236, 236, 229),
    "chart_text":     (107, 114, 128),
}

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FONT_PATHS = {
    "bold": [
        os.path.join(_BASE, "assets", "fonts", "NotoSansKR-Bold.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Bold.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/NanumGothicBold.ttf",
    ],
    "regular": [
        os.path.join(_BASE, "assets", "fonts", "NotoSansKR-Regular.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/NanumGothic.ttf",
    ],
}

STOCK_CODES = {
    # ── v3 브리핑 데이터 핵심 종목 ─────────────────────────────────────
    "삼성생명":           "032830",
    "삼성SDI":            "006400",
    "LG화학":             "051910",
    "NH투자증권":         "005940",
    "올릭스":             "226950",
    "한글과컴퓨터":       "030520",
    "메타바이오메드":     "059210",
    "이오테크닉스":       "039030",
    "삼양엔씨켐":         "000415",
    "코셈":               "086390",
    "다원넥스뷰":         "313760",
    "벡트":               "B110010",
    "지구홀딩스":         "253590",
    "드림텍":             "bluepar",
    "워트":               "396060",
    "CJ프레시웨이":       "051500",
    "성우":               "204620",
    # ── 기존 종목 ──────────────────────────────────────────────────────
    "삼성전자":           "005930",
    "SK하이닉스":         "000660",
    "현대차":             "005380",
    "현대로템":           "064350",
    "현대위아":           "011210",
    "신세계":             "004170",
    "두산에너빌리티":     "034020",
    "크래프톤":           "259960",
    "하이브":             "352820",
    "에이피알":           "278470",
    "기아":               "000270",
    "LG에너지솔루션":     "373220",
    "POSCO홀딩스":        "005490",
    "삼성바이오로직스":   "207940",
    "카카오":             "035720",
    "네이버":             "035420",
    "셀트리온":           "068270",
    "한화에어로스페이스": "012450",
    "HD현대중공업":       "329180",
    "한국항공우주":       "047810",
    "LIG넥스원":          "079550",
    "에코프로비엠":       "247540",
    "포스코퓨처엠":       "003670",
    "삼성전기":           "009150",
    "현대모비스":         "012330",
    "KB금융":             "105560",
    "신한지주":           "055550",
    "하나금융지주":       "086790",
    "카카오뱅크":         "323410",
    "엔씨소프트":         "036570",
    # ─── 신규 추가 ───────────────────────────────
    "파마리서치":         "214450",
    "STX엔진":            "077970",
    "한화시스템":         "272210",
    "LIG넥스원":          "079550",
    "풍산":               "103140",
    "한전기술":           "052690",
    "두산퓨얼셀":         "336260",
    "LS일렉트릭":         "010120",
    "효성중공업":         "298040",
    "HD현대일렉트릭":     "267260",
    "삼성중공업":         "010140",
    "대우조선해양":       "042660",
    "현대건설":           "000720",
    "GS건설":             "006360",
    "대한항공":           "003490",
    "아시아나항공":       "020560",
    "에코프로":           "086520",
    "포스코인터내셔널":   "047050",
    "고려아연":           "010130",
    "OCI홀딩스":          "010060",
}

STOCK_NAME_ALIASES = {
    "SK 하이닉스":           "SK하이닉스",
    "SK하이닉스스":          "SK하이닉스",
    "현대 차":               "현대차",
    "현대자동차":            "현대차",
    "두산 에너빌리티":       "두산에너빌리티",
    "두산에너":              "두산에너빌리티",
    "한화 에어로스페이스":   "한화에어로스페이스",
    "POSCO 홀딩스":          "POSCO홀딩스",
    "포스코홀딩스":          "POSCO홀딩스",
    "LG 에너지솔루션":       "LG에너지솔루션",
    "LG에너지 솔루션":       "LG에너지솔루션",
    "삼성 전자":             "삼성전자",
    "삼성 전기":             "삼성전기",
    "삼성바이오":            "삼성바이오로직스",
    "카카오 뱅크":           "카카오뱅크",
    "HD 현대중공업":         "HD현대중공업",
    "한국 항공우주":         "한국항공우주",
    "현대 로템":             "현대로템",
    "현대 위아":             "현대위아",
    "에코프로 비엠":         "에코프로비엠",
    "포스코 퓨처엠":         "포스코퓨처엠",
    "현대 모비스":           "현대모비스",
    "신한 지주":             "신한지주",
    "하나 금융지주":         "하나금융지주",
    "하나금융":              "하나금융지주",
    "KB 금융":               "KB금융",
    "엔씨":                  "엔씨소프트",
    # ─── 신규 추가 ───────────────────────────────
    "파마리서치코리아":      "파마리서치",
    "파마 리서치":           "파마리서치",
    "STX 엔진":              "STX엔진",
    "에스티엑스엔진":        "STX엔진",
    "한화 시스템":           "한화시스템",
    "LIG 넥스원":            "LIG넥스원",
    "LS 일렉트릭":           "LS일렉트릭",
    "효성 중공업":           "효성중공업",
    "HD현대 일렉트릭":       "HD현대일렉트릭",
    "HD 현대일렉트릭":       "HD현대일렉트릭",
    "삼성 중공업":           "삼성중공업",
    "대우 조선해양":         "대우조선해양",
    "현대 건설":             "현대건설",
    "GS 건설":               "GS건설",
    "대한 항공":             "대한항공",
    "아시아나 항공":         "아시아나항공",
    "포스코 인터내셔널":     "포스코인터내셔널",
    "고려 아연":             "고려아연",
    "OCI 홀딩스":            "OCI홀딩스",
    "두산 퓨얼셀":           "두산퓨얼셀",
    "한전 기술":             "한전기술",
}


def normalize_stock_name(name: str) -> str:
    name = name.strip()
    if name in STOCK_NAME_ALIASES:
        return STOCK_NAME_ALIASES[name]
    no_space = name.replace(" ", "")
    if no_space in STOCK_CODES:
        return no_space
    for alias, canonical in STOCK_NAME_ALIASES.items():
        if alias.replace(" ", "") == no_space:
            return canonical
    return name


# ── 채널 성격 분류 (경제방송 vs 유튜브) ──────────────────────────────────────
# 공중파/종편/케이블 증권방송 채널명을 등록해 두면 "경제방송"으로 표시되고,
# 목록에 없는 채널명은 모두 "유튜브"로 간주합니다(개인/기업 유튜브 채널 다수 대응).
ECONOMIC_BROADCAST_CHANNELS = {
    "한국경제TV", "한국경제tv", "매일경제TV", "매경TV", "MBN", "SBS Biz", "SBS비즈",
    "YTN", "YTN사이언스", "연합뉴스TV", "이데일리TV", "이데일리", "머니투데이방송", "MTN",
    "서울경제TV", "아시아경제TV", "KBS", "KBS뉴스", "SBS", "MBC", "채널A",
    "TV조선", "JTBC", "블룸버그", "Bloomberg", "CNBC",
}


def classify_channel_type(channel: str) -> str:
    """채널명을 '경제방송' 또는 '유튜브'로 분류합니다."""
    name = (channel or "").strip()
    if not name:
        return ""
    for known in ECONOMIC_BROADCAST_CHANNELS:
        if known.lower() in name.lower() or name.lower() in known.lower():
            return "경제방송"
    return "유튜브"


# 일부 소스 데이터는 channel 필드에 실제 채널명 대신 "유튜브"/"경제방송" 같은
# 대분류 값만 담아 보내고, 실제 채널명은 speaker(main_speaker) 필드에 넣어 둔다.
# 이를 그대로 렌더링하면 channel_type 배지와 channel 배지가 똑같은 문구로 중복
# 표시되는 문제가 생기므로, 아래 함수로 정규화한다.
_COARSE_CHANNEL_LABELS = {"유튜브", "youtube", "유튜브채널", "유튜브 채널", "경제방송", "증권방송", "방송"}


def _is_coarse_channel_label(text: str) -> bool:
    return (text or "").strip().lower() in {lbl.lower() for lbl in _COARSE_CHANNEL_LABELS}


def resolve_channel_identity(channel: str, speaker: str):
    """
    channel/speaker 필드 표기가 뒤섞인 소스 데이터를 정규화합니다.
    - channel 문자열에 대분류 단어가 섞여 있으면 제거해 실제 채널명만 남깁니다
      (예: "이데일리TV 유튜브" → "이데일리TV").
    - channel이 대분류 단어 자체이고 speaker에 실제 채널명이 들어온 경우,
      그 값을 channel로 승격시키고 speaker는 미상으로 비웁니다
      (예: channel="유튜브", speaker="815머니톡" → channel="815머니톡", speaker="").
    반환: (channel, speaker) 정리된 튜플.
    """
    channel = (channel or "").strip()
    speaker = (speaker or "").strip()

    cleaned = channel
    for label in _COARSE_CHANNEL_LABELS:
        cleaned = re.sub(rf"\s*[\(\[]?\s*{re.escape(label)}\s*[\)\]]?\s*", " ",
                          cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    if cleaned:
        channel = cleaned
    elif speaker and _is_coarse_channel_label(channel):
        channel, speaker = speaker, ""

    return channel, speaker


NEWS_IMAGE_FALLBACKS = {
    "삼성전자":       "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Samsung_Logo.svg/800px-Samsung_Logo.svg.png",
    "SK하이닉스":     "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/SK_Hynix_Logo.svg/800px-SK_Hynix_Logo.svg.png",
    "현대차":         "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Hyundai_Motor_Company_logo.svg/800px-Hyundai_Motor_Company_logo.svg.png",
    "현대로템":       "https://www.hyundai-rotem.co.kr/images/common/logo.png",
    "두산에너빌리티": "https://www.doosan.com/images/common/logo_doosan.png",
    # ─── 신규 추가 ───────────────────────────────
    "파마리서치":     "https://upload.wikimedia.org/wikipedia/ko/thumb/5/5e/Pharmaresearch_logo.png/320px-Pharmaresearch_logo.png",
    "STX엔진":        "https://upload.wikimedia.org/wikipedia/ko/thumb/2/2e/STX_Engine_logo.png/320px-STX_Engine_logo.png",
    "한화에어로스페이스": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Hanwha_logo.svg/800px-Hanwha_logo.svg.png",
    "한화시스템":     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Hanwha_logo.svg/800px-Hanwha_logo.svg.png",
    "LIG넥스원":      "https://upload.wikimedia.org/wikipedia/ko/thumb/8/8e/LIG_Nex1_logo.png/320px-LIG_Nex1_logo.png",
    "HD현대중공업":   "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/HD_Hyundai_logo.svg/800px-HD_Hyundai_logo.svg.png",
    "한국항공우주":   "https://upload.wikimedia.org/wikipedia/ko/thumb/9/9e/Korea_Aerospace_Industries_logo.png/320px-Korea_Aerospace_Industries_logo.png",
}
