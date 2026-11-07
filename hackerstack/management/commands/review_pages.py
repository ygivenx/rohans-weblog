"""Review fetched pages: Jev (preferred, probabilities) or Claude Haiku 5.5 (fallback).

Reads JEV_API_KEY / ANTHROPIC_API_KEY from the environment only. With neither set it raises
ReviewUnavailable, which the daily job records as a skip rather than an error.
"""

import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hackerstack import jev
from hackerstack.management.commands.classify_resources import (
    SECOND_OPINION_TAG,
    build_prompt,
)
from hackerstack.models import CollectionRun, Resource
from hackerstack.review import (
    MODEL,
    apply_jev_verdict,
    apply_verdict,
    decide,
    make_client,
    resolve_provider,
    review_batch,
)


class Command(BaseCommand):
    help = "Review fetched pages with Jev (JEV_API_KEY) or Claude Haiku 5.5 (ANTHROPIC_API_KEY)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=300)
        parser.add_argument("--batch-size", type=int, default=40, help="Anthropic only")
        parser.add_argument(
            "--workers", type=int, default=6, help="Jev only: parallel requests"
        )
        parser.add_argument(
            "--provider", choices=["auto", "jev", "anthropic"], default="auto"
        )
        parser.add_argument(
            "--second-opinion", action="store_true", help="Anthropic only"
        )
        parser.add_argument(
            "--include-reviewed",
            action="store_true",
            help="Jev: also re-review pages another model already reviewed (resumable)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Jev: show verdicts, save nothing"
        )
        parser.add_argument(
            "--sample-seed", type=int, help="Shuffle the selection with this seed"
        )

    def handle(self, *args, **options):
        provider = resolve_provider(options["provider"])
        limit, second = options["limit"], options["second_opinion"]
        if not 1 <= limit <= 25000 or not 1 <= options["batch_size"] <= 60:
            raise CommandError("--limit must be 1-25000 and --batch-size 1-60")
        if not 1 <= options["workers"] <= 16:
            raise CommandError("--workers must be 1-16")
        if provider == "jev" and second:
            self.stdout.write(
                "Second opinions are not used with Jev: it returns confidence scores."
            )
            return
        qs = Resource.objects.filter(is_active=True, fetch_status="ok")
        if second:
            qs = qs.filter(llm_relevant=False).exclude(
                llm_model__endswith=SECOND_OPINION_TAG
            )
        elif provider == "jev" and options["include_reviewed"]:
            qs = qs.exclude(llm_model__startswith=jev.MODEL_PREFIX)
        else:
            qs = qs.filter(llm_classified_at__isnull=True)
        todo = list(qs.order_by("-score", "id"))
        if options["sample_seed"] is not None:
            random.Random(options["sample_seed"]).shuffle(todo)
        todo = todo[:limit]
        if not todo:
            self.stdout.write("Nothing to review")
            return
        if provider == "jev":
            self.run_jev(todo, options)
        else:
            self.run_anthropic(todo, options["batch_size"], second)

    # --- Jev -------------------------------------------------------------------------------

    def run_jev(self, todo, options):
        key, dry = jev.api_key(), options["dry_run"]
        run = None if dry else CollectionRun.objects.create(source="review")
        sent = saved = failed = consecutive = tokens = 0
        fatal = None
        rows = []
        try:
            with ThreadPoolExecutor(max_workers=options["workers"]) as pool:
                futures = {pool.submit(jev.review, r, key): r for r in todo}
                for future in as_completed(futures):
                    resource = futures[future]
                    try:
                        verdict = future.result()
                    except jev.JevAuthError as exc:
                        fatal = str(exc)
                    except jev.JevError as exc:
                        failed += 1
                        consecutive += 1
                        if consecutive >= 10:
                            fatal = f"10 consecutive failures (last: {exc})"
                    except (
                        Exception
                    ) as exc:  # a bug must not lose the whole run's progress
                        failed += 1
                        consecutive += 1
                        self.stderr.write(
                            f"unexpected {type(exc).__name__} on {resource.pk}"
                        )
                        if consecutive >= 10:
                            fatal = f"10 consecutive failures ({type(exc).__name__})"
                    else:
                        consecutive = 0
                        sent += 1
                        tokens += verdict.input_tokens
                        if dry:
                            rows.append((resource, verdict))
                        else:
                            apply_jev_verdict(resource, verdict)
                            saved += 1
                    if fatal:
                        for f in futures:
                            f.cancel()
                        break
                    done = sent + failed
                    if not dry and done % 500 == 0:
                        self.stdout.write(
                            f"{done}/{len(todo)} saved={saved} failed={failed}"
                        )
                        self.stdout.flush()
        finally:
            if run:
                run.requests, run.records = sent, saved
                run.status = (
                    "failed" if fatal else ("partial" if failed else "complete")
                )
                run.finished_at = timezone.now()
                run.detail = f"{jev.MODEL}; failed={failed}; input tokens={tokens}" + (
                    f"; stopped: {fatal}" if fatal else ""
                )
                run.save()
        if dry:
            self.report_dry_run(rows)
        self.stdout.write(
            f"{'dry-run' if dry else (run.status if run else '')}: {sent} reviewed, {failed} failed, "
            f"input tokens={tokens}"
        )
        if fatal:
            raise CommandError(fatal)

    def report_dry_run(self, rows):
        """Verdicts next to any earlier ones, plus agreement counts. Nothing is saved."""
        for resource, v in sorted(rows, key=lambda x: x[1].relevance):
            prior = {True: "yes", False: "NO", None: "-"}[resource.llm_relevant]
            relevant, topic, kind = decide(v)
            self.stdout.write(
                f"{v.relevance:4.2f} prior={prior:3} {resource.title[:46]:46} | "
                f"{(topic or '(keep ' + resource.category + ')'):18} "
                f"topic {v.topic_confidence:.2f} -> {v.topic[:11]:11} | kind {v.kind[:9]:9} {v.kind_confidence:.2f}"
            )
        agree = Counter()
        for resource, v in rows:
            if resource.llm_relevant is None and not resource.llm_classified_at:
                continue
            band = (
                "hide"
                if v.relevance < 0.30
                else ("keep" if v.relevance >= 0.50 else "unsure")
            )
            agree[(resource.llm_relevant, band)] += 1
        self.stdout.write("prior verdict x Jev band: " + str(dict(agree)))

    # --- Anthropic (fallback) -----------------------------------------------------------------

    def run_anthropic(self, todo, size, second):
        import anthropic

        client = make_client()
        run = CollectionRun.objects.create(source="review-2nd" if second else "review")
        sent = saved = failed = consecutive = tokens_in = tokens_out = 0
        fatal = None
        try:
            for start in range(0, len(todo), size):
                batch = todo[start : start + size]
                by_id = {r.id: r for r in batch}
                try:
                    results, usage = review_batch(
                        client, build_prompt(batch, second_opinion=second)
                    )
                except (
                    anthropic.AuthenticationError,
                    anthropic.PermissionDeniedError,
                ) as exc:
                    fatal = f"API key rejected ({type(exc).__name__})"
                    break
                except (
                    anthropic.APIError,
                    ValueError,
                    KeyError,
                    TypeError,
                    json.JSONDecodeError,
                ) as exc:
                    failed += 1
                    consecutive += 1
                    self.stderr.write(f"batch at {start} failed: {type(exc).__name__}")
                    if consecutive >= 3:
                        fatal = "3 consecutive failed batches"
                        break
                    continue
                consecutive = 0
                sent += len(batch)
                tokens_in += usage["input_tokens"]
                tokens_out += usage["output_tokens"]
                seen = set()
                for item in results:
                    r = by_id.get(item.get("id")) if isinstance(item, dict) else None
                    if r is None or r.id in seen:
                        continue
                    if apply_verdict(r, item, MODEL, second_opinion=second):
                        seen.add(r.id)
                        saved += 1
        finally:
            run.requests = sent  # units used today: items sent for review
            run.records = saved
            run.status = "failed" if fatal else ("partial" if failed else "complete")
            run.finished_at = timezone.now()
            run.detail = (
                f"{MODEL} effort=low; batches failed={failed}; tokens in={tokens_in} out={tokens_out}"
                + (f"; stopped: {fatal}" if fatal else "")
            )
            run.save()
        self.stdout.write(
            f"{run.status}: {saved}/{len(todo)} reviewed, {failed} failed batches, "
            f"tokens in={tokens_in} out={tokens_out}"
        )
        if fatal:
            raise CommandError(fatal)
