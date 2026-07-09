import os
import json
import glob
import shutil

# dawidd6/action-download-artifact@v3 는 artifact 이름 폴더를 한 단계 더 만들어서 저장함
# 예: output/KO/frames_raw/generated-assets-123/00_opening.png
# → output/KO/frames/ 로 모두 이동 후 asset_map 생성

RAW_DIR    = "output/KO/frames_raw"
FRAMES_DIR = "output/KO/frames"

os.makedirs(FRAMES_DIR, exist_ok=True)

# 하위 폴더 포함 전체 PNG 탐색
all_pngs = glob.glob(os.path.join(RAW_DIR, "**", "*.png"), recursive=True)

if not all_pngs:
    # frames_raw 가 없거나 비어있으면 frames 디렉토리 직접 탐색 (fallback)
    all_pngs = glob.glob(os.path.join(FRAMES_DIR, "**", "*.png"), recursive=True)
    print(f"⚠️ frames_raw 비어있음 → frames 디렉토리 직접 사용 ({len(all_pngs)}개)")
else:
    # frames_raw → frames 로 파일 이동
    for src in all_pngs:
        dst = os.path.join(FRAMES_DIR, os.path.basename(src))
        shutil.copy2(src, dst)
    print(f"✅ {len(all_pngs)}개 PNG → {FRAMES_DIR} 복사 완료")

# frames 디렉토리 기준으로 최종 목록 생성 (정렬)
frames_raw = sorted(glob.glob(os.path.join(FRAMES_DIR, "*.png")))

# ── 수정 5: 중복 파일명 제거 ──────────────────────────────────────────────
seen_basenames = set()
frames = []
for f in frames_raw:
    basename = os.path.basename(f)
    if basename not in seen_basenames:
        seen_basenames.add(basename)
        frames.append(f)
    else:
        print(f"  ⚠️ 중복 프레임 제거됨: {basename}")

asset_map = {"frames": frames, "lang": "KO"}
out_path = "output/KO/asset_map.json"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(asset_map, f, ensure_ascii=False, indent=2)

print(f"✅ asset_map.json 생성 완료 ({len(frames)}개 프레임)")
for f in frames:
    print(f"   {f}")
