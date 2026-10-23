from __future__ import annotations

import asyncio
import threading
from datetime import datetime, time, timedelta
from typing import Any, Callable
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from .checker import CheckResult, SiteChecker
from .database import Database
from .notifier import EmailNotifier
from .reports import build_report


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
        self._monitor_locks: dict[int, threading.Lock] = {}

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
            self.sync_email_jobs()
            self.notifier.start()

    def stop(self) -> None:
        with self._lock:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)
            self.notifier.stop()

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

    def sync_email_jobs(self) -> None:
        with self._lock:
            active: set[str] = set()
            for rule in self.db.list_email_rules(enabled_only=True):
                if rule["rule_type"] != "daily_summary":
                    continue
                job_id = f"email-summary-{rule['id']}"
                active.add(job_id)
                trigger = CronTrigger(day_of_week=rule["weekdays"], hour=rule["hour"], minute=rule["minute"], timezone=self._scheduler.timezone)
                existing = self._scheduler.get_job(job_id)
                if existing:
                    existing.reschedule(trigger=trigger)
                else:
                    self._scheduler.add_job(
                        self.queue_daily_summary, trigger,
                        id=job_id, args=[rule["id"]], replace_existing=True,
                        max_instances=1, coalesce=True, misfire_grace_time=3600,
                    )
            for job in list(self._scheduler.get_jobs()):
                if job.id.startswith("email-summary-") and job.id not in active:
                    self._scheduler.remove_job(job.id)

    def queue_daily_summary(self, rule_id: int, now: datetime | None = None, manual: bool = False) -> bool:
        rule = self.db.get_email_rule(rule_id)
        if not rule or not rule["enabled"] or rule["rule_type"] != "daily_summary" or self.db.get_setting("smtp_enabled", "0") != "1":
            return False
        now = now or datetime.now()
        day = now.date() - timedelta(days=1 if rule["report_period"] == "yesterday" else 0)
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max).replace(microsecond=0) if rule["report_period"] == "yesterday" else now
        report = build_report(self.db, start, end, now=now)
        slot = f"manual:{uuid4()}" if manual else f"{now.date()}:{rule['hour']:02d}:{rule['minute']:02d}:{rule['report_period']}"
        queued = self.db.queue_summary(rule_id, slot, report)
        if queued:
            self.notifier.wake()
        return bool(queued)

    def run_all_now(self) -> None:
        for monitor in self.db.list_monitors(include_disabled=False):
            self.run_now(int(monitor["id"]))

    def _job_id(self, monitor_id: int) -> str:
        return f"monitor-{monitor_id}"

    def _run_monitor_job(self, monitor_id: int) -> None:
        with self._lock:
            monitor_lock = self._monitor_locks.setdefault(monitor_id, threading.Lock())
        if not monitor_lock.acquire(blocking=False):
            return
        try:
            self._check_monitor(monitor_id)
        finally:
            monitor_lock.release()

    def _check_monitor(self, monitor_id: int) -> None:
        monitor = self.db.get_monitor(monitor_id)
        if not monitor or not monitor.get("enabled"):
            return

        result = asyncio.run(self.checker.check_monitor(monitor))
        if not self.db.record_check_result(monitor_id, result):
            return

        if self.on_result:
            fresh_monitor = self.db.get_monitor(monitor_id) or monitor
            self.on_result(fresh_monitor, result)
        self.notifier.wake()
