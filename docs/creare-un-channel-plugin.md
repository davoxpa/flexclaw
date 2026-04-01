# Creare un channel plugin

Un channel plugin è un modulo Python che espone una funzione `start_bot()` e viene avviato in un thread daemon all'avvio del framework.

## Struttura della directory

```text
plugin/channel/my_channel/
├── __init__.py          # Esporta start_bot
├── bot.py               # Entry point e loop principale
├── config.yaml          # Configurazione del canale
├── config.py            # Parsing della configurazione (opzionale)
├── handlers.py          # Handler per messaggi e comandi (opzionale)
└── requirements.txt     # Dipendenze pip (opzionale)
```

## 1. Implementa `start_bot()`

Il loader importa `plugin.channel.<id>` e chiama `start_bot()` in un thread daemon. La funzione deve:

- essere sincrona (può usare `asyncio` internamente)
- restare in esecuzione finché il canale è attivo
- gestire lo shutdown tramite `stop_event`

Crea `bot.py`:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

shutdown_event: asyncio.Event | None = None


def start_bot(stop_event: asyncio.Event | None = None) -> None:
    """Entry point del channel plugin.

    Viene chiamato dal loader in un thread daemon.
    """
    global shutdown_event
    shutdown_event = stop_event

    logger.info("My channel avviato")

    try:
        asyncio.run(_main_loop())
    except Exception:
        logger.exception("Errore nel channel my_channel")
    finally:
        logger.info("My channel fermato")


async def _main_loop() -> None:
    """Loop principale async."""
    # Inizializza il client del servizio
    # Registra gli handler
    # Avvia il loop

    while True:
        if shutdown_event and shutdown_event.is_set():
            break
        # Gestisci messaggi in arrivo
        await asyncio.sleep(1)
```

Regole:

- La signature deve essere `start_bot(stop_event: asyncio.Event | None = None) -> None`.
- La funzione gira in un thread daemon: non blocca l'avvio degli altri plugin.
- Se usi una libreria con il suo event loop (es. `python-telegram-bot`), disabilita i signal handler con `stop_signals=()` per evitare conflitti col thread.
- Controlla `stop_event` periodicamente per lo shutdown pulito.
- Gestisci le eccezioni nel loop principale per evitare crash silenziosi.

## 2. Esporta `start_bot`

Crea `__init__.py`:

```python
"""My channel plugin."""

from plugin.channel.my_channel.bot import start_bot

__all__ = ["start_bot"]
```

## 3. Scrivi la configurazione

Crea `config.yaml`:

```yaml
id: "my_channel"
name: "My Channel"
description: "Integrazione con il servizio X"
version: "0.1.0"
author: "Il tuo nome"

my_service:
  api_token: null       # Impostare via variabile ambiente
  polling_interval: 5
  allowed_users: "*"
```

La struttura sotto il blocco del servizio è libera. Usa variabili ambiente per i segreti, non hardcodare token nel file.

## 4. Parsing della configurazione (opzionale)

Se la configurazione è articolata, crea un modulo `config.py` con una dataclass:

```python
from dataclasses import dataclass
from pathlib import Path
import os
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


@dataclass
class MyChannelConfig:
    api_token: str
    polling_interval: int
    allowed_users: str | list[int]

    def is_user_allowed(self, user_id: int) -> bool:
        if self.allowed_users == "*":
            return True
        return user_id in self.allowed_users


def load_config() -> MyChannelConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = raw.get("my_service", {})
    return MyChannelConfig(
        api_token=cfg.get("api_token") or os.environ.get("MY_SERVICE_TOKEN", ""),
        polling_interval=cfg.get("polling_interval", 5),
        allowed_users=cfg.get("allowed_users", "*"),
    )


def reload_config() -> "MyChannelConfig":
    global config
    config = load_config()
    return config


config = load_config()
```

Esporre una funzione `reload_config()` permette di ricaricare la configurazione a runtime (es. tramite un comando admin).

## 5. Handler separati (opzionale)

Per canali con molti comandi, separa i handler in `handlers.py`:

```python
import logging
from core import agent_os
from core.session import get_session

logger = logging.getLogger(__name__)


async def handle_message(user_id: int, chat_id: int, text: str) -> str:
    """Gestisce un messaggio in arrivo e ritorna la risposta."""
    session = get_session("my_channel", str(chat_id))
    team = agent_os.get_team()

    response = team.run(text, session_id=session.session_id)
    return response.content
```

I handler usano il core del framework:

- `core.agent_os` per ottenere il team di agenti
- `core.session` per gestire le sessioni per chat
- `core.audit` per il logging delle azioni sensibili

## 6. Aggiungi le dipendenze

Crea `requirements.txt` se servono librerie esterne:

```text
aiohttp>=3.9
pyyaml>=6.0
```

Il loader le installa automaticamente all'avvio.

## 7. Abilita il plugin

Aggiungi il canale in `config/plugin.config.yaml`:

```yaml
channel:
  - id: my_channel
    status: enabled
```

## Esempio completo: telegram_bot

Il progetto include `plugin/channel/telegram_bot/` come riferimento completo:

- `bot.py` — costruisce l'app Telegram con `_build_app()`, avvia polling o webhook in `start_bot()`
- `config.py` — dataclass `TelegramConfig` con `load_config()` e `reload_config()`
- `handlers.py` — handler per comandi (`/help`, `/status`, `/model`, ecc.), messaggi testuali, file, callback, errori
- `config.yaml` — impostazioni per admin, utenti autorizzati, modalità polling/webhook, streaming tool step

Punti chiave dall'implementazione Telegram:

- `stop_signals=()` nel polling per compatibilità col thread daemon
- Streaming progressivo dei tool step tramite `core.event_stream`
- Invio automatico dei file generati nella sandbox
- Gestione risposte lunghe con suddivisione in chunk
- Reload della configurazione a runtime via comando admin `/reload`

## Ciclo di vita

```text
main.py
  └─ loader.start_channels()
       └─ per ogni channel abilitato:
            ├─ import plugin.channel.<id>
            ├─ crea thread daemon "channel-<id>"
            └─ chiama start_bot(stop_event) nel thread
```

Il thread resta attivo per tutta la durata del processo. Se `start_bot()` termina o lancia un'eccezione, il thread muore silenziosamente. Usa logging e gestione errori nel loop principale per evitare interruzioni non volute.
