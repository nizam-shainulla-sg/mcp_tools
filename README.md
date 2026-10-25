# Weather MCP Server (learning project)

A minimal Python MCP server using the free [Open-Meteo](https://open-meteo.com) API (no API key).
It demonstrates all three MCP primitives (tools, resources, prompts) over stdio.

## Features

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
server.py         # the MCP server (all tools, resource, prompt)
requirements.txt  # mcp[cli], httpx
```

## Reusing for another topic

Replace the "data source" section and the tool bodies (e.g. news, stocks, GitHub). Keep the decorators, type hints and docstrings: they become the schema the model sees.
