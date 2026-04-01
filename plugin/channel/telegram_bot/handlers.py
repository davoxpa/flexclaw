from core.audit import audit_log

from pathlib import Path

# Importa la funzione per ottenere la sandbox dal config di progetto
from core.loader import get_sandbox_dir
# --- Sicurezza: sanitizzazione input e validazione file ---
import re

ALLOWED_FILE_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

def sanitize_user_input(text: str) -> str:
    """Sanitizza input utente rimuovendo caratteri pericolosi e normalizzando lo spazio."""
    # Rimuove caratteri di controllo, escape, sequenze sospette
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalizza whitespace multiplo
    text = re.sub(r"\s+", " ", text).strip()
    # Limita la lunghezza massima (difensivo)
    return text[:2000]

def is_valid_file(file_path: Path) -> tuple[bool, str]:
    """Verifica estensione e dimensione file."""
    ext = file_path.suffix.lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"Estensione non ammessa: {ext}"
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        return False, f"File troppo grande: {size//1024//1024}MB (max {MAX_FILE_SIZE_MB}MB)"
    return True, ""
import logging

from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.ext import ContextTypes

from core.agent_os import (
    get_available_models,
    get_current_model,
    knowledge_count,
    knowledge_list,
    knowledge_search,
    set_model,
    validate_model_token,
)
from core.event_stream import RunProgress, stream_with_progress
from core.loader import get_enabled_plugins
from core.session import get_session_id, is_session_reset, reset_session
from plugin.channel.telegram_bot.config import config, reload_config, save_allowed_users

logger = logging.getLogger(__name__)


# Directory sandbox presa dal config di progetto
SANDBOX_DIR = Path(get_sandbox_dir())
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

# I file caricati finiscono direttamente nella sandbox
UPLOAD_DIR = SANDBOX_DIR

# Estensioni leggibili come testo (non inviate come allegati binari all'API LLM)
_TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".xml", ".html", ".css", ".js", ".py", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".rtf"}

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce messaggi di testo e li inoltra all'agente AI."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        logger.info("Utente non autorizzato: %s", user.id if user else "unknown")
        return

    should_reply, text = _should_reply(update, context)
    if not should_reply:
        return
    # Sanitizza input utente
    text = sanitize_user_input(text)

    chat_id = update.effective_chat.id
    username = user.username or user.first_name if user else "unknown"
    logger.info(
        "Messaggio ricevuto da %s (id=%s, chat=%d): %s",
        username,
        user.id if user else "?",
        chat_id,
        text[:200] + "..." if len(text) > 200 else text,
    )

    # Contesto dal messaggio citato (reply)
    reply_ctx = _get_reply_context(update.message)
    file_paths: list[Path] = []
    inline_parts: list[str] = []

    # Se il reply contiene un file, lo scarica nella sandbox
    reply = update.message.reply_to_message
    if reply and (reply.document or reply.photo or reply.audio or reply.video or reply.voice):
        reply_file = await _download_file_from_message(reply)
        if reply_file:
            valid, reason = is_valid_file(reply_file)
            audit_log(_user_id(user.id if user else None), "file_reply_upload", {"file": str(reply_file), "valid": valid, "reason": reason})
            if not valid:
                await update.message.reply_text(f"❌ File non valido: {reason}")
                return
            text_content = _read_text_file(reply_file)
            if text_content is not None:
                inline_parts.append(f"[Contenuto del file {reply_file.name}]:\n{text_content}")
            else:
                file_paths.append(reply_file)

    parts = []
    if reply_ctx:
        parts.append(reply_ctx)
    if inline_parts:
        parts.extend(inline_parts)
    parts.append(text)
    full_message = "\n\n".join(parts)

    audit_log(_user_id(user.id if user else None), "user_message", {"text": text, "files": [str(f) for f in file_paths]})
    await _stream_and_respond(
        update=update,
        message=full_message,
        user_id=_user_id(user.id if user else None),
        session_id=_session_id(chat_id),
        file_paths=file_paths or None,
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce messaggi con file allegati e li inoltra all'agente AI."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        logger.info("Utente non autorizzato (file): %s", user.id if user else "unknown")
        return

    chat_id = update.effective_chat.id
    caption = update.message.caption or ""
    username = user.username or user.first_name if user else "unknown"

    file_path = await _download_file(update, context)
    if not file_path:
        await update.message.reply_text("Formato file non supportato.")
        return
    valid, reason = is_valid_file(file_path)
    audit_log(_user_id(user.id if user else None), "file_upload", {"file": str(file_path), "valid": valid, "reason": reason})
    if not valid:
        await update.message.reply_text(f"❌ File non valido: {reason}")
        return

    logger.info(
        "File ricevuto da %s (id=%s, chat=%d): %s caption=%s",
        username,
        user.id if user else "?",
        chat_id,
        file_path.name,
        caption[:100] if caption else "",
    )

    # Contesto dal messaggio citato (reply)
    reply_ctx = _get_reply_context(update.message)
    base_message = caption or f"Analizza questo file: {file_path.name}"
    if reply_ctx:
        base_message = f"{reply_ctx}\n{base_message}".strip()

    await update.message.reply_text(
        f"📎 File ricevuto: *{file_path.name}*\nElaborazione in corso…",
        parse_mode="Markdown",
    )

    # File di testo → contenuto inline; binari → allegato
    text_content = _read_text_file(file_path)
    if text_content is not None:
        full_message = f"{base_message}\n\n[Contenuto del file {file_path.name}]:\n{text_content}"
        audit_log(_user_id(user.id if user else None), "file_text_content", {"file": str(file_path)})
        await _stream_and_respond(
            update=update,
            message=full_message,
            user_id=_user_id(user.id if user else None),
            session_id=_session_id(chat_id),
        )
    else:
        await _stream_and_respond(
            update=update,
            message=base_message,
            user_id=_user_id(user.id if user else None),
            session_id=_session_id(chat_id),
            file_paths=[file_path],
        )


# Limite massimo per un singolo messaggio Telegram
MAX_MSG_LEN = 4096

# Identificativo del canale per il session manager
_CHANNEL = "tg"


def _session_id(chat_id: int) -> str:
    """Session ID via core session manager."""
    return get_session_id(_CHANNEL, chat_id)


def _user_id(user_id: int | None) -> str:
    """Genera un user_id dal profilo Telegram."""
    return f"tg_user_{user_id}" if user_id else "tg_anonymous"


async def _send_long_text(update: Update, text: str) -> None:
    """Invia risposte lunghe suddividendole in chunk."""
    for i in range(0, len(text), MAX_MSG_LEN):
        await update.message.reply_text(text[i : i + MAX_MSG_LEN])


def _snapshot_sandbox() -> dict[Path, float]:
    """Restituisce una mappa file → mtime dei file nella sandbox."""
    if not SANDBOX_DIR.exists():
        return {}
    return {f: f.stat().st_mtime for f in SANDBOX_DIR.rglob("*") if f.is_file()}


async def _send_new_files(
    update: Update,
    run_completed,
    before: dict[Path, float],
) -> None:
    """Invia via Telegram i file creati o modificati dall'agente."""
    files_to_send: list[Path] = []

    # 1. File nuovi O modificati nella sandbox
    after = _snapshot_sandbox()
    for fp, mtime in after.items():
        is_new = fp not in before
        is_modified = fp in before and mtime > before[fp]
        if (is_new or is_modified) and fp not in files_to_send:
            files_to_send.append(fp)

    # Invia ogni file come documento Telegram
    for file_path in files_to_send:
        try:
            await update.message.reply_document(
                document=file_path.open("rb"),
                filename=file_path.name,
            )
            logger.info("File inviato via Telegram: %s", file_path.name)
        except Exception:
            logger.exception("Errore nell'invio del file %s", file_path.name)


async def _safe_edit(msg, text: str, parse_mode: str | None = None) -> None:
    """Modifica un messaggio ignorando errori di contenuto invariato o rete."""
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
    except BadRequest:
        pass
    except (TimedOut, NetworkError):
        logger.debug("Timeout/rete durante edit messaggio, skip")


def _format_step_line(tool_name: str, args: dict | None, status: str) -> str:
    """Formatta una singola riga dello step con icona di stato e dettagli."""
    icons = {"running": "⏳", "done": "✅", "error": "❌"}
    icon = icons.get(status, "⏳")
    detail = ""
    if args:
        for key in ("query", "file_name", "filename", "path", "filepath", "url", "input"):
            if key in args and args[key]:
                value = str(args[key])
                # Tronca valori troppo lunghi per leggibilità
                if len(value) > 60:
                    value = value[:57] + "..."
                detail = f'  "{value}"'
                break
    return f"  {icon} {tool_name}{detail}"


# Icone per gli stati dei task
_TASK_ICONS = {
    "pending": "⬜",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
    "blocked": "🚫",
}


def _build_steps_text(tasks: list[dict], tool_steps: list[dict]) -> str:
    """Costruisce il blocco di testo con task e tool step raggruppati per agente."""
    lines: list[str] = []

    # Sezione task (decomposizione del prompt)
    if tasks:
        lines.append("📋 Task")
        for task in tasks:
            icon = _TASK_ICONS.get(task["status"], "⬜")
            assignee = f" → {task['assignee']}" if task.get("assignee") else ""
            lines.append(f"  {icon} {task['title']}{assignee}")

    # Sezione tool call raggruppati per agente
    if tool_steps:
        if tasks:
            lines.append("")
        # Raggruppa gli step per agente mantenendo l'ordine di apparizione
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


async def _stream_and_respond(
    update: Update,
    message: str,
    user_id: str,
    session_id: str,
    file_paths: list[Path] | None = None,
) -> None:
    """Esegue lo streaming: messaggio 1 con task/step live, messaggio 2 con risposta pulita."""
    before = _snapshot_sandbox()
    show_steps = config.show_tool_steps
    status_msg = None
    run_completed_event = None
    last_progress: RunProgress | None = None

    async for progress in stream_with_progress(
        message=message,
        user_id=user_id,
        session_id=session_id,
        file_paths=file_paths,
    ):
        last_progress = progress

        # Aggiorna messaggio con step live
        if show_steps and (progress.tasks or progress.tool_steps):
            text = _build_steps_text(
                [{"id": t.id, "title": t.title, "assignee": t.assignee, "status": t.status} for t in progress.tasks],
                [{"id": s.id, "name": s.name, "args": s.args, "status": s.status, "agent": s.agent} for s in progress.tool_steps],
            )
            if status_msg is None:
                status_msg = await update.message.reply_text(text, parse_mode="MarkdownV2")
            else:
                await _safe_edit(status_msg, text, parse_mode="MarkdownV2")

        if progress.completed:
            run_completed_event = progress.raw_completed_event

    # Messaggio finale con risposta pulita
    final_content = last_progress.final_content if last_progress else None
    response = final_content or "Nessuna risposta dall'agente."
    await _send_long_text(update, response)
    await _send_new_files(update, run_completed_event, before)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Risponde al comando /start."""
    await update.message.reply_text(
        "Ciao! Sono FlexClaw 🐾\n"
        "Mandami un messaggio o un file e ti risponderò con l'AI.\n"
        "Digita /help per vedere i comandi disponibili."
    )


# ── Comandi Telegram ────────────────────────────────────────────────────────

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra l'elenco dei comandi disponibili."""
    text = (
        "🐾 *Comandi FlexClaw*\n\n"
        "/help — Mostra questo messaggio\n"
        "/status — Stato del sistema\n"
        "/model — Mostra/cambia modello AI\n"
        "/reset — Resetta la sessione corrente\n"
        "/history — Info sulla sessione corrente\n"
        "/knowledge — Cerca nella knowledge base\n"
    )

    # Comandi admin visibili solo all'admin
    user = update.effective_user
    if user and user.id == config.admin_user_id:
        text += (
            "\n🔐 *Comandi Admin*\n"
            "/model <provider:model\\_id> — Cambia modello\n"
            "/users — Gestione utenti autorizzati\n"
            "/logs — Consulta log recenti\n"
            "/reload — Ricarica configurazione\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resetta la sessione corrente creando un nuovo session_id."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        return

    chat_id = update.effective_chat.id
    new_session = reset_session(_CHANNEL, chat_id)

    logger.info("Sessione resettata per chat %d → %s", chat_id, new_session)
    await update.message.reply_text("✅ Sessione resettata. Il contesto precedente è stato dimenticato.")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra lo stato del sistema: modello, plugin, sessione."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        return

    chat_id = update.effective_chat.id
    channels, tools = get_enabled_plugins()

    channels_str = ", ".join(channels) if channels else "nessuno"
    tools_str = ", ".join(tools) if tools else "nessuno"

    text = (
        "📊 *Stato FlexClaw*\n\n"
        f"🤖 Modello: `{get_current_model()}`\n"
        f"💬 Sessione: `{_session_id(chat_id)}`\n"
        f"📡 Canali attivi: {len(channels)} (`{channels_str}`)\n"
        f"🔧 Tool attivi: {len(tools)} (`{tools_str}`)\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# Prefisso per i callback data dei bottoni modello
_MODEL_CB_PREFIX = "model:"


def _build_model_keyboard() -> InlineKeyboardMarkup:
    """Costruisce la tastiera inline con un bottone per ogni modello disponibile."""
    current = get_current_model()
    buttons = []
    for m in get_available_models():
        label = f"✅ {m}" if m == current else m
        buttons.append([InlineKeyboardButton(label, callback_data=f"{_MODEL_CB_PREFIX}{m}")])
    return InlineKeyboardMarkup(buttons)


async def handle_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra il modello corrente con bottoni per cambiarlo (admin)."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        return

    is_admin = user and user.id == config.admin_user_id
    text = f"🤖 *Modello attuale:* `{get_current_model()}`"

    if is_admin:
        text += "\n\nSeleziona un modello:"
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=_build_model_keyboard(),
        )
    else:
        models_list = "\n".join(f"  • `{m}`" for m in get_available_models())
        text += f"\n\n📋 *Modelli disponibili:*\n{models_list}"
        await update.message.reply_text(text, parse_mode="Markdown")


async def handle_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il tap sui bottoni di selezione modello."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not user or user.id != config.admin_user_id:
        await query.answer("🔒 Solo l'admin può cambiare modello.", show_alert=True)
        return

    new_model = query.data.removeprefix(_MODEL_CB_PREFIX)

    # Se è già il modello attivo, non fare nulla
    if new_model == get_current_model():
        await query.answer("Già selezionato.")
        return

    # Verifica che sia nella lista
    if new_model not in get_available_models():
        await query.answer("❌ Modello non disponibile.", show_alert=True)
        return

    ok, message = set_model(new_model)
    if ok:
        # Aggiorna il messaggio con la nuova selezione
        text = f"🤖 *Modello attuale:* `{get_current_model()}`\n\nSeleziona un modello:"
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=_build_model_keyboard(),
        )
    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra informazioni sulla sessione corrente."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        return

    chat_id = update.effective_chat.id
    session = _session_id(chat_id)
    was_reset = is_session_reset(_CHANNEL, chat_id)

    text = (
        "📜 *Info Sessione*\n\n"
        f"🆔 Session ID: `{session}`\n"
        f"🔄 Resettata: {'sì' if was_reset else 'no'}\n"
        f"📝 Storico: ultime 5 conversazioni in memoria\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cerca nella knowledge base o mostra informazioni."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        return

    query = " ".join(context.args) if context.args else ""

    if not query:
        # Listing documenti tramite API core
        count, docs = knowledge_list()
        if count == 0:
            await update.message.reply_text(
                "🧠 *Knowledge Base*\n\nLa knowledge base è vuota.\n"
                "Invia un file o chiedi di salvare un contenuto per popolarla.",
                parse_mode="Markdown",
            )
            return

        lines = [f"🧠 *Knowledge Base* ({count} chunk, {len(docs)} documenti)\n"]
        for i, (name, ftype) in enumerate(docs.items(), 1):
            lines.append(f"{i}. {name}  `[{ftype}]`")
        lines.append("\n`/knowledge <termine>` per cercare")

        text = "\n".join(lines)
        if len(text) > MAX_MSG_LEN:
            text = text[: MAX_MSG_LEN - 3] + "..."

        await update.message.reply_text(text, parse_mode="Markdown")
        return

    # Ricerca tramite API core
    try:
        results = knowledge_search(query=query, max_results=5)
        if not results:
            await update.message.reply_text(f"🔍 Nessun risultato per: _{query}_", parse_mode="Markdown")
            return

        text = f"🔍 *Risultati per:* _{query}_\n\n"
        for i, doc in enumerate(results, 1):
            name = doc.name or "Senza titolo"
            content = doc.content or ""
            preview = content[:200] + "..." if len(content) > 200 else content
            text += f"*{i}. {name}*\n{preview}\n\n"

        if len(text) > MAX_MSG_LEN:
            text = text[: MAX_MSG_LEN - 3] + "..."

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Errore nella ricerca knowledge")
        await update.message.reply_text("❌ Errore durante la ricerca nella knowledge base.")


# ── Comandi Admin ───────────────────────────────────────────────────────────

def _is_admin(update: Update) -> bool:
    """Verifica se l'utente è l'admin configurato."""
    user = update.effective_user
    return user is not None and user.id == config.admin_user_id


async def handle_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce gli utenti autorizzati (solo admin).

    /users           → mostra la lista utenti
    /users add <id>  → aggiunge un utente
    /users rm <id>   → rimuove un utente
    /users set *     → apre a tutti
    """
    if not _is_admin(update):
        await update.message.reply_text("🔒 Comando riservato all'admin.")
        return

    args = context.args or []

    # Nessun argomento → mostra lista attuale
    if not args:
        users = config.allowed_users
        if users == "*":
            text = "👥 *Utenti autorizzati:* tutti (`*`)"
        else:
            lines = [f"👥 *Utenti autorizzati:* {len(users)}\n"]
            for uid in users:
                lines.append(f"  • `{uid}`")
            lines.append("\n`/users add <id>` — aggiungi")
            lines.append("`/users rm <id>` — rimuovi")
            lines.append("`/users set *` — apri a tutti")
            text = "\n".join(lines)
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    action = args[0].lower()

    if action == "set" and len(args) == 2 and args[1] == "*":
        save_allowed_users("*")
        logger.info("Admin ha aperto il bot a tutti gli utenti")
        await update.message.reply_text("✅ Bot aperto a tutti gli utenti.")
        return

    if action in ("add", "rm") and len(args) == 2:
        try:
            target_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ ID utente non valido. Deve essere un numero.")
            return

        current = config.allowed_users
        # Se attualmente è "*", converti in lista con solo l'admin
        if current == "*":
            current = [config.admin_user_id] if config.admin_user_id else []

        if action == "add":
            if target_id in current:
                await update.message.reply_text(f"ℹ️ Utente `{target_id}` già autorizzato.")
                return
            current.append(target_id)
            save_allowed_users(current)
            logger.info("Admin ha aggiunto utente %d", target_id)
            await update.message.reply_text(f"✅ Utente `{target_id}` aggiunto.")

        else:  # action == "rm"
            if target_id not in current:
                await update.message.reply_text(f"ℹ️ Utente `{target_id}` non in lista.")
                return
            current.remove(target_id)
            save_allowed_users(current)
            logger.info("Admin ha rimosso utente %d", target_id)
            await update.message.reply_text(f"✅ Utente `{target_id}` rimosso.")



        # ...existing code...

async def handle_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra le ultime righe dei log (solo admin).

    /logs           → ultime 20 righe di telegram.log
    /logs <n>       → ultime n righe (max 50)
    /logs app       → ultime 20 righe di app.log
    /logs core      → ultime 20 righe di core.log
    """
    if not _is_admin(update):
        await update.message.reply_text("🔒 Comando riservato all'admin.")
        return

    from core.logging_config import LOG_DIR

    args = context.args or []

    # Individua file e numero righe
    log_file = "telegram.log"
    num_lines = 20

    for arg in args:
        if arg.isdigit():
            num_lines = min(int(arg), 50)
        elif arg in ("app", "core", "tools", "telegram"):
            log_file = f"{arg}.log"

    log_path = LOG_DIR / log_file
    if not log_path.exists():
        await update.message.reply_text(f"📄 File `{log_file}` non trovato.")
        return

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        tail = lines[-num_lines:] if len(lines) > num_lines else lines
        content = "\n".join(tail)

        # Tronca se troppo lungo per Telegram
        if len(content) > MAX_MSG_LEN - 30:
            content = content[-(MAX_MSG_LEN - 30):]

        text = f"📋 *{log_file}* (ultime {len(tail)} righe)\n\n```\n{content}\n```"
        if len(text) > MAX_MSG_LEN:
            # Se il blocco code è troppo grande, invia come testo semplice
            text = f"📋 {log_file} (ultime {len(tail)} righe)\n\n{content}"
            await _send_long_text(update, text)
        else:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Errore nella lettura dei log")
        await update.message.reply_text("❌ Errore nella lettura dei log.")


async def handle_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ricarica la configurazione del plugin Telegram senza riavvio (solo admin)."""
    if not _is_admin(update):
        await update.message.reply_text("🔒 Comando riservato all'admin.")
        return

    try:
        new_config = reload_config()
        logger.info("Configurazione Telegram ricaricata dall'admin")
        text = (
            "🔄 *Configurazione ricaricata*\n\n"
            f"👤 Admin: `{new_config.admin_user_id}`\n"
            f"👥 Utenti: `{new_config.allowed_users}`\n"
            f"📡 Modo: `{new_config.mode}`\n"
            f"💬 Reply mode: `{new_config.reply_mode}`\n"
            f"🔧 Tool steps: `{new_config.show_tool_steps}`\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        logger.exception("Errore nel reload della configurazione")
        await update.message.reply_text("❌ Errore nel reload della configurazione.")


def _get_reply_context(message) -> str:
    """Estrae il contesto dal messaggio a cui si sta facendo reply."""
    reply = message.reply_to_message
    if not reply:
        return ""

    parts: list[str] = []

    # Testo del messaggio originale
    if reply.text:
        parts.append(f"[Messaggio citato]: {reply.text}")
    elif reply.caption:
        parts.append(f"[Didascalia citata]: {reply.caption}")

    # File allegato al messaggio originale
    if reply.document:
        parts.append(f"[File citato]: {reply.document.file_name or 'documento'}")
    elif reply.photo:
        parts.append("[Foto citata]")
    elif reply.audio:
        parts.append(f"[Audio citato]: {reply.audio.file_name or 'audio'}")
    elif reply.video:
        parts.append(f"[Video citato]: {reply.video.file_name or 'video'}")
    elif reply.voice:
        parts.append("[Messaggio vocale citato]")

    return "\n".join(parts)


def _should_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """Determina se il bot deve rispondere e restituisce il testo pulito."""
    text = update.message.text or ""
    chat_type = update.effective_chat.type

    # Nelle chat private risponde sempre
    if chat_type == "private":
        return True, text

    # Nei gruppi, in modalità "mention" risponde solo se citato con @
    if config.reply_mode == "mention":
        bot_username = context.bot.username
        if bot_username and f"@{bot_username}" in text:
            clean_text = text.replace(f"@{bot_username}", "").strip()
            return True, clean_text
        return False, text

    # reply_mode "all" → risponde sempre
    return True, text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce messaggi di testo e li inoltra all'agente AI."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        logger.info("Utente non autorizzato: %s", user.id if user else "unknown")
        return

    should_reply, text = _should_reply(update, context)
    if not should_reply:
        return

    chat_id = update.effective_chat.id
    username = user.username or user.first_name if user else "unknown"
    logger.info(
        "Messaggio ricevuto da %s (id=%s, chat=%d): %s",
        username,
        user.id if user else "?",
        chat_id,
        text[:200] + "..." if len(text) > 200 else text,
    )

    # Contesto dal messaggio citato (reply)
    reply_ctx = _get_reply_context(update.message)
    file_paths: list[Path] = []
    inline_parts: list[str] = []

    # Se il reply contiene un file, lo scarica nella sandbox
    reply = update.message.reply_to_message
    if reply and (reply.document or reply.photo or reply.audio or reply.video or reply.voice):
        reply_file = await _download_file_from_message(reply)
        if reply_file:
            # File di testo → contenuto inline; binari → allegato
            text_content = _read_text_file(reply_file)
            if text_content is not None:
                inline_parts.append(f"[Contenuto del file {reply_file.name}]:\n{text_content}")
            else:
                file_paths.append(reply_file)

    parts = []
    if reply_ctx:
        parts.append(reply_ctx)
    if inline_parts:
        parts.extend(inline_parts)
    parts.append(text)
    full_message = "\n\n".join(parts)

    await _stream_and_respond(
        update=update,
        message=full_message,
        user_id=_user_id(user.id if user else None),
        session_id=_session_id(chat_id),
        file_paths=file_paths or None,
    )


async def _download_file_from_message(message) -> Path | None:
    """Scarica il file allegato a un messaggio Telegram e lo salva nella sandbox."""
    if message.photo:
        file_obj = await message.photo[-1].get_file()
        filename = f"{file_obj.file_unique_id}.jpg"
    elif message.audio:
        file_obj = await message.audio.get_file()
        filename = message.audio.file_name or f"{file_obj.file_unique_id}.mp3"
    elif message.voice:
        file_obj = await message.voice.get_file()
        filename = f"{file_obj.file_unique_id}.ogg"
    elif message.video:
        file_obj = await message.video.get_file()
        filename = message.video.file_name or f"{file_obj.file_unique_id}.mp4"
    elif message.document:
        file_obj = await message.document.get_file()
        filename = message.document.file_name or f"{file_obj.file_unique_id}"
    else:
        return None

    dest = UPLOAD_DIR / filename
    await file_obj.download_to_drive(str(dest))
    logger.info("File scaricato: %s", dest)
    return dest


async def _download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Path | None:
    """Scarica il file allegato al messaggio corrente."""
    return await _download_file_from_message(update.message)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce messaggi con file allegati e li inoltra all'agente AI."""
    user = update.effective_user
    if not config.is_user_allowed(user.id if user else None):
        logger.info("Utente non autorizzato (file): %s", user.id if user else "unknown")
        return

    chat_id = update.effective_chat.id
    caption = update.message.caption or ""
    username = user.username or user.first_name if user else "unknown"

    file_path = await _download_file(update, context)
    if not file_path:
        await update.message.reply_text("Formato file non supportato.")
        return

    logger.info(
        "File ricevuto da %s (id=%s, chat=%d): %s caption=%s",
        username,
        user.id if user else "?",
        chat_id,
        file_path.name,
        caption[:100] if caption else "",
    )

    # Contesto dal messaggio citato (reply)
    reply_ctx = _get_reply_context(update.message)
    base_message = caption or f"Analizza questo file: {file_path.name}"
    if reply_ctx:
        base_message = f"{reply_ctx}\n{base_message}".strip()

    await update.message.reply_text(
        f"📎 File ricevuto: *{file_path.name}*\nElaborazione in corso…",
        parse_mode="Markdown",
    )

    # File di testo → contenuto inline; binari → allegato
    text_content = _read_text_file(file_path)
    if text_content is not None:
        full_message = f"{base_message}\n\n[Contenuto del file {file_path.name}]:\n{text_content}"
        await _stream_and_respond(
            update=update,
            message=full_message,
            user_id=_user_id(user.id if user else None),
            session_id=_session_id(chat_id),
        )
    else:
        await _stream_and_respond(
            update=update,
            message=base_message,
            user_id=_user_id(user.id if user else None),
            session_id=_session_id(chat_id),
            file_paths=[file_path],
        )
