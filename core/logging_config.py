"""Configurazione centralizzata del logging con file separati per modulo."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Formato comune per tutti i log
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3


def _make_handler(filename: str, level: int = logging.DEBUG) -> RotatingFileHandler:
    """Crea un handler rotativo per un file di log specifico."""
    handler = RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def setup_logging(console_level: int = logging.INFO) -> None:
    """Configura il logging dell'applicazione con file separati.

    File generati in data/logs/:
    - app.log      → tutto (root logger)
    - core.log     → moduli core (agent_os, agent_builder, loader)
    - agents.log   → attività agenti: chiamate tool, task, tempi di risposta
    - tools.log    → plugin tool

    I plugin canale (es. telegram, discord) registrano i propri handler autonomamente.
    """
    # Handler console per output minimo
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    # Root logger: cattura tutto in app.log + console
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console_handler)
    root.addHandler(_make_handler("app.log"))

    # Logger specifici per modulo
    core_logger = logging.getLogger("core")
    core_logger.addHandler(_make_handler("core.log"))

    # Log dedicato per attività agenti (event_stream + agent_api)
    agents_logger = logging.getLogger("core.event_stream")
    agents_logger.addHandler(_make_handler("agents.log"))
    logging.getLogger("core.agent_api").addHandler(_make_handler("agents.log"))

    tools_logger = logging.getLogger("plugin.tool")
    tools_logger.addHandler(_make_handler("tools.log"))

    # Silenzia i logger rumorosi del polling Telegram, delle richieste HTTP e di newspaper
    for noisy in ("httpcore", "httpx", "telegram.ext", "hpack", "httpcore.http11", "newspaper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
