"""Tool Agno per lo scheduling di prompt ripetuti o programmati."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agno.tools import Toolkit

from plugin.tool.scheduler_tool.engine import SchedulerEngine
from plugin.tool.scheduler_tool.storage import (
    SchedulerStorage,
    Task,
    TaskOutput,
    TaskSchedule,
)

logger = logging.getLogger(__name__)

# Istanza singleton dell'engine — condivisa tra tutte le istanze del tool
_engine: Optional[SchedulerEngine] = None


def _get_engine() -> SchedulerEngine:
    """Restituisce l'istanza singleton dell'engine, avviandolo se necessario."""
    global _engine
    if _engine is None:
        _engine = SchedulerEngine()
        _engine.start()
    return _engine


class SchedulerTool(Toolkit):
    """Gestisce task schedulati: crea, elenca, sospende, riprende ed elimina task.

    Ogni task esegue automaticamente un prompt verso l'agent AI in base alla
    schedulazione configurata, e invia il risultato al canale di origine
    (Telegram, Discord, ecc.) tramite il notification_registry.

    IMPORTANTE: lo scheduler non conosce i plugin canale. Se un plugin canale
    non è presente o non è avviato, le notifiche vengono silenziosamente saltate.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        super().__init__(name="scheduler_tool")
        # Avvia l'engine al caricamento del tool
        _get_engine()
        self.register(self.schedule_task)
        self.register(self.list_tasks)
        self.register(self.get_task)
        self.register(self.pause_task)
        self.register(self.resume_task)
        self.register(self.delete_task)
        self.register(self.update_task_prompt)

    def schedule_task(
        self,
        name: str,
        prompt: str,
        schedule_type: str,
        channel_type: str,
        chat_id: str,
        every: Optional[int] = None,
        unit: Optional[str] = None,
        cron_expression: Optional[str] = None,
        run_at: Optional[str] = None,
        daily_time: Optional[str] = None,
        weekly_day: Optional[str] = None,
        weekly_time: Optional[str] = None,
    ) -> str:
        """Crea e attiva un nuovo task schedulato.

        Args:
            name: Nome descrittivo del task (es. "Report meteo mattutino").
            prompt: Testo del prompt da inviare all'agent ad ogni esecuzione.
            schedule_type: Tipo di schedulazione. Valori validi:
                - "interval" → esecuzione ripetuta ogni N unità di tempo.
                - "cron" → espressione cron standard a 5 campi.
                - "once" → esecuzione unica a una data/ora specifica.
                - "daily" → ogni giorno a un orario fisso.
                - "weekly" → ogni settimana in un giorno e orario fisso.
            channel_type: Canale di output (es. "telegram", "discord").
            chat_id: ID della chat/canale dove inviare i risultati.
            every: [per interval] numero di unità (es. 5 per ogni 5 minuti).
            unit: [per interval] "minutes" | "hours" | "days" | "weeks".
            cron_expression: [per cron] 5 campi cron (es. "0 8 * * 1").
            run_at: [per once] datetime ISO (es. "2026-04-10T10:00:00").
            daily_time: [per daily] orario "HH:MM" (es. "08:30").
            weekly_day: [per weekly] giorno in inglese (es. "monday").
            weekly_time: [per weekly] orario "HH:MM" (es. "09:00").

        Returns:
            Conferma con ID del task e prossima esecuzione pianificata.
        """
        try:
            schedule = TaskSchedule(
                type=schedule_type,
                every=every,
                unit=unit,
                cron_expression=cron_expression,
                run_at=run_at,
                time=daily_time or weekly_time,
                day=weekly_day,
            )
            output = TaskOutput(channel_type=channel_type, chat_id=chat_id)
            task = Task.create(name=name, prompt=prompt, schedule=schedule, output=output)

            _get_engine().add_task(task)

            next_run = _get_engine().get_next_run(task.id)
            next_run_str = next_run or "non determinabile"

            return (
                f"✅ Task schedulato con successo!\n"
                f"• ID: {task.id}\n"
                f"• Nome: {task.name}\n"
                f"• Tipo: {schedule_type}\n"
                f"• Prossima esecuzione: {next_run_str}\n"
                f"• Canale output: {channel_type} (chat_id={chat_id})"
            )
        except ValueError as exc:
            return f"❌ Errore nella configurazione del task: {exc}"
        except Exception as exc:
            logger.exception("Errore nella creazione del task schedulato")
            return f"❌ Errore imprevisto: {exc}"

    def list_tasks(self) -> str:
        """Elenca tutti i task schedulati con stato, tipo e prossima esecuzione.

        Returns:
            Lista formattata dei task presenti nello storage scheduler.
        """
        engine = _get_engine()
        tasks = SchedulerStorage().get_all()

        if not tasks:
            return "Nessun task schedulato presente."

        result = []
        for task in tasks:
            next_run = engine.get_next_run(task.id) or task.next_run or "—"
            schedule_desc = _describe_schedule(task.schedule)
            result.append({
                "id": task.id[:8] + "…",
                "id_completo": task.id,
                "nome": task.name,
                "status": task.status,
                "schedulazione": schedule_desc,
                "prossima_esecuzione": next_run,
                "esecuzioni": task.run_count,
                "errori": task.error_count,
                "canale": f"{task.output.channel_type}:{task.output.chat_id}",
            })

        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_task(self, task_id: str) -> str:
        """Restituisce i dettagli completi di un task specifico.

        Args:
            task_id: ID completo del task (ottenuto da list_tasks).

        Returns:
            Dettagli del task in formato JSON, oppure messaggio di errore.
        """
        task = SchedulerStorage().get(task_id)
        if not task:
            return f"❌ Task non trovato: '{task_id}'"

        engine = _get_engine()
        data = task.to_dict()
        data["next_run_live"] = engine.get_next_run(task_id)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def pause_task(self, task_id: str) -> str:
        """Sospende un task attivo senza eliminarlo.

        Il task rimane nello storage con status 'paused' e può essere ripreso
        in qualsiasi momento con resume_task().

        Args:
            task_id: ID completo del task da sospendere.

        Returns:
            Conferma dell'operazione o messaggio di errore.
        """
        task = SchedulerStorage().get(task_id)
        if not task:
            return f"❌ Task non trovato: '{task_id}'"

        success = _get_engine().pause_task(task_id)
        if success:
            return f"⏸ Task '{task.name}' sospeso con successo."
        return f"❌ Impossibile sospendere il task '{task.name}' (status attuale: {task.status})."

    def resume_task(self, task_id: str) -> str:
        """Riprende un task precedentemente sospeso.

        Args:
            task_id: ID completo del task da riprendere.

        Returns:
            Conferma con prossima esecuzione pianificata, o messaggio di errore.
        """
        task = SchedulerStorage().get(task_id)
        if not task:
            return f"❌ Task non trovato: '{task_id}'"

        success = _get_engine().resume_task(task_id)
        if success:
            next_run = _get_engine().get_next_run(task_id) or "non determinabile"
            return (
                f"▶️ Task '{task.name}' ripreso.\n"
                f"• Prossima esecuzione: {next_run}"
            )
        return (
            f"❌ Impossibile riprendere il task '{task.name}' "
            f"(status attuale: {task.status}). Solo i task 'paused' possono essere ripresi."
        )

    def delete_task(self, task_id: str) -> str:
        """Elimina definitivamente un task.

        L'operazione è irreversibile. Il task viene rimosso dallo storage
        e da APScheduler.

        Args:
            task_id: ID completo del task da eliminare.

        Returns:
            Conferma dell'eliminazione o messaggio di errore.
        """
        task = SchedulerStorage().get(task_id)
        task_name = task.name if task else task_id

        success = _get_engine().delete_task(task_id)
        if success:
            return f"🗑 Task '{task_name}' eliminato definitivamente."
        return f"❌ Task non trovato: '{task_id}'"

    def update_task_prompt(self, task_id: str, new_prompt: str) -> str:
        """Aggiorna il prompt di un task esistente senza modificarne la schedulazione.

        Args:
            task_id: ID completo del task da aggiornare.
            new_prompt: Nuovo testo del prompt.

        Returns:
            Conferma dell'aggiornamento o messaggio di errore.
        """
        task = SchedulerStorage().get(task_id)
        if not task:
            return f"❌ Task non trovato: '{task_id}'"

        success = _get_engine().update_task_prompt(task_id, new_prompt)
        if success:
            return f"✏️ Prompt del task '{task.name}' aggiornato con successo."
        return f"❌ Impossibile aggiornare il task '{task.name}'."


# ── Helper ────────────────────────────────────────────────────────────────────


def _describe_schedule(schedule: TaskSchedule) -> str:
    """Genera una descrizione leggibile della schedulazione di un task."""
    if schedule.type == "interval":
        return f"ogni {schedule.every} {schedule.unit}"
    if schedule.type == "cron":
        return f"cron: {schedule.cron_expression}"
    if schedule.type == "once":
        return f"una volta il {schedule.run_at}"
    if schedule.type == "daily":
        return f"ogni giorno alle {schedule.time}"
    if schedule.type == "weekly":
        return f"ogni {schedule.day} alle {schedule.time}"
    return schedule.type
