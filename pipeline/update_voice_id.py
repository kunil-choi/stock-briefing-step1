import os
import json
import requests
import glob

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE_NAME = "MyCustomVoice_StockBriefing"
SAMPLE_DIR = "voice_sample"
VOICE_ID_CACHE = "/tmp/new_voice_id.txt"


def get_existing_voice_id(name: str) -> str | None:
    """같은 이름의 Voice Clone이 이미 있으면 ID 반환"""
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": ELEVENLABS_API_KEY}
    )
    if resp.status_code != 200:
        print(f"❌ 보이스 목록 조회 실패: {resp.status_code}")
        return None

    voices = resp.json().get("voices", [])
    for v in voices:
        if v.get("name") == name:
            print(f"  기존 Voice Clone 발견: {v['voice_id']}")
            return v["voice_id"]
    return None


def delete_voice(voice_id: str):
    """기존 Voice Clone 삭제"""
    resp = requests.delete(
        f"https://api.elevenlabs.io/v1/voices/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY}
    )
    if resp.status_code == 200:
        print(f"  🗑️ 기존 Voice Clone 삭제 완료: {voice_id}")
    else:
        print(f"  ⚠️ 삭제 실패: {resp.status_code}")


def create_voice_clone(sample_files: list) -> str | None:
    """새 Voice Clone 생성 후 voice_id 반환"""
    files = []
    for path in sample_files:
        files.append(
            ("files", (os.path.basename(path), open(path, "rb"), "audio/mpeg"))
        )

    resp = requests.post(
        "https://api.elevenlabs.io/v1/voices/add",
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        data={
            "name": VOICE_NAME,
            "description": "Stock briefing custom voice, auto-updated via GitHub Actions"
        },
        files=files
    )

    # 파일 핸들 닫기
    for _, (_, fh, _) in files:
        fh.close()

    if resp.status_code == 200:
        voice_id = resp.json().get("voice_id")
        print(f"  ✅ Voice Clone 생성 완료: {voice_id}")
        return voice_id
    else:
        print(f"  ❌ Voice Clone 생성 실패: {resp.status_code} - {resp.text}")
        return None


def main():
    if not ELEVENLABS_API_KEY:
        raise EnvironmentError("❌ ELEVENLABS_API_KEY 환경변수가 없습니다.")

    # 샘플 파일 수집 (mp3, wav, m4a 지원)
    sample_files = []
    for ext in ["*.mp3", "*.wav", "*.m4a"]:
        sample_files.extend(glob.glob(os.path.join(SAMPLE_DIR, ext)))

    if not sample_files:
        raise FileNotFoundError(f"❌ {SAMPLE_DIR}/ 폴더에 녹음 파일이 없습니다.")

    print(f"📂 샘플 파일 {len(sample_files)}개 발견:")
    for f in sample_files:
        print(f"   - {f}")

    # 기존 Voice Clone 삭제 후 재생성
    existing_id = get_existing_voice_id(VOICE_NAME)
    if existing_id:
        delete_voice(existing_id)

    new_voice_id = create_voice_clone(sample_files)
    if not new_voice_id:
        raise RuntimeError("❌ Voice Clone 생성 실패")

    # 다음 스텝에서 읽을 수 있도록 임시 파일에 저장
    with open(VOICE_ID_CACHE, "w") as f:
        f.write(new_voice_id)

    print(f"\n✅ 완료! 새 Voice ID: {new_voice_id}")
    print(f"   → ELEVENLABS_VOICE_ID Secret이 자동 업데이트됩니다.")


if __name__ == "__main__":
    main()
