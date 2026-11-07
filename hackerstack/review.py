"""Page review shared by the local agy command and the production Anthropic command."""

import json
import os

from django.core.management.base import CommandError
from django.utils import timezone

from . import jev
from .ranking import HALF_LIVES
from .management.commands.classify_resources import (
    CATEGORY_KEYS,
    SCHEMA,
    SECOND_OPINION_TAG,
    clean,
)

MODEL = "claude-haiku-5-5"


class ReviewUnavailable(CommandError):
    """The reviewer is not configured (no API key). The daily job treats this as a skip."""


def apply_verdict(resource, item, model_label, second_opinion=False):
    """Validate one model verdict and save it. Returns True when it was stored."""
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("relevant"), bool)
        or item.get("best_category") not in CATEGORY_KEYS
    ):
        return False
    resource.llm_relevant = item["relevant"]
    resource.llm_category = item["best_category"]
    resource.llm_reason = clean(str(item.get("reason", "")), 200)
    resource.llm_model = model_label[:40] + (
        SECOND_OPINION_TAG if second_opinion else ""
    )
    resource.llm_classified_at = timezone.now()
    resource.save(
        update_fields=[
            "llm_relevant",
            "llm_category",
            "llm_reason",
            "llm_model",
            "llm_classified_at",
        ]
    )
    return True


def require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ReviewUnavailable("ANTHROPIC_API_KEY is not set")


def make_client():
    import anthropic  # imported lazily so the web process never needs it

    return anthropic.Anthropic(max_retries=2, timeout=120.0)


def review_batch(client, prompt):
    """One Messages API call with a schema-constrained reply. Returns (results, usage)."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"model stopped with {response.stop_reason}")
    # Haiku 5.5 may emit thinking blocks first: read the text block by type, not position.
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ValueError("no text block in response")
    results = json.loads(text)["results"]
    usage = dict(
        input_tokens=getattr(response.usage, "input_tokens", 0),
        output_tokens=getattr(response.usage, "output_tokens", 0),
    )
    return results, usage


# Jev returns probabilities, so decisions use thresholds (tuned on a labelled sample, see README).
HIDE_BELOW = 0.30  # P(on-topic) under this: confidently off-topic, hidden by default
RELEVANT_AT = 0.50  # at or above: on-topic, eligible for a refined topic
TOPIC_MIN_CONFIDENCE = 0.50  # below this the keyword topic is kept
KIND_MIN_CONFIDENCE = 0.60  # below this the existing kind is kept


def resolve_provider(requested="auto"):
    """Pick the reviewer from the environment: Jev first, then Anthropic."""
    has_jev = bool(jev.api_key())
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if requested == "jev":
        if not has_jev:
            raise ReviewUnavailable("JEV_API_KEY is not set")
        return "jev"
    if requested == "anthropic":
        require_api_key()
        return "anthropic"
    if has_jev:
        return "jev"
    if has_anthropic:
        return "anthropic"
    raise ReviewUnavailable("neither JEV_API_KEY nor ANTHROPIC_API_KEY is set")


def decide(verdict):
    """Pure decision rule: what to store for a Jev verdict. Unit-tested without any model."""
    if verdict.relevance < HIDE_BELOW:
        relevant = False
    elif verdict.relevance >= RELEVANT_AT:
        relevant = True
    else:
        relevant = None  # uncertain: stays visible with its keyword topic
    topic = (
        verdict.topic
        if relevant and verdict.topic_confidence >= TOPIC_MIN_CONFIDENCE
        else ""
    )
    kind = verdict.kind if verdict.kind_confidence >= KIND_MIN_CONFIDENCE else ""
    return relevant, topic, kind


def apply_jev_verdict(resource, verdict, model=jev.MODEL):
    relevant, topic, kind = decide(verdict)
    resource.llm_relevant = relevant
    resource.llm_category = topic
    resource.llm_score = verdict.relevance
    resource.llm_topic_confidence = verdict.topic_confidence
    resource.llm_reason = f"{verdict.relevance:.0%} likely on-topic"
    resource.llm_model = model[:60]
    resource.llm_classified_at = timezone.now()
    fields = [
        "llm_relevant",
        "llm_category",
        "llm_score",
        "llm_topic_confidence",
        "llm_reason",
        "llm_model",
        "llm_classified_at",
    ]
    if kind and kind != resource.kind and not resource.curated:
        old = resource.kind
        resource.kind = kind
        fields.append("kind")
        # Follow the new kind's freshness half-life unless an editor tuned it by hand.
        if resource.half_life_days == HALF_LIVES.get(old):
            resource.half_life_days = HALF_LIVES[kind]
            fields.append("half_life_days")
    resource.save(update_fields=fields)
