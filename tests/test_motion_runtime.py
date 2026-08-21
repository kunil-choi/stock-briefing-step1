# tests/test_motion_runtime.py
"""
html_theme.MOTION_JS(window.__setT(t) 애니메이션 런타임) 검증 스크립트.
pytest 미사용, 다른 tests/*.py와 동일하게 순수 assert 기반. Playwright로
실제 페이지에 로드해 __setT(t)를 여러 t로 호출하며 DOM 상태를 확인한다
(ffmpeg 불필요 — 정지 화면 검증이 아니라 JS 실행 결과만 본다).

Playwright가 설치돼 있지 않거나 브라우저 실행에 실패하면 스킵 메시지만
출력하고 통과 처리한다.

실행: python tests/test_motion_runtime.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PIPELINE = os.path.join(_HERE, "..", "pipeline")
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)


def _playwright_available():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b.close()
        return True
    except Exception as e:
        print(f"⚠️  Playwright 브라우저 실행 불가 — motion_runtime 테스트 스킵: {e}")
        return False


_TEST_HTML = """
<div id="c" data-anim="count" data-to="3152.47" data-decimals="2" data-suffix="pt"
     data-delay="0.2" data-dur="0.9">0</div>
<div id="g" data-anim="grow" data-to="72" data-delay="0" data-dur="0.8"
     style="width:0%;"></div>
<div id="f" data-anim="fadeup" data-delay="0" data-dur="0.5"
     style="opacity:0;transform:translateY(26px);"></div>
<div id="p" data-anim="pop" data-delay="0.5" data-dur="0.35"
     style="opacity:0;transform:scale(0.6);"></div>
<svg><path id="d" data-anim="draw" data-delay="0" data-dur="1.0"
     d="M0,0 L100,0 L100,100" /></svg>
<svg><circle id="dot" data-anim="dot" data-points="0,0;50,10;100,100" data-delay="0" data-dur="1.0"
     cx="100" cy="100" r="5" /></svg>
"""


def _load_page(pw_page):
    from assets.html_theme import shell
    html = shell("모션 런타임 테스트", _TEST_HTML)
    pw_page.set_content(html, wait_until="load")


def test_count_reaches_exact_target_with_formatting():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        page.evaluate("() => window.__setT(0.0)")
        assert page.eval_on_selector("#c", "el => el.textContent") == "0.00pt"

        # delay=0.2, dur=0.9 → t=1.1이면 (t-delay)/dur = 1.0 → 정확히 target
        page.evaluate("() => window.__setT(1.1)")
        text = page.eval_on_selector("#c", "el => el.textContent")
        assert text == "3,152.47pt", f"천단위 콤마/소수점/suffix 포맷이 예상과 다름: {text}"
        b.close()
    print("✅ count: delay/dur 경과 후 정확히 target(천단위 콤마 포함)에 도달")


def test_grow_width_percentage():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        page.evaluate("() => window.__setT(0.0)")
        assert page.eval_on_selector("#g", "el => el.style.width") == "0%"

        page.evaluate("() => window.__setT(0.8)")
        w = page.eval_on_selector("#g", "el => el.style.width")
        assert w == "72%", f"grow가 dur 경과 후 정확히 target%에 도달해야 함: {w}"
        b.close()
    print("✅ grow: width가 0%에서 target%까지 정확히 성장")


def test_fadeup_opacity_and_translate():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        page.evaluate("() => window.__setT(0.0)")
        op0 = page.eval_on_selector("#f", "el => el.style.opacity")
        assert op0 == "0", f"t=0이면 opacity 0이어야 함: {op0}"

        page.evaluate("() => window.__setT(0.5)")
        op1 = float(page.eval_on_selector("#f", "el => el.style.opacity"))
        tf1 = page.eval_on_selector("#f", "el => el.style.transform")
        assert op1 >= 0.99, f"dur 경과 후 거의 완전히 보여야 함: {op1}"
        assert "translateY(0" in tf1 or "translateY(0px)" in tf1, f"dur 경과 후 원위치여야 함: {tf1}"
    print("✅ fadeup: opacity 0→1, translateY 26px→0 확인")


def test_pop_scale_and_opacity():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        # delay=0.5 이전에는 아직 시작 전(scale 0.6, opacity 0)
        page.evaluate("() => window.__setT(0.3)")
        op0 = page.eval_on_selector("#p", "el => el.style.opacity")
        assert op0 == "0", f"delay 이전엔 opacity 0이어야 함: {op0}"

        page.evaluate("() => window.__setT(0.85)")
        tf = page.eval_on_selector("#p", "el => el.style.transform")
        op = float(page.eval_on_selector("#p", "el => el.style.opacity"))
        assert "scale(1)" in tf, f"delay+dur 경과 후 scale(1)이어야 함: {tf}"
        assert op >= 0.99
        b.close()
    print("✅ pop: delay 이전엔 숨김, delay+dur 경과 후 scale(1)/opacity(1)")


def test_draw_dashoffset_reaches_zero():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        page.evaluate("() => window.__setT(0.0)")
        off0 = float(page.eval_on_selector("#d", "el => el.style.strokeDashoffset"))
        length = page.eval_on_selector("#d", "el => el.getTotalLength()")
        assert abs(off0 - length) < 0.5, "t=0이면 dashoffset이 path 전체 길이와 같아야 함(안 그려짐)"

        page.evaluate("() => window.__setT(1.0)")
        off1 = float(page.eval_on_selector("#d", "el => el.style.strokeDashoffset"))
        assert abs(off1) < 0.5, f"dur 경과 후 dashoffset이 0이어야 함(선이 다 그려짐): {off1}"
        b.close()
    print("✅ draw: dashoffset이 path 길이→0으로 진행(선이 그려지는 효과)")


def test_dot_tracks_draw_progress_not_final_point():
    """svg_line_chart()의 광점: 선이 그려지는 진행률(p)에 따라 방금 그려진
    지점으로 cx/cy가 옮겨가야 한다 — 처음부터 최종 지점에 고정돼 있으면
    안 된다(육안 검증에서 실제로 발견한 버그의 회귀 가드)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        page.evaluate("() => window.__setT(0.0)")
        cx0 = float(page.eval_on_selector("#dot", "el => el.getAttribute('cx')"))
        assert cx0 == 0.0, f"t=0이면 첫 점(0,0)에 있어야 함: cx={cx0}"

        page.evaluate("() => window.__setT(0.5)")
        cx_mid = float(page.eval_on_selector("#dot", "el => el.getAttribute('cx')"))
        assert cx_mid == 50.0, f"진행률 50%면 가운데 점(50,10)에 있어야 함: cx={cx_mid}"

        page.evaluate("() => window.__setT(1.0)")
        cx_end = float(page.eval_on_selector("#dot", "el => el.getAttribute('cx')"))
        assert cx_end == 100.0, f"완료 시 마지막 점(100,100)에 있어야 함: cx={cx_end}"
        b.close()
    print("✅ dot: 최종 지점에 고정되지 않고 draw 진행률을 따라 이동")


def test_setT_is_pure_and_idempotent():
    """같은 t를 여러 번(임의 순서로) 넣어도 항상 같은 DOM 상태가 나와야 한다
    — render_html_to_frames()가 프레임을 다시 캡처하거나 순서를 바꿔도
    안전해야 하므로(문서 P1-2 요구사항)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        _load_page(page)

        def snapshot(t):
            page.evaluate(f"() => window.__setT({t})")
            return page.eval_on_selector_all(
                "[data-anim]",
                "els => els.map(el => el.textContent + '|' + el.style.width + '|' "
                "+ el.style.opacity + '|' + el.style.transform + '|' + el.style.strokeDashoffset)"
            )

        s1 = snapshot(0.45)
        page.evaluate("() => window.__setT(0.9)")  # 다른 t로 이동
        s2 = snapshot(0.45)  # 같은 t로 복귀
        s3 = snapshot(0.1)
        s4 = snapshot(0.45)  # 순서를 뒤섞어도

        assert s1 == s2 == s4, f"같은 t인데 상태가 다름(순수 함수 위반): {s1} vs {s2} vs {s4}"
        assert s1 != s3, "sanity check: 다른 t는 다른 상태여야 함"
        b.close()
    print("✅ __setT(t): 순수 함수 확인(같은 t → 항상 같은 결과, 호출 순서 무관)")


if __name__ == "__main__":
    if not _playwright_available():
        sys.exit(0)

    test_count_reaches_exact_target_with_formatting()
    test_grow_width_percentage()
    test_fadeup_opacity_and_translate()
    test_pop_scale_and_opacity()
    test_draw_dashoffset_reaches_zero()
    test_dot_tracks_draw_progress_not_final_point()
    test_setT_is_pure_and_idempotent()
    print("\n✅ motion_runtime 테스트 전체 통과")
