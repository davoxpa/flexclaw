import logging
import os
from pathlib import Path
from typing import Any

import yaml
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.team.team import Team
from agno.vectordb.chroma import ChromaDb

from agno.models.utils import get_model as resolve_model

from core.agent_builder import BuildResult, build_from_yaml
from core.loader import get_sandbox_dir, load_tool_instructions, load_tools

logger = logging.getLogger(__name__)

# ── Configurazione principale ───────────────────────────────────────────────

_MAIN_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "main.config.yaml"
_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.yaml"


def _load_main_config() -> dict[str, Any]:
    """Legge config/main.config.yaml."""
    return yaml.safe_load(_MAIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _load_state() -> dict[str, Any]:
    """Legge lo stato persistente da data/state.yaml."""
    if _STATE_PATH.exists():
        return yaml.safe_load(_STATE_PATH.read_text(encoding="utf-8")) or {}
    return {}


def _save_state(state: dict[str, Any]) -> None:
    """Salva lo stato persistente in data/state.yaml."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        yaml.dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# Mappatura provider → variabile d'ambiente necessaria
PROVIDER_ENV_MAP: dict[str, str | None] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "azure-ai-foundry": "AZURE_API_KEY",
    "litellm": "LITELLM_API_KEY",
    "ollama": None,  # nessun token, modello locale
}


def validate_model_token(model_string: str) -> tuple[bool, str]:
    """Verifica che la variabile d'ambiente necessaria per il provider sia presente.

    Restituisce (True, "") se tutto ok, oppure (False, messaggio_errore).
    """
    if ":" not in model_string:
        return False, (
            f"Formato modello non valido: '{model_string}'. "
            "Usa la sintassi 'provider:model_id' (es. 'openrouter:openai/gpt-4o')."
        )

    provider = model_string.split(":", 1)[0].lower()
    env_var = PROVIDER_ENV_MAP.get(provider)

    # Provider locale (ollama) → nessun token richiesto
    if env_var is None and provider in PROVIDER_ENV_MAP:
        return True, ""

    # Provider sconosciuto → avviso ma non blocca
    if provider not in PROVIDER_ENV_MAP:
        logger.warning("Provider '%s' non mappato, impossibile validare il token", provider)
        return True, ""

    if not os.getenv(env_var):
        return False, f"Token mancante: la variabile d'ambiente {env_var} non è impostata."

    return True, ""


# ── Caricamento modello di default ──────────────────────────────────────────

_config = _load_main_config()
_state = _load_state()
# Priorità: stato salvato → primo modello della lista config
_models_list = _config.get("models", [])
_default_model: str = _state.get("last_model") or (
    _models_list[0] if _models_list else "openrouter:openai/gpt-4o"
)

# Validazione token all'avvio
_valid, _error_msg = validate_model_token(_default_model)
if not _valid:
    raise RuntimeError(
        f"Impossibile avviare FlexClaw — {_error_msg}\n"
        f"Modello configurato: {_default_model}"
    )

# Modello corrente (modificabile a runtime)
_current_model: str = _default_model

logger.debug("Modello di default: %s", _current_model)

db_sqlite = SqliteDb(db_file="data/db/flexclaw_sqlite.db")

# Istruzioni dai tool plugin abilitati
_plugin_instructions = load_tool_instructions()

# Tool plugin caricati dinamicamente
_plugin_tools = load_tools()
logger.debug("Caricati %d tool plugin: %s", len(_plugin_tools), [t.name for t in _plugin_tools])

# ── Knowledge ───────────────────────────────────────────────────────────────

knowledge = Knowledge(
    vector_db=ChromaDb(
        collection="flexclaw_knowledge",
        path="data/chromadb",
        persistent_client=True,
        embedder=OpenAILikeEmbedder(
            id="openai/text-embedding-3-small",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
        ),
    ),
)

# Il KnowledgeTool viene caricato dinamicamente per evitare coupling diretto core → plugin
import importlib as _importlib  # noqa: E402

try:
    _kt_module = _importlib.import_module("plugin.tool.knowledge_tool")
    _KnowledgeToolClass = getattr(_kt_module, "KnowledgeTool")
    knowledge_tool = _KnowledgeToolClass(knowledge=knowledge, base_dir=Path(get_sandbox_dir()))
except (ModuleNotFoundError, AttributeError):
    logger.warning("KnowledgeTool non trovato, funzionalità knowledge-save disabilitata")
    knowledge_tool = None

# ── Build agenti e team da YAML ─────────────────────────────────────────────

_build_result: BuildResult = build_from_yaml(
    model=_current_model,
    knowledge=knowledge,
    db=db_sqlite,
    special_tools={"knowledge_tool": knowledge_tool} if knowledge_tool else {},
    plugin_tools=_plugin_tools,
    plugin_instructions=_plugin_instructions,
)

flexclaw_team: Team = _build_result.team
logger.debug(
    "Team principale '%s' costruito con %d membri da agents.config.yaml",
    flexclaw_team.name,
    len(flexclaw_team.members),
)


# ── Funzioni per gestione modello a runtime ─────────────────────────────────


def _update_model_recursive(member: Agent | Team, model_obj: object) -> None:
    """Aggiorna il modello ricorsivamente su agenti e team annidati."""
    member.model = model_obj
    if isinstance(member, Team) and member.members:
        for sub_member in member.members:
            _update_model_recursive(sub_member, model_obj)


def get_current_model() -> str:
    """Restituisce la stringa del modello attualmente in uso."""
    return _current_model


def get_available_models() -> list[str]:
    """Restituisce la lista dei modelli disponibili da main.config.yaml."""
    cfg = _load_main_config()
    return cfg.get("models", [])


def _save_last_model(model_string: str) -> None:
    """Persiste l'ultimo modello selezionato in data/state.yaml."""
    state = _load_state()
    state["last_model"] = model_string
    _save_state(state)


def set_model(model_string: str) -> tuple[bool, str]:
    """Cambia il modello su team e agenti a runtime (ricorsivo per team annidati).

    Restituisce (True, messaggio_ok) oppure (False, messaggio_errore).
    """
    global _current_model

    valid, error_msg = validate_model_token(model_string)
    if not valid:
        return False, error_msg

    model_obj = resolve_model(model_string)
    if model_obj is None:
        return False, f"Impossibile risolvere il modello: {model_string}"

    # Aggiorna ricorsivamente team leader e tutti i membri (anche team annidati)
    _update_model_recursive(flexclaw_team, model_obj)

    _current_model = model_string
    _save_last_model(model_string)
    logger.info("Modello cambiato a runtime e salvato: %s", model_string)
    return True, f"Modello cambiato a: {model_string}"


# ── API Knowledge Base ──────────────────────────────────────────────────────


def knowledge_count() -> int:
    """Restituisce il numero di chunk nella knowledge base."""
    try:
        vdb = knowledge.vector_db
        collection = vdb.client.get_collection(vdb.collection_name)
        return collection.count()
    except Exception:
        logger.exception("Errore nel conteggio knowledge")
        return 0


def knowledge_list(limit: int = 50) -> tuple[int, dict[str, str]]:
    """Restituisce (num_chunk, {nome_doc: tipo}) dalla knowledge base."""
    try:
        vdb = knowledge.vector_db
        collection = vdb.client.get_collection(vdb.collection_name)
        count = collection.count()
        if count == 0:
            return 0, {}

        results = collection.get(limit=limit, include=["metadatas"])
        seen: dict[str, str] = {}
        for meta in results["metadatas"]:
            name = meta.get("name", meta.get("original_name", "Senza titolo"))
            ftype = meta.get("type", "?")
            if name not in seen:
                seen[name] = ftype
        return count, seen
    except Exception:
        logger.exception("Errore nel listing knowledge")
        return 0, {}


def knowledge_search(query: str, max_results: int = 5) -> list:
    """Cerca nella knowledge base e restituisce i risultati."""
    return knowledge.search(query=query, max_results=max_results)
