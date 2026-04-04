"""Storage thread-safe per i task dello scheduler (YAML persistente)."""

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

_STORAGE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "scheduler" / "tasks.yaml"
)

_ARCHIVE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "scheduler" / "executed_tasks.yaml"
)


def _now_iso() -> str:
    """Restituisce il timestamp corrente in formato ISO 8601 (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Dataclass del modello dati ────────────────────────────────────────────────


@dataclass
class TaskSchedule:
    """Configurazione della schedulazione di un task."""

    type: str
    """Tipo: interval | cron | once | daily | weekly"""

    every: Optional[int] = None
    """Per type=interval: numero di unità di tempo tra le esecuzioni."""

    unit: Optional[str] = None
    """Per type=interval: minutes | hours | days | weeks."""

    cron_expression: Optional[str] = None
    """Per type=cron: espressione standard a 5 campi (es. '0 8 * * 1')."""

    run_at: Optional[str] = None
    """Per type=once: datetime ISO (es. '2026-04-10T10:00:00')."""

    time: Optional[str] = None
    """Per type=daily e type=weekly: orario 'HH:MM'."""

    day: Optional[str] = None
    """Per type=weekly: nome giorno in inglese (es. 'monday')."""


@dataclass
class TaskOutput:
    """Destinazione dell'output del task."""

    channel_type: str
    """Canale: telegram | discord."""

    chat_id: str
    """ID della chat Telegram o del canale Discord."""


@dataclass
class Task:
    """Rappresentazione completa di un task schedulato."""

    id: str
    name: str
    prompt: str
    status: str
    """Stato: active | paused | completed | error."""

    schedule: TaskSchedule
    output: TaskOutput
    session_id: str
    created_at: str
    updated_at: str
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None

    @classmethod
    def create(
        cls,
        name: str,
        prompt: str,
        schedule: TaskSchedule,
        output: TaskOutput,
    ) -> "Task":
        """Factory: crea un nuovo Task con ID e timestamps generati automaticamente."""
        task_id = str(uuid.uuid4())
        now = _now_iso()
        return cls(
            id=task_id,
            name=name,
            prompt=prompt,
            status="active",
            schedule=schedule,
            output=output,
            session_id=f"scheduler_{task_id}",
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        """Converte il task in dizionario per la serializzazione YAML."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Crea un Task da un dizionario deserializzato da YAML."""
        return cls(
            id=data["id"],
            name=data["name"],
            prompt=data["prompt"],
            status=data["status"],
            schedule=TaskSchedule(**data.get("schedule", {})),
            output=TaskOutput(**data.get("output", {})),
            session_id=data.get("session_id", f"scheduler_{data['id']}"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            next_run=data.get("next_run"),
            last_run=data.get("last_run"),
            run_count=data.get("run_count", 0),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error"),
        )


# ── Storage YAML ──────────────────────────────────────────────────────────────


class SchedulerStorage:
    """Gestisce la persistenza dei task su file YAML con lock thread-safe."""

    def __init__(self, path: Path = _STORAGE_PATH, archive_path: Path = _ARCHIVE_PATH):
        self._path = path
        self._archive_path = archive_path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Operazioni private su file ────────────────────────────────────────────

    def _read(self) -> list[dict]:
        """Legge il file YAML e restituisce la lista grezza dei task."""
        if not self._path.exists():
            return []
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        return raw.get("tasks", [])

    def _write(self, tasks: list[dict]) -> None:
        """Scrive la lista dei task sul file YAML."""
        self._path.write_text(
            yaml.dump(
                {"tasks": tasks},
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _read_archive(self) -> list[dict]:
        """Legge il file archivio YAML e restituisce la lista grezza dei task eseguiti."""
        if not self._archive_path.exists():
            return []
        raw = yaml.safe_load(self._archive_path.read_text(encoding="utf-8")) or {}
        return raw.get("tasks", [])

    def _write_archive(self, tasks: list[dict]) -> None:
        """Scrive la lista dei task archiviati sul file YAML."""
        self._archive_path.write_text(
            yaml.dump(
                {"tasks": tasks},
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    # ── API pubblica CRUD ─────────────────────────────────────────────────────

    def get_all(self) -> list[Task]:
        """Restituisce tutti i task presenti nello storage."""
        with self._lock:
            return [Task.from_dict(d) for d in self._read()]

    def get(self, task_id: str) -> Optional[Task]:
        """Restituisce un singolo task per ID, o None se non trovato."""
        with self._lock:
            for item in self._read():
                if item.get("id") == task_id:
                    return Task.from_dict(item)
        return None

    def add(self, task: Task) -> None:
        """Aggiunge un nuovo task allo storage."""
        with self._lock:
            tasks = self._read()
            tasks.append(task.to_dict())
            self._write(tasks)

    def update(self, task_id: str, **fields) -> Optional[Task]:
        """Aggiorna i campi specificati di un task.

        Supporta aggiornamenti di campi annidati (schedule, output) tramite dict.
        Restituisce il task aggiornato, oppure None se non trovato.
        """
        with self._lock:
            tasks = self._read()
            for i, item in enumerate(tasks):
                if item.get("id") != task_id:
                    continue
                fields["updated_at"] = _now_iso()
                for key, value in fields.items():
                    if isinstance(value, dict) and isinstance(item.get(key), dict):
                        item[key].update(value)
                    else:
                        item[key] = value
                tasks[i] = item
                self._write(tasks)
                return Task.from_dict(item)
        return None

    def delete(self, task_id: str) -> bool:
        """Elimina un task per ID.

        Restituisce True se eliminato, False se non trovato.
        """
        with self._lock:
            tasks = self._read()
            filtered = [t for t in tasks if t.get("id") != task_id]
            if len(filtered) == len(tasks):
                return False
            self._write(filtered)
            return True

    def archive(self, task_id: str) -> bool:
        """Sposta un task terminato (completed/error/expired) nel file executed_tasks.yaml.

        Rimuove il task da tasks.yaml e lo appende a executed_tasks.yaml.
        Restituisce True se spostato, False se il task non è stato trovato.
        """
        with self._lock:
            tasks = self._read()
            target: dict | None = next((t for t in tasks if t.get("id") == task_id), None)
            if target is None:
                return False
            # Rimuovi dal file principale
            self._write([t for t in tasks if t.get("id") != task_id])
            # Appendi all'archivio
            archived = self._read_archive()
            archived.append(target)
            self._write_archive(archived)
        return True
