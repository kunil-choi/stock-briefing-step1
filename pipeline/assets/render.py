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
