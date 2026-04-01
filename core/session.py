"""Gestione centralizzata delle sessioni per tutti i canali."""

import time

# Sessioni sovrascritte da /reset — chiave: (canale, chat_id)
_session_overrides: dict[tuple[str, int], str] = {}


def get_session_id(channel: str, chat_id: int) -> str:
    """Restituisce il session_id per un dato canale e chat."""
    return _session_overrides.get((channel, chat_id), f"{channel}_{chat_id}")


def reset_session(channel: str, chat_id: int) -> str:
    """Crea un nuovo session_id invalidando il precedente."""
    new_session = f"{channel}_{chat_id}_{int(time.time())}"
    _session_overrides[(channel, chat_id)] = new_session
    return new_session


def is_session_reset(channel: str, chat_id: int) -> bool:
    """Verifica se la sessione è stata resettata."""
    return (channel, chat_id) in _session_overrides
