"""Run against a local Vite server; all API traffic is mocked."""
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    candidate = {
        "symbol": "SPY", "strike": 93, "currentPrice": 100, "dte": 35,
        "expirationDate": "2026-11-24", "netCredit": 96.70, "netReturnPct": 1.04,
        "capitalRequired": 9300, "netBreakEven": 92.03, "netMaxLoss": 9203.30,
        "estimatedRoundTripCosts": 3.30, "bid": 1, "ask": 1.05,
        "bidAskSpreadPct": 4.88, "delta": -.19, "openInterest": 1000,
        "closeTarget": .50, "targetNetProfit": 46.70, "source": "cboe",
    }
    requests = []
    failures = []
    state = {"fail": False}

    def respond(route) -> None:
        url = urlparse(route.request.url)
        if url.path != "/api/scan":
            route.fulfill(json={"status": "ok"})
            return
        params = parse_qs(url.query)
        requests.append(params)
        if state["fail"]:
            route.fulfill(status=503, json={"detail": "测试服务暂不可用"})
            return
        simple = params.get("profile") == ["simple"]
        affordable = float(params.get("max_capital", ["0"])[0]) in (0, 10000)
        rows = [candidate] if simple and affordable else []
        route.fulfill(json={"data": rows, "cached": False, "profile": "simple" if simple else "advanced",
                            "relaxed": False, "noTrade": not rows})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.route("**/api/**", respond)
        page.goto("http://127.0.0.1:5173")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("heading", name="先看现金，再看权利金。")).to_be_visible()
        expect(page.locator(".simple-candidate")).to_have_count(1)
        expect(page.locator(".simple-credit strong")).to_have_text("$96.70")
        page.get_by_text("报价与退出参考", exact=True).click()
        expect(page.get_by_text("若买回价降至", exact=False)).to_be_visible()
        page.screenshot(path="/tmp/option-strategy-desktop.png", full_page=True)

        page.get_by_label("单笔可用现金上限", exact=True).fill("1000")
        page.get_by_role("button", name="应用条件").click()
        expect(page.get_by_role("heading", name="没有符合条件的合约")).to_be_visible()
        expect(page.locator(".simple-candidate")).to_have_count(0)

        page.get_by_label("单笔可用现金上限", exact=True).fill("10000")
        page.get_by_label("每张单边费用", exact=True).fill("1.25")
        page.get_by_role("button", name="应用条件").click()
        expect(page.locator(".simple-candidate")).to_have_count(1)
        assert requests[-1]["fee_per_contract"] == ["1.25"]
        assert requests[-1]["max_capital"] == ["10000"]

        state["fail"] = True
        page.get_by_role("button", name="刷新报价").click()
        expect(page.get_by_role("alert")).to_contain_text("测试服务暂不可用")
        expect(page.locator(".simple-candidate")).to_have_count(0)
        state["fail"] = False
        page.get_by_role("button", name="刷新报价").click()
        expect(page.locator(".simple-candidate")).to_have_count(1)
        assert requests[-1]["force_refresh"] == ["true"]

        page.get_by_role("button", name="高级扫描", exact=True).click()
        expect(page.get_by_role("heading", name="暂无符合条件的期权")).to_be_visible()
        page.get_by_role("button", name="简单模式 · 现金担保 Put", exact=True).click()
        expect(page.locator(".simple-candidate")).to_have_count(1)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path="/tmp/option-strategy-mobile.png", full_page=True)
        assert page.locator(".simple-scanner").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert not failures, failures
        browser.close()
    print(json.dumps({"browser_checks": "passed", "scan_requests": len(requests)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
