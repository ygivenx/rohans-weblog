"""Utility functions for the blog app."""

import markdown
import bleach
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
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class", "style"],
    "pre": ["class", "style"],
    "div": ["class", "style"],
    "span": ["class", "style"],
    "th": ["align"],
    "td": ["align"],
}


def render_markdown(content: str) -> str:
    """
    Convert markdown content to sanitized HTML.

    Uses bleach to sanitize output and prevent XSS attacks.
    """
    if not content:
        return ""

    html = markdown.markdown(
        content,
        extensions=[
            "extra",
            "toc",
            "pymdownx.highlight",
            "pymdownx.superfences",
        ],
        extension_configs={
            "pymdownx.highlight": {
                "css_class": "codehilite",
                "use_pygments": True,
                "guess_lang": True,
                "noclasses": True,
                "pygments_style": "monokai",
            },
            "pymdownx.superfences": {},
        },
    )

    css_sanitizer = CSSSanitizer(
        allowed_css_properties=[
            "color",
            "background",
            "background-color",
            "font-weight",
            "font-style",
            "line-height",
        ]
    )

    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        css_sanitizer=css_sanitizer,
        strip=True,
    )
