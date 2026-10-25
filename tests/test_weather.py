"""Offline tests for the weather server: the Open-Meteo HTTP layer is mocked."""
import httpx
import pytest

import server as w

pytestmark = pytest.mark.anyio

PLACE = {"name": "Singapore", "country": "Singapore", "latitude": 1.29, "longitude": 103.85}


def patch_api(monkeypatch, responses, calls=None):
    """Replace server._get_json; `responses` maps URL -> payload (or a list popped in order)."""
    async def fake(url, params):
        if calls is not None:
            calls.append((url, params))
        r = responses[url]
        return r.pop(0) if isinstance(r, list) else r
    monkeypatch.setattr(w, "_get_json", fake)


def geo(*places):
    return {w.GEOCODE_URL: [{"results": [p]} if p else {} for p in places]}


# --- helpers ----------------------------------------------------------------

def test_describe_known_and_unknown():
    assert w.describe(0) == "Clear sky"
    assert w.describe(95) == "Thunderstorm"
    assert w.describe(1234) == "Unknown (code 1234)"


@pytest.mark.parametrize("aqi,label", [
    (None, "unknown"), (0, "Good"), (50, "Good"), (51, "Moderate"), (100, "Moderate"),
    (150, "Unhealthy for sensitive groups"), (200, "Unhealthy"), (300, "Very unhealthy"),
    (301, "Hazardous"),
])
def test_aqi_label_boundaries(aqi, label):
    assert w._aqi_label(aqi) == label


async def test_geocode_found_and_missing(monkeypatch):
    patch_api(monkeypatch, geo(PLACE, None))
    assert (await w._geocode("Singapore"))["name"] == "Singapore"
    assert await w._geocode("Nowhere") is None


async def test_get_json_real_transport(monkeypatch):
    """Exercise the real _get_json against an in-memory httpx transport."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": req.url.params["q"]}))
    real = httpx.AsyncClient
    monkeypatch.setattr(w.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    assert await w._get_json("https://example.test/x", {"q": "1"}) == {"ok": "1"}


async def test_get_json_raises_on_http_error(monkeypatch):
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    real = httpx.AsyncClient
    monkeypatch.setattr(w.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    with pytest.raises(httpx.HTTPStatusError):
        await w._get_json("https://example.test/x", {})


# --- tools ------------------------------------------------------------------

async def test_current_weather(monkeypatch):
    patch_api(monkeypatch, {
        **geo(PLACE),
        w.FORECAST_URL: {
            "current": {"temperature_2m": 30.1, "apparent_temperature": 35, "relative_humidity_2m": 80,
                        "precipitation": 0.2, "weather_code": 3, "wind_speed_10m": 7.5},
            "current_units": {"temperature_2m": "°C", "apparent_temperature": "°C",
                              "relative_humidity_2m": "%", "precipitation": "mm", "wind_speed_10m": "km/h"},
        },
    })
    out = await w.get_current_weather("Singapore")
    assert "Current weather in Singapore, Singapore" in out
    assert "Overcast" in out and "30.1°C (feels like 35°C)" in out and "Humidity: 80%" in out


async def test_forecast_clamps_days_and_formats(monkeypatch):
    calls = []
    daily = {"time": ["2026-10-25", "2026-10-26"], "weather_code": [0, 63],
             "temperature_2m_max": [31, 29], "temperature_2m_min": [25, 24],
             "precipitation_probability_max": [10, 70]}
    units = {"temperature_2m_max": "°C", "precipitation_probability_max": "%"}
    patch_api(monkeypatch, {**geo(PLACE, PLACE), w.FORECAST_URL: [
        {"daily": daily, "daily_units": units}, {"daily": daily, "daily_units": units}]}, calls)

    out = await w.get_forecast("Singapore", days=99)
    assert out.startswith("7-day forecast for Singapore")
    assert "2026-10-26: Rain, 24-29°C, rain chance 70%" in out
    assert calls[-1][1]["forecast_days"] == 7

    await w.get_forecast("Singapore", days=-5)
    assert calls[-1][1]["forecast_days"] == 1


async def test_air_quality(monkeypatch):
    patch_api(monkeypatch, {**geo(PLACE), w.AIR_QUALITY_URL: {
        "current": {"us_aqi": 120, "pm2_5": 40.5, "pm10": 60, "ozone": 80},
        "current_units": {"pm2_5": "µg/m³", "pm10": "µg/m³", "ozone": "µg/m³"}}})
    out = await w.get_air_quality("Singapore")
    assert "US AQI: 120 (Unhealthy for sensitive groups)" in out
    assert "PM2.5: 40.5µg/m³" in out


async def test_sun_times(monkeypatch):
    patch_api(monkeypatch, {**geo(PLACE), w.FORECAST_URL: {"daily": {
        "time": ["2026-10-25"], "sunrise": ["2026-10-25T06:58"], "sunset": ["2026-10-25T19:08"],
        "uv_index_max": [11.2]}}})
    out = await w.get_sun_times("Singapore")
    assert "Sunrise: 06:58" in out and "Sunset: 19:08" in out and "Max UV index: 11.2" in out


@pytest.mark.parametrize("tool", [w.get_current_weather, w.get_forecast, w.get_air_quality, w.get_sun_times])
async def test_unknown_city_returns_readable_message(monkeypatch, tool):
    patch_api(monkeypatch, geo(None))
    assert await tool("Atlantis") == "Could not find a city named 'Atlantis'."


def current(temp, code=0, hum=50):
    return {"current": {"temperature_2m": temp, "relative_humidity_2m": hum, "weather_code": code},
            "current_units": {"temperature_2m": "°C", "relative_humidity_2m": "%"}}


@pytest.mark.parametrize("temp_a,temp_b,expected", [
    (30, 25, "Alpha is warmer by 5°C."),
    (20, 26.5, "Beta is warmer by 6.5°C."),
    (22, 22, "Same temperature."),
])
async def test_compare_weather(monkeypatch, temp_a, temp_b, expected):
    a, b = {**PLACE, "name": "Alpha"}, {**PLACE, "name": "Beta"}
    patch_api(monkeypatch, {**geo(a, b), w.FORECAST_URL: [current(temp_a), current(temp_b)]})
    out = await w.compare_weather("Alpha", "Beta")
    assert out.startswith("Weather comparison:") and "- Alpha:" in out and "- Beta:" in out
    assert out.endswith(expected)


async def test_compare_weather_second_city_missing(monkeypatch):
    patch_api(monkeypatch, {**geo(PLACE, None), w.FORECAST_URL: [current(30)]})
    assert await w.compare_weather("Singapore", "Atlantis") == "Could not find a city named 'Atlantis'."


# --- resource and prompt ------------------------------------------------------

def test_about_resource():
    assert "Open-Meteo" in w.about()


def test_weather_briefing_prompt():
    assert "Tokyo" in w.weather_briefing("Tokyo")


async def test_tools_registered_with_mcp():
    names = {t.name for t in await w.mcp.list_tools()}
    assert names == {"get_current_weather", "get_forecast", "get_air_quality",
                     "get_sun_times", "compare_weather"}
