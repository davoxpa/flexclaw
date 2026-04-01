def get_sandbox_dir() -> str:
    """Restituisce il percorso della sandbox directory dal main.config.yaml."""
    cfg = _load_main_config()
    return cfg.get("sandbox_dir", "sandbox")
"""Carica dinamicamente i plugin (channel e tool) abilitati in plugin.config.yaml."""

import importlib
import logging
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import yaml
from agno.tools import Toolkit

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "plugin.config.yaml"
MAIN_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "main.config.yaml"
PLUGIN_TOOL_DIR = Path(__file__).resolve().parent.parent / "plugin" / "tool"
PLUGIN_CHANNEL_DIR = Path(__file__).resolve().parent.parent / "plugin" / "channel"

_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _load_config() -> dict[str, Any]:
    """Legge la configurazione dei plugin."""
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _load_main_config() -> dict[str, Any]:
    """Legge la configurazione principale per le variabili globali."""
    return yaml.safe_load(MAIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _get_global_vars() -> dict[str, str]:
    """Restituisce le variabili globali scalari da main.config.yaml."""
    cfg = _load_main_config()
    return {k: str(v) for k, v in cfg.items() if isinstance(v, (str, int, float, bool))}


def _resolve_vars(value: str, variables: dict[str, str]) -> str:
    """Sostituisce ${variabile} in una stringa con i valori dal dizionario."""
    return _VAR_PATTERN.sub(lambda m: variables.get(m.group(1), m.group(0)), value)


def _get_enabled_tools() -> list[dict[str, Any]]:
    """Restituisce i blocchi completi dei tool con status 'enabled'.

    I tool con special=true vengono esclusi (gestiti direttamente da agent_os).
    """
    raw = _load_config()
    return [
        item for item in raw.get("tool", [])
        if item.get("status") == "enabled" and not item.get("special")
    ]


def _load_enabled(section: str) -> list[str]:
    """Restituisce gli id dei plugin con status 'enabled' per la sezione data."""
    raw = _load_config()
    items = raw.get(section, [])
    return [item["id"] for item in items if item.get("status") == "enabled"]


def get_enabled_plugins() -> tuple[list[str], list[str]]:
    """Restituisce i canali e i tool abilitati."""
    return _load_enabled("channel"), _load_enabled("tool")


# ── Installazione dipendenze plugin ─────────────────────────────────────────


def _find_plugin_requirements() -> list[Path]:
    """Trova i requirements.txt dei plugin abilitati."""
    channels, tools = get_enabled_plugins()
    paths: list[Path] = []

    for tool_id in tools:
        req = PLUGIN_TOOL_DIR / tool_id / "requirements.txt"
        if req.exists():
            paths.append(req)

    for channel_id in channels:
        req = PLUGIN_CHANNEL_DIR / channel_id / "requirements.txt"
        if req.exists():
            paths.append(req)

    return paths


def install_plugin_deps() -> None:
    """Installa le dipendenze dei plugin abilitati se non già presenti."""
    req_files = _find_plugin_requirements()
    if not req_files:
        return

    # Rileva se usare uv o pip
    uv_cmd = ["uv", "pip", "install", "--quiet", "-r"]
    pip_cmd = [sys.executable, "-m", "pip", "install", "--quiet", "-r"]
    try:
        use_uv = subprocess.run(
            ["uv", "--version"], capture_output=True
        ).returncode == 0
    except FileNotFoundError:
        use_uv = False

    for req_path in req_files:
        plugin_name = req_path.parent.name
        cmd = [*(uv_cmd if use_uv else pip_cmd), str(req_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.debug("Dipendenze di '%s' verificate", plugin_name)
        else:
            logger.warning(
                "Errore nell'installazione dipendenze di '%s': %s",
                plugin_name,
                result.stderr.strip(),
            )


def get_sandbox_dir() -> str:
    """Restituisce la directory sandbox da main.config.yaml."""
    cfg = _load_main_config()
    return cfg.get("sandbox_dir", "sandbox")


# ── Channel plugin ──────────────────────────────────────────────────────────


def start_channels() -> list[threading.Thread]:
    """Avvia ogni canale abilitato in un thread daemon separato."""
    enabled = _load_enabled("channel")
    threads: list[threading.Thread] = []

    for channel_id in enabled:
        module_path = f"plugin.channel.{channel_id}"
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError:
            logger.warning("Plugin canale '%s' non trovato (%s)", channel_id, module_path)
            continue

        start_fn = getattr(module, "start_bot", None)
        if not start_fn or not callable(start_fn):
            logger.warning("Plugin '%s' non espone start_bot()", channel_id)
            continue

        thread = threading.Thread(
            target=start_fn,
            name=f"channel-{channel_id}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)
        logger.debug("Canale '%s' avviato in background", channel_id)

    return threads


# ── Tool plugin ─────────────────────────────────────────────────────────────


def _get_tool_config(tool_entry: dict[str, Any]) -> dict[str, Any]:
    """Restituisce la configurazione di un tool.

    Tool SDK (con 'class' inline) → usa il blocco da plugin.config.yaml.
    Tool custom (senza 'class') → legge config.yaml dalla cartella plugin/tool/<id>/.
    """
    if "class" in tool_entry:
        return tool_entry
    tool_id = tool_entry["id"]
    config_file = PLUGIN_TOOL_DIR / tool_id / "config.yaml"
    if not config_file.exists():
        return tool_entry
    return yaml.safe_load(config_file.read_text(encoding="utf-8")) or tool_entry


def load_tool_instructions() -> str:
    """Raccoglie le agent_instructions dai tool abilitati."""
    enabled = _get_enabled_tools()
    parts: list[str] = []
    for tool_entry in enabled:
        cfg = _get_tool_config(tool_entry)
        instructions = cfg.get("agent_instructions", "").strip()
        if instructions:
            parts.append(instructions)
    return "\n".join(parts)


def _resolve_tool_class(tool_entry: dict[str, Any]) -> type | None:
    """Risolve la classe Toolkit per un tool.

    Tool SDK: 'class' nel blocco inline → importa la classe Agno.
    Tool custom: cerca nel modulo locale plugin/tool/<id>/.
    """
    cfg = _get_tool_config(tool_entry)
    class_path = cfg.get("class")

    if class_path:
        module_path, class_name = class_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            return getattr(module, class_name, None)
        except (ModuleNotFoundError, AttributeError):
            logger.warning("Classe '%s' non trovata per tool '%s'", class_path, tool_entry["id"])
            return None

    tool_id = tool_entry["id"]
    module_path = f"plugin.tool.{tool_id}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        logger.warning("Plugin tool '%s' non trovato (%s)", tool_id, module_path)
        return None

    for attr_name in module.__all__ if hasattr(module, "__all__") else dir(module):
        attr = getattr(module, attr_name, None)
        if isinstance(attr, type) and issubclass(attr, Toolkit) and attr is not Toolkit:
            return attr

    logger.warning("Plugin tool '%s' non espone una classe Toolkit", tool_id)
    return None


def load_tools() -> list[Toolkit]:
    """Carica e restituisce le istanze dei tool abilitati.

    Tool SDK Agno: usa 'class' e 'params' dal blocco inline, risolve ${sandbox_dir}.
    Tool custom: passa base_dir dalla config globale.
    """
    enabled = _get_enabled_tools()
    tools: list[Toolkit] = []
    variables = _get_global_vars()
    sandbox = get_sandbox_dir()

    for tool_entry in enabled:
        tool_class = _resolve_tool_class(tool_entry)
        if not tool_class:
            continue

        cfg = _get_tool_config(tool_entry)
        is_sdk = bool(cfg.get("class"))

        try:
            if is_sdk:
                # Legge e risolve ${variabile} nei parametri del costruttore
                params = dict(cfg.get("params", {}))
                for key, val in params.items():
                    if isinstance(val, str):
                        params[key] = _resolve_vars(val, variables)
                # Converte Path per parametri noti
                if "base_dir" in params:
                    params["base_dir"] = Path(params["base_dir"])
                instance = tool_class(**params)
            else:
                # Tool custom: passa base_dir dalla config globale
                instance = tool_class(base_dir=Path(sandbox))

            # Sovrascrive il nome del toolkit se specificato nel config
            toolkit_name = cfg.get("toolkit_name")
            if toolkit_name:
                instance.name = toolkit_name

            tools.append(instance)
            logger.debug("Tool '%s' caricato (name='%s')", tool_entry["id"], instance.name)
        except Exception:
            logger.exception("Errore nell'inizializzazione del tool '%s'", tool_entry["id"])

    return tools
