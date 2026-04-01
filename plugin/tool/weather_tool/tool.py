"""Tool per generare infografiche meteo come immagini PNG."""

import json
import logging
from pathlib import Path

from agno.tools import Toolkit

logger = logging.getLogger(__name__)


class WeatherTool(Toolkit):
    """Genera infografiche meteo in formato PNG da dati strutturati."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="weather_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.register(self.format_weather)

    def format_weather(self, weather_json: str) -> str:
        """Genera un'infografica meteo come immagine PNG.

        Args:
            weather_json: Dati meteo in formato JSON con lo schema:
                {
                    "location": "Nome città",
                    "days": [
                        {
                            "date": "31/03/2026",
                            "day_name": "Martedì",
                            "icon": "☀️",
                            "condition": "Sereno",
                            "temp_min": 12,
                            "temp_max": 22,
                            "humidity": 55,
                            "wind_speed": 15,
                            "wind_dir": "NW",
                            "precipitation_mm": 0,
                            "details": "Descrizione opzionale"
                        }
                    ]
                }

        Returns:
            Percorso del file PNG creato, oppure messaggio di errore.
        """
        try:
            data = json.loads(weather_json)
        except json.JSONDecodeError as e:
            return f"Errore nel parsing JSON: {e}"

        location = data.get("location", "Sconosciuta")
        days = data.get("days", [])

        if not days:
            return "Errore: nessun giorno presente nei dati meteo."

        html = _build_html(location, days)
        file_name = f"meteo_{location.lower().replace(' ', '_')}.png"
        output_path = self.base_dir / file_name

        try:
            _render_to_png(html, output_path, len(days))
            return f"Infografica meteo creata: {output_path}"
        except Exception as e:
            logger.exception("Errore nella generazione dell'infografica meteo")
            return f"Errore nella generazione dell'immagine: {e}"


# ── Costruzione HTML ────────────────────────────────────────────────────────


def _build_html(location: str, days: list[dict]) -> str:
    """Costruisce l'HTML dell'infografica meteo."""
    num_days = len(days)

    if num_days == 1:
        layout = "single"
    elif num_days <= 3:
        layout = "compact"
    elif num_days <= 7:
        layout = "week"
    else:
        layout = "extended"

    day_cards = "\n".join(_build_day_card(d, layout) for d in days)

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #fff;
    padding: 24px;
  }}

  .header {{
    text-align: center;
    margin-bottom: 20px;
  }}

  .header h1 {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 1px;
  }}

  .header .subtitle {{
    font-size: 13px;
    color: rgba(255,255,255,0.6);
    margin-top: 4px;
  }}

  .grid {{
    display: grid;
    gap: 12px;
    {_grid_columns(layout)}
  }}

  .card {{
    background: rgba(255,255,255,0.08);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: {_card_padding(layout)};
    text-align: center;
  }}

  .card .day-name {{
    font-size: {_font_size(layout, "day")}px;
    font-weight: 600;
    color: rgba(255,255,255,0.9);
  }}

  .card .date {{
    font-size: {_font_size(layout, "date")}px;
    color: rgba(255,255,255,0.5);
    margin-bottom: 8px;
  }}

  .card .icon {{
    font-size: {_font_size(layout, "icon")}px;
    margin: 8px 0;
  }}

  .card .condition {{
    font-size: {_font_size(layout, "condition")}px;
    font-weight: 500;
    color: rgba(255,255,255,0.85);
    margin-bottom: 8px;
  }}

  .temps {{
    display: flex;
    justify-content: center;
    gap: 12px;
    margin: 8px 0;
  }}

  .temp-max {{
    font-size: {_font_size(layout, "temp")}px;
    font-weight: 700;
    color: #fbbf24;
  }}

  .temp-min {{
    font-size: {_font_size(layout, "temp")}px;
    font-weight: 500;
    color: #93c5fd;
  }}

  .details-row {{
    display: flex;
    justify-content: center;
    gap: 16px;
    margin-top: 8px;
    flex-wrap: wrap;
  }}

  .detail {{
    font-size: {_font_size(layout, "detail")}px;
    color: rgba(255,255,255,0.6);
  }}

  .detail span {{
    color: rgba(255,255,255,0.9);
  }}

  .description {{
    font-size: 12px;
    color: rgba(255,255,255,0.55);
    margin-top: 8px;
    line-height: 1.4;
  }}

  .single .card {{
    max-width: 400px;
    margin: 0 auto;
    padding: 32px;
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>📍 {_escape_html(location)}</h1>
    <div class="subtitle">Previsioni meteo — {_date_range(days)}</div>
  </div>
  <div class="grid {layout}">
    {day_cards}
  </div>
</body>
</html>"""


def _build_day_card(day: dict, layout: str) -> str:
    """Costruisce la card HTML per un singolo giorno."""
    day_name = _escape_html(day.get("day_name", ""))
    date = _escape_html(day.get("date", ""))
    icon = day.get("icon", "🌡️")
    condition = _escape_html(day.get("condition", ""))
    temp_max = day.get("temp_max", "–")
    temp_min = day.get("temp_min", "–")

    # Dettagli opzionali
    parts = []
    if "humidity" in day:
        parts.append(f'<div class="detail">💧 <span>{day["humidity"]}%</span></div>')
    if "wind_speed" in day:
        wind = f'{day["wind_speed"]} km/h'
        if "wind_dir" in day:
            wind += f" {_escape_html(day['wind_dir'])}"
        parts.append(f'<div class="detail">💨 <span>{wind}</span></div>')
    if day.get("precipitation_mm", 0) > 0:
        parts.append(
            f'<div class="detail">🌧️ <span>{day["precipitation_mm"]} mm</span></div>'
        )

    details_html = (
        f'<div class="details-row">{"".join(parts)}</div>' if parts else ""
    )

    # Descrizione testuale solo per layout con pochi giorni
    desc_html = ""
    if layout in ("single", "compact") and day.get("details"):
        desc_html = f'<div class="description">{_escape_html(day["details"])}</div>'

    return f"""<div class="card">
      <div class="day-name">{day_name}</div>
      <div class="date">{date}</div>
      <div class="icon">{icon}</div>
      <div class="condition">{condition}</div>
      <div class="temps">
        <div class="temp-max">{temp_max}°</div>
        <div class="temp-min">{temp_min}°</div>
      </div>
      {details_html}
      {desc_html}
    </div>"""


# ── Utilità layout ──────────────────────────────────────────────────────────


def _grid_columns(layout: str) -> str:
    """Restituisce il CSS grid-template-columns per il layout."""
    match layout:
        case "single":
            return "grid-template-columns: 1fr;"
        case "compact":
            return "grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));"
        case "week":
            return "grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));"
        case _:
            return "grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));"


def _card_padding(layout: str) -> str:
    """Restituisce il padding CSS per le card."""
    match layout:
        case "single":
            return "32px"
        case "compact":
            return "20px"
        case _:
            return "14px 10px"


def _font_size(layout: str, element: str) -> int:
    """Restituisce la dimensione font per tipo di layout ed elemento."""
    sizes = {
        "single": {
            "day": 22, "date": 14, "icon": 64,
            "condition": 18, "temp": 28, "detail": 14,
        },
        "compact": {
            "day": 18, "date": 12, "icon": 48,
            "condition": 15, "temp": 22, "detail": 12,
        },
        "week": {
            "day": 14, "date": 11, "icon": 36,
            "condition": 12, "temp": 18, "detail": 11,
        },
        "extended": {
            "day": 13, "date": 10, "icon": 28,
            "condition": 11, "temp": 16, "detail": 10,
        },
    }
    return sizes.get(layout, sizes["week"]).get(element, 12)


def _date_range(days: list[dict]) -> str:
    """Restituisce la stringa dell'intervallo di date."""
    if len(days) == 1:
        return days[0].get("date", "")
    first = days[0].get("date", "")
    last = days[-1].get("date", "")
    return f"{first} → {last}"


def _escape_html(text: str) -> str:
    """Escape basilare per evitare injection HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Rendering HTML → PNG ───────────────────────────────────────────────────


def _render_to_png(html: str, output_path: Path, num_days: int) -> None:
    """Renderizza l'HTML in un file PNG usando playwright."""
    from playwright.sync_api import sync_playwright

    # Larghezza adattiva al numero di giorni
    if num_days == 1:
        width = 460
    elif num_days <= 3:
        width = 640
    elif num_days <= 7:
        width = 900
    else:
        width = 1100

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 100})
        page.set_content(html, wait_until="networkidle")

        # Altezza dinamica basata sul contenuto
        height = page.evaluate("document.body.scrollHeight") + 48
        page.set_viewport_size({"width": width, "height": height})

        page.screenshot(path=str(output_path), full_page=True)
        browser.close()
