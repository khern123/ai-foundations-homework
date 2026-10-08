"""Design review on the running app (:5173 + :8000): screenshots + contrast + focus + overflow checks."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
WEB = "http://localhost:5173"


def lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


pairs = [("Body text #14213d on white", "#14213d", "#ffffff", 4.5), ("Muted #5b6678 on white", "#5b6678", "#ffffff", 4.5),
         ("Pink text #b3165a on white", "#b3165a", "#ffffff", 4.5), ("White on navy #0b2545", "#ffffff", "#0b2545", 4.5),
         ("Brand pink #f6a8c4 on navy", "#f6a8c4", "#0b2545", 4.5), ("Focus ring #e0457b on white", "#e0457b", "#ffffff", 3.0),
         ("Focus ring #e0457b on navy", "#e0457b", "#0b2545", 3.0), ("Muted on panel #f6f8fb", "#5b6678", "#f6f8fb", 4.5)]
for name, fg, bg, need in pairs:
    r = ratio(fg, bg)
    print(f"{'PASS' if r >= need else 'FAIL'} contrast {name}: {r:.2f}:1 (needs {need})")

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True, args=["--no-proxy-server"])
    for label, vp in [("desktop", {"width": 1280, "height": 860}), ("mobile", {"width": 390, "height": 844})]:
        pg = b.new_page(viewport=vp)
        for name, path in [("home", "/"), ("products", "/products"), ("detail", "/products/davenport-college-crewneck"), ("login", "/login")]:
            pg.goto(WEB + path)
            pg.get_by_role("heading", level=1).first.wait_for()
            pg.wait_for_timeout(700)
            imgs_ok = pg.evaluate("[...document.images].filter(i => i.complete && i.getBoundingClientRect().top < innerHeight).every(i => i.naturalWidth > 0)")
            fits = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
            print(f"{'PASS' if imgs_ok and fits else 'FAIL'} {label} {name}: images ok={imgs_ok}, no sideways scroll={fits}")
            pg.screenshot(path=OUT / f"{label}_{name}.png")
        pg.goto(WEB + "/products/davenport-college-crewneck")
        pg.get_by_role("button", name="Open chat").click()
        pg.wait_for_timeout(400)
        pg.screenshot(path=OUT / f"{label}_chat.png")
        pg.keyboard.press("Escape")
        pg.keyboard.press("Tab")
        outline = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle + ' ' + getComputedStyle(document.activeElement).outlineColor")
        print(f"{'PASS' if outline.startswith('solid') else 'FAIL'} {label} keyboard focus visible: {outline}")
        motion = pg.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
        pg.emulate_media(reduced_motion="reduce")
        anim = pg.locator(".product-img").first.evaluate("e => getComputedStyle(e.closest('.product-card') || e).animationName") if pg.locator(".product-img").count() else "none"
        print(f"{'PASS' if anim == 'none' else 'FAIL'} {label} reduced motion disables card animation (was {motion}): {anim}")
        pg.close()
    b.close()
