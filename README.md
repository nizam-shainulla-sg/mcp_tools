# MCP Servers (learning project)

Two minimal Python MCP servers that demonstrate all three MCP primitives (tools, resources, prompts) over stdio:

- **Weather** (`server.py`): free [Open-Meteo](https://open-meteo.com) API, no key needed.
- **US Stocks news** (`stocks_server.py`): [Finnhub](https://finnhub.io) API, free key required.

Jump to [Weather](#weather-server-serverpy), [Stocks](#us-stocks-news-server-stocks_serverpy), or [`.mcp.json`](#project-config-mcpjson).

## Weather server (`server.py`)

| Tool | Description |
|------|-------------|
| `get_current_weather(city)` | Current conditions, temperature, humidity, wind |
| `get_forecast(city, days=3)` | Daily forecast, 1 to 7 days |
| `get_air_quality(city)` | US AQI, PM2.5, PM10, ozone |
| `get_sun_times(city)` | Sunrise, sunset, max UV index |
| `compare_weather(city_a, city_b)` | Side-by-side current weather of two cities |

Also: resource `weather://about` and prompt `weather_briefing(city)`.

## Requirements

Python 3.10+ (developed on 3.12). On an Intel Mac, if `cryptography` tries to compile from source, install with `pip install --only-binary cryptography -r requirements.txt`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Test it with the MCP Inspector (no Claude needed)

```bash
mcp dev server.py
```

Opens a web UI where you can list tools, call `get_current_weather`, read the resource, and try the prompt. Best way to see the raw MCP protocol.

## Wire it into Claude Code

Use the venv's Python with an absolute path to server.py:

```bash
claude mcp add weather -- /absolute/path/to/.venv/bin/python /absolute/path/to/server.py
```

Then start `claude` and run `/mcp` to confirm `weather` is connected. Try:

- "What's the weather in Singapore?"
- "Give me a 5-day forecast for Tokyo"
- `@weather:weather://about` (resource)
- `/mcp__weather__weather_briefing` (prompt)

Useful commands: `claude mcp list`, `claude mcp remove weather`.
Add `--scope project` to store the config in a shareable `.mcp.json`.

## Concepts map

| Concept   | Where in server.py            | Who triggers it     |
|-----------|-------------------------------|---------------------|
| Tool      | `@mcp.tool()` functions       | The model           |
| Resource  | `@mcp.resource("weather://about")` | The app / user |
| Prompt    | `@mcp.prompt()`               | The user (slash command) |
| Transport | `mcp.run(transport="stdio")`  | Client launches the script |

Rule to remember: with stdio, never `print()`: stdout carries the protocol. Log to stderr.

## Project layout

```
server.py         # weather MCP server
stocks_server.py  # US stocks news MCP server (Finnhub)
tests/            # offline pytest suites for both servers
requirements-dev.txt  # pytest, pytest-cov, pytest-html
requirements.txt  # mcp[cli], httpx, python-dotenv
.mcp.json         # project-scoped Claude Code config for both servers
.env.example      # template for FINNHUB_API_KEY
```

## US Stocks News server (`stocks_server.py`)

Uses the [Finnhub](https://finnhub.io) API (free tier, 60 calls/min). Get a free key at finnhub.io, then:

```bash
cp .env.example .env     # then edit .env and paste your key
```

`.env` is gitignored; never commit it. `.env.example` is the committed template.

| Tool | Description |
|------|-------------|
| `get_quote(symbol)` | Price, change %, day range |
| `get_company_news(symbol, days=7, limit=5)` | Recent headlines with source, date, link |
| `get_market_news(category="general", limit=5)` | Broad market news (`general`, `forex`, `crypto`, `merger`) |
| `search_symbol(query)` | Company name to ticker |
| `get_analyst_recommendations(symbol)` | Latest buy/hold/sell counts |

Also: resource `stocks://about` and prompt `stock_briefing(symbol)` (`/mcp__stocks__stock_briefing`).

Inspect it without Claude: `mcp dev stocks_server.py`.

Register it with Claude Code (use absolute paths):

```bash
claude mcp add stocks -- /absolute/path/to/.venv/bin/python /absolute/path/to/stocks_server.py
```

Try: "Any news on NVDA this week?", "Quote for TSLA", "What are analysts saying about MSFT?", "Find the ticker for Palantir".

If `FINNHUB_API_KEY` is missing, the tools return an error asking you to set it. A real environment variable overrides `.env`.

Not financial advice; data may be delayed.

## Tests and coverage

Offline tests for both servers (HTTP mocked, no API key or network needed):

```bash
pip install -r requirements-dev.txt
pytest
```

This prints a coverage table (line and branch) and writes `report.html` with test results plus a per-file coverage summary. `report.html` is gitignored.

## Project config (`.mcp.json`)

`.mcp.json` is committed, so anyone who clones the repo gets both servers in Claude Code without running `claude mcp add`:

```json
{
  "mcpServers": {
    "weather": { "command": ".venv/bin/python", "args": ["server.py"] },
    "stocks": { "command": ".venv/bin/python", "args": ["stocks_server.py"] }
  }
}
```

- Paths are relative: create the `.venv` (see Setup), then run `claude` from the repo root. On Windows use `.venv\\Scripts\\python.exe` as the command.
- It contains no secrets: the Finnhub key comes from the gitignored `.env`.
- Claude Code asks you to approve project servers the first time; confirm with `/mcp`.

## Reusing for another topic

Replace the "data source" section and the tool bodies (e.g. news, stocks, GitHub). Keep the decorators, type hints and docstrings: they become the schema the model sees.
