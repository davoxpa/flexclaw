import asyncio
import logging
import os
import ssl

import aiohttp
import certifi
import discord

from plugin.channel.discord_bot.config import config
from plugin.channel.discord_bot.handlers import setup_handlers

logger = logging.getLogger(__name__)

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

    @client.event
    async def on_error(event_name, *args, **kwargs):
        """Gestisce errori non catturati dagli handler."""
        logger.exception("Errore non gestito nell'evento '%s'", event_name)

    return client


def start_bot(stop_event: asyncio.Event | None = None) -> None:
    """Entry point sincrono — chiamato dal loader in un thread daemon."""
    global shutdown_event
    shutdown_event = stop_event

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
