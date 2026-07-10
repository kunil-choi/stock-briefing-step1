# pipeline/assets/render.py
"""
HTML/CSS 슬라이드를 Playwright(Chromium)로 PNG 프레임으로 렌더링한다.
PIL 직접 드로잉 대신 실제 슬라이드(PPT)처럼 레이아웃을 구성해 스크린샷을 뜬다.
프로세스당 브라우저 인스턴스 하나를 재사용하고, 파이프라인 종료 시 close_renderer()로 정리한다.
"""
import os
from playwright.sync_api import sync_playwright

from .config import W, H

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
            page.evaluate(_AUTOFIT_JS)
        except Exception as e:
            print(f"  ⚠️ autofit 텍스트 축소 실패(무시하고 진행): {e}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        page.screenshot(path=out_path)
    finally:
        page.close()
    print(f"  ✅ {os.path.basename(out_path)}")
    return out_path


def close_renderer():
    global _playwright, _browser
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None
