"""Registry centralizzato per le notifiche dei canali.

Questo modulo è il punto di integrazione tra lo scheduler e i plugin canale.
NON conosce nessun canale specifico: i plugin canale si registrano
autonomamente all'avvio tramite `register()`.

Pattern di utilizzo:
  - Plugin canale (es. telegram_bot, discord_bot): chiamano `register()` in start_bot().
  - Scheduler tool: chiama `send()` senza sapere quali canali sono disponibili.

Se il canale non è registrato (plugin disabilitato o cartella eliminata),
`send()` restituisce False senza errori bloccanti.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Tipo del sender: (chat_id, text, task_name) -> successo
SenderFn = Callable[[str, str, Optional[str]], bool]

# Registry: channel_type → funzione di invio registrata dal plugin canale
_registry: dict[str, SenderFn] = {}


def register(channel_type: str, sender: SenderFn) -> None:
    """Registra la funzione di invio per un tipo di canale.

    Chiamato dai plugin canale al loro avvio (in start_bot()).
    Sovrascrive la registrazione precedente se già presente.

    Args:
        channel_type: identificatore del canale (es. "telegram", "discord").
        sender: callable (chat_id, text, task_name) -> bool.
    """
    _registry[channel_type] = sender
    logger.debug("Canale '%s' registrato nel notification_registry", channel_type)


def send(
    channel_type: str,
    chat_id: str,
    text: str,
    task_name: Optional[str] = None,
) -> bool:
    """Invia una notifica al canale indicato, se disponibile.

    Se il canale non è registrato (plugin non presente o disabilitato),
    logga un warning e restituisce False senza sollevare eccezioni.

    Args:
        channel_type: tipo di canale (es. "telegram", "discord").
        chat_id: ID della chat o del canale di destinazione.
        text: testo da inviare.
        task_name: nome del task (opzionale, per il titolo del messaggio).

    Returns:
        True se la notifica è stata inviata con successo, False altrimenti.
    """
    sender = _registry.get(channel_type)
    if sender is None:
        logger.warning(
            "Canale '%s' non registrato — notifica scheduler non inviata "
            "(plugin disabilitato o non presente?)",
            channel_type,
        )
        return False

    try:
        return sender(chat_id, text, task_name)
    except Exception:
        logger.exception(
            "Errore nell'invio della notifica al canale '%s'", channel_type
        )
        return False


def available_channels() -> list[str]:
    """Restituisce i tipi di canale attualmente registrati."""
    return list(_registry.keys())
