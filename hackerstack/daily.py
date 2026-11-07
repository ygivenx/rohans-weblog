"""The daily job: ordered, independently retryable steps with per-day budgets.

Safety properties (each is covered by tests):
- Resumable: every step's command already resumes where it stopped (backfill windows, unfetched
  pages, unreviewed pages), so re-running a step never repeats finished work.
- Isolated: one failing step never blocks the steps after it.
- Bounded: a step gets at most MAX_ATTEMPTS tries per UTC day, and a retry receives only the
  budget left after earlier attempts that day, so retries cannot overspend request budgets.
- Persist-before-run: the attempt is counted before the command starts, so a crash loop cannot
  turn a daily budget into an unbounded one.
- Exclusive: a DB lock stops the worker and a manual run from overlapping; a stale lock expires.

State lives in CollectionCursor rows (no schema change): key `daily:<date>:<step>` holds the
attempt count in `page` and a done flag in `cycle`.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import Callable

from django.core.management import call_command
from django.db.models import Q, Sum

from django.utils import timezone

from .models import CollectionCursor, CollectionRun
from .review import ReviewUnavailable

MAX_ATTEMPTS = 3
RETRY_DELAYS = (600, 1800, 3600)  # seconds before attempt 2, 3 (and a final long wait)
LOCK_KEY = "daily:lock"
LOCK_STALE = timedelta(hours=3)
KEEP_DAYS = 14


@dataclass(frozen=True)
class Step:
    name: str
    command: str
    source: str  # CollectionRun.source whose `requests` counts units used today
    budget: int  # units per UTC day (HTTP requests, pages, or reviewed items)
    kwargs: Callable[[int], dict] = field(default=lambda remaining: {})
    min_units: int = 1


STEPS = (
    Step(
        "history",
        "backfill_hackerstack",
        "hn-backfill",
        120,
        lambda n: dict(initialize=True, max_requests=n),
    ),
    Step(
        "recent",
        "sync_hackerstack",
        "hn",
        12,
        lambda n: dict(mode="recent", max_requests=n),
    ),
    Step("pages", "fetch_pages", "page-fetch", 300, lambda n: dict(limit=n, workers=8)),
    Step("review", "review_pages", "review", 300, lambda n: dict(limit=n)),
    Step(
        "second_opinion",
        "review_pages",
        "review-2nd",
        300,
        lambda n: dict(limit=n, second_opinion=True),
    ),
)
STEP_NAMES = [s.name for s in STEPS]


@dataclass
class JobResult:
    busy: bool = False
    ran: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    retry_in: int | None = (
        None  # seconds until a retry is useful; None = wait for tomorrow
    )

    @property
    def finished(self):
        return not self.busy and self.retry_in is None


def utc_day(now=None):
    return (now or timezone.now()).astimezone(dt_timezone.utc).date()


def day_start(day):
    return datetime.combine(day, time.min, tzinfo=dt_timezone.utc)


def seconds_until_next_day(now=None):
    now = now or timezone.now()
    nxt = day_start(utc_day(now) + timedelta(days=1)) + timedelta(minutes=5)
    return max(60, int((nxt - now).total_seconds()))


def _key(day, step):
    return f"daily:{day.isoformat()}:{step}"


def used_today(source, day):
    total = CollectionRun.objects.filter(
        source=source, started_at__gte=day_start(day)
    ).aggregate(n=Sum("requests"))["n"]
    return total or 0


def acquire_lock(now=None):
    now = now or timezone.now()
    lock, _ = CollectionCursor.objects.get_or_create(key=LOCK_KEY)
    # Atomic compare-and-set: only one caller flips an unlocked (or stale) lock.
    won = CollectionCursor.objects.filter(
        Q(page=0) | Q(updated_at__lt=now - LOCK_STALE), pk=lock.pk
    ).update(page=1, updated_at=now)
    return bool(won)


def release_lock():
    CollectionCursor.objects.filter(key=LOCK_KEY).update(page=0)


def _seed_from_legacy_marker(day):
    """The first worker cycle used a single `worker:daily` marker; honour it once so the
    collection steps are not run a second time on the day this version deploys."""
    if CollectionCursor.objects.filter(
        key__startswith=f"daily:{day.isoformat()}:"
    ).exists():
        return
    legacy = CollectionCursor.objects.filter(key="worker:daily", cycle__gt=0).first()
    if legacy and utc_day(legacy.updated_at) == day:
        for name in ("history", "recent"):
            CollectionCursor.objects.get_or_create(
                key=_key(day, name), defaults=dict(page=1, cycle=1)
            )


def _cleanup(day):
    cutoff = day - timedelta(days=KEEP_DAYS)
    for row in CollectionCursor.objects.filter(key__startswith="daily:2"):
        try:
            if datetime.fromisoformat(row.key.split(":")[1]).date() < cutoff:
                row.delete()
        except ValueError:
            continue


def step_status(day=None):
    day = day or utc_day()
    rows = []
    for step in STEPS:
        state = CollectionCursor.objects.filter(key=_key(day, step.name)).first()
        rows.append(
            dict(
                step=step.name,
                done=bool(state and state.cycle),
                attempts=state.page if state else 0,
                remaining=max(0, step.budget - used_today(step.source, day)),
            )
        )
    return rows


def run_daily_job(only=None, force=False, now=None, log=lambda message: None):
    """Run every step that is not done for today. Safe to call repeatedly."""
    now = now or timezone.now()
    day = utc_day(now)
    result = JobResult()
    if only and only not in STEP_NAMES:
        raise ValueError(f"Unknown step {only!r}; choose from {', '.join(STEP_NAMES)}")
    if not acquire_lock(now):
        result.busy = True
        log("Another daily job holds the lock; not running.")
        return result
    try:
        _seed_from_legacy_marker(day)
        _cleanup(day)
        pending_attempts = []
        for step in STEPS:
            if only and step.name != only:
                continue
            state, _ = CollectionCursor.objects.get_or_create(key=_key(day, step.name))
            if force:
                state.page, state.cycle = 0, 0
                state.save()
            if state.cycle:
                continue
            if state.page >= MAX_ATTEMPTS:
                log(f"{step.name}: gave up for today after {state.page} attempts")
                result.failed.append(step.name)
                continue
            remaining = step.budget - used_today(step.source, day)
            if remaining < step.min_units:
                state.cycle = (
                    1  # budget already spent today (e.g. by an earlier attempt)
                )
                state.save()
                log(f"{step.name}: today's budget is already used")
                continue
            state.page += 1  # persist the attempt before running
            state.save()
            try:
                call_command(step.command, **step.kwargs(remaining))
            except ReviewUnavailable as exc:
                state.cycle = 1  # not configured: not an error, nothing to retry
                state.save()
                result.skipped.append(step.name)
                log(f"{step.name}: skipped ({exc})")
            except Exception as exc:  # isolate: later steps must still run
                CollectionRun.objects.create(
                    source=f"daily:{step.name}",
                    status="failed",
                    finished_at=timezone.now(),
                    detail=f"attempt {state.page}/{MAX_ATTEMPTS}: {type(exc).__name__}: {str(exc)[:300]}",
                )
                result.failed.append(step.name)
                pending_attempts.append(state.page)
                log(
                    f"{step.name}: failed on attempt {state.page}: {type(exc).__name__}"
                )
            else:
                state.cycle = 1
                state.save()
                result.ran.append(step.name)
                log(f"{step.name}: done")
        retryable = [a for a in pending_attempts if a < MAX_ATTEMPTS]
        if retryable:
            result.retry_in = RETRY_DELAYS[min(max(retryable), len(RETRY_DELAYS)) - 1]
        return result
    finally:
        release_lock()
