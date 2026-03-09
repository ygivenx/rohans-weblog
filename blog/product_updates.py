import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import FeedItem, ProductUpdate, Tag


def verify_github_signature(raw_body, signature_header, secret):
    """Verify GitHub webhook HMAC signature."""
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def _parse_iso_datetime(value):
    if not value:
        return timezone.now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return timezone.now()


def _github_release_summary(payload):
    body = (payload.get("release") or {}).get("body") or ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[:8])


def _gumroad_summary(product):
    description = product.get("description") or ""
    if not description:
        return ""
    cleaned = " ".join(description.split())
    return cleaned[:280] + ("..." if len(cleaned) > 280 else "")


def _format_gumroad_price(product):
    # Gumroad API can return integer cents or formatted strings.
    if product.get("formatted_price"):
        return str(product["formatted_price"])

    price_cents = product.get("price")
    currency = (product.get("currency") or "USD").upper()
    if isinstance(price_cents, int):
        return f"{currency} {price_cents / 100:.2f}"
    if isinstance(price_cents, str) and price_cents.isdigit():
        return f"{currency} {int(price_cents) / 100:.2f}"
    return ""


def _tags_for_update(update):
    base = ["product"]
    if update.source == "github":
        base += ["github", "release"]
        if update.repo:
            base.append(update.repo.replace("_", "-").replace(" ", "-").lower())
    else:
        base += ["gumroad"]
    return base


def _feed_payload(update):
    if update.source == "github":
        title = update.display_title
        body_lines = [
            f"**{update.title}**",
            "",
        ]
        if update.summary:
            body_lines.append(update.summary)
            body_lines.append("")
        body_lines.append("Type: `release`")
        if update.version:
            body_lines.append(f"Version: `{update.version}`")
        if update.owner and update.repo:
            body_lines.append(f"Repo: `{update.owner}/{update.repo}`")
        return {
            "title": title,
            "body": "\n".join(body_lines),
            "url": update.url,
        }

    body_lines = []
    if update.summary:
        body_lines.append(update.summary)
        body_lines.append("")
    if update.price:
        body_lines.append(f"Price: **{update.price}**")
    body_lines.append("[Buy now](%s)" % update.url)
    return {
        "title": update.title,
        "body": "\n".join(body_lines),
        "url": update.url,
    }


def mirror_product_update_to_feed(update):
    """Create or update mirrored feed item for a product update."""
    if not getattr(settings, "PRODUCTS_FEED_MIRROR", True):
        return None

    payload = _feed_payload(update)

    if update.mirrored_feed_item_id:
        item = update.mirrored_feed_item
        item.content_type = "link"
        item.title = payload["title"]
        item.body = payload["body"]
        item.url = payload["url"]
        item.save()
    else:
        item = FeedItem.objects.create(
            content_type="link",
            title=payload["title"],
            body=payload["body"],
            url=payload["url"],
        )
        update.mirrored_feed_item = item
        update.save(update_fields=["mirrored_feed_item", "updated_date"])

    tags = []
    for tag_name in _tags_for_update(update):
        tag, _ = Tag.objects.get_or_create(name=tag_name)
        tags.append(tag)
    item.tags.set(tags)
    return item


@transaction.atomic
def upsert_github_release(payload):
    """Normalize GitHub release payload into ProductUpdate."""
    repo_data = payload.get("repository") or {}
    release = payload.get("release") or {}
    owner = (repo_data.get("owner") or {}).get("login", "")
    repo = repo_data.get("name", "")
    version = release.get("tag_name") or release.get("name") or ""
    release_id = release.get("id")

    if not release_id:
        return None, False

    obj, created = ProductUpdate.objects.update_or_create(
        source="github",
        external_id=str(release_id),
        defaults={
            "kind": "release",
            "title": release.get("name") or f"{repo} {version}".strip(),
            "summary": _github_release_summary(payload),
            "url": release.get("html_url") or repo_data.get("html_url") or "",
            "owner": owner,
            "repo": repo,
            "version": version,
            "raw_payload": payload,
            "published_at": _parse_iso_datetime(release.get("published_at")),
            "is_visible": True,
        },
    )

    mirror_product_update_to_feed(obj)
    return obj, created


def _fetch_gumroad_products(access_token):
    params = urlencode({"access_token": access_token})
    url = f"https://api.gumroad.com/v2/products?{params}"
    req = Request(url, headers={"User-Agent": "rohans-weblog/1.0"})
    with urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("products") or []


@transaction.atomic
def sync_gumroad_products():
    """Sync listed Gumroad products into ProductUpdate records."""
    token = getattr(settings, "GUMROAD_ACCESS_TOKEN", "")
    if not token:
        return {"created": 0, "updated": 0, "total": 0}

    products = _fetch_gumroad_products(token)
    created_count = 0
    updated_count = 0

    for product in products:
        external_id = str(
            product.get("id")
            or product.get("short_product_id")
            or product.get("permalink")
            or product.get("name")
        )
        url = product.get("short_url") or product.get("url") or ""

        obj, created = ProductUpdate.objects.update_or_create(
            source="gumroad",
            external_id=external_id,
            defaults={
                "kind": "product",
                "title": product.get("name") or "Gumroad Product",
                "summary": _gumroad_summary(product),
                "url": url,
                "price": _format_gumroad_price(product),
                "currency": (product.get("currency") or "").upper(),
                "product_slug": product.get("permalink") or "",
                "raw_payload": product,
                "published_at": _parse_iso_datetime(product.get("published_at")),
                "is_visible": bool(product.get("published", True)),
            },
        )

        mirror_product_update_to_feed(obj)
        if created:
            created_count += 1
        else:
            updated_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "total": len(products),
    }
