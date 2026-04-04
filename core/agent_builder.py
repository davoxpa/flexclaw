"""Costruisce agenti e team Agno da config/agents.config.yaml."""

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

import yaml
from agno.agent import Agent
from agno.knowledge.knowledge import Knowledge
from agno.team.mode import TeamMode
from agno.team.team import Team
from agno.tools import Toolkit

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "agents.config.yaml"

# Mappa stringhe YAML → enum TeamMode
_TEAM_MODES: dict[str, TeamMode] = {
    "coordinate": TeamMode.coordinate,
    "route": TeamMode.route,
    "broadcast": TeamMode.broadcast,
    "tasks": TeamMode.tasks,
}

# Chiavi riservate nei blocchi agent/team, gestite dal builder (non passate al costruttore)
_AGENT_RESERVED_KEYS = {"tools", "instructions"}
_TEAM_RESERVED_KEYS = {"members", "instructions", "mode", "knowledge", "tools"}

# Regex per ${variabile} nelle istruzioni
_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass
class BuildResult:
    """Risultato della costruzione da YAML."""

    team: Team
    agents: dict[str, Agent] = field(default_factory=dict)
    teams: dict[str, Team] = field(default_factory=dict)


# ── Funzioni interne ─────────────────────────────────────────────────────────


def _load_config(config_path: Path) -> dict[str, Any]:
    """Legge il file YAML di configurazione agenti/team."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _instantiate_builtin_tool(
    tool_def: dict[str, Any],
    variables: dict[str, str] | None = None,
) -> Toolkit:
    """Importa e istanzia un tool builtin Agno da class path e parametri."""
    class_path: str = tool_def["class"]
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    tool_class = getattr(module, class_name)
    params = dict(tool_def.get("params", {}))

    # Risolve ${variabile} nei parametri
    if variables:
        for key, val in params.items():
            if isinstance(val, str):
                params[key] = _VAR_PATTERN.sub(
                    lambda m: variables.get(m.group(1), m.group(0)), val
                )

    # Converte stringhe Path per parametri noti
    for key in ("base_dir", "target_directory"):
        if key in params and isinstance(params[key], str):
            if key == "base_dir":
                params[key] = Path(params[key])

    return tool_class(**params)


def _resolve_tools(
    tool_ids: list[str],
    builtin_tools: dict[str, dict[str, Any]],
    plugin_tools: list[Toolkit],
    special_tools: dict[str, Toolkit],
    variables: dict[str, str] | None = None,
) -> list[Toolkit]:
    """Risolve una lista di id tool in istanze Toolkit.

    Ordine di lookup:
    1. special_tools (es. knowledge_tool) — iniettati dal contesto runtime
    2. builtin_tools definiti nel YAML — importa e istanzia la classe Agno
    3. plugin_tools caricati dal loader — cerca per Toolkit.name
    """
    resolved: list[Toolkit] = []
    # Indice plugin per nome per lookup veloce
    plugin_by_name = {t.name: t for t in plugin_tools}

    for tool_id in tool_ids:
        # 1. Tool speciali (knowledge_tool, ecc.)
        if tool_id in special_tools:
            resolved.append(special_tools[tool_id])
            continue

        # 2. Tool builtin definiti nel YAML
        if tool_id in builtin_tools:
            try:
                resolved.append(_instantiate_builtin_tool(builtin_tools[tool_id], variables))
            except Exception:
                logger.exception("Errore nell'istanziare builtin_tool '%s'", tool_id)
            continue

        # 3. Plugin tool (by name)
        if tool_id in plugin_by_name:
            resolved.append(plugin_by_name[tool_id])
            continue

        logger.warning("Tool '%s' non trovato (builtin, plugin o special)", tool_id)

    return resolved


def _resolve_instructions(
    raw_instructions: list[str],
    shared: dict[str, str],
) -> list[str]:
    """Sostituisce ${variabile} nelle istruzioni con i valori da shared_instructions."""
    resolved: list[str] = []
    for instr in raw_instructions:
        # Se l'intera stringa è solo ${var}, sostituisci direttamente
        match = _VAR_PATTERN.fullmatch(instr.strip())
        if match:
            var_name = match.group(1)
            value = shared.get(var_name, "")
            if value:
                resolved.append(value)
            else:
                logger.warning("Variabile condivisa '${%s}' non trovata", var_name)
            continue

        # Altrimenti sostituisci inline tutte le ${var}
        def _replacer(m: re.Match) -> str:
            return shared.get(m.group(1), m.group(0))

        resolved.append(_VAR_PATTERN.sub(_replacer, instr))
    return resolved


def _build_agent(
    agent_id: str,
    agent_cfg: dict[str, Any],
    model: str,
    builtin_tools: dict[str, dict[str, Any]],
    plugin_tools: list[Toolkit],
    special_tools: dict[str, Toolkit],
    shared_instructions: dict[str, str],
    variables: dict[str, str] | None = None,
) -> Agent:
    """Costruisce un singolo Agent dalla configurazione YAML."""
    tools = _resolve_tools(
        agent_cfg.get("tools", []),
        builtin_tools,
        plugin_tools,
        special_tools,
        variables,
    )
    instructions = _resolve_instructions(
        agent_cfg.get("instructions", []),
        shared_instructions,
    )

    # Parametri passthrough: tutto ciò che non è riservato viene passato ad Agent()
    extra_params: dict[str, Any] = {
        k: v for k, v in agent_cfg.items() if k not in _AGENT_RESERVED_KEYS
    }

    # Usa il modello specificato dall'agente o quello del contesto
    agent_model = extra_params.pop("model", None) or model

    agent = Agent(
        model=agent_model,
        tools=tools,
        instructions=instructions,
        **extra_params,
    )
    logger.debug("Agente '%s' costruito con %d tool", agent_cfg.get("name", agent_id), len(tools))
    return agent


def _build_team(
    team_id: str,
    team_cfg: dict[str, Any],
    model: str,
    agents: dict[str, Agent],
    teams: dict[str, Team],
    knowledge: Knowledge | None,
    db: Any,
    builtin_tools: dict[str, dict[str, Any]] | None = None,
    plugin_tools: list[Toolkit] | None = None,
    special_tools: dict[str, Toolkit] | None = None,
    variables: dict[str, str] | None = None,
) -> Team:
    """Costruisce un singolo Team dalla configurazione YAML."""
    # Risolve i membri: cerca prima negli agenti, poi nei team (supporta nesting)
    member_ids = team_cfg.get("members", [])
    members: list[Union[Agent, Team]] = []
    for member_id in member_ids:
        if member_id in agents:
            members.append(agents[member_id])
        elif member_id in teams:
            members.append(teams[member_id])
        else:
            logger.error("Membro '%s' del team '%s' non trovato", member_id, team_id)

    # Risolve la modalità del team
    mode_str = team_cfg.get("mode", "coordinate")
    mode = _TEAM_MODES.get(mode_str)
    if mode is None:
        logger.warning("Modalità '%s' non valida, uso 'coordinate'", mode_str)
        mode = TeamMode.coordinate

    # Parametri passthrough al costruttore Team()
    extra_params: dict[str, Any] = {
        k: v for k, v in team_cfg.items() if k not in _TEAM_RESERVED_KEYS
    }

    # Modello: specificato nel team o ereditato dal contesto
    team_model = extra_params.pop("model", None) or model

    # Knowledge: se abilitata nel YAML, usa l'istanza condivisa
    use_knowledge = team_cfg.get("knowledge", False)

    # Istruzioni (nessuna variabile ${} nei team, ma supportato per coerenza)
    instructions = team_cfg.get("instructions", [])

    # Risolve i tool del team (seguendo lo stesso meccanismo degli agenti)
    team_tool_ids = team_cfg.get("tools", [])
    resolved_team_tools = _resolve_tools(
        team_tool_ids,
        builtin_tools or {},
        plugin_tools or [],
        special_tools or {},
        variables,
    )

    team = Team(
        mode=mode,
        model=team_model,
        members=members,
        instructions=instructions,
        tools=resolved_team_tools if resolved_team_tools else None,
        knowledge=knowledge if use_knowledge else None,
        db=db,
        **extra_params,
    )
    logger.debug(
        "Team '%s' costruito — modo: %s, membri: %s, tool: %d",
        team_cfg.get("name", team_id),
        mode_str,
        [m.name for m in members],
        len(resolved_team_tools),
    )
    return team


# ── Ordinamento topologico per team annidati ─────────────────────────────────


def _topological_sort(teams_cfg: dict[str, dict[str, Any]], agents_keys: set[str]) -> list[str]:
    """Ordina i team in modo che i team-figli vengano costruiti prima dei team-padre."""
    visited: set[str] = set()
    order: list[str] = []

    def _visit(team_id: str) -> None:
        if team_id in visited:
            return
        visited.add(team_id)
        # Processa prima le dipendenze (team annidati tra i members)
        for member_id in teams_cfg.get(team_id, {}).get("members", []):
            if member_id in teams_cfg and member_id not in agents_keys:
                _visit(member_id)
        order.append(team_id)

    for tid in teams_cfg:
        _visit(tid)
    return order


# ── Funzione pubblica ────────────────────────────────────────────────────────


def build_from_yaml(
    model: str,
    knowledge: Knowledge | None = None,
    db: Any = None,
    special_tools: dict[str, Toolkit] | None = None,
    plugin_tools: list[Toolkit] | None = None,
    plugin_instructions: str = "",
    config_path: Path | None = None,
) -> BuildResult:
    """Costruisce agenti e team da agents.config.yaml.

    Args:
        model: stringa del modello corrente (es. "openrouter:openai/gpt-4o")
        knowledge: istanza Knowledge condivisa (ChromaDB)
        db: database per persistenza sessioni (es. SqliteDb)
        special_tools: tool speciali iniettati dal contesto (es. {"knowledge_tool": ...})
        plugin_tools: tool plugin caricati dal loader
        plugin_instructions: istruzioni raccolte dai config.yaml dei plugin
        config_path: percorso al file YAML (default: config/agents.config.yaml)
    """
    cfg = _load_config(config_path or _CONFIG_PATH)

    builtin_tools_cfg = cfg.get("builtin_tools", {})
    variables = {k: str(v) for k, v in cfg.get("vars", {}).items()}
    shared = dict(cfg.get("shared_instructions", {}))

    # Rende le variabili disponibili anche come ${var} nelle istruzioni
    shared.update(variables)

    # Inietta plugin_instructions come variabile condivisa speciale
    if plugin_instructions:
        shared["plugin_instructions"] = plugin_instructions

    agents_cfg = cfg.get("agents", {})
    teams_cfg = cfg.get("teams", {})
    main_team_id = cfg.get("main_team", "")

    # Costruisci tutti gli agenti
    built_agents: dict[str, Agent] = {}
    for agent_id, agent_def in agents_cfg.items():
        built_agents[agent_id] = _build_agent(
            agent_id=agent_id,
            agent_cfg=agent_def,
            model=model,
            builtin_tools=builtin_tools_cfg,
            plugin_tools=plugin_tools or [],
            special_tools=special_tools or {},
            shared_instructions=shared,
            variables=variables,
        )

    # Costruisci i team in ordine topologico (team-figli prima dei team-padre)
    agents_keys = set(agents_cfg.keys())
    build_order = _topological_sort(teams_cfg, agents_keys)

    built_teams: dict[str, Team] = {}
    for team_id in build_order:
        team_def = teams_cfg[team_id]
        built_teams[team_id] = _build_team(
            team_id=team_id,
            team_cfg=team_def,
            model=model,
            agents=built_agents,
            teams=built_teams,
            knowledge=knowledge,
            db=db,
            builtin_tools=builtin_tools_cfg,
            plugin_tools=plugin_tools or [],
            special_tools=special_tools or {},
            variables=variables,
        )

    # Identifica il team principale
    if main_team_id not in built_teams:
        available = list(built_teams.keys())
        raise ValueError(
            f"main_team '{main_team_id}' non trovato. Team disponibili: {available}"
        )

    return BuildResult(
        team=built_teams[main_team_id],
        agents=built_agents,
        teams=built_teams,
    )
