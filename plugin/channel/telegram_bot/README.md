# Telegram Bot

Plugin canale che integra FlexClaw con Telegram, permettendo l'interazione con gli agenti tramite messaggi e comandi.

## Funzionalità

### Comandi

| Comando | Descrizione |
|---------|-------------|
| `/start` | Messaggio di benvenuto |
| `/help` | Elenco comandi disponibili |
| `/status` | Stato del sistema (modello, plugin, sessione) |
| `/model` | Mostra/cambia modello AI (admin) |
| `/reset` | Resetta la sessione corrente |
| `/history` | Info sulla sessione corrente |
| `/knowledge` | Cerca nella knowledge base |

### Gestione file

Il bot accetta file allegati (documenti, foto, audio, video, vocali) e li salva nella sandbox per l'elaborazione. I file di testo vengono letti inline, i binari vengono passati come allegati all'agente.

### Streaming live

Durante l'elaborazione, il bot mostra in tempo reale i task e i tool step eseguiti dagli agenti (configurabile con `show_tool_steps`).

## Configurazione

1. Copiare il contenuto di `config.example.yaml` dentro `config/plugin.config.yaml`, nella sezione `channel:`
2. Configurare `config.yaml` nella cartella del plugin con le impostazioni specifiche di Telegram
3. Impostare la variabile d'ambiente `TELEGRAM_TOKEN` nel file `.env`

### Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `TELEGRAM_TOKEN` | Token del bot ottenuto da [@BotFather](https://t.me/BotFather) |

### Parametri in config.yaml

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `admin_user_id` | int | — | ID Telegram dell'admin (comandi privilegiati) |
| `allowed_users` | `"*"` o `[int]` | `"*"` | Utenti autorizzati (`"*"` = tutti) |
| `mode` | string | `"polling"` | `"polling"` (dev) o `"webhook"` (prod) |
| `webhook.url` | string | null | URL pubblico per il webhook |
| `webhook.port` | int | 8443 | Porta locale del webhook |
| `reply_mode` | string | `"all"` | `"all"` o `"mention"` (solo nei gruppi) |
| `show_tool_steps` | bool | true | Mostra gli step dei tool in tempo reale |

## Dipendenze

Installare con:

```bash
uv pip install -r plugin/channel/telegram_bot/requirements.txt
```

- `python-telegram-bot` — libreria Telegram
- `pyyaml` — parsing config.yaml
- `core.event_stream` — aggregatore eventi agnostico
- `core.session` — gestione sessioni centralizzata
- `core.agent_os` — API knowledge e modelli

## Struttura

```
plugin/channel/telegram_bot/
├── __init__.py          # Export di start_bot
├── bot.py               # Setup Application e avvio polling/webhook
├── config.py            # Parsing e dataclass TelegramConfig
├── config.yaml          # Configurazione specifica del bot
├── config.example.yaml  # Esempio per plugin.config.yaml
├── handlers.py          # Tutti gli handler dei comandi e messaggi
├── requirements.txt     # Dipendenze del plugin
└── README.md
```
