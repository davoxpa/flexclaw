# Weather Tool

Plugin custom per la generazione di infografiche meteo come immagini PNG.

## Funzionalità

- **`format_weather(weather_json)`** — genera un'infografica PNG a partire da dati meteo in JSON

Il layout si adatta automaticamente al numero di giorni (da 1 a 14): singolo, compatto, settimanale, esteso.

### Schema JSON

```json
{
  "location": "Roma",
  "days": [
    {
      "date": "01/04/2026",
      "day_name": "Mercoledì",
      "icon": "☀️",
      "condition": "Sereno",
      "temp_min": 12,
      "temp_max": 22,
      "humidity": 55,
      "wind_speed": 15,
      "wind_dir": "NW",
      "precipitation_mm": 0,
      "details": "Cieli sereni per tutto il giorno."
    }
  ]
}
```

Campi obbligatori: `date`, `day_name`, `icon`, `condition`, `temp_min`, `temp_max`.
Campi opzionali: `humidity`, `wind_speed`, `wind_dir`, `precipitation_mm`, `details`.

## Configurazione

1. Copiare il contenuto di `config.example.yaml` dentro `config/plugin.config.yaml`, nella sezione `tool:`
2. Il tool riceve automaticamente `base_dir` dalla config globale (`sandbox_dir` in `main.config.yaml`)

## Dipendenze

Installare con:

```bash
uv pip install -r plugin/tool/weather_tool/requirements.txt
playwright install chromium
```

- `agno` (SDK) — per `Toolkit`
- `playwright` — rendering HTML → PNG

## Struttura

```
plugin/tool/weather_tool/
├── __init__.py          # Export della classe WeatherTool
├── tool.py              # Implementazione del generatore infografiche
├── config.yaml          # Config locale (agent_instructions lette dal loader)
├── config.example.yaml  # Esempio per plugin.config.yaml
├── requirements.txt     # Dipendenze del plugin
└── README.md
```
