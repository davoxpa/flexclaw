from pathlib import Path
from dotenv import load_dotenv
import os
import signal
import sys
import threading

# Carica l'ambiente PRIMA di importare agent_os
project_root = Path(__file__).resolve().parent
load_dotenv(project_root / ".env")

# Configura il logging PRIMA di ogni altro import
from core.logging_config import setup_logging  # noqa: E402

setup_logging()

from core.loader import start_channels, get_enabled_plugins, install_plugin_deps  # noqa: E402
from rich.theme import Theme  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402
from rich.console import Console  # noqa: E402


THEME = Theme({
    "agent": "bold green",
    "info": "dim white",
    "accent": "bold magenta",
})

console = Console(theme=THEME)

LOGO = r"""
   _____ _            ____ _                 
  |  ___| | _____  __/ ___| | __ ___      __ 
  | |_  | |/ _ \ \/ / |   | |/ _` \ \ /\ / / 
  |  _| | |  __/>  <| |___| | (_| |\ V  V /  
  |_|   |_|\___/_/\_\\____|_|\__,_| \_/\_/   
"""

PORT = int(os.environ.get("AGENT_OS_PORT", 7777))


def _start_health_server() -> None:
    """Avvia un server HTTP minimale con endpoint /health su PORT."""
    import uvicorn
    from fastapi import FastAPI

    health_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @health_app.get("/health")
    def health_check() -> dict:
        return {"status": "ok"}

    uvicorn.run(health_app, host="0.0.0.0", port=PORT, log_level="warning")


def show_welcome():
    console.print(Text(LOGO, style="bold cyan"), highlight=False)
    console.print(
        Panel(
            "[info]AgentOS in avvio — Telegram + API HTTP[/info]",
            title="[agent]FlexClaw OS v0.1[/agent]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # Mostra canali e plugin attivi
    channels, tools = get_enabled_plugins()

    table = Table(title="Plugin attivi", border_style="cyan", show_lines=False)
    table.add_column("Tipo", style="bold magenta", width=10)
    table.add_column("ID", style="bold green")

    for ch in channels:
        table.add_row("Channel", ch)
    for tl in tools:
        table.add_row("Tool", tl)

    console.print(table)
    console.print()


if __name__ == "__main__":
    show_welcome()
    install_plugin_deps()
    try:
        # Avvia il server health check in background su PORT
        health_thread = threading.Thread(
            target=_start_health_server,
            name="health-server",
            daemon=True,
        )
        health_thread.start()

        # Avvia i plugin channel abilitati in background
        threads = start_channels()
        if not threads:
            console.print("[info]Nessun plugin channel abilitato. Uscita.[/info]")
            sys.exit(0)

        # Attendi che un thread finisca o arrivi un segnale di interruzione
        for t in threads:
            while t.is_alive():
                t.join(timeout=1)
    except KeyboardInterrupt:
        console.print("\n[info]Server arrestato. Alla prossima! 👋[/info]")
        sys.exit(0)
