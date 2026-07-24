# pipeline/assets/panel_avatars.py
"""
전문가·방송 언급 화면(builders._build_mention_page)에 쓰는 일반화된 일러스트
아바타 10종(assets/character/avatar_01.png ~ avatar_10.png, generate_panel_avatars.py로
생성) 중 하나를 발언자/채널 이름으로 결정적으로 골라준다.

실제 인물의 얼굴이 아니라 순수 일러스트이므로 "이 아바타가 실제로 그
사람과 닮았는지"는 애초에 고려 대상이 아니다 — 같은 발언자·채널은 매번
같은 아바타를 쓰도록 이름을 해시해 안정적으로 배정하는 것만이 목적이다
(방송 안에서 같은 사람이 여러 장면에 걸쳐 다른 얼굴로 보이면 오히려
어색하므로).
"""
import hashlib
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_AVATAR_DIR = os.path.join(_HERE, "..", "..", "assets", "character")
AVATAR_COUNT = 10


def get_avatar_path(name: str) -> str:
    """name(발언자 이름 또는 채널명)을 해시해 avatar_NN.png 경로를 반환한다.
    빈 문자열이 들어와도(예: 채널명 없음) 항상 유효한 경로 하나를 반환한다."""
    key = (name or "").strip() or "default"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    idx = int(digest, 16) % AVATAR_COUNT + 1
    return os.path.join(_AVATAR_DIR, f"avatar_{idx:02d}.png")
