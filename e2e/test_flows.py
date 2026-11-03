"""Browser end-to-end checks. Run the app first (see README), then:
    pip install playwright && playwright install chromium
    python e2e/test_flows.py            # BASE_URL=http://localhost:8000 by default
Screenshots land in e2e/shots/. This is a script, not part of the pytest suite or CI."""
import os
import pathlib
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
SHOTS = pathlib.Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)
errors = []


def ok(name):
    print("PASS", name, flush=True)


def check(pg):
    pg.get_by_role("button", name="Check").click()
    pg.wait_for_timeout(1400)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE)
        pg.wait_for_selector("text=Know when to get care")
        res = pg.locator("section.result")
        pg.screenshot(path=SHOTS / "01_home.png")
        pg.screenshot(path=SHOTS / "01_home_full.png", full_page=True)

        check(pg)
        expect(res.locator(".level")).to_have_text("Low so far")
        expect(res.locator(".ask")).to_contain_text("Haemoglobin (blood) test")
        ok("empty -> Low so far + asks")
        pg.screenshot(path=SHOTS / "02_low_so_far.png")
        res.get_by_role("button", name="Show family").click()
        expect(pg.locator("dialog.family .level")).to_have_text("Low so far")
        pg.locator("dialog.family").get_by_role("button", name="Close").click()
        ok("show family opens and closes")

        pg.get_by_role("button", name="Clear").click()
        pg.fill("#weeks", "30")
        pg.get_by_text("Bleeding from the vagina").click()
        pg.get_by_text("Severe belly pain").click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Go now")
        expect(res.locator(".chips")).to_contain_text("Vaginal bleeding")
        assert res.locator(".ask").count() == 0
        ok("bleeding -> Go now, no ask-for")
        pg.screenshot(path=SHOTS / "03_go_now.png")
        res.get_by_role("button", name="Show family").click()
        pg.wait_for_timeout(250)
        pg.screenshot(path=SHOTS / "04_family.png")
        pg.locator("dialog.family").get_by_role("button", name="Close").click()

        pg.get_by_role("button", name="Clear").click()
        pg.fill("#weeks", "30")
        pg.locator("details.numbers summary").click()
        pg.fill("#hb", "8.5")
        check(pg)
        expect(pg.locator(".errors")).to_contain_text("when the blood test was done")
        assert pg.locator("section.result").count() == 0
        ok("Hb without date is blocked")
        pg.screenshot(path=SHOTS / "05_error.png")
        pg.get_by_text("Last 4 weeks").click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Watch")
        expect(res.locator(".chips")).to_contain_text("Moderate anaemia")
        ok("Hb 8.5 recent -> Watch")
        pg.screenshot(path=SHOTS / "06_watch.png")

        pg.get_by_role("button", name="Clear").click()
        pg.locator("details.numbers summary").click()
        pg.fill("#bps", "175")
        pg.fill("#bpd", "112")
        pg.get_by_text("Earlier", exact=True).click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Watch")
        ok("earlier severe BP -> Watch, not Go now")
        pg.get_by_text("Today", exact=True).click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Go now")
        ok("same BP today -> Go now")
        pg.fill("#bps", "-4")
        pg.fill("#bpd", "7")
        check(pg)
        expect(pg.locator(".errors")).to_contain_text("must be between")
        assert pg.locator("section.result").count() == 0
        ok("impossible BP is blocked and the old result is removed")

        pg.get_by_role("button", name="Clear").click()
        pg.fill("#weeks", "28")
        pg.locator("details.numbers summary").click()
        pg.fill("#hb", "12.4")
        pg.get_by_text("Last 4 weeks").click()
        pg.fill("#bps", "112")
        pg.fill("#bpd", "72")
        pg.get_by_text("Today", exact=True).click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Low")
        assert res.locator(".ask").count() == 0
        ok("complete current numbers -> plain Low")
        pg.screenshot(path=SHOTS / "07_low.png")

        # ---- real offline: service worker takes over, then the network goes away ----
        pg.evaluate("navigator.serviceWorker.ready.then(() => true)")
        pg.reload()
        pg.wait_for_selector("text=Know when to get care")
        pg.wait_for_function("navigator.serviceWorker.controller !== null")
        ctx.set_offline(True)
        pg.reload()
        pg.wait_for_selector("text=Know when to get care")
        ok("app loads with the network off (service worker)")
        pg.fill("#weeks", "30")
        pg.get_by_text("Severe headache").click()
        pg.get_by_text("Swelling of face or hands").click()
        check(pg)
        expect(res.locator(".level")).to_have_text("Go now")
        res.get_by_text("Explain in plain words").click()
        expect(res).to_contain_text("No connection")
        ok("offline: result still works, explanation says 'No connection'")
        pg.screenshot(path=SHOTS / "08_offline.png")
        ctx.set_offline(False)

        # ---- desktop ----
        d = b.new_page(viewport={"width": 1280, "height": 900})
        d.goto(BASE)
        d.wait_for_selector("text=Know when to get care")
        d.screenshot(path=SHOTS / "09_desktop.png")
        b.close()
    real = [e for e in errors if "net::ERR" not in e]
    print("page errors:", real)
    sys.exit(1 if real else 0)


if __name__ == "__main__":
    main()
