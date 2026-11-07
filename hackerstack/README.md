# HackerStack

Native Django directory at `/hackerstack/` (the slashless path redirects normally).
No JS framework, third-party search service, paid API, or per-search model calls.

## Run

```sh
uv run python manage.py migrate
uv run python manage.py seed_hackerstack
uv run python manage.py backfill_hackerstack --initialize --max-requests 24
uv run python manage.py sync_hackerstack --mode recent --max-requests 12
uv run python manage.py runserver
```

Search indexes resource titles, descriptions, URLs, categories, and keywords using
SQLite FTS5 locally and a PostgreSQL GIN full-text index in production. Pages contain
24 results. Search is token AND matching; an exact title phrase is promoted in the
recommended sort. No full linked-page content is fetched or claimed to be indexed.

## Collection and honest coverage

`data/resources.json` contains 56 editorial seeds. Seeding is idempotent and preserves
owner edits. Community ingestion retains exact discussion URLs, current vote counts,
observation dates, source identifiers, and deduplicated resource associations.

`backfill_hackerstack` initializes yearly windows from 2006 to the current snapshot
for the versioned vocabulary in `backfill.py`. It splits intervals recursively when
HN reports 900+ results or an inexact count, below the usual 1,000-result search cap.
Half-open intervals avoid boundary overlaps. Pages and interval states are committed
atomically. Interrupted runs resume. A one-second interval that cannot be exhausted
is marked blocked, not complete. Invalid records mark an interval for review.

**A completed window means its query's reported results were scanned, not that all
semantically relevant links on HN were found.** Vocabulary misses, deleted/private
content, search-provider omissions, and index changes remain possible. A website's
articles are distinct resources; votes on one article are not transferred to every
page on its domain. Automatically assigned categories are discovery-query labels.

`sync_hackerstack --mode popular` is the original capped sampling collector; use
`backfill_hackerstack` for historical coverage. Recent mode refreshes the latest
50 matches per query. Historical windows extended on each daily run fill temporal
gaps left by that quick refresh.

```sh
# Extract outbound links from a selected HN thread. HN comment votes are not assumed.
uv run python manage.py sync_hackerstack --thread-id 43998472 --category agents --max-requests 2
# Import a legitimately obtained JSON array of Lobsters stories.
uv run python manage.py sync_hackerstack --lobsters-file /path/to/stories.json --category engineering
# Recompute scores without network calls.
uv run python manage.py rank_hackerstack
```

Lobsters imports expect `short_id`, `url`, `title`, optional integer `score`,
nonnegative `comment_count`, and optional ISO `created_at`. Imports are atomic.
Lobsters currently disallows general crawlers, so no crawler is enabled. **No
historical Lobsters archive has been acquired.** Comment extraction is currently
explicit per thread; it is not a census of all historical comment links.

## Ranking v2

All components are 0–1:

```
P = max over submissions: ln(1 + max(votes, 0)) /
                         [ln(1 + max(votes, 0)) + ln(1 + source_scale)]
C = 1 - exp(-distinct_source_and_thread_pairs / 3)
E = 1 for editorial seeds, otherwise 0
F = 2 ** (-content_age_days / half_life_days)
R = Jev's P(on-topic) from the page title, heading and description; 0.5 when not reviewed
score = 100 * (0.20 + 0.40*P + 0.20*C + 0.15*E + 0.05*R) * (0.20 + 0.80*F)
```

Reference vote scales: HN 500, Lobsters 100. These are tuning parameters, not
empirically calibrated community percentiles. A comment mention has no popularity
points. Distinct discussions measure attention, not positive sentiment or independent
human endorsement. The baseline prevents unvoted resources from disappearing.

Half-lives: news 30 days; tools/docs 180; articles/websites 365; papers 730;
courses 1,825. Unknown content dates start at freshness 0.5, reduced further if the
earliest known discussion is older than one half-life. Discussion age is a proxy,
not a claimed publication date. A fetch never resets age. Editors can supply a
verified content date, date basis, and appropriate half-life in Django admin.

These choices are inspectable heuristics, not validated quality predictions.

## Page review (Jev; Claude Haiku 5.5 as fallback)

Three steps improve descriptions, topics and labels. None of them guesses from keywords.

1. `fetch_pages --limit 5000` reads each URL's own `<title>`, first `<h1>` and description
   (standard library only). It honours `robots.txt`, spaces requests per host, refuses
   non-public IPs on every redirect hop, and reads at most 150 KB. It resumes where it
   stopped; `--retry-failed` retries timeouts and 429/5xx. A fetched description replaces
   the placeholder text unless an editor changed it.
2. `review_pages` sends one request per fetched page to Jev (TypeSafe AI, pinned model
   `jev-1.14.0`) with three questions answered together: P(on-topic), best topic (12
   options) and kind of resource (7 options). The key is read from `JEV_API_KEY` only.
   Without it, `ANTHROPIC_API_KEY` selects the Claude Haiku 5.5 fallback; with neither the
   step is skipped. `--include-reviewed` re-reviews pages another model reviewed (resumable),
   `--dry-run` prints verdicts and agreement with earlier ones without saving, and
   `--sample-seed N` shuffles the selection.
3. Decisions come from thresholds (in `review.py`, tuned on a labelled sample): P < 0.30
   hides the link (balanced); P >= 0.50 marks it on-topic; between the two it is "uncertain"
   and stays visible with its keyword topic. The refined topic is used only when the link is
   on-topic and topic confidence >= 0.50; the kind label changes only at confidence >= 0.60
   and never for editor-curated links (the freshness half-life follows the new kind unless it
   was tuned by hand). The raw probability is stored (`llm_score`) so thresholds can be
   re-tuned without re-calling the model.

Page text is untrusted data: Jev only answers questions about it and never follows
instructions in it. The text sent is public page titles, headings and descriptions. TypeSafe's
docs state Jev is not trained on customer requests; log retention is not stated.

On the site, a link judged on-topic is listed under the reviewed topic (marked ✦ when it
differs from the keyword topic); links judged off-topic are hidden by default and shown under
"Show filtered-out links". Jev's confidence adds a small boost to ranking (R above).

## Snapshot bootstrap

The worker's request budget cannot rebuild a reviewed index quickly, so
`hackerstack/data/snapshot.jsonl.gz` carries resources, evidence and backfill coverage.
`load_snapshot` runs once per snapshot file (marker `snapshot:<size>`), creates missing
rows only, fills still-empty review fields on existing rows, never overwrites editor
changes, rolls back on a bad file, and re-ranks. Refresh it with
`python manage.py export_snapshot` after more fetching or reviewing, then commit.

## Daily job (resumable, retried on error)

`run_hackerstack_worker` runs `hackerstack/daily.py` once a UTC day. Steps, in order, each with
a per-day budget: `history` (backfill, 120 requests), `recent` (12), `pages` (`fetch_pages`,
300 pages), `review` and `second_opinion` (`review_pages`, 300 pages each; the second-opinion step is
only used by the Claude fallback, since Jev returns confidence scores).

- **Resumable:** each command picks up where it stopped, so re-running never repeats work.
- **Isolated:** a failing step is logged as a failed `CollectionRun` (`daily:<step>`) and the
  steps after it still run.
- **Retried, bounded:** up to 3 attempts per step per day, waiting 10 min, then 30 min; a retry
  gets only the budget left after earlier attempts, so retries cannot overspend. After the third
  failure the step waits for tomorrow.
- **Persist-before-run:** the attempt is counted before the command starts, so a crash loop
  cannot become an unbounded budget.
- **Exclusive:** a DB lock stops two runs overlapping; a lock older than 3 hours is treated as
  dead, and the worker clears it on start.
- **Review is optional:** with `JEV_API_KEY` (preferred) or `ANTHROPIC_API_KEY` set the review steps
  run; with neither they are skipped (not failed). Add the key as a GitHub secret of that name; the
  deploy writes it into the indexer's environment. Only environment variables are read, and keys
  are never logged.

Operate it by hand: `python manage.py run_daily_job --status` shows each step's state and
remaining budget; `run_daily_job` runs whatever is not done today; `--step pages --force`
re-runs one step; `docker compose exec hackerstack-indexer python manage.py run_daily_job`
runs it in production. State is kept in `CollectionCursor` rows (`daily:<date>:<step>`), pruned
after 14 days.

## Resource limits and production

The Compose `hackerstack-indexer` service waits for migrations, seeds the directory,
then uses at most **132 network requests daily**: 120 historical + 12 recent. Each
client paces requests at one/second, times out after 15 seconds, allows at most one
retry (counted against budget), and rejects responses larger than 4 MB. Successful
responses are cached for 24 hours, pruned after seven days, and kept in a dedicated
Docker volume. Cached work is also bounded. Restart markers prevent immediately
repeating a daily batch after a container restart. The worker gets 0.5 CPU and 256 MB.

The historical budget is higher than the initial 24-request sampling budget so the
archive can make progress. Stop/pause it with `docker compose stop hackerstack-indexer`.
Manual commands have their own budgets; do not run overlapping backfills. Inspect
CollectionRun and BackfillWindow in admin for failures and coverage. The public page
shows partial coverage and score-calculation time. No completeness date is promised.

Deployment is the existing main-branch GitHub Actions → Hostinger pipeline. The
deployment's test job now runs the suite against PostgreSQL before changing the site;
ordinary CI tests SQLite. The existing database volume stores the catalog. No local
SQLite database is uploaded. Production builds its own index with the worker.

## Verify

```sh
uv run python manage.py test --noinput
uv run python manage.py makemigrations --check --dry-run
uv run black --check .
uv run python manage.py check --deploy
```

Tests cover unsafe URLs, output escaping, full-text insert/update/delete, filters,
pagination, repeat ingestion, comment/thread deduplication, unknown dates, age decay,
vote saturation, batched reranking, atomic imports, and interrupted collection.
