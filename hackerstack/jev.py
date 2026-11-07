"""Jev (TypeSafe AI "System One") client: returns probabilities, not prose.

One request per page. The page text is the `state`; three questions are evaluated in parallel
against it: how likely the link is on-topic (noul), which topic fits best (choice), and what
kind of resource it is (choice). Standard library only. The API key is read from the
environment (JEV_API_KEY) and is never logged or included in error text.

Docs: https://docs.typesafe.ai/api/system-one
"""

import json
import os
import random
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import CATEGORIES, KINDS

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# A pinned version: thresholds are tuned against it, and `jev-latest` moves with releases.
MODEL = "jev-1.14.0"
MODEL_PREFIX = "jev-"
MAX_ATTEMPTS = 5

TOPIC_CRITERIA = {
    "agents": "AI agents, coding agents, agent harnesses, tool use, MCP, orchestration, context engineering",
    "llms": "Language model foundations: architectures, transformers, pretraining, model releases and capabilities",
    "rl": "Reinforcement learning, RLHF, post-training, reward models, alignment training methods",
    "evals": "Evaluation, benchmarks, and testing of models or software quality",
    "retrieval": "Search, retrieval-augmented generation, embeddings, vector databases, memory for LLMs",
    "inference": "Inference and serving, GPUs and hardware, quantization, performance, local models, ML compilers",
    "data": "Training data, datasets, synthetic data, fine-tuning, data engineering for ML",
    "production": "Production engineering: deploying, observability, infrastructure, reliability, MLOps",
    "safety": "Interpretability, AI safety, security, vulnerabilities, adversarial attacks, prompt injection",
    "multimodal": "Vision, audio, video, image generation, speech, and robotics",
    "research": "Research papers, scientific discovery, surveys, and general AI research",
    "engineering": "General software engineering craft: programming languages, compilers, operating systems, databases, distributed systems, practices, essays",
}
KIND_CRITERIA = {
    "tool": "A software tool, library, framework, app or open-source project that people can use",
    "paper": "A research paper or preprint",
    "course": "A course, book, tutorial series, lecture or other learning resource",
    "documentation": "Reference documentation, a specification, or a manual",
    "article": "A blog post, essay, or technical write-up",
    "news": "A news report or announcement about recent events",
    "website": "A general website, homepage, directory or collection of links",
}
assert set(TOPIC_CRITERIA) == {k for k, _ in CATEGORIES}
assert set(KIND_CRITERIA) == {k for k, _ in KINDS}

QUESTIONS = {
    "relevant": {
        "type": "noul",
        "instructions": (
            "Is this link substantively about artificial intelligence or software engineering, for "
            "example a tool, library, paper, tutorial or course, technical write-up, model or product "
            "release, or an essay about building software? Mainstream news, politics, privacy or "
            "legal stories, finance, and consumer-product news that merely mention a word like "
            "'database' or 'agent' are not."
        ),
        "criteria": {
            "true": "The link itself is about AI or software engineering.",
            "false": "The link is not about AI or software engineering.",
        },
    },
    "topic": {
        "type": "choice",
        "instructions": "Which single topic best describes what this link is about?",
        "criteria": TOPIC_CRITERIA,
    },
    "kind": {
        "type": "choice",
        "instructions": "What kind of resource is this link?",
        "criteria": KIND_CRITERIA,
    },
}


class JevError(Exception):
    """A request failed in a way that retrying will not fix (bad request, parse failure)."""


class JevAuthError(JevError):
    """The key is missing, invalid or lacks access. Stop instead of retrying every page."""


@dataclass(frozen=True)
class Verdict:
    relevance: float  # P(on-topic), 0-1
    topic: str
    topic_confidence: float
    kind: str
    kind_confidence: float
    input_tokens: int


def api_key():
    return os.environ.get("JEV_API_KEY", "").strip()


def page_state(resource):
    """The text Jev judges. Titles and descriptions come from the open web: they are data only."""
    return {
        "hn_title": (resource.title or "")[:200],
        "page_title": (resource.page_title or "")[:200],
        "heading": (resource.page_h1 or "")[:150],
        "description": (resource.page_description or "")[:400],
        "site": resource.url.split("/")[2][:60] if resource.url.count("/") >= 2 else "",
    }


def parse_answers(body):
    """Validate a response strictly: every number in range, every choice a known key."""
    try:
        answers = body["answers"]
        relevance = float(answers["relevant"]["noul"])
        topic, kind = answers["topic"], answers["kind"]
        verdict = Verdict(
            relevance=relevance,
            topic=topic["choice"],
            topic_confidence=float(topic["confidence"]),
            kind=kind["choice"],
            kind_confidence=float(kind["confidence"]),
            input_tokens=int((body.get("usage") or {}).get("input_tokens", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise JevError(f"unexpected response shape ({type(exc).__name__})") from None
    for value in (verdict.relevance, verdict.topic_confidence, verdict.kind_confidence):
        if not 0.0 <= value <= 1.0:
            raise JevError("probability outside 0-1")
    if verdict.topic not in TOPIC_CRITERIA or verdict.kind not in KIND_CRITERIA:
        raise JevError("choice is not one of the offered options")
    return verdict


def post(payload, key, timeout=30, sleep=time.sleep):
    """POST with exponential backoff on 429/529/5xx and network errors. Returns parsed JSON."""
    data = json.dumps(payload).encode()
    for attempt in range(MAX_ATTEMPTS):
        request = Request(
            ENDPOINT,
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "HackerStack/1.0 (+https://rohansweblog.com/hackerstack/)",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read(1_000_001)[:1_000_000])
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise JevAuthError(f"API key rejected (HTTP {exc.code})") from None
            if exc.code in (429, 529) or exc.code >= 500:
                try:
                    wait = float(exc.headers.get("Retry-After", ""))
                except ValueError:
                    wait = 2.0**attempt
                if attempt == MAX_ATTEMPTS - 1:
                    raise JevError(f"gave up after HTTP {exc.code}") from None
                sleep(min(60.0, wait) + random.random())
                continue
            raise JevError(f"request rejected (HTTP {exc.code})") from None
        except (URLError, TimeoutError, OSError):
            if attempt == MAX_ATTEMPTS - 1:
                raise JevError("network error") from None
            sleep(2.0**attempt + random.random())
        except ValueError:
            raise JevError("response was not JSON") from None
    raise JevError("unreachable")  # pragma: no cover


def review(resource, key, model=MODEL, **kwargs):
    body = post(
        {"model": model, "state": page_state(resource), "questions": QUESTIONS},
        key,
        **kwargs,
    )
    return parse_answers(body)
