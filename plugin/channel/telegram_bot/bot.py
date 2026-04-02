import asyncio
import os
import logging
import time
from urllib.parse import urlparse

from telegram.error import Conflict, TimedOut, NetworkError
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from core.logging_config import _make_handler
from plugin.channel.telegram_bot.config import config
from plugin.channel.telegram_bot.handlers import (
    handle_file,
    handle_help,
    handle_history,
    handle_knowledge,
    handle_logs,
    handle_message,
    handle_model,
    handle_model_callback,
    handle_reload,
    handle_reset,
    handle_start,
    handle_status,
    handle_users,
)

logger = logging.getLogger(__name__)

# Aggiunge l'handler su file dedicato solo la prima volta (evita duplicati al reload)
_channel_logger = logging.getLogger("plugin.channel.telegram_bot")
if not _channel_logger.handlers:
    _channel_logger.addHandler(_make_handler("telegram.log"))

# Evento per segnalare lo shutdown dall'esterno
shutdown_event = None


async def _error_handler(update, context):
    """Gestisce gli errori del bot evitando log inutili per conflitti di polling."""
    if isinstance(context.error, Conflict):
        logger.warning("Conflitto polling — un'altra istanza era ancora attiva, retry automatico")
        return
    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.warning("Errore di rete temporaneo: %s", context.error)
        return
    logger.error("Errore bot non gestito: %s", context.error, exc_info=context.error)


def _build_app():
    """Crea l'Application con tutti gli handler registrati."""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN non impostato nell'ambiente")

    async def _post_init(application) -> None:
        """Registra i comandi nel menu suggerimenti di Telegram."""
        await application.bot.set_my_commands([
            BotCommand("help", "Mostra i comandi disponibili"),
            BotCommand("model", "Cambia il modello AI"),
            BotCommand("knowledge", "Cerca nella knowledge base"),
            BotCommand("status", "Stato del sistema"),
            BotCommand("history", "Cronologia della sessione"),
            BotCommand("reset", "Resetta la sessione corrente"),
        ])

    app = ApplicationBuilder().token(token).post_init(_post_init).build()

    # Comandi
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("model", handle_model))
    app.add_handler(CommandHandler("reset", handle_reset))
    app.add_handler(CommandHandler("history", handle_history))
    app.add_handler(CommandHandler("knowledge", handle_knowledge))

    # Comandi admin
    app.add_handler(CommandHandler("users", handle_users))
    app.add_handler(CommandHandler("logs", handle_logs))
    app.add_handler(CommandHandler("reload", handle_reload))

    # Callback per bottoni inline (selezione modello)
    app.add_handler(CallbackQueryHandler(handle_model_callback, pattern=r"^model:"))

    # File: foto, audio, video, documenti, messaggi vocali
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
        handle_file,
    ))

    # Messaggi di testo libero
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def start_bot(stop_event: "asyncio.Event | None" = None) -> None:
    """Entry point sincrono — sceglie polling o webhook in base alla config.

    stop_signals=() disabilita i signal handlers, rendendo il bot
    compatibile con l'esecuzione in thread secondari.
    """
    global shutdown_event
    shutdown_event = stop_event

    app = _build_app()
    app.add_error_handler(_error_handler)

    if config.mode == "webhook":
        if not config.webhook_url:
            raise RuntimeError("webhook.url non configurato in config.yaml")

        webhook_path = urlparse(config.webhook_url).path or "/telegram/webhook"
        logger.debug(
            "Bot Telegram avviato in webhook mode — url=%s porta=%s",
            config.webhook_url,
            config.webhook_port,
        )
        app.run_webhook(
            listen="0.0.0.0",
            port=config.webhook_port,
            url_path=webhook_path,
            webhook_url=config.webhook_url,
            stop_signals=(),
        )
    else:
        # Breve attesa per lasciar scadere eventuali sessioni polling precedenti
        time.sleep(1)
        logger.debug("Bot Telegram avviato in polling mode")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
            stop_signals=(),
        )
