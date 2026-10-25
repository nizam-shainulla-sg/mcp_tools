"""Offline tests: the Finnhub HTTP layer is mocked, no API key needed.

Run: python tests/test_stocks.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import stocks_server as s  # noqa: E402

FAKE = {
    "/quote": {"c": 190.5, "d": 1.2, "dp": 0.63, "h": 191, "l": 188, "o": 189, "pc": 189.3, "t": 1760000000},
    "/company-news": [{"datetime": 1760000000, "headline": "Apple ships thing", "source": "X",
                       "summary": "s" * 300, "url": "http://u"}],
    "/news": [],
    "/search": {"result": [{"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"}]},
    "/stock/recommendation": [{"period": "2026-10-01", "strongBuy": 10, "buy": 20, "hold": 5, "sell": 1, "strongSell": 0}],
}


async def fake_get(path, params=None):
    return FAKE[path]


async def main():
    s._get_json = fake_get
    q = await s.get_quote("aapl")
    assert "AAPL" in q and "$190.50" in q, q
    n = await s.get_company_news("aapl", days=99, limit=99)
    assert "Apple ships thing" in n and "..." in n, n
    assert "No general market news" in await s.get_market_news()
    assert "Unknown category" in await s.get_market_news("bogus")
    assert "AAPL: APPLE INC" in await s.search_symbol("apple")
    assert "Strong buy: 10" in await s.get_analyst_recommendations("msft")

    FAKE["/quote"] = {"c": 0}
    assert "No quote found" in await s.get_quote("ZZZZ")

    # real _get_json with no key must explain, not crash
    import importlib
    importlib.reload(s)
    os.environ.pop("FINNHUB_API_KEY", None)
    assert "FINNHUB_API_KEY is not set" in await s.get_quote("AAPL")
    print("all tests passed")


asyncio.run(main())
