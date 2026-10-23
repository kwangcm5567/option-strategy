"""Position refresh regression checks against Vite with all API traffic mocked."""
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    state = {"fail": False, "missing": False, "quantity": 5, "calls": []}
    errors = []

    def respond(route) -> None:
        url = urlparse(route.request.url)
        if url.path == "/api/positions/import-tiger":
            state["quantity"] = 4
            route.fulfill(json={"options_imported": 0, "stocks_imported": 0, "skipped": 0})
        elif url.path == "/api/positions":
            route.fulfill(json={"data": [{"id": 1, "symbol": "QQQ", "strategy": "sell_put",
                "strike": 675, "premium": 1.96, "quantity": state["quantity"],
                "expiration_date": "2026-10-29", "open_date": "2026-10-01", "status": "open"}]})
        elif url.path == "/api/portfolio/snapshot":
            state["calls"].append(parse_qs(url.query))
            if state["fail"]:
                route.fulfill(status=503, json={"detail": "quote feed unavailable"})
                return
            quantity = state["quantity"]
            row = {"id": 1, "symbol": "QQQ", "strategy": "sell_put", "quantity": quantity,
                "currentPrice": 702.99, "currentPremium": 3.14, "unrealizedPnl": -118 * quantity,
                "unrealizedPnlPct": -60.2, "profitProgress": -60.2, "bid": 3.01, "ask": 3.14,
                "markBasis": "ask", "source": "cboe", "quoteAsOf": "2026-10-22 23:42:58",
                "quoteStatus": "delayed", "theta": -.60, "positionTheta": 60 * quantity}
            if state["missing"]:
                row = {"id": 1, "unrealizedPnl": None, "error": "未取得该到期日及行权价的有效 Bid/Ask，暂不计算盈亏"}
            totals = {"totalDelta": 85, "dailyThetaIncome": 300, "totalVega": -125,
                "totalCapitalAtRisk": 67500 * quantity, "sellPutCount": quantity, "buyCallCount": 0}
            route.fulfill(json={"data": [row], "greeks": None if state["missing"] else totals,
                "scenarios": [{"label": "大跌 15%", "pnlChange": -38000},
                              {"label": "平盘", "pnlChange": 0}],
                "fetchedAt": "2026-10-22T23:45:00+00:00"})
        else:
            route.fulfill(json={"data": [] if url.path == "/api/stocks" else {}})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        page.route("**/api/**", respond)
        page.goto("http://127.0.0.1:5173/#/positions")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("平仓参考价（ASK）", exact=True)).to_be_visible()
        expect(page.get_by_text("$3.14/股", exact=True)).to_be_visible()
        expect(page.get_by_text("-$590.00", exact=True)).to_be_visible()
        expect(page.get_by_text("+$300.00", exact=True)).to_be_visible()
        expect(page.get_by_text("已达最大利润", exact=False)).to_have_count(0)
        expect(page.get_by_text("2026-10-22 23:42:58", exact=False)).to_be_visible()
        page.get_by_role("button", name="压力测试", exact=False).click()
        expect(page.get_by_text("-$38000.00", exact=True)).to_be_visible()

        page.get_by_role("button", name="刷新行情", exact=True).click()
        expect(page.get_by_role("button", name="刷新行情", exact=True)).to_be_enabled()
        assert state["calls"][-1]["force_refresh"] == ["true"]

        state["fail"] = True
        page.get_by_role("button", name="刷新行情", exact=True).click()
        expect(page.get_by_text("行情刷新失败", exact=False)).to_be_visible()
        expect(page.get_by_text("-$590.00", exact=True)).to_have_count(0)
        state["fail"] = False
        page.get_by_role("button", name="刷新行情", exact=True).click()
        expect(page.get_by_text("-$590.00", exact=True)).to_be_visible()

        state["missing"] = True
        page.get_by_role("button", name="刷新行情", exact=True).click()
        expect(page.get_by_text("未实现盈亏（报价 0/1）", exact=True)).to_be_visible()
        expect(page.get_by_text("未取得该到期日", exact=False)).to_be_visible()
        state["missing"] = False
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        expect(page.get_by_text("-$590.00", exact=True)).to_be_visible()

        before = len(state["calls"])
        page.locator('input[type="file"]').set_input_files({
            "name": "test.csv", "mimeType": "text/csv", "buffer": b"Symbol,Holdings\nQQQ,4",
        })
        expect(page.get_by_text("-$472.00", exact=True)).to_be_visible()
        assert len(state["calls"]) > before  # Same number of positions, different quantity.
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("button", name="刷新行情", exact=True)).to_be_visible()
        assert not errors, errors
        page.screenshot(path="/tmp/positions-refresh-mobile.png", full_page=True)
        browser.close()
    print(json.dumps({"positions_browser_checks": "passed", "snapshot_requests": len(state["calls"])}))


if __name__ == "__main__":
    main()
