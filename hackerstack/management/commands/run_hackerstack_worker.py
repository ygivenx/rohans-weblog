"""A single low-duty-cycle collector process, separate from web requests."""

import signal
import threading
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, close_old_connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from hackerstack.models import CollectionCursor


class Command(BaseCommand):
    help = "Seed once; daily historical backfill (120 requests) and recent refresh (12 requests)"

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
        while not stop.is_set():
            marker, _ = CollectionCursor.objects.get_or_create(key="worker:daily")
            if marker.cycle:
                seconds = (
                    marker.updated_at + timedelta(days=1) - timezone.now()
                ).total_seconds()
                if seconds > 0:
                    if options["once"] or stop.wait(seconds):
                        break
            # Persist before collecting: restarts cannot turn a daily budget into a loop.
            marker.cycle += 1
            marker.save()
            for mode in ("history", "recent"):
                if stop.is_set():
                    break
                try:
                    if mode == "history":
                        call_command(
                            "backfill_hackerstack", initialize=True, max_requests=120
                        )
                    else:
                        call_command("sync_hackerstack", mode=mode, max_requests=12)
                except CommandError:
                    self.stderr.write(
                        f"{mode} collection failed; see CollectionRun in admin. No immediate retry."
                    )
            close_old_connections()
            if options["once"] or stop.wait(86400):
                break
