"""Engine di scheduling: gestisce APScheduler e l'esecuzione dei task."""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from plugin.tool.scheduler_tool.storage import SchedulerStorage, Task, TaskSchedule

logger = logging.getLogger(__name__)

# ── Mappatura unit → parametro APScheduler ────────────────────────────────────
_UNIT_MAP = {
    "minutes": "minutes",
    "hours": "hours",
    "days": "days",
    "weeks": "weeks",
}

# ── Mappatura nome giorno → numero (APScheduler/cron day_of_week) ─────────────
_DAY_MAP = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}


def _build_trigger(schedule: TaskSchedule):
    """Costruisce il trigger APScheduler dal config di schedulazione del task."""
    schedule_type = schedule.type

    if schedule_type == "interval":
        unit = _UNIT_MAP.get(schedule.unit or "minutes", "minutes")
        return IntervalTrigger(**{unit: schedule.every or 5})

    if schedule_type == "cron":
        parts = (schedule.cron_expression or "* * * * *").split()
        if len(parts) != 5:
            raise ValueError(
                f"Espressione cron non valida: '{schedule.cron_expression}'. "
                "Usa il formato a 5 campi: minuto ora giorno-mese mese giorno-settimana"
            )
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )

    if schedule_type == "once":
        run_at = schedule.run_at or ""
        try:
            # Supporta formati ISO con o senza timezone.
            # Se il datetime è naive (senza tz), APScheduler lo interpreta
            # come ora locale — non forzare UTC altrimenti si sfasa di +2 ore.
            run_dt = datetime.fromisoformat(run_at)
        except ValueError as exc:
            raise ValueError(
                f"Data/ora non valida per task 'once': '{run_at}'. "
                "Usa il formato ISO 8601 (es. '2026-04-10T10:00:00')."
            ) from exc
        return DateTrigger(run_date=run_dt)

    if schedule_type == "daily":
        time_str = schedule.time or "08:00"
        hour, minute = time_str.split(":")
        return CronTrigger(hour=int(hour), minute=int(minute))

    if schedule_type == "weekly":
        time_str = schedule.time or "08:00"
        hour, minute = time_str.split(":")
        day_abbr = _DAY_MAP.get((schedule.day or "monday").lower(), "mon")
        return CronTrigger(
            day_of_week=day_abbr,
            hour=int(hour),
            minute=int(minute),
        )

    raise ValueError(
        f"Tipo di schedulazione non supportato: '{schedule_type}'. "
        "Valori validi: interval, cron, once, daily, weekly."
    )


class SchedulerEngine:
    """Engine che gestisce il ciclo di vita dei task schedulati.

    Usa APScheduler con MemoryJobStore in background per la gestione dei trigger.
    La persistenza è affidata interamente a SchedulerStorage (YAML): all'avvio,
    tutti i task con status='active' vengono ricaricati e riprogrammati.

    IMPORTANTE: questa classe non sa nulla dei plugin canale. L'invio
    delle notifiche avviene tramite core.notification_registry, che i plugin
    canale popolano al loro avvio. Se un canale non è registrato, la notifica
    viene saltata silenziosamente.
    """

    def __init__(self, storage: Optional[SchedulerStorage] = None):
        self._storage = storage or SchedulerStorage()
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": ThreadPoolExecutor(max_workers=4)},
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)

    def start(self) -> None:
        """Avvia lo scheduler e riprogramma tutti i task attivi dallo storage."""
        self._scheduler.start()
        now = datetime.now()
        active_tasks = [t for t in self._storage.get_all() if t.status == "active"]
        reloaded = 0
        for task in active_tasks:
            try:
                # Task 'once' con orario già passato: non rischedulare, marca come expired
                if task.schedule.type == "once" and task.schedule.run_at:
                    run_dt = datetime.fromisoformat(task.schedule.run_at)
                    if run_dt < now:
                        self._storage.update(task.id, status="expired")
                        self._storage.archive(task.id)
                        logger.info(
                            "Task 'once' scaduto archiviato al riavvio: '%s' (%s) — era previsto per %s",
                            task.name, task.id, task.schedule.run_at,
                        )
                        continue

                self._add_apscheduler_job(task)
                reloaded += 1
                logger.info("Task schedulato ricaricato all'avvio: '%s' (%s)", task.name, task.id)
            except Exception:
                logger.exception("Impossibile riavviare il task '%s' (%s)", task.name, task.id)
        logger.info("SchedulerEngine avviato — %d task ricaricati (su %d attivi)", reloaded, len(active_tasks))

    def stop(self) -> None:
        """Ferma lo scheduler in modo pulito."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("SchedulerEngine fermato")

    # ── Gestione task ─────────────────────────────────────────────────────────

    def add_task(self, task: Task) -> None:
        """Aggiunge un task allo storage e lo programma in APScheduler."""
        with self._lock:
            self._storage.add(task)
            self._add_apscheduler_job(task)
        logger.info("Nuovo task aggiunto: '%s' (%s)", task.name, task.id)

    def pause_task(self, task_id: str) -> bool:
        """Sospende un task: lo rimuove da APScheduler e aggiorna lo status."""
        with self._lock:
            task = self._storage.get(task_id)
            if not task or task.status != "active":
                return False
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)
            self._storage.update(task_id, status="paused")
        logger.info("Task sospeso: '%s' (%s)", task.name if task else "?", task_id)
        return True

    def resume_task(self, task_id: str) -> bool:
        """Riprende un task sospeso: lo ri-aggiunge ad APScheduler."""
        with self._lock:
            task = self._storage.get(task_id)
            if not task or task.status != "paused":
                return False
            self._add_apscheduler_job(task)
            self._storage.update(task_id, status="active")
        logger.info("Task ripreso: '%s' (%s)", task.name if task else "?", task_id)
        return True

    def delete_task(self, task_id: str) -> bool:
        """Elimina un task da storage e APScheduler."""
        with self._lock:
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)
            deleted = self._storage.delete(task_id)
        logger.info("Task eliminato: %s (trovato=%s)", task_id, deleted)
        return deleted

    def update_task_prompt(self, task_id: str, new_prompt: str) -> bool:
        """Aggiorna il prompt di un task senza modificare la schedulazione."""
        updated = self._storage.update(task_id, prompt=new_prompt)
        return updated is not None

    def get_next_run(self, task_id: str) -> Optional[str]:
        """Restituisce il prossimo orario di esecuzione di un job APScheduler."""
        job = self._scheduler.get_job(task_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%dT%H:%M:%S")
        return None

    # ── Esecuzione task ───────────────────────────────────────────────────────

    def _add_apscheduler_job(self, task: Task) -> None:
        """Aggiunge o sostituisce il job APScheduler per un task."""
        trigger = _build_trigger(task.schedule)
        self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task.id,
            name=task.name,
            args=[task.id],
            replace_existing=True,
        )
        next_run = self.get_next_run(task.id)
        if next_run:
            self._storage.update(task.id, next_run=next_run)

    def _execute_task(self, task_id: str) -> None:
        """Esegue un task: invia il prompt all'agent e notifica il canale di output.

        Questo metodo gira in un thread APScheduler separato.
        Crea un nuovo event loop asyncio per chiamare send_message (async).

        Comportamento in caso di errore:
        - Task "once": status → "error" (non può essere rieseguito)
        - Task ripetuti (daily/interval/cron/weekly): status rimane "active",
          incrementa error_count. Il task continuerà ad eseguire regolarmente.
        """
        # Import lazy per evitare circolarità al momento del caricamento del modulo
        from core import notification_registry
        from core.agent_api import send_message

        task = self._storage.get(task_id)
        if not task:
            logger.warning("Task non trovato per l'esecuzione: %s", task_id)
            return

        if task.status != "active":
            logger.debug("Task '%s' non attivo (%s), skip esecuzione", task.name, task.status)
            return

        is_repeating = task.schedule.type != "once"
        run_count = task.run_count + 1
        # Session ID unica per esecuzione: evita accumulo infinito di contesto LLM
        exec_session_id = f"sched_{task_id[:8]}_{run_count}"

        logger.info(
            "Esecuzione task schedulato: '%s' (%s) — run #%d",
            task.name, task_id, run_count,
        )

        # ── Fase 1: chiamata LLM ──────────────────────────────────────────────
        response_text: str | None = None
        llm_error: Exception | None = None
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    send_message(
                        message=task.prompt,
                        session_id=exec_session_id,
                        user_id=f"scheduler_{task_id}",
                    )
                )
            finally:
                loop.close()
            response_text = result.content or "(nessuna risposta)"
        except Exception as exc:
            llm_error = exc
            logger.exception(
                "Errore LLM nel task '%s' (%s) run #%d: %s",
                task.name, task_id, run_count, exc,
            )

        # ── Fase 2: notifica canale (indipendente da LLM) ─────────────────────
        if response_text is not None:
            try:
                notification_registry.send(
                    channel_type=task.output.channel_type,
                    chat_id=task.output.chat_id,
                    text=response_text,
                    task_name=task.name,
                )
            except Exception as exc:
                # Errore di notifica: logga ma non blocca l'aggiornamento statistiche
                logger.error(
                    "Errore notifica canale '%s' per task '%s' (%s): %s",
                    task.output.channel_type, task.name, task_id, exc,
                )

        # ── Fase 3: aggiornamento statistiche ─────────────────────────────────
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        next_run = self.get_next_run(task_id)
        task_current = self._storage.get(task_id)
        updates: dict = {
            "last_run": now_str,
            "run_count": run_count,
        }
        if next_run:
            updates["next_run"] = next_run

        if llm_error is None:
            # Esecuzione riuscita
            if task.schedule.type == "once":
                updates["status"] = "completed"
                logger.info("Task 'once' completato: '%s' (%s)", task.name, task_id)
        else:
            # Esecuzione fallita
            updates["error_count"] = (task_current.error_count + 1) if task_current else 1
            updates["last_error"] = str(llm_error)
            if task.schedule.type == "once":
                # Task irripetibile: segna come errore permanente
                updates["status"] = "error"
                logger.error("Task 'once' fallito definitivamente: '%s' (%s)", task.name, task_id)
            else:
                # Task ripetuto: rimane active, riprova alla prossima scadenza
                logger.warning(
                    "Errore task ripetuto '%s' (%s) — status rimane active, riprova alla prossima scadenza",
                    task.name, task_id,
                )

        self._storage.update(task_id, **updates)

        # ── Fase 4: archiviazione task terminati ──────────────────────────────
        final_status = updates.get("status")
        if final_status in ("completed", "error"):
            self._storage.archive(task_id)
            logger.info(
                "Task archiviato in executed_tasks.yaml: '%s' (%s) — status: %s",
                task.name, task_id, final_status,
            )

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Listener APScheduler per gli errori di job non gestiti."""
        logger.error(
            "APScheduler job error — job_id=%s exception=%s",
            event.job_id,
            event.exception,
        )
