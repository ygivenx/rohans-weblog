from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


CATEGORIES = [
    ("agents", "Agents & harnesses"),
    ("llms", "LLM foundations"),
    ("rl", "RL & post-training"),
    ("evals", "Evaluation & testing"),
    ("retrieval", "Search & memory"),
    ("inference", "Inference & hardware"),
    ("data", "Data & fine-tuning"),
    ("production", "Production engineering"),
    ("safety", "Interpretability & security"),
    ("multimodal", "Multimodal & robotics"),
    ("research", "Research & discovery"),
    ("engineering", "Engineering perspectives"),
]
KINDS = [
    (v, v.title())
    for v in ("website", "article", "course", "documentation", "tool", "paper", "news")
]


class Resource(models.Model):
    url = models.URLField(max_length=2000, unique=True)
    title = models.CharField(max_length=400)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=30, choices=CATEGORIES, db_index=True)
    kind = models.CharField(
        max_length=20, choices=KINDS, default="article", db_index=True
    )
    keywords = models.TextField(blank=True)
    curated = models.BooleanField(default=False, db_index=True)
    # Content dates must be supplied by a source or editor, never a crawl timestamp.
    content_date = models.DateField(null=True, blank=True, db_index=True)
    date_basis = models.CharField(max_length=160, blank=True)
    half_life_days = models.PositiveIntegerField(
        default=365, validators=[MinValueValidator(1), MaxValueValidator(10000)]
    )
    provenance = models.URLField(max_length=2000, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)
    search_text = models.TextField(blank=True, editable=False)
    score = models.FloatField(default=0, db_index=True, editable=False)
    popularity = models.FloatField(default=0, editable=False)
    freshness = models.FloatField(default=0.5, editable=False)
    corroboration = models.FloatField(default=0, editable=False)
    evidence_count = models.PositiveIntegerField(default=0, editable=False)
    ranked_at = models.DateTimeField(null=True, editable=False)
    # Fetched from the page itself by fetch_pages (no LLM). Empty fetch_status = never tried.
    page_title = models.CharField(max_length=400, blank=True)
    page_h1 = models.CharField(max_length=400, blank=True)
    page_description = models.TextField(blank=True)
    fetch_status = models.CharField(max_length=30, blank=True, db_index=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    # Written by classify_resources from the fetched page text only. Null = not reviewed.
    llm_relevant = models.BooleanField(null=True, blank=True, db_index=True)
    llm_category = models.CharField(max_length=30, blank=True, choices=CATEGORIES)
    llm_reason = models.CharField(max_length=200, blank=True)
    llm_model = models.CharField(max_length=60, blank=True)
    llm_classified_at = models.DateTimeField(null=True, blank=True)

    @property
    def topic(self):
        """Topic shown on the site: the AI review's category only when it judged the link relevant."""
        if self.llm_relevant and self.llm_category:
            return self.llm_category
        return self.category

    @property
    def topic_label(self):
        return dict(CATEGORIES).get(self.topic, self.topic)

    @property
    def topic_changed_by_review(self):
        return self.topic != self.category

    def save(self, *args, **kwargs):
        self.search_text = " ".join(
            [
                self.title,
                self.description,
                self.url,
                self.keywords,
                self.page_title,
                self.page_h1,
                self.page_description,
                self.get_category_display(),
                self.kind,
            ]
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"search_text"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-score", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(half_life_days__gte=1), name="hs_positive_half_life"
            )
        ]


class Evidence(models.Model):
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="evidence"
    )
    source = models.CharField(
        max_length=20, choices=[("hn", "Hacker News"), ("lobsters", "Lobsters")]
    )
    source_id = models.CharField(max_length=100)
    thread_id = models.CharField(max_length=100)
    discussion_url = models.URLField(max_length=2000)
    title = models.CharField(max_length=400, blank=True)
    points = models.IntegerField(null=True, blank=True)
    comments = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField(auto_now=True)
    kind = models.CharField(
        max_length=20,
        default="submission",
        choices=[("submission", "Submission"), ("mention", "Comment mention")],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "source", "source_id"], name="hs_unique_evidence"
            )
        ]
        ordering = ["-points", "id"]


class CollectionRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    source = models.CharField(max_length=30, default="hn")
    requests = models.PositiveIntegerField(default=0)
    cache_hits = models.PositiveIntegerField(default=0)
    records = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="running")
    detail = models.TextField(blank=True)


class CollectionCursor(models.Model):
    key = models.CharField(max_length=200, unique=True)
    page = models.PositiveIntegerField(default=0)
    cycle = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class BackfillWindow(models.Model):
    query = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORIES)
    start = models.BigIntegerField()
    end = models.BigIntegerField()
    page = models.PositiveIntegerField(default=0)
    expected_hits = models.PositiveIntegerField(null=True)
    indexed_hits = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    note = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["query", "start", "end"], name="hs_unique_window"
            ),
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")), name="hs_window_range"
            ),
        ]
