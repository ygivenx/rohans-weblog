import re

from django.db import connection
from django.db.models import Case, IntegerField, Value, When
from django.db.models.expressions import RawSQL


def search(resources, query):
    # Tokenize to prevent raw search operators from becoming executable syntax.
    tokens = re.findall(r"\w+", query.lower(), flags=re.UNICODE)[:12]
    if not tokens:
        return resources.none() if query.strip() else resources
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchVector

        resources = resources.annotate(
            vector=SearchVector("search_text", config="simple")
        )
        resources = resources.filter(
            vector=SearchQuery(" ".join(tokens), config="simple")
        )
    else:
        expression = " AND ".join('"' + t + '"' for t in tokens)
        resources = resources.filter(
            pk__in=RawSQL(
                "SELECT rowid FROM hackerstack_fts WHERE hackerstack_fts MATCH %s",
                [expression],
            )
        )
    return resources.annotate(
        title_match=Case(
            When(title__icontains=query, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    )
