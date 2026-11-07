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

## Ranking v1

All components are 0–1:

```
P = max over submissions: ln(1 + max(votes, 0)) /
                         [ln(1 + max(votes, 0)) + ln(1 + source_scale)]
C = 1 - exp(-distinct_source_and_thread_pairs / 3)
E = 1 for editorial seeds, otherwise 0
F = 2 ** (-content_age_days / half_life_days)
score = 100 * (0.20 + 0.45*P + 0.20*C + 0.15*E) * (0.20 + 0.80*F)
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

## Page review (no per-link LLM calls in production)

Three offline steps improve descriptions and topics. None of them runs in the deployed
worker, and none sends anything to an LLM except step 3, which runs locally.

1. `fetch_pages --limit 5000` reads each URL's own `<title>`, first `<h1>` and
   description (standard library only). It honours `robots.txt`, spaces requests per
   host, refuses non-public IPs on every redirect hop, and reads at most 150 KB. It
   resumes where it stopped; `--retry-failed` retries timeouts and 429/5xx.
2. Fetched descriptions replace the placeholder text unless an editor changed it.
3. `classify_resources` packs 40 fetched pages per call to the local `agy` CLI
   (default model "Gemini 3.8 Flash (Low)") and stores `llm_relevant`, `llm_category`
   and a short reason. `--second-opinion` re-checks the "not relevant" rows with a
   lenient prompt so a link stays hidden only when both passes agree. Pages that could
   not be fetched are never reviewed. Page text is untrusted: it is JSON-encoded,
   control characters are stripped, the model is told to ignore instructions in it, and
   the call runs sandboxed with no tools.

On the site, a link judged relevant is listed under the reviewed topic (marked ✦ when it
differs from the keyword topic); links judged not relevant are hidden by default and shown
under "Show N filtered out". Ranking is unchanged.

## Snapshot bootstrap

The worker's request budget cannot rebuild a reviewed index quickly, so
`hackerstack/data/snapshot.jsonl.gz` carries resources, evidence and backfill coverage.
`load_snapshot` runs once per snapshot file (marker `snapshot:<size>`), creates missing
rows only, fills still-empty review fields on existing rows, never overwrites editor
changes, rolls back on a bad file, and re-ranks. Refresh it with
`python manage.py export_snapshot` after more fetching or reviewing, then commit.

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
