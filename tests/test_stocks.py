"""Offline tests for the stocks server: the Finnhub HTTP layer is mocked, no API key needed.

Run: pytest   (writes report.html with test results and coverage)
"""
import httpx
import pytest

import stocks_server as s

pytestmark = pytest.mark.anyio

ARTICLE = {"datetime": 1760000000, "headline": "Apple ships thing", "source": "X",
           "summary": "s" * 300, "url": "http://u"}


def patch_api(monkeypatch, payload=None, error=None):
    calls = []

    async def fake(path, params=None):
        calls.append((path, params))
        if error:
            raise s.StocksError(error)
        return payload[path] if isinstance(payload, dict) and path in payload else payload
    monkeypatch.setattr(s, "_get_json", fake)
    return calls


def real_get_json(monkeypatch, handler, key="k"):
    """Run the real _get_json against an in-memory httpx transport."""
    if key is None:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    else:
        monkeypatch.setenv("FINNHUB_API_KEY", key)
    real = httpx.AsyncClient
    monkeypatch.setattr(s.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


# --- _get_json ----------------------------------------------------------------

async def test_get_json_sends_key_header_and_params(monkeypatch):
    seen = {}

    def handler(req):
        seen["token"] = req.headers["X-Finnhub-Token"]
        seen["q"] = req.url.params["symbol"]
        return httpx.Response(200, json={"ok": True})
    real_get_json(monkeypatch, handler, key="secret")
    assert await s._get_json("/quote", {"symbol": "AAPL"}) == {"ok": True}
    assert seen == {"token": "secret", "q": "AAPL"}


async def test_get_json_without_key_explains(monkeypatch):
    real_get_json(monkeypatch, lambda r: httpx.Response(200, json={}), key=None)
    with pytest.raises(s.StocksError, match="FINNHUB_API_KEY is not set"):
        await s._get_json("/quote")


@pytest.mark.parametrize("status,message", [
    (401, "rejected the API key"), (429, "rate limit"), (500, "HTTP 500"),
])
async def test_get_json_http_errors_become_stocks_errors(monkeypatch, status, message):
    real_get_json(monkeypatch, lambda r: httpx.Response(status))
    with pytest.raises(s.StocksError, match=message):
        await s._get_json("/quote")


async def test_get_json_network_error(monkeypatch):
    def boom(req):
        raise httpx.ConnectError("down")
    real_get_json(monkeypatch, boom)
    with pytest.raises(s.StocksError, match="Could not reach Finnhub: ConnectError"):
        await s._get_json("/quote")


# --- helpers ------------------------------------------------------------------

def test_sym_normalises():
    assert s._sym("  aapl ") == "AAPL"


def test_fmt_time_is_utc():
    assert s._fmt_time(0) == "1970-01-01 00:00 UTC"


def test_fmt_articles_truncates_summary_and_clamps_limit():
    out = s._fmt_articles([ARTICLE] * 30, limit=99)
    assert out.count("Apple ships thing") == 20
    assert "s" * 197 + "..." in out and "s" * 198 not in out
    assert s._fmt_articles([ARTICLE] * 3, limit=0).count("Apple ships thing") == 1


def test_fmt_articles_handles_missing_optional_fields():
    out = s._fmt_articles([{"datetime": 0, "headline": "H"}], limit=5)
    assert "H (?)" in out


# --- tools --------------------------------------------------------------------

QUOTE = {"c": 190.5, "d": 1.2, "dp": 0.63, "h": 191, "l": 188, "o": 189, "pc": 189.3, "t": 1760000000}


async def test_get_quote(monkeypatch):
    calls = patch_api(monkeypatch, QUOTE)
    out = await s.get_quote(" aapl")
    assert calls == [("/quote", {"symbol": "AAPL"})]
    assert "$190.50 (+1.20, +0.63%)" in out and "$188.00 - $191.00" in out


async def test_get_quote_unknown_symbol(monkeypatch):
    patch_api(monkeypatch, {"c": 0})
    assert "No quote found for 'ZZZZ'" in await s.get_quote("zzzz")


async def test_get_company_news_clamps_days(monkeypatch):
    calls = patch_api(monkeypatch, [ARTICLE])
    out = await s.get_company_news("aapl", days=99, limit=99)
    assert "last 30 days" in out and "Apple ships thing" in out and "..." in out
    params = calls[0][1]
    assert params["symbol"] == "AAPL" and params["from"] < params["to"]
    assert "last 1 days" in await s.get_company_news("aapl", days=0)


async def test_get_company_news_empty(monkeypatch):
    patch_api(monkeypatch, [])
    assert "No news found for AAPL in the last 7 days" in await s.get_company_news("aapl")


async def test_get_market_news(monkeypatch):
    patch_api(monkeypatch, [ARTICLE])
    assert "Latest crypto market news" in await s.get_market_news(" Crypto ")


async def test_get_market_news_empty_and_bad_category(monkeypatch):
    patch_api(monkeypatch, [])
    assert "No general market news" in await s.get_market_news()
    assert "Unknown category 'bogus'" in await s.get_market_news("bogus")


async def test_search_symbol(monkeypatch):
    patch_api(monkeypatch, {"result": [{"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"}]})
    assert "AAPL: APPLE INC (Common Stock)" in await s.search_symbol("apple")


async def test_search_symbol_caps_results_and_handles_none(monkeypatch):
    many = [{"symbol": f"S{i}", "description": "d"} for i in range(20)]
    patch_api(monkeypatch, {"result": many})
    assert (await s.search_symbol("s")).count("\n- ") == 8
    patch_api(monkeypatch, {"result": None})
    assert "No symbols match 'zzz'" in await s.search_symbol("zzz")


async def test_get_analyst_recommendations(monkeypatch):
    patch_api(monkeypatch, [{"period": "2026-10-01", "strongBuy": 10, "buy": 20, "hold": 5,
                             "sell": 1, "strongSell": 0}])
    out = await s.get_analyst_recommendations("msft")
    assert "MSFT (period 2026-10-01)" in out and "Strong buy: 10" in out


async def test_get_analyst_recommendations_empty(monkeypatch):
    patch_api(monkeypatch, [])
    assert "No analyst recommendations found for MSFT" in await s.get_analyst_recommendations("msft")


@pytest.mark.parametrize("call", [
    lambda: s.get_quote("AAPL"),
    lambda: s.get_company_news("AAPL"),
    lambda: s.get_market_news(),
    lambda: s.search_symbol("apple"),
    lambda: s.get_analyst_recommendations("AAPL"),
])
async def test_every_tool_returns_api_errors_as_text(monkeypatch, call):
    patch_api(monkeypatch, error="Finnhub rate limit hit")
    assert await call() == "Finnhub rate limit hit"


# --- resource and prompt ------------------------------------------------------

def test_about_resource():
    assert "Finnhub" in s.about()


def test_stock_briefing_prompt():
    assert "NVDA" in s.stock_briefing("NVDA")


async def test_tools_registered_with_mcp():
    names = {t.name for t in await s.mcp.list_tools()}
    assert names == {"get_quote", "get_company_news", "get_market_news",
                     "search_symbol", "get_analyst_recommendations"}
