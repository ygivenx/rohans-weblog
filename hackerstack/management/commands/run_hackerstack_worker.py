"""A single low-duty-cycle collector process, separate from web requests."""

import signal
import threading

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, close_old_connections
from django.db.migrations.executor import MigrationExecutor
from hackerstack.daily import (
    RETRY_DELAYS,
    release_lock,
    run_daily_job,
    seconds_until_next_day,
)


class Command(BaseCommand):
    help = "Seed once, load the snapshot once, then run the resumable daily job (collect, fetch pages, review)"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        ready = False
        for _ in range(60):
            close_old_connections()
            try:
                executor = MigrationExecutor(connection)
                ready = not executor.migration_plan(executor.loader.graph.leaf_nodes())
            except Exception:
                ready = False
            if ready or stop.wait(5):
                break
        if stop.is_set():
            return
        if not ready:
            raise CommandError("Database migrations were not ready within five minutes")
        call_command("seed_hackerstack")
        try:
            # One-time bootstrap of the reviewed index; marker makes restarts a no-op.
            call_command("load_snapshot")
        except CommandError as exc:
            self.stderr.write(
                f"Snapshot not loaded ({exc}); continuing with daily collection."
            )
        # A previous process may have died mid-run holding the lock; this worker is the
        # normal sole runner, so start clean. Steps are resumable, so nothing is repeated.
        release_lock()
        while not stop.is_set():
            try:
                result = run_daily_job(log=self.stdout.write)
            except Exception as exc:  # the loop must survive anything, e.g. a DB blip
                self.stderr.write(
                    f"Daily job crashed ({type(exc).__name__}); will retry."
                )
                close_old_connections()
                result = None
            close_old_connections()
            if options["once"]:
                break
            if result is None:
                wait = RETRY_DELAYS[0]
            elif result.busy:
                wait = 300
            else:
                wait = result.retry_in or seconds_until_next_day()
            if stop.wait(wait):
                break
