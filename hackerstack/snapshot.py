"""Portable, idempotent snapshot of the index (resources, evidence, backfill coverage).

The production worker cannot rebuild 20k reviewed resources in a reasonable time under its
request budget, so a snapshot is committed and loaded once. Loading never overwrites rows
that already exist except to fill page-review fields that are still empty.
"""

import gzip
import json
from datetime import date, datetime

from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from .ingestion import PLACEHOLDER_DESCRIPTION
from .jev import MODEL_PREFIX
from .models import BackfillWindow, Evidence, Resource
from .ranking import HALF_LIVES

RESOURCE_FIELDS = [
    "url",
    "title",
    "description",
    "category",
    "kind",
    "keywords",
    "curated",
    "content_date",
    "date_basis",
    "half_life_days",
    "provenance",
    "is_active",
    "search_text",
    "page_title",
    "page_h1",
    "page_description",
    "fetch_status",
    "fetched_at",
    "llm_relevant",
    "llm_category",
    "llm_reason",
    "llm_model",
    "llm_classified_at",
    "llm_score",
    "llm_topic_confidence",
]
# A Jev verdict replaces none/older-model verdicts on existing rows (Jev is the primary reviewer).
LLM_FIELDS = [
    "llm_relevant",
    "llm_category",
    "llm_reason",
    "llm_model",
    "llm_classified_at",
    "llm_score",
    "llm_topic_confidence",
]
FILL_FIELDS = [
    "page_title",
    "page_h1",
    "page_description",
    "fetch_status",
    "fetched_at",
    "llm_relevant",
    "llm_category",
    "llm_reason",
    "llm_model",
    "llm_classified_at",
]
EVIDENCE_FIELDS = [
    "source",
    "source_id",
    "thread_id",
    "discussion_url",
    "title",
    "points",
    "comments",
    "published_at",
    "kind",
]
WINDOW_FIELDS = [
    "query",
    "category",
    "start",
    "end",
    "page",
    "expected_hits",
    "indexed_hits",
    "status",
    "note",
]
DATE_FIELDS = {"content_date"}
DATETIME_FIELDS = {"fetched_at", "llm_classified_at", "published_at"}
CHUNK = 500


def _encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _decode(record):
    for key in DATE_FIELDS & record.keys():
        record[key] = parse_date(record[key]) if record[key] else None
    for key in DATETIME_FIELDS & record.keys():
        record[key] = parse_datetime(record[key]) if record[key] else None
    return record


def export_snapshot(path):
    counts = dict(resource=0, evidence=0, window=0)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as out:

        def write(kind, record):
            out.write(
                json.dumps(
                    dict(t=kind, **record), ensure_ascii=False, separators=(",", ":")
                )
                + "\n"
            )
            counts[kind] += 1

        for r in Resource.objects.order_by("pk").iterator(chunk_size=1000):
            write("resource", {f: _encode(getattr(r, f)) for f in RESOURCE_FIELDS})
        for e in (
            Evidence.objects.select_related("resource")
            .order_by("pk")
            .iterator(chunk_size=1000)
        ):
            write(
                "evidence",
                dict(
                    url=e.resource.url,
                    **{f: _encode(getattr(e, f)) for f in EVIDENCE_FIELDS},
                ),
            )
        for w in BackfillWindow.objects.order_by("pk").iterator(chunk_size=1000):
            write("window", {f: getattr(w, f) for f in WINDOW_FIELDS})
    return counts


def _flush_resources(chunk, stats):
    existing = {
        r.url: r for r in Resource.objects.filter(url__in=[c["url"] for c in chunk])
    }
    new = [Resource(**c) for c in chunk if c["url"] not in existing]
    Resource.objects.bulk_create(new, ignore_conflicts=True)
    stats["resources_created"] += len(new)
    for c in chunk:
        obj = existing.get(c["url"])
        if obj is None:
            continue
        changed = []
        # Decide before the fill-empty pass below, which would copy llm_model onto an unreviewed
        # row and make this look like "already Jev-reviewed".
        take_jev = (c.get("llm_model") or "").startswith(
            MODEL_PREFIX
        ) and not obj.llm_model.startswith(MODEL_PREFIX)
        for field in FILL_FIELDS:
            empty = (
                getattr(obj, field) is None
                if field == "llm_relevant"
                else not getattr(obj, field)
            )
            if empty and c[field] not in (None, ""):
                setattr(obj, field, c[field])
                changed.append(field)
        if take_jev:
            for field in LLM_FIELDS:
                setattr(obj, field, c[field])
            changed.extend(f for f in LLM_FIELDS if f not in changed)
            if c["kind"] != obj.kind and not obj.curated:
                old_kind = obj.kind
                obj.kind = c["kind"]
                changed.append("kind")
                if obj.half_life_days == HALF_LIVES.get(old_kind):  # not hand-tuned
                    obj.half_life_days = c["half_life_days"]
                    changed.append("half_life_days")
        # A fetched page description replaces the placeholder, but never an editor's text.
        incoming = c["description"]
        if (
            obj.description == PLACEHOLDER_DESCRIPTION
            and incoming
            and incoming != PLACEHOLDER_DESCRIPTION
        ):
            obj.description = incoming
            changed.append("description")
        if changed:
            obj.save(update_fields=changed)  # save() also refreshes search_text
            stats["resources_filled"] += 1


def _flush_evidence(chunk, stats):
    ids = dict(
        Resource.objects.filter(url__in={c["url"] for c in chunk}).values_list(
            "url", "id"
        )
    )
    rows = [
        Evidence(resource_id=ids[c.pop("url")], **c) for c in chunk if c["url"] in ids
    ]
    Evidence.objects.bulk_create(rows, ignore_conflicts=True)
    stats["evidence_seen"] += len(rows)


def load_snapshot(path):
    stats = dict(
        resources_created=0, resources_filled=0, evidence_seen=0, windows_seen=0
    )
    buffers = dict(resource=[], evidence=[], window=[])
    flushers = dict(resource=_flush_resources, evidence=_flush_evidence)

    def flush(kind):
        chunk, buffers[kind] = buffers[kind], []
        if not chunk:
            return
        if kind == "window":
            BackfillWindow.objects.bulk_create(
                [BackfillWindow(**c) for c in chunk], ignore_conflicts=True
            )
            stats["windows_seen"] += len(chunk)
        else:
            flushers[kind](chunk, stats)

    with transaction.atomic():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                record = json.loads(line)
                kind = record.pop("t")
                if kind not in buffers:
                    raise ValueError(f"Unknown snapshot record type: {kind}")
                if kind != "resource":
                    # Evidence needs every resource row present, including the last partial chunk.
                    flush("resource")
                buffers[kind].append(_decode(record))
                if len(buffers[kind]) >= CHUNK:
                    flush(kind)
        for kind in (
            "resource",
            "evidence",
            "window",
        ):  # resources must exist before evidence
            flush(kind)
    return stats
