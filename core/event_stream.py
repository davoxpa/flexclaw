"""Aggregatore di eventi Agno in strutture FlexClaw agnostiche.

Trasforma gli eventi specifici dell'SDK Agno in dataclass generiche,
evitando che i plugin canale dipendano direttamente dai tipi Agno.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from agno.run.agent import (
    ToolCallCompletedEvent as MemberToolCallCompletedEvent,
    ToolCallErrorEvent as MemberToolCallErrorEvent,
    ToolCallStartedEvent as MemberToolCallStartedEvent,
)
from agno.run.team import (
    RunCompletedEvent,
    TaskCreatedEvent,
    TaskUpdatedEvent,
    ToolCallCompletedEvent,
    ToolCallErrorEvent,
    ToolCallStartedEvent,
)

from core.agent_api import stream_message

logger = logging.getLogger(__name__)


# ── Dataclass eventi FlexClaw ───────────────────────────────────────────────


@dataclass
class TaskInfo:
    """Informazioni su un task creato dal team leader."""
    id: str
    title: str
    assignee: str
    status: str


@dataclass
class ToolStepInfo:
    """Informazioni su una chiamata a un tool."""
    id: str
    name: str
    args: dict | None
    status: str  # "running", "done", "error"
    agent: str


@dataclass
class RunProgress:
    """Stato aggregato di una run in corso."""
    tasks: list[TaskInfo] = field(default_factory=list)
    tool_steps: list[ToolStepInfo] = field(default_factory=list)
    final_content: str | None = None
    completed: bool = False
    raw_completed_event: object | None = None


# ── Aggregatore ─────────────────────────────────────────────────────────────


async def stream_with_progress(
    message: str,
    user_id: str,
    session_id: str,
    file_paths: list[Path] | None = None,
) -> AsyncIterator[RunProgress]:
    """Consuma gli eventi Agno e produce snapshot progressivi di RunProgress.

    Ogni yield contiene lo stato aggiornato con tasks e tool_steps.
    L'ultimo yield ha completed=True e final_content popolato.
    """
    progress = RunProgress()

    async for event in stream_message(
        message=message,
        file_paths=file_paths,
        user_id=user_id,
        session_id=session_id,
    ):
        updated = False

        # ── Task ────────────────────────────────────────────────────────
        if isinstance(event, TaskCreatedEvent):
            logger.info("Task creato: %s → %s", event.title, event.assignee)
            progress.tasks.append(TaskInfo(
                id=event.task_id,
                title=event.title,
                assignee=event.assignee,
                status=event.status,
            ))
            updated = True

        elif isinstance(event, TaskUpdatedEvent):
            logger.info("Task aggiornato: %s → %s", event.task_id, event.status)
            for task in progress.tasks:
                if task.id == event.task_id:
                    task.status = event.status
                    break
            updated = True

        # ── Tool call del team leader ───────────────────────────────────
        elif isinstance(event, ToolCallStartedEvent) and event.tool and event.tool.tool_name:
            agent_label = getattr(event, "team_name", "") or "Team Leader"
            logger.info("Tool call (team): %s agent=%s", event.tool.tool_name, agent_label)
            progress.tool_steps.append(ToolStepInfo(
                id=event.tool.tool_call_id,
                name=event.tool.tool_name,
                args=event.tool.tool_args,
                status="running",
                agent=agent_label,
            ))
            updated = True

        elif isinstance(event, ToolCallCompletedEvent) and event.tool:
            _update_step_status(progress.tool_steps, event.tool.tool_call_id, "done")
            updated = True

        elif isinstance(event, ToolCallErrorEvent) and event.tool:
            logger.error("Tool error (team): %s – %s", event.tool.tool_name, getattr(event, "error", "unknown"))
            _update_step_status(progress.tool_steps, event.tool.tool_call_id, "error")
            updated = True

        # ── Tool call dei membri ────────────────────────────────────────
        elif isinstance(event, MemberToolCallStartedEvent) and event.tool and event.tool.tool_name:
            agent_label = getattr(event, "agent_name", "") or "Agente"
            logger.info("Tool call (member): %s agent=%s", event.tool.tool_name, agent_label)
            progress.tool_steps.append(ToolStepInfo(
                id=event.tool.tool_call_id,
                name=event.tool.tool_name,
                args=event.tool.tool_args,
                status="running",
                agent=agent_label,
            ))
            updated = True

        elif isinstance(event, MemberToolCallCompletedEvent) and event.tool:
            _update_step_status(progress.tool_steps, event.tool.tool_call_id, "done")
            updated = True

        elif isinstance(event, MemberToolCallErrorEvent) and event.tool:
            logger.error("Tool error (member): %s – %s", event.tool.tool_name, getattr(event, "error", "unknown"))
            _update_step_status(progress.tool_steps, event.tool.tool_call_id, "error")
            updated = True

        # ── Run completata ──────────────────────────────────────────────
        elif isinstance(event, RunCompletedEvent):
            progress.completed = True
            progress.raw_completed_event = event
            if event.content:
                progress.final_content = str(event.content)
            logger.info("Run completata. Lunghezza risposta: %d", len(progress.final_content or ""))
            updated = True

        if updated:
            yield progress

    # Finalizza stati rimasti aperti
    for task in progress.tasks:
        if task.status in ("pending", "in_progress"):
            task.status = "completed"
    for step in progress.tool_steps:
        if step.status == "running":
            step.status = "done"
    progress.completed = True
    yield progress


def _update_step_status(steps: list[ToolStepInfo], tool_call_id: str, status: str) -> None:
    """Aggiorna lo status di uno step dato il suo tool_call_id."""
    for step in steps:
        if step.id == tool_call_id:
            step.status = status
            break
