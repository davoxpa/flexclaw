"""Handler per messaggi, file e comandi slash del bot Discord."""

import logging
import re
from pathlib import Path

import discord

from core.audit import audit_log
from core.agent_os import (
    get_available_models,
    get_current_model,
    knowledge_list,
    knowledge_search,
    set_model,
)
from core.event_stream import RunProgress, stream_with_progress
from core.loader import get_enabled_plugins, get_sandbox_dir
from core.session import get_session_id, is_session_reset, reset_session
from plugin.channel.discord_bot.config import config, reload_config, save_allowed_users

logger = logging.getLogger(__name__)

# Directory sandbox presa dal config di progetto
SANDBOX_DIR = Path(get_sandbox_dir())
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

# Limite massimo per un singolo messaggio Discord
MAX_MSG_LEN = 2000

# Identificativo del canale per il session manager
_CHANNEL = "dc"

# --- Sicurezza: sanitizzazione input e validazione file ---

ALLOWED_FILE_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# Estensioni leggibili come testo (non inviate come allegati binari all'API LLM)
_TEXT_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".xml", ".html", ".css", ".js",
    ".py", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".rtf",
}


def sanitize_user_input(text: str) -> str:
    """Sanitizza input utente rimuovendo caratteri pericolosi e normalizzando lo spazio."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def is_valid_file(file_path: Path) -> tuple[bool, str]:
    """Verifica estensione e dimensione file."""
    ext = file_path.suffix.lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"Estensione non ammessa: {ext}"
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        return False, f"File troppo grande: {size // 1024 // 1024}MB (max {MAX_FILE_SIZE_MB}MB)"
    return True, ""


def _read_text_file(file_path: Path, max_chars: int = 15000) -> str | None:
    """Legge il contenuto di un file di testo, troncando se troppo lungo."""
    if file_path.suffix.lower() not in _TEXT_EXTENSIONS:
        return None
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + "\n… [troncato]"
        return content
    except Exception:
        logger.warning("Impossibile leggere il file come testo: %s", file_path)
        return None


# --- Utilità ---


def _session_id(channel_id: int) -> str:
    """Session ID via core session manager."""
    return get_session_id(_CHANNEL, channel_id)


def _user_id(user_id: int | None) -> str:
    """Genera un user_id dal profilo Discord."""
    return f"dc_user_{user_id}" if user_id else "dc_anonymous"


def _snapshot_sandbox() -> dict[Path, float]:
    """Restituisce una mappa file → mtime dei file nella sandbox."""
    if not SANDBOX_DIR.exists():
        return {}
    return {f: f.stat().st_mtime for f in SANDBOX_DIR.rglob("*") if f.is_file()}


async def _send_long_text(destination, text: str) -> None:
    """Invia risposte lunghe suddividendole in chunk da 2000 caratteri."""
    for i in range(0, len(text), MAX_MSG_LEN):
        await destination.send(text[i : i + MAX_MSG_LEN])


async def _send_new_files(destination, before: dict[Path, float]) -> None:
    """Invia i file creati o modificati dall'agente."""
    after = _snapshot_sandbox()
    for fp, mtime in after.items():
        is_new = fp not in before
        is_modified = fp in before and mtime > before[fp]
        if is_new or is_modified:
            try:
                await destination.send(file=discord.File(str(fp), filename=fp.name))
                logger.info("File inviato via Discord: %s", fp.name)
            except Exception:
                logger.exception("Errore nell'invio del file %s", fp.name)


# --- Formattazione step dei tool ---

_TASK_ICONS = {
    "pending": "⬜",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
    "blocked": "🚫",
}


def _format_step_line(tool_name: str, args: dict | None, status: str) -> str:
    """Formatta una singola riga dello step con icona di stato e dettagli."""
    icons = {"running": "⏳", "done": "✅", "error": "❌"}
    icon = icons.get(status, "⏳")
    detail = ""
    if args:
        for key in ("query", "file_name", "filename", "path", "filepath", "url", "input"):
            if key in args and args[key]:
                value = str(args[key])
                if len(value) > 60:
                    value = value[:57] + "..."
                detail = f'  "{value}"'
                break
    return f"  {icon} {tool_name}{detail}"


def _build_steps_text(tasks: list[dict], tool_steps: list[dict]) -> str:
    """Costruisce il blocco di testo con task e tool step raggruppati per agente."""
    lines: list[str] = []

    if tasks:
        lines.append("📋 Task")
        for task in tasks:
            icon = _TASK_ICONS.get(task["status"], "⬜")
            assignee = f" → {task['assignee']}" if task.get("assignee") else ""
            lines.append(f"  {icon} {task['title']}{assignee}")

    if tool_steps:
        if tasks:
            lines.append("")
        agents_order: list[str] = []
        steps_by_agent: dict[str, list[dict]] = {}
        for step in tool_steps:
            agent = step.get("agent", "")
            if agent not in steps_by_agent:
                agents_order.append(agent)
                steps_by_agent[agent] = []
            steps_by_agent[agent].append(step)

        for agent in agents_order:
            lines.append(f"🤖 {agent}")
            for step in steps_by_agent[agent]:
                lines.append(_format_step_line(step["name"], step["args"], step["status"]))

    return "```\n" + "\n".join(lines) + "\n```"


# --- Streaming e risposta ---


async def _stream_and_respond(
    destination,
    message_text: str,
    user_id: str,
    session_id: str,
    file_paths: list[Path] | None = None,
) -> None:
    """Esegue lo streaming: messaggio con step live, poi risposta finale."""
    before = _snapshot_sandbox()
    show_steps = config.show_tool_steps
    status_msg = None
    last_progress: RunProgress | None = None

    async for progress in stream_with_progress(
        message=message_text,
        user_id=user_id,
        session_id=session_id,
        file_paths=file_paths,
    ):
        last_progress = progress

        # Aggiorna messaggio con step live
        if show_steps and (progress.tasks or progress.tool_steps):
            text = _build_steps_text(
                [
                    {"id": t.id, "title": t.title, "assignee": t.assignee, "status": t.status}
                    for t in progress.tasks
                ],
                [
                    {"id": s.id, "name": s.name, "args": s.args, "status": s.status, "agent": s.agent}
                    for s in progress.tool_steps
                ],
            )
            # Tronca se supera il limite Discord
            if len(text) > MAX_MSG_LEN:
                text = text[: MAX_MSG_LEN - 4] + "\n```"

            if status_msg is None:
                status_msg = await destination.send(text)
            else:
                try:
                    await status_msg.edit(content=text)
                except discord.HTTPException:
                    pass

    # Risposta finale
    final_content = last_progress.final_content if last_progress else None
    response = final_content or "Nessuna risposta dall'agente."
    await _send_long_text(destination, response)
    await _send_new_files(destination, before)


# --- Contesto reply ---


def _get_reply_context(message: discord.Message) -> str:
    """Estrae il contesto dal messaggio a cui si sta facendo reply."""
    ref = message.reference
    if not ref or not ref.resolved or not isinstance(ref.resolved, discord.Message):
        return ""

    original = ref.resolved
    parts: list[str] = []

    if original.content:
        parts.append(f"[Messaggio citato]: {original.content}")

    for att in original.attachments:
        parts.append(f"[File citato]: {att.filename}")

    return "\n".join(parts)


# --- Download allegati ---


async def _download_attachment(attachment: discord.Attachment) -> Path | None:
    """Scarica un allegato Discord nella sandbox."""
    # Validazione nome file: rimuove caratteri pericolosi
    safe_name = re.sub(r"[^\w.\-]", "_", attachment.filename)
    file_path = SANDBOX_DIR / safe_name

    try:
        await attachment.save(file_path)
        return file_path
    except Exception:
        logger.exception("Errore nel download dell'allegato %s", attachment.filename)
        return None


# --- Registrazione handler ---


def setup_handlers(client: discord.Client, tree: discord.app_commands.CommandTree) -> None:
    """Registra tutti gli handler e i comandi slash sul client Discord."""

    # ── Messaggi di testo e file ────────────────────────────────────────

    @client.event
    async def on_message(message: discord.Message) -> None:
        """Gestisce messaggi di testo e allegati."""
        # Ignora i messaggi del bot stesso
        if message.author == client.user:
            return

        # Ignora bot
        if message.author.bot:
            return

        # Verifica autorizzazione utente
        if not config.is_user_allowed(message.author.id):
            return

        # Verifica guild autorizzata
        if message.guild and not config.is_guild_allowed(message.guild.id):
            return

        # Logica reply_mode: in DM risponde sempre, nei canali dipende dalla config
        is_dm = isinstance(message.channel, discord.DMChannel)
        text = message.content or ""

        if not is_dm:
            if config.reply_mode == "mention":
                if not client.user or client.user not in message.mentions:
                    return
                # Rimuove la menzione dal testo
                text = text.replace(f"<@{client.user.id}>", "").strip()
                text = text.replace(f"<@!{client.user.id}>", "").strip()
            # reply_mode "all" → risponde sempre

        # Se ci sono allegati, gestiscili
        if message.attachments:
            await _handle_file_message(message, text)
            return

        # Messaggio di solo testo
        if not text:
            return

        text = sanitize_user_input(text)

        username = message.author.display_name
        logger.info(
            "Messaggio ricevuto da %s (id=%s, canale=%s): %s",
            username,
            message.author.id,
            message.channel.id,
            text[:200] + "..." if len(text) > 200 else text,
        )

        # Contesto dal messaggio citato (reply)
        reply_ctx = _get_reply_context(message)
        parts = []
        if reply_ctx:
            parts.append(reply_ctx)
        parts.append(text)
        full_message = "\n\n".join(parts)

        uid = _user_id(message.author.id)
        sid = _session_id(message.channel.id)
        audit_log(uid, "user_message", {"text": text, "channel": "discord"})

        async with message.channel.typing():
            await _stream_and_respond(
                destination=message.channel,
                message_text=full_message,
                user_id=uid,
                session_id=sid,
            )

    async def _handle_file_message(message: discord.Message, caption: str) -> None:
        """Gestisce messaggi con allegati."""
        uid = _user_id(message.author.id)
        sid = _session_id(message.channel.id)
        file_paths: list[Path] = []
        inline_parts: list[str] = []

        for attachment in message.attachments:
            file_path = await _download_attachment(attachment)
            if not file_path:
                await message.channel.send(f"❌ Impossibile scaricare: {attachment.filename}")
                continue

            valid, reason = is_valid_file(file_path)
            audit_log(uid, "file_upload", {"file": str(file_path), "valid": valid, "reason": reason})
            if not valid:
                await message.channel.send(f"❌ File non valido ({attachment.filename}): {reason}")
                continue

            # File di testo → contenuto inline; binari → allegato
            text_content = _read_text_file(file_path)
            if text_content is not None:
                inline_parts.append(f"[Contenuto del file {file_path.name}]:\n{text_content}")
            else:
                file_paths.append(file_path)

        if not file_paths and not inline_parts:
            return

        # Contesto dal messaggio citato
        reply_ctx = _get_reply_context(message)
        base_message = caption or "Analizza i file allegati."
        base_message = sanitize_user_input(base_message)

        parts = []
        if reply_ctx:
            parts.append(reply_ctx)
        if inline_parts:
            parts.extend(inline_parts)
        parts.append(base_message)
        full_message = "\n\n".join(parts)

        filenames = ", ".join(fp.name for fp in file_paths)
        if filenames:
            await message.channel.send(f"📎 File ricevuti: **{filenames}**\nElaborazione in corso…")

        async with message.channel.typing():
            await _stream_and_respond(
                destination=message.channel,
                message_text=full_message,
                user_id=uid,
                session_id=sid,
                file_paths=file_paths or None,
            )

    # ── Comandi slash ───────────────────────────────────────────────────

    @tree.command(name="help", description="Mostra i comandi disponibili")
    async def cmd_help(interaction: discord.Interaction) -> None:
        text = (
            "🐾 **Comandi FlexClaw**\n\n"
            "`/help` — Mostra questo messaggio\n"
            "`/status` — Stato del sistema\n"
            "`/model` — Mostra/cambia modello AI\n"
            "`/reset` — Resetta la sessione corrente\n"
            "`/history` — Info sulla sessione corrente\n"
            "`/knowledge` — Cerca nella knowledge base\n"
        )

        if interaction.user.id == config.admin_user_id:
            text += (
                "\n🔐 **Comandi Admin**\n"
                "`/model_set <modello>` — Cambia modello\n"
                "`/users` — Gestione utenti autorizzati\n"
                "`/users_add <id>` — Aggiungi utente\n"
                "`/users_rm <id>` — Rimuovi utente\n"
                "`/reload` — Ricarica configurazione\n"
            )

        await interaction.response.send_message(text, ephemeral=True)

    @tree.command(name="status", description="Stato del sistema")
    async def cmd_status(interaction: discord.Interaction) -> None:
        if not config.is_user_allowed(interaction.user.id):
            await interaction.response.send_message("🔒 Non autorizzato.", ephemeral=True)
            return

        channels, tools = get_enabled_plugins()
        channels_str = ", ".join(channels) if channels else "nessuno"
        tools_str = ", ".join(tools) if tools else "nessuno"

        channel_id = interaction.channel_id or 0
        text = (
            "📊 **Stato FlexClaw**\n\n"
            f"🤖 Modello: `{get_current_model()}`\n"
            f"💬 Sessione: `{_session_id(channel_id)}`\n"
            f"📡 Canali attivi: {len(channels)} (`{channels_str}`)\n"
            f"🔧 Tool attivi: {len(tools)} (`{tools_str}`)\n"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @tree.command(name="model", description="Mostra il modello AI corrente")
    async def cmd_model(interaction: discord.Interaction) -> None:
        if not config.is_user_allowed(interaction.user.id):
            await interaction.response.send_message("🔒 Non autorizzato.", ephemeral=True)
            return

        is_admin = interaction.user.id == config.admin_user_id
        current = get_current_model()
        available = get_available_models()

        if is_admin and available:
            # Menu a tendina per l'admin
            view = _ModelSelectView(available, current)
            text = f"🤖 **Modello attuale:** `{current}`\n\nSeleziona un modello:"
            await interaction.response.send_message(text, view=view, ephemeral=True)
        else:
            models_list = "\n".join(f"  • `{m}`" for m in available)
            text = f"🤖 **Modello attuale:** `{current}`\n\n📋 **Modelli disponibili:**\n{models_list}"
            await interaction.response.send_message(text, ephemeral=True)

    @tree.command(name="model_set", description="Cambia il modello AI (admin)")
    @discord.app_commands.describe(model="ID del modello da impostare")
    async def cmd_model_set(interaction: discord.Interaction, model: str) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Solo l'admin può cambiare modello.", ephemeral=True)
            return

        if model not in get_available_models():
            await interaction.response.send_message("❌ Modello non disponibile.", ephemeral=True)
            return

        ok, msg = set_model(model)
        if ok:
            await interaction.response.send_message(f"✅ Modello cambiato: `{model}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

    @tree.command(name="reset", description="Resetta la sessione corrente")
    async def cmd_reset(interaction: discord.Interaction) -> None:
        if not config.is_user_allowed(interaction.user.id):
            await interaction.response.send_message("🔒 Non autorizzato.", ephemeral=True)
            return

        channel_id = interaction.channel_id or 0
        new_session = reset_session(_CHANNEL, channel_id)
        logger.info("Sessione resettata per canale %d → %s", channel_id, new_session)
        await interaction.response.send_message(
            "✅ Sessione resettata. Il contesto precedente è stato dimenticato.",
        )

    @tree.command(name="history", description="Info sulla sessione corrente")
    async def cmd_history(interaction: discord.Interaction) -> None:
        if not config.is_user_allowed(interaction.user.id):
            await interaction.response.send_message("🔒 Non autorizzato.", ephemeral=True)
            return

        channel_id = interaction.channel_id or 0
        session = _session_id(channel_id)
        was_reset = is_session_reset(_CHANNEL, channel_id)

        text = (
            "📜 **Info Sessione**\n\n"
            f"🆔 Session ID: `{session}`\n"
            f"🔄 Resettata: {'sì' if was_reset else 'no'}\n"
            f"📝 Storico: ultime 5 conversazioni in memoria\n"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @tree.command(name="knowledge", description="Cerca nella knowledge base")
    @discord.app_commands.describe(query="Termine da cercare (vuoto = mostra documenti)")
    async def cmd_knowledge(interaction: discord.Interaction, query: str = "") -> None:
        if not config.is_user_allowed(interaction.user.id):
            await interaction.response.send_message("🔒 Non autorizzato.", ephemeral=True)
            return

        if not query:
            count, docs = knowledge_list()
            if count == 0:
                await interaction.response.send_message(
                    "🧠 **Knowledge Base**\n\nLa knowledge base è vuota.\n"
                    "Invia un file o chiedi di salvare un contenuto per popolarla.",
                )
                return

            lines = [f"🧠 **Knowledge Base** ({count} chunk, {len(docs)} documenti)\n"]
            for i, (name, ftype) in enumerate(docs.items(), 1):
                lines.append(f"{i}. {name}  `[{ftype}]`")
            lines.append("\n`/knowledge <termine>` per cercare")
            text = "\n".join(lines)
            if len(text) > MAX_MSG_LEN:
                text = text[: MAX_MSG_LEN - 3] + "..."
            await interaction.response.send_message(text)
            return

        await interaction.response.defer()

        try:
            results = knowledge_search(query=query, max_results=5)
            if not results:
                await interaction.followup.send(f"🔍 Nessun risultato per: *{query}*")
                return

            text = f"🔍 **Risultati per:** *{query}*\n\n"
            for i, doc in enumerate(results, 1):
                name = doc.name or "Senza titolo"
                content = doc.content or ""
                preview = content[:200] + "..." if len(content) > 200 else content
                text += f"**{i}. {name}**\n{preview}\n\n"

            if len(text) > MAX_MSG_LEN:
                text = text[: MAX_MSG_LEN - 3] + "..."

            await interaction.followup.send(text)
        except Exception:
            logger.exception("Errore nella ricerca knowledge")
            await interaction.followup.send("❌ Errore durante la ricerca nella knowledge base.")

    # ── Comandi Admin ───────────────────────────────────────────────────

    @tree.command(name="users", description="Mostra gli utenti autorizzati (admin)")
    async def cmd_users(interaction: discord.Interaction) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Comando riservato all'admin.", ephemeral=True)
            return

        users = config.allowed_users
        if users == "*":
            text = "👥 **Utenti autorizzati:** tutti (`*`)"
        else:
            lines = [f"👥 **Utenti autorizzati:** {len(users)}\n"]
            for uid in users:
                lines.append(f"  • `{uid}`")
            lines.append("\n`/users_add <id>` — aggiungi")
            lines.append("`/users_rm <id>` — rimuovi")
            lines.append("`/users_open` — apri a tutti")
            text = "\n".join(lines)

        await interaction.response.send_message(text, ephemeral=True)

    @tree.command(name="users_add", description="Aggiungi un utente autorizzato (admin)")
    @discord.app_commands.describe(user_id="ID Discord dell'utente da aggiungere")
    async def cmd_users_add(interaction: discord.Interaction, user_id: str) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Comando riservato all'admin.", ephemeral=True)
            return

        try:
            target_id = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ ID non valido. Deve essere un numero.", ephemeral=True)
            return

        current = config.allowed_users
        if current == "*":
            current = [config.admin_user_id] if config.admin_user_id else []

        if target_id in current:
            await interaction.response.send_message(f"ℹ️ Utente `{target_id}` già autorizzato.", ephemeral=True)
            return

        current.append(target_id)
        save_allowed_users(current)
        logger.info("Admin ha aggiunto utente %d", target_id)
        await interaction.response.send_message(f"✅ Utente `{target_id}` aggiunto.", ephemeral=True)

    @tree.command(name="users_rm", description="Rimuovi un utente autorizzato (admin)")
    @discord.app_commands.describe(user_id="ID Discord dell'utente da rimuovere")
    async def cmd_users_rm(interaction: discord.Interaction, user_id: str) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Comando riservato all'admin.", ephemeral=True)
            return

        try:
            target_id = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ ID non valido. Deve essere un numero.", ephemeral=True)
            return

        current = config.allowed_users
        if current == "*":
            await interaction.response.send_message("ℹ️ Il bot è aperto a tutti, non c'è lista.", ephemeral=True)
            return

        if target_id not in current:
            await interaction.response.send_message(f"ℹ️ Utente `{target_id}` non in lista.", ephemeral=True)
            return

        current.remove(target_id)
        save_allowed_users(current)
        logger.info("Admin ha rimosso utente %d", target_id)
        await interaction.response.send_message(f"✅ Utente `{target_id}` rimosso.", ephemeral=True)

    @tree.command(name="users_open", description="Apri il bot a tutti gli utenti (admin)")
    async def cmd_users_open(interaction: discord.Interaction) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Comando riservato all'admin.", ephemeral=True)
            return

        save_allowed_users("*")
        logger.info("Admin ha aperto il bot a tutti gli utenti")
        await interaction.response.send_message("✅ Bot aperto a tutti gli utenti.", ephemeral=True)

    @tree.command(name="reload", description="Ricarica la configurazione (admin)")
    async def cmd_reload(interaction: discord.Interaction) -> None:
        if interaction.user.id != config.admin_user_id:
            await interaction.response.send_message("🔒 Comando riservato all'admin.", ephemeral=True)
            return

        try:
            new_config = reload_config()
            logger.info("Configurazione Discord ricaricata dall'admin")
            text = (
                "🔄 **Configurazione ricaricata**\n\n"
                f"👤 Admin: `{new_config.admin_user_id}`\n"
                f"👥 Utenti: `{new_config.allowed_users}`\n"
                f"🌐 Guild: `{new_config.guild_ids}`\n"
                f"💬 Reply mode: `{new_config.reply_mode}`\n"
                f"🔧 Tool steps: `{new_config.show_tool_steps}`\n"
            )
            await interaction.response.send_message(text, ephemeral=True)
        except Exception:
            logger.exception("Errore nel reload della configurazione")
            await interaction.response.send_message("❌ Errore nel reload della configurazione.", ephemeral=True)


# --- UI Components ---


class _ModelSelect(discord.ui.Select):
    """Menu a tendina per la selezione del modello AI."""

    def __init__(self, models: list[str], current: str) -> None:
        options = [
            discord.SelectOption(
                label=m,
                value=m,
                default=(m == current),
            )
            for m in models[:25]  # Discord limita a 25 opzioni
        ]
        super().__init__(placeholder="Seleziona un modello…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        new_model = self.values[0]
        if new_model == get_current_model():
            await interaction.response.send_message("Già selezionato.", ephemeral=True)
            return

        ok, msg = set_model(new_model)
        if ok:
            await interaction.response.send_message(f"✅ Modello cambiato: `{new_model}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


class _ModelSelectView(discord.ui.View):
    """View con il menu a tendina per la selezione del modello."""

    def __init__(self, models: list[str], current: str) -> None:
        super().__init__(timeout=60)
        self.add_item(_ModelSelect(models, current))
