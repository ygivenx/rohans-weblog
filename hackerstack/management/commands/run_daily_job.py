from django.core.management.base import BaseCommand, CommandError

from hackerstack.daily import STEP_NAMES, run_daily_job, step_status


class Command(BaseCommand):
    help = (
        "Run the daily job once (the worker does this on a schedule). Safe to re-run: finished "
        "steps are skipped. --step runs one step; --force re-runs it even if done; --status shows state."
    )

    def add_arguments(self, parser):
        parser.add_argument("--step", choices=STEP_NAMES)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reset and re-run (all steps, or --step)",
        )
        parser.add_argument("--status", action="store_true")

    def handle(self, *args, **options):
        if options["status"]:
            for row in step_status():
                self.stdout.write(
                    f"{row['step']:15} done={row['done']!s:5} attempts={row['attempts']} "
                    f"budget_left_today={row['remaining']}"
                )
            return
        result = run_daily_job(
            only=options["step"], force=options["force"], log=self.stdout.write
        )
        if result.busy:
            raise CommandError("Another daily job is running; try again later")
        self.stdout.write(
            f"ran={result.ran} skipped={result.skipped} failed={result.failed} "
            f"retry_in={result.retry_in}"
        )
        if result.failed:
            raise CommandError(
                "Some steps failed; re-run to retry the remaining budget"
            )
