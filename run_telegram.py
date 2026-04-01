"""Entry point per avviare il bot Telegram FlexClaw."""

import logging
from pathlib import Path

from dotenv import load_dotenv

# Carica le variabili d'ambiente prima di ogni altro import
load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

from plugin.telegram_bot import start_bot  # noqa: E402

if __name__ == "__main__":
    start_bot()
