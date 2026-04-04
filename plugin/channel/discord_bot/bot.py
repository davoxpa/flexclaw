import asyncio
import logging
import os
import ssl

import aiohttp
import certifi
import discord

from core.logging_config import _make_handler
from core import notification_registry
from plugin.channel.discord_bot.config import config
from plugin.channel.discord_bot.handlers import setup_handlers

logger = logging.getLogger(__name__)

# Aggiunge l'handler su file dedicato solo la prima volta (evita duplicati al reload)
_channel_logger = logging.getLogger("plugin.channel.discord_bot")
if not _channel_logger.handlers:
    _channel_logger.addHandler(_make_handler("discord.log"))

# Evento per segnalare lo shutdown dall'esterno
shutdown_event: asyncio.Event | None = None


def _build_client() -> discord.Client:
    """Crea il client Discord con gli intents necessari."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)

    # Registra tutti gli handler e i comandi slash
    setup_handlers(client, tree)

    @client.event
    async def on_ready():
        """Sincronizza i comandi slash al primo avvio."""
        # Sincronizza comandi nelle guild configurate o globalmente
        if config.guild_ids:
            for guild_id in config.guild_ids:
                guild = discord.Object(id=guild_id)
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
        else:
            await tree.sync()

        logger.info(
            "Bot Discord connesso come %s (ID: %s) — %d server",
            client.user.name,
            client.user.id,
            len(client.guilds),
        )
        # Log dettagliato delle guild per facilitare la configurazione
        for guild in client.guilds:
            logger.info(
                "  Guild: %s (ID: %s) — %d membri",
                guild.name,
                guild.id,
                guild.member_count or 0,
            )
            # Logga i membri solo se già in cache (richiede intent members)
            if guild.members:
                for member in guild.members:
                    if not member.bot:
                        logger.info(
                            "    Utente: %s (ID: %s)",
                            member.name,
                            member.id,
                        )

    @client.event
    async def on_error(event_name, *args, **kwargs):
        """Gestisce errori non catturati dagli handler."""
        logger.exception("Errore non gestito nell'evento '%s'", event_name)

    return client


def _resolve_discord_channel_id(http_client: "httpx.Client", token: str, channel_id: str) -> str:
    """Risolve il nome di un canale Discord al suo ID numerico.

    Se `channel_id` è già numerico lo restituisce invariato.
    Altrimenti cerca nelle guild del bot il canale con quel nome.
    """
    if channel_id.isdigit():
        return channel_id

    auth_headers = {"Authorization": f"Bot {token}"}
    # Ottieni tutte le guild del bot
    guilds_resp = http_client.get(
        "https://discord.com/api/v10/users/@me/guilds",
        headers=auth_headers,
    )
    guilds_resp.raise_for_status()

    for guild in guilds_resp.json():
        channels_resp = http_client.get(
            f"https://discord.com/api/v10/guilds/{guild['id']}/channels",
            headers=auth_headers,
        )
        if channels_resp.status_code != 200:
            continue
        for ch in channels_resp.json():
            # Tipo 0 = canale testuale
            if ch.get("type") == 0 and ch.get("name") == channel_id:
                logger.debug("Canale Discord '%s' risolto → ID %s", channel_id, ch["id"])
                return ch["id"]

    raise ValueError(f"Canale Discord '{channel_id}' non trovato nelle guild del bot")


def _make_discord_sender():
    """Crea e restituisce la funzione di invio notifiche per il notification_registry.

    Usa httpx + certifi per evitare errori SSL su macOS.
    Supporta sia ID numerici che nomi del canale (risolve automaticamente via API).
    """
    import os
    import httpx

    def sender(channel_id: str, text: str, task_name: str | None) -> bool:
        token = os.environ.get("DISCORD_TOKEN")
        if not token:
            logger.warning("DISCORD_TOKEN non configurato — notifica scheduler Discord non inviata")
            return False
        header = f"\u23f0 **Task: {task_name}**\n\n" if task_name else ""
        message = (header + text)[:2000]
        try:
            with httpx.Client(verify=certifi.where(), timeout=30) as client:
                resolved_id = _resolve_discord_channel_id(client, token, channel_id)
                resp = client.post(
                    f"https://discord.com/api/v10/channels/{resolved_id}/messages",
                    json={"content": message},
                    headers={"Authorization": f"Bot {token}"},
                )
                resp.raise_for_status()
                return resp.status_code in (200, 201)
        except Exception as exc:
            logger.error("Errore invio notifica Discord scheduler: %s", exc)
            return False

    return sender


def start_bot(stop_event: asyncio.Event | None = None) -> None:
    """Entry point sincrono — chiamato dal loader in un thread daemon."""
    global shutdown_event
    shutdown_event = stop_event

    # Registra il sender nel registry centralizzato (usato dallo scheduler)
    notification_registry.register("discord", _make_discord_sender())

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN non impostato nell'ambiente — bot Discord non avviato")
        return

    client = _build_client()

    # Intercetta la creazione della session HTTP di discord.py per iniettare
    # un connector con i certificati CA di certifi.
    # Su macOS, Python 3.11 non carica i CA di sistema; discord.py crea
    # il connector senza contesto SSL esplicito causando CERTIFICATE_VERIFY_FAILED.
    _original_static_login = client.http.static_login

    async def _static_login_with_ssl(token: str):
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        client.http.connector = aiohttp.TCPConnector(limit=0, ssl=ssl_ctx)
        return await _original_static_login(token)

    client.http.static_login = _static_login_with_ssl

    logger.debug("Bot Discord avviato")

    try:
        client.run(token, log_handler=None)
    except Exception:
        logger.exception("Errore fatale nel bot Discord")
