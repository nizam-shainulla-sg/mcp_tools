"""Weather MCP server: a minimal, learn-by-reading example.

MCP has three core primitives, and this file shows all three:
  - Tool     : an action the model can call      (get_current_weather, get_forecast, ...)
  - Resource : read-only data the app can attach (weather://about)
  - Prompt   : a reusable prompt template        (weather_briefing)

Transport is stdio: Claude Code launches this script as a subprocess and
talks JSON-RPC over stdin/stdout.  Because stdout IS the protocol channel,
NEVER use print() here.  Log to stderr instead.

To reuse for another topic, only change the "data source" section and the
tool bodies; the MCP plumbing stays the same.
"""

import logging
import sys

import httpx
from mcp.server.fastmcp import FastMCP

# --- logging: stderr only (stdout is reserved for the MCP protocol) ---------
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("weather-mcp")

mcp = FastMCP("weather")

# --- data source: Open-Meteo (free, no API key) -----------------------------
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# WMO weather codes -> human text
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


def describe(code: int) -> str:
    return WMO_CODES.get(code, f"Unknown (code {code})")


async def _get_json(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _aqi_label(aqi: int | None) -> str:
    if aqi is None:
        return "unknown"
    for limit, label in ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"),
                         (200, "Unhealthy"), (300, "Very unhealthy")):
        if aqi <= limit:
            return label
    return "Hazardous"


async def _geocode(city: str) -> dict | None:
    data = await _get_json(GEOCODE_URL, {"name": city, "count": 1})
    results = data.get("results")
    return results[0] if results else None


# --- tools -------------------------------------------------------------------
# The docstring and type hints become the tool description and input schema
# that the model sees, so write them for the model, not just for humans.

@mcp.tool()
async def get_current_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. "Singapore" or "London".
    """
    log.info("get_current_weather city=%s", city)
    place = await _geocode(city)
    if not place:
        # Returning a readable message (instead of raising) lets the model recover.
        return f"Could not find a city named '{city}'."

    data = await _get_json(FORECAST_URL, {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "precipitation,weather_code,wind_speed_10m",
        "timezone": "auto",
    })
    c, u = data["current"], data["current_units"]
    return (
        f"Current weather in {place['name']}, {place.get('country', '')}:\n"
        f"- Conditions: {describe(c['weather_code'])}\n"
        f"- Temperature: {c['temperature_2m']}{u['temperature_2m']} "
        f"(feels like {c['apparent_temperature']}{u['apparent_temperature']})\n"
        f"- Humidity: {c['relative_humidity_2m']}{u['relative_humidity_2m']}\n"
        f"- Precipitation: {c['precipitation']}{u['precipitation']}\n"
        f"- Wind: {c['wind_speed_10m']}{u['wind_speed_10m']}"
    )


@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """Get a daily weather forecast for a city.

    Args:
        city: City name, e.g. "Singapore".
        days: Number of days to forecast, 1 to 7 (default 3).
    """
    log.info("get_forecast city=%s days=%s", city, days)
    days = max(1, min(days, 7))
    place = await _geocode(city)
    if not place:
        return f"Could not find a city named '{city}'."

    data = await _get_json(FORECAST_URL, {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max",
        "forecast_days": days,
        "timezone": "auto",
    })
    d, u = data["daily"], data["daily_units"]
    lines = [f"{days}-day forecast for {place['name']}, {place.get('country', '')}:"]
    for i, day in enumerate(d["time"]):
        lines.append(
            f"- {day}: {describe(d['weather_code'][i])}, "
            f"{d['temperature_2m_min'][i]}-{d['temperature_2m_max'][i]}{u['temperature_2m_max']}, "
            f"rain chance {d['precipitation_probability_max'][i]}{u['precipitation_probability_max']}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_air_quality(city: str) -> str:
    """Get the current air quality (US AQI and particulate levels) for a city.

    Args:
        city: City name, e.g. "Delhi".
    """
    log.info("get_air_quality city=%s", city)
    place = await _geocode(city)
    if not place:
        return f"Could not find a city named '{city}'."

    data = await _get_json(AIR_QUALITY_URL, {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "us_aqi,pm10,pm2_5,ozone",
        "timezone": "auto",
    })
    c, u = data["current"], data["current_units"]
    aqi = c["us_aqi"]
    return (
        f"Air quality in {place['name']}, {place.get('country', '')}:\n"
        f"- US AQI: {aqi} ({_aqi_label(aqi)})\n"
        f"- PM2.5: {c['pm2_5']}{u['pm2_5']}\n"
        f"- PM10: {c['pm10']}{u['pm10']}\n"
        f"- Ozone: {c['ozone']}{u['ozone']}"
    )


@mcp.tool()
async def get_sun_times(city: str) -> str:
    """Get today's sunrise, sunset and UV index for a city.

    Args:
        city: City name, e.g. "Mumbai".
    """
    log.info("get_sun_times city=%s", city)
    place = await _geocode(city)
    if not place:
        return f"Could not find a city named '{city}'."

    data = await _get_json(FORECAST_URL, {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "daily": "sunrise,sunset,uv_index_max",
        "forecast_days": 1,
        "timezone": "auto",
    })
    d = data["daily"]
    return (
        f"Sun times in {place['name']}, {place.get('country', '')} ({d['time'][0]}, local time):\n"
        f"- Sunrise: {d['sunrise'][0].split('T')[1]}\n"
        f"- Sunset: {d['sunset'][0].split('T')[1]}\n"
        f"- Max UV index: {d['uv_index_max'][0]}"
    )


@mcp.tool()
async def compare_weather(city_a: str, city_b: str) -> str:
    """Compare the current temperature, humidity and conditions of two cities.

    Args:
        city_a: First city name, e.g. "Mumbai".
        city_b: Second city name, e.g. "Singapore".
    """
    log.info("compare_weather %s vs %s", city_a, city_b)
    rows = []
    for city in (city_a, city_b):
        place = await _geocode(city)
        if not place:
            return f"Could not find a city named '{city}'."
        data = await _get_json(FORECAST_URL, {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "timezone": "auto",
        })
        rows.append((place["name"], data["current"], data["current_units"]))

    lines = ["Weather comparison:"]
    for name, c, u in rows:
        lines.append(
            f"- {name}: {describe(c['weather_code'])}, "
            f"{c['temperature_2m']}{u['temperature_2m']}, "
            f"humidity {c['relative_humidity_2m']}{u['relative_humidity_2m']}"
        )
    diff = round(rows[0][1]["temperature_2m"] - rows[1][1]["temperature_2m"], 1)
    warmer = rows[0][0] if diff > 0 else rows[1][0]
    lines.append(f"{warmer} is warmer by {abs(diff)}{rows[0][2]['temperature_2m']}." if diff else "Same temperature.")
    return "\n".join(lines)


# --- resource ----------------------------------------------------------------
# Resources are data the client can read/attach (in Claude Code, via @-mention).
# They are addressed by URI and are not "called" by the model like tools.

@mcp.resource("weather://about")
def about() -> str:
    """Describes the data source and its limits."""
    return (
        "Weather data comes from Open-Meteo (https://open-meteo.com), "
        "a free API that needs no key. Free for non-commercial use."
    )


# --- prompt ------------------------------------------------------------------
# Prompts are templates the user triggers (in Claude Code: /mcp__weather__weather_briefing).

@mcp.prompt()
def weather_briefing(city: str) -> str:
    """Ask for a short weather briefing with advice."""
    return (
        f"Use the weather tools to get the current weather and the 3-day forecast "
        f"for {city}. Then give me a 3-sentence briefing and say whether I need "
        f"an umbrella."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
