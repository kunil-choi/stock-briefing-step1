# pipeline/assets/render.py
"""
HTML/CSS 슬라이드를 Playwright(Chromium)로 PNG 프레임으로 렌더링한다.
PIL 직접 드로잉 대신 실제 슬라이드(PPT)처럼 레이아웃을 구성해 스크린샷을 뜬다.
프로세스당 브라우저 인스턴스 하나를 재사용하고, 파이프라인 종료 시 close_renderer()로 정리한다.
"""
import os
import time
from playwright.sync_api import sync_playwright

from .config import W, H

# 영상 모션그래픽 업그레이드(Phase 1) — 장면당 애니메이션을 캡처하는 길이/fps.
# GitHub Actions 러너(2코어)에서 15분 영상 전체를 30fps로 캡처하면 27,000장이
# 되어 절대 완주할 수 없다 — 그래서 각 장면의 "등장" 구간(앞 MOTION_LEAD_SECONDS
# 초)만 캡처하고 나머지는 마지막 프레임을 정지 홀드한다(video_renderer.py의
# compose_scene() 참고). 24fps는 30fps보다 러너에 유리하면서도 육안으로 끊김이
# 느껴지지 않는 절충값이다.
MOTION_LEAD_SECONDS = float(os.environ.get("MOTION_LEAD_SECONDS", "3.0"))
MOTION_FPS = int(os.environ.get("MOTION_FPS", "24"))

# __setT(t)에 이 값을 넣으면(ease()가 진행률을 0~1로 클램프하므로) delay/dur가
# 뭐든 모든 data-anim 요소가 항상 "완료" 상태로 정착한다 — 정지 PNG(대표
# 썸네일/폴백/워크플로우 glob 대상)는 항상 이 완료 상태로 찍어야 한다(t=0으로
# 찍으면 카운트업 전 "0", 성장 전 빈 막대 같은 미완성 화면이 저장되어 버림).
_MOTION_SETTLED_T = 999

_playwright = None
_browser = None

# 스크린샷 직전에 [data-autofit="true"] 요소들을 실측해 data-max-lines를
# 넘치면 폰트 크기를 data-min-font까지 줄인다(html_theme.autofit_text() 참고).
# -webkit-line-clamp CSS가 이미 안전망으로 걸려 있으므로, 이 스크립트가 실패해도
# 화면 밖으로 흘러넘치지는 않는다(요구사항 5의 실측 기반 1차 보정 담당).
_AUTOFIT_JS = """
() => {
  const els = document.querySelectorAll('[data-autofit="true"]');
  els.forEach(el => {
    const maxLines = parseInt(el.dataset.maxLines || '2', 10);
    const minFont = parseInt(el.dataset.minFont || '16', 10);
    const style = window.getComputedStyle(el);
    let fontSize = parseFloat(style.fontSize);
    const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.35;
    const maxHeight = lineHeight * maxLines + 1;
    let guard = 0;
    while (el.scrollHeight > maxHeight && fontSize > minFont && guard < 40) {
      fontSize -= 1;
      el.style.fontSize = fontSize + 'px';
      guard++;
    }
  });
}
"""


def _get_browser():
    global _playwright, _browser
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch()
    return _browser


def render_html_to_png(html: str, out_path: str) -> str:
    browser = _get_browser()
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    try:
        page.set_content(html, wait_until="load")
        try:
            # @font-face로 임베드한 커스텀 서체(예: 썸네일 헤드라인용 Black Han
            # Sans)가 "load" 이벤트 시점엔 아직 파싱 전일 수 있어, 폰트가 실제
            # 적용된 뒤에 오토핏 측정/스크린샷을 하도록 기다린다.
            page.evaluate("() => document.fonts.ready")
        except Exception as e:
            print(f"  ⚠️ 폰트 로딩 대기 실패(무시하고 진행): {e}")
        _settle_motion(page)
        try:
            page.evaluate(_AUTOFIT_JS)
        except Exception as e:
            print(f"  ⚠️ autofit 텍스트 축소 실패(무시하고 진행): {e}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        page.screenshot(path=out_path)
    finally:
        page.close()
    print(f"  ✅ {os.path.basename(out_path)}")
    return out_path


def _settle_motion(page) -> None:
    """이 페이지에 MOTION_JS(html_theme.MOTION_JS)가 실려 있으면 모든
    data-anim 요소를 "완료" 상태로 고정한다. 정지 PNG(대표 썸네일/렌더링
    실패 시 폴백/워크플로우 glob 대상)는 카운트업 도중("0")이나 성장 전
    (빈 막대) 같은 미완성 화면이 아니라 항상 완성된 최종 상태로 찍혀야
    한다. data-anim 마커가 없는 일반 정지 슬라이드에는 아무 영향이 없다
    (__setT가 순회할 요소가 없음)."""
    try:
        has_motion = page.evaluate("() => typeof window.__setT === 'function'")
        if has_motion:
            page.evaluate(f"() => window.__setT({_MOTION_SETTLED_T})")
    except Exception as e:
        print(f"  ⚠️ 모션 상태 고정 실패(무시하고 진행): {e}")


def render_html_to_frames(html: str, out_dir: str, lead: float = None,
                           fps: int = None) -> list:
    """애니메이션 HTML을 프레임 시퀀스로 캡처한다.

    HTML 안에 window.__setT(t) 함수가 정의되어 있어야 한다(html_theme.MOTION_JS
    — shell()/centered_shell()이 반환하는 모든 HTML에 이미 실려 있다). 페이지는
    한 번만 로드하고, __setT(t)로 상태만 바꿔가며 스크린샷을 찍는다(프레임마다
    set_content()를 다시 부르면 HTML 파싱/폰트 로딩이 반복돼 수십 배 느려짐).

    실제로 data-anim 마커가 있는 슬라이드만 프레임을 캡처한다 — 없으면
    (일반 정지 슬라이드) 즉시 빈 리스트를 반환해 호출부가 기존 정지 PNG
    경로로 자연스럽게 폴백하게 한다. 렌더링 도중 예외가 나도 마찬가지로
    빈 리스트를 반환한다(절대 규칙 2번 — 실패해도 회귀 없음).

    반환값: 캡처된 PNG 경로 리스트(f_00000.png, f_00001.png, ... 순서대로 정렬됨).
    """
    lead = MOTION_LEAD_SECONDS if lead is None else lead
    fps = MOTION_FPS if fps is None else fps
    if lead <= 0 or fps <= 0:
        return []

    browser = _get_browser()
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    started = time.monotonic()
    try:
        page.set_content(html, wait_until="load")
        try:
            page.evaluate("() => document.fonts.ready")
        except Exception as e:
            print(f"  ⚠️ 폰트 로딩 대기 실패(무시하고 진행): {e}")

        has_motion = page.evaluate("() => typeof window.__setT === 'function'")
        has_anim_elements = has_motion and page.evaluate(
            "() => document.querySelectorAll('[data-anim]').length > 0"
        )
        if not has_anim_elements:
            return []

        os.makedirs(out_dir, exist_ok=True)
        frame_paths = []
        n_frames = max(1, int(round(lead * fps)))
        for i in range(n_frames):
            t = i / fps
            page.evaluate(f"() => window.__setT({t})")
            try:
                page.evaluate(_AUTOFIT_JS)
            except Exception:
                pass
            frame_path = os.path.join(out_dir, f"f_{i:05d}.png")
            page.screenshot(path=frame_path)
            frame_paths.append(frame_path)

        # video_renderer._compose_scene_from_frames()가 "-framerate {fps}"로
        # 이 프레임들을 다시 읽을 때 정확히 같은 fps를 써야 lead 클립 길이가
        # 어긋나지 않는다. fps 인자가 호출부에서 오버라이드될 수 있어(이
        # 함수의 fps 파라미터), video_renderer.py 쪽의 MOTION_FPS 상수가
        # 항상 일치한다고 가정하면 위험하다 — 실제로 쓰인 fps를 프레임
        # 디렉토리 자체에 같이 남겨 자기 완결적으로 만든다.
        with open(os.path.join(out_dir, "_fps.txt"), "w", encoding="utf-8") as f:
            f.write(str(fps))

        elapsed = time.monotonic() - started
        print(f"  🎞️ 프레임 시퀀스 캡처: {len(frame_paths)}장 "
              f"({lead:.1f}초, {fps}fps, {elapsed:.1f}초 소요, {os.path.basename(out_dir)})")
        return frame_paths
    except Exception as e:
        print(f"  ⚠️ 프레임 시퀀스 캡처 실패 → 정지 프레임 경로로 폴백: {e}")
        return []
    finally:
        page.close()


def close_renderer():
    global _playwright, _browser
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None
