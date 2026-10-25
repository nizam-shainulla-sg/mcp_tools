"""US stocks news MCP server (Finnhub).

Tools:    get_quote, get_company_news, get_market_news, search_symbol,
          get_analyst_recommendations
Resource: stocks://about
Prompt:   stock_briefing

Needs a free API key from https://finnhub.io in the FINNHUB_API_KEY env var.
Transport is stdio, so NEVER print() to stdout; log to stderr.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("stocks-mcp")

mcp = FastMCP("stocks")

BASE_URL = "https://finnhub.io/api/v1"
NEWS_CATEGORIES = ("general", "forex", "crypto", "merger")


class StocksError(Exception):
    """A problem we can explain to the model in plain words."""


async def _get_json(path: str, params: dict | None = None):
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise StocksError(
            "FINNHUB_API_KEY is not set. Get a free key at https://finnhub.io "
            "and register the server with: claude mcp add stocks -e FINNHUB_API_KEY=<key> -- ..."
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}{path}", params=params or {}, headers={"X-Finnhub-Token": key}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            raise StocksError("Finnhub rejected the API key (401).")
        if code == 429:
            raise StocksError("Finnhub rate limit hit (60 calls/min on the free tier). Retry shortly.")
        raise StocksError(f"Finnhub returned HTTP {code}.")
    except httpx.HTTPError as e:
        raise StocksError(f"Could not reach Finnhub: {e.__class__.__name__}.")


def _sym(symbol: str) -> str:
    return symbol.strip().upper()


def _fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_articles(articles: list, limit: int) -> str:
    limit = max(1, min(limit, 20))
    lines = []
    for a in articles[:limit]:
        summary = (a.get("summary") or "").strip()
        if len(summary) > 200:
            summary = summary[:197] + "..."
        lines.append(
            f"- [{_fmt_time(a['datetime'])}] {a['headline']} ({a.get('source', '?')})\n"
            f"  {summary}\n  {a.get('url', '')}".rstrip()
        )
    return "\n".join(lines)


@mcp.tool()
async def get_quote(symbol: str) -> str:
    """Get the latest price quote for a US stock.

    Args:
        symbol: Ticker symbol, e.g. "AAPL" or "TSLA".
    """
    symbol = _sym(symbol)
    log.info("get_quote %s", symbol)
    try:
        q = await _get_json("/quote", {"symbol": symbol})
    except StocksError as e:
        return str(e)
    if not q.get("c"):
        return f"No quote found for '{symbol}'. Try search_symbol to find the right ticker."
    return (
        f"{symbol} quote:\n"
        f"- Price: ${q['c']:.2f} ({q['d']:+.2f}, {q['dp']:+.2f}%)\n"
        f"- Day range: ${q['l']:.2f} - ${q['h']:.2f}\n"
        f"- Open: ${q['o']:.2f}, previous close: ${q['pc']:.2f}\n"
        f"- As of: {_fmt_time(q['t'])}"
    )


@mcp.tool()
async def get_company_news(symbol: str, days: int = 7, limit: int = 5) -> str:
    """Get recent news headlines for a US-listed company.

    Args:
        symbol: Ticker symbol, e.g. "NVDA".
        days: How many days back to look, 1 to 30 (default 7).
        limit: Max articles to return, 1 to 20 (default 5).
    """
    symbol = _sym(symbol)
    log.info("get_company_news %s days=%s", symbol, days)
    days = max(1, min(days, 30))
    today = datetime.now(timezone.utc).date()
    try:
        articles = await _get_json("/company-news", {
            "symbol": symbol,
            "from": (today - timedelta(days=days)).isoformat(),
            "to": today.isoformat(),
        })
    except StocksError as e:
        return str(e)
    if not articles:
        return f"No news found for {symbol} in the last {days} days."
    return f"Latest news for {symbol} (last {days} days):\n" + _fmt_articles(articles, limit)


@mcp.tool()
async def get_market_news(category: str = "general", limit: int = 5) -> str:
    """Get the latest broad market news headlines.

    Args:
        category: One of "general", "forex", "crypto", "merger" (default "general").
        limit: Max articles to return, 1 to 20 (default 5).
    """
    category = category.strip().lower()
    if category not in NEWS_CATEGORIES:
        return f"Unknown category '{category}'. Use one of: {', '.join(NEWS_CATEGORIES)}."
    log.info("get_market_news %s", category)
    try:
        articles = await _get_json("/news", {"category": category})
    except StocksError as e:
        return str(e)
    if not articles:
        return f"No {category} market news right now."
    return f"Latest {category} market news:\n" + _fmt_articles(articles, limit)


@mcp.tool()
async def search_symbol(query: str) -> str:
    """Find ticker symbols by company name or partial ticker.

    Args:
        query: e.g. "apple" or "micro".
    """
    log.info("search_symbol %s", query)
    try:
        data = await _get_json("/search", {"q": query})
    except StocksError as e:
        return str(e)
    results = data.get("result") or []
    if not results:
        return f"No symbols match '{query}'."
    lines = [f"- {r['symbol']}: {r['description']} ({r.get('type', '')})" for r in results[:8]]
    return f"Symbols matching '{query}':\n" + "\n".join(lines)


@mcp.tool()
async def get_analyst_recommendations(symbol: str) -> str:
    """Get the latest analyst buy/hold/sell counts for a stock.

    Args:
        symbol: Ticker symbol, e.g. "MSFT".
    """
    symbol = _sym(symbol)
    log.info("get_analyst_recommendations %s", symbol)
    try:
        data = await _get_json("/stock/recommendation", {"symbol": symbol})
    except StocksError as e:
        return str(e)
    if not data:
        return f"No analyst recommendations found for {symbol}."
    r = data[0]  # most recent period first
    return (
        f"Analyst recommendations for {symbol} (period {r['period']}):\n"
        f"- Strong buy: {r['strongBuy']}\n- Buy: {r['buy']}\n- Hold: {r['hold']}\n"
        f"- Sell: {r['sell']}\n- Strong sell: {r['strongSell']}"
    )


@mcp.resource("stocks://about")
def about() -> str:
    """Describes the data source and its limits."""
    return (
        "Data comes from Finnhub (https://finnhub.io), free tier: 60 calls/min, "
        "US stocks, quotes may be delayed. For information only, not financial advice."
    )


@mcp.prompt()
def stock_briefing(symbol: str) -> str:
    """Ask for a short news briefing on a stock."""
    return (
        f"Use the stocks tools to get the quote, the last 7 days of company news and "
        f"the analyst recommendations for {symbol}. Summarize in 4 bullet points: price "
        f"move, top news themes, analyst sentiment, and one risk to watch. "
        f"Note this is not financial advice."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
