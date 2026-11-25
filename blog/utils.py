"""Utility functions for the blog app."""

from functools import lru_cache

import bleach
import markdown
from bleach.css_sanitizer import CSSSanitizer

# Pagination constants
POSTS_PER_PAGE = 10
TILS_PER_PAGE = 20
BOOKMARKS_PER_PAGE = 20
FEED_PER_PAGE = 20

# Allowed HTML tags for sanitized markdown output
ALLOWED_TAGS = [
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "a",
    "strong",
    "em",
    "code",
    "pre",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "div",
    "span",
    "img",
    "sup",
    "sub",
    "del",
    "ins",
    "details",
    "summary",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class", "style"],
    "pre": ["class", "style"],
    "blockquote": ["class"],
    "div": ["class", "style"],
    "details": ["open"],
    "span": ["class", "style"],
    "th": ["align"],
    "td": ["align"],
}

_MARKDOWN_EXTENSIONS = [
    "extra",
    "toc",
    "pymdownx.highlight",
    "pymdownx.superfences",
]

_MARKDOWN_EXTENSION_CONFIGS = {
    "pymdownx.highlight": {
        "css_class": "codehilite",
        "use_pygments": True,
        "guess_lang": True,
        "noclasses": True,
        "pygments_style": "monokai",
    },
    "pymdownx.superfences": {},
}

_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color",
        "background",
        "background-color",
        "font-weight",
        "font-style",
        "line-height",
    ]
)

_BLEACH_CLEANER = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    css_sanitizer=_CSS_SANITIZER,
    strip=True,
)


@lru_cache(maxsize=512)
def _render_markdown_cached(content: str) -> str:
    html = markdown.markdown(
        content,
        extensions=_MARKDOWN_EXTENSIONS,
        extension_configs=_MARKDOWN_EXTENSION_CONFIGS,
    )
    return _BLEACH_CLEANER.clean(html)


def render_markdown(content: str) -> str:
    """Convert markdown content to sanitized HTML, cached by content string."""
    if not content:
        return ""
    return _render_markdown_cached(content)
