"""Carica e espone la configurazione del plugin Telegram."""

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


@dataclass
class TelegramConfig:
    """Configurazione del plugin Telegram."""
    admin_user_id: int | None
    allowed_users: str | list[int]  # "*" oppure lista di user_id Telegram
    mode: str  # "polling" | "webhook"
    webhook_url: str | None
    webhook_port: int
    reply_mode: str  # "all" | "mention"
    show_tool_steps: bool  # Mostra il messaggio con gli step dei tool

    def is_user_allowed(self, user_id: int | None) -> bool:
        """Verifica se l'utente è autorizzato a usare il bot."""
        if self.allowed_users == "*":
            return True
        if user_id is None:
            return False
        if isinstance(self.allowed_users, list):
            return user_id in self.allowed_users
        return False


def _parse_allowed_users(raw) -> str | list[int]:
    """Normalizza il valore di allowed_users dal YAML."""
    if raw == "*":
        return "*"
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, str) and raw.isdigit():
        return [int(raw)]
    if isinstance(raw, list):
        return [int(x) for x in raw]
    return "*"


def load_config() -> TelegramConfig:
    """Legge config.yaml e restituisce un oggetto TelegramConfig."""
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    tg = raw.get("telegram", {})
    wh = tg.get("webhook", {})
    return TelegramConfig(
        admin_user_id=tg.get("admin_user_id"),
        allowed_users=_parse_allowed_users(tg.get("allowed_users", "*")),
        mode=tg.get("mode", "polling"),
        webhook_url=wh.get("url"),
        webhook_port=wh.get("port", 8443),
        reply_mode=tg.get("reply_mode", "all"),
        show_tool_steps=tg.get("show_tool_steps", True),
    )


# Singleton accessibile da tutti i moduli del plugin
config = load_config()


def reload_config() -> TelegramConfig:
    """Ricarica la configurazione da disco e aggiorna il singleton."""
    global config
    config = load_config()
    return config


def save_allowed_users(users: str | list[int]) -> None:
    """Aggiorna allowed_users nel config.yaml e ricarica il singleton."""
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["telegram"]["allowed_users"] = users
    CONFIG_PATH.write_text(
        yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    reload_config()
