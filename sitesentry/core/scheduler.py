from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .checker import CheckResult, SiteChecker
from .database import Database
from .notifier import EmailNotifier


ResultCallback = Callable[[dict[str, Any], CheckResult], None]


class MonitorScheduler:
    def __init__(
        self,
        db: Database,
        checker: SiteChecker,
        notifier: EmailNotifier,
        on_result: ResultCallback | None = None,
    ) -> None:
        self.db = db
        self.checker = checker
        self.notifier = notifier
        self.on_result = on_result
        self._scheduler = BackgroundScheduler(daemon=True)
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def set_on_result(self, callback: ResultCallback | None) -> None:
        self.on_result = callback

    def start(self) -> None:
        with self._lock:
            if not self._scheduler.running:
                self._scheduler.start(paused=False)
            self.sync_jobs()

    def stop(self) -> None:
        with self._lock:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)

    def sync_jobs(self) -> None:
        with self._lock:
            active_ids: set[str] = set()
            for monitor in self.db.list_monitors(include_disabled=False):
                monitor_id = int(monitor["id"])
                job_id = self._job_id(monitor_id)
                active_ids.add(job_id)
                trigger = IntervalTrigger(seconds=max(10, int(monitor.get("interval_seconds") or 60)))
                existing = self._scheduler.get_job(job_id)
                if existing:
                    existing.reschedule(trigger=trigger)
                else:
                    self._scheduler.add_job(
                        self._run_monitor_job,
                        trigger=trigger,
                        id=job_id,
                        args=[monitor_id],
                        max_instances=1,
                        coalesce=True,
                        next_run_time=datetime.now(),
                        replace_existing=True,
                    )

            for job in list(self._scheduler.get_jobs()):
                if job.id.startswith("monitor-") and job.id not in active_ids:
                    self._scheduler.remove_job(job.id)

    def run_now(self, monitor_id: int) -> None:
        thread = threading.Thread(target=self._run_monitor_job, args=(monitor_id,), daemon=True)
        thread.start()

    def run_all_now(self) -> None:
        for monitor in self.db.list_monitors(include_disabled=False):
            self.run_now(int(monitor["id"]))

    def _job_id(self, monitor_id: int) -> str:
        return f"monitor-{monitor_id}"

    def _run_monitor_job(self, monitor_id: int) -> None:
        monitor = self.db.get_monitor(monitor_id)
        if not monitor or not monitor.get("enabled"):
            return

        old_status = monitor.get("last_status") or "unknown"
        result = asyncio.run(self.checker.check_monitor(monitor))
        status = "up" if result.ok else "down"
        self.db.add_log(
            monitor_id=monitor_id,
            monitor_name=str(monitor.get("name") or ""),
            status=status,
            ok=result.ok,
            response_ms=result.response_ms,
            status_code=result.status_code,
            error=result.error,
            attempts=result.attempts,
            detail_json=result.detail_json(),
            checked_at=result.checked_at,
        )
        self.db.set_monitor_result(
            monitor_id=monitor_id,
            status=status,
            status_code=result.status_code,
            response_ms=result.response_ms,
            error=result.error,
            checked_at=result.checked_at,
        )

        should_alert_down = not result.ok and (old_status != "down" or self.notifier.cooldown_expired(monitor, "down"))
        should_alert_recovery = result.ok and old_status == "down"
        if should_alert_down:
            self.notifier.send_monitor_alert("down", monitor, result)
        elif should_alert_recovery:
            self.notifier.send_monitor_alert("recovery", monitor, result)

        if self.on_result:
            fresh_monitor = self.db.get_monitor(monitor_id) or monitor
            self.on_result(fresh_monitor, result)
