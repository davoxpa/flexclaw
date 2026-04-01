import logging
import mimetypes
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from agno.agent.agent import RunOutput, RunOutputEvent
from agno.media import Audio as AgnoAudio
from agno.media import File as AgnoFile
from agno.media import Image as AgnoImage
from agno.media import Video as AgnoVideo
from agno.run.team import TeamRunOutputEvent

from core.agent_os import flexclaw_team

logger = logging.getLogger(__name__)

# Estensioni raggruppate per categoria
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".csv", ".txt", ".md", ".json", ".xml", ".html",
}

ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS

# Fallback per estensioni con mime type non riconosciuto da mimetypes
_MIME_FALLBACK: dict[str, str] = {
    ".md": "text/md",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".xml": "text/xml",
    ".css": "text/css",
    ".js": "text/javascript",
    ".py": "text/x-python",
    ".rtf": "text/rtf",
    ".doc": "application/octet-stream",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/octet-stream",
    ".xlsx": "application/octet-stream",
}


def _resolve_mime(file_path: Path) -> str:
    """Determina il mime type compatibile con Agno per un file."""
    mime, _ = mimetypes.guess_type(str(file_path))
    if mime and mime != "application/octet-stream":
        return mime
    return _MIME_FALLBACK.get(file_path.suffix.lower(), "text/plain")


@dataclass
class ChatResult:
    """Risultato di una conversazione con l'agente."""
    content: Optional[str]
    session_id: str
    run_output: RunOutput


def _classify_file(file_path: Path) -> str:
    """Classifica un file in base alla sua estensione."""
    ext = file_path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


def _build_media(file_path: Path, category: str):
    """Crea l'oggetto media Agno corrispondente alla categoria."""
    mime = _resolve_mime(file_path)
    path_str = str(file_path)

    if category == "image":
        return AgnoImage(filepath=path_str)
    if category == "audio":
        return AgnoAudio(filepath=path_str, mime_type=mime)
    if category == "video":
        return AgnoVideo(filepath=path_str, mime_type=mime)
    return AgnoFile(filepath=path_str, mime_type=mime)


def _prepare_media(file_paths: list[Path]):
    """Prepara le liste di media raggruppate per tipo."""
    images: list[AgnoImage] = []
    audios: list[AgnoAudio] = []
    videos: list[AgnoVideo] = []
    documents: list[AgnoFile] = []

    for fp in file_paths:
        if fp.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        category = _classify_file(fp)
        media_obj = _build_media(fp, category)
        if category == "image":
            images.append(media_obj)
        elif category == "audio":
            audios.append(media_obj)
        elif category == "video":
            videos.append(media_obj)
        else:
            documents.append(media_obj)

    return images, audios, videos, documents


async def send_message(
    message: Optional[str] = None,
    file_paths: Optional[list[Path]] = None,
    user_id: str = "flexclaw_user",
    session_id: str = "flexclaw_session",
) -> ChatResult:
    """Invia testo e/o file al team e restituisce la risposta."""
    logger.info("send_message(user=%s, session=%s, files=%d)", user_id, session_id, len(file_paths or []))
    logger.debug("Messaggio: %s", message)
    images, audios, videos, documents = _prepare_media(file_paths or [])

    text_input = message or ""
    if not text_input and not file_paths:
        text_input = "ciao"

    # Inietta la data/ora corrente in ogni richiesta
    now = datetime.now().strftime("%d/%m/%Y, ore %H:%M")
    text_input = f"[Data e ora corrente: {now}]\n{text_input}"

    run_output = await flexclaw_team.arun(
        input=text_input,
        user_id=user_id,
        session_id=session_id,
        images=images or None,
        audio=audios or None,
        videos=videos or None,
        files=documents or None,
    )

    return ChatResult(
        content=str(run_output.content) if run_output.content else None,
        session_id=session_id,
        run_output=run_output,
    )


async def stream_message(
    message: Optional[str] = None,
    file_paths: Optional[list[Path]] = None,
    user_id: str = "flexclaw_user",
    session_id: str = "flexclaw_session",
) -> AsyncIterator[Union[RunOutputEvent, TeamRunOutputEvent]]:
    """Invia testo e/o file al team in streaming, restituendo eventi."""
    logger.info("stream_message(user=%s, session=%s, files=%d)", user_id, session_id, len(file_paths or []))
    logger.debug("Messaggio: %s", message)
    images, audios, videos, documents = _prepare_media(file_paths or [])

    text_input = message or ""
    if not text_input and not file_paths:
        text_input = "ciao"

    # Inietta la data/ora corrente in ogni richiesta
    now = datetime.now().strftime("%d/%m/%Y, ore %H:%M")
    text_input = f"[Data e ora corrente: {now}]\n{text_input}"

    event_stream = flexclaw_team.arun(
        input=text_input,
        user_id=user_id,
        session_id=session_id,
        images=images or None,
        audio=audios or None,
        videos=videos or None,
        files=documents or None,
        stream=True,
        stream_events=True,
    )

    async for event in event_stream:
        yield event
