from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import Database
from app.services.puller import PullManager
from app.services.site_syncer import SiteSyncManager


class SchedulerService:
    def __init__(self, db: Database, pull_manager: PullManager, site_syncer: SiteSyncManager) -> None:
        self.db = db
        self.pull_manager = pull_manager
        self.site_syncer = site_syncer
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.reload()

    def reload(self) -> None:
        settings = self.db.get_settings()
        self.scheduler.remove_all_jobs()
        if not settings.get("scheduler_enabled"):
            return
        interval_hours = max(int(settings.get("scheduler_interval_hours", 12)), 1)
        self.scheduler.add_job(
            self.start_scheduled_sync,
            IntervalTrigger(hours=interval_hours),
            id="scheduled-sync",
            replace_existing=True,
        )

    def start_scheduled_sync(self) -> None:
        self.pull_manager.start_pull()
        self.site_syncer.start_sync()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
