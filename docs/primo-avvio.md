# Primo avvio

Per partire da zero ti servono solo Python 3.11+, `uv` e un bot Telegram.

## 1. Installa le dipendenze

```bash
uv sync
```

## 2. Crea il file ambiente

```bash
cp .env.example .env
```

Apri `.env` e imposta almeno:

- `TELEGRAM_TOKEN`
- la chiave del provider del modello che vuoi usare

Configurazione minima consigliata:

```env
TELEGRAM_TOKEN=...
OPENROUTER_API_KEY=...
```

## 3. Controlla le config principali

Di default il progetto parte già con:

- canale Telegram abilitato in `config/plugin.config.yaml`
- team principale definito in `config/agents.config.yaml`
- modalità Telegram configurata in `plugin/channel/telegram_bot/config.yaml`

Per il primo test locale basta verificare che in `plugin/channel/telegram_bot/config.yaml` ci sia:

- `mode: polling`
- `allowed_users: "*"` oppure il tuo user id Telegram

## 4. Avvia FlexClaw

```bash
uv run python main.py
```

## 5. Cosa succede all'avvio

`main.py` esegue queste operazioni:

1. carica `.env`
2. inizializza il logging
3. legge i plugin abilitati
4. installa le dipendenze dei plugin mancanti
5. avvia il bot Telegram

Se tutto è corretto, vedrai il banner di FlexClaw e la tabella con channel e tool attivi.

## 6. Primo test

Apri il bot Telegram e prova:

- `/help`
- `/status`
- un messaggio normale
- un file `.txt` o `.md`

Il bot risponderà usando il team configurato e, se necessario, invierà anche i file generati nella `sandbox/`.

## Variabili ambiente

Variabili già previste in `.env.example`:

- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `ANTHROPIC_API_KEY`
- `GROQ_API_KEY`
- `MISTRAL_API_KEY`
- `TOGETHER_API_KEY`
- `TELEGRAM_TOKEN`
