# Repository Guidelines — Rohan's Weblog

## Project Overview & Stack
Rohan Singh's weblog built with Django (`rohansweblog.com`).

- **Framework**: Django 5.0+
- **Database**: SQLite (development), PostgreSQL 16 (production, in Docker)
- **Markdown**: `python-markdown` with `pymdown-extensions`, `bleach`, `martor`, and syntax highlighting (`Pygments`)
- **Package Manager**: `uv`
- **Hosting**: Hostinger VPS (KVM 2, Ubuntu 24.04), Docker Compose

## Project Structure & Module Organization
This is a Django monorepo-style app.

- `blog/`: main app (`models.py`, `views.py`, `urls.py`, `admin.py`, `search.py`, `utils.py`, `product_updates.py`, `context_processors.py`, `templates/blog/`, `static/blog/`, and custom management commands in `management/commands/`).
- `rohans_weblog/`: project config (`settings.py`, root `urls.py`, `wsgi.py`, `asgi.py`).
- `.github/workflows/`: CI and deployment workflows.
- Operational files: `docker-compose.yml`, `Dockerfile`, `nginx*.conf`, `deploy*.sh`, `setup-ssl.sh`.
- Data and generated artifacts: `db.sqlite3`, `staticfiles/`.

### Models (`blog/models.py`)
- `Tag`: Reusable tags across content types.
- `BlogPost`: Full blog posts with markdown content, tags, and publish status (`is_published`).
- `TIL`: "Today I Learned" short markdown entries.
- `Bookmark`: Saved links with descriptions and optional `via_url`.
- `FeedItem`: Microblog/tumblelog entries (`link`, `note`, `code`).
- `ProductUpdate`: Normalized store for external product updates (`github` releases and `gumroad` products), optionally mirrored to `FeedItem`.

### URLs (`blog/urls.py`)
- `/` — Feed listing (`feed_list`)
- `/posts/` and `/posts/<slug>/` — Blog posts listing and detail
- `/til/` and `/til/<slug>/` — TIL listing and detail
- `/feed/<slug>/` — Individual feed item detail
- `/products/` — Product updates listing
- `/tags/<slug>/` — Content filtered by tag
- `/search/` — Full-text search
- `/about/` — About page
- `/webhooks/github/` and `/webhooks/gumroad/` — Incoming webhooks
- `/admin/` — Django admin interface

## Build, Test, and Development Commands
Use `uv` for local development.

- `uv sync --extra dev`: install runtime + dev dependencies.
- `uv run python manage.py migrate`: apply database migrations.
- `uv run python manage.py makemigrations`: create new migrations after model changes.
- `uv run python manage.py runserver`: start local server at `127.0.0.1:8000`.
- `uv run python manage.py collectstatic --noinput`: collect static files.
- `uv run python manage.py check --deploy`: run Django deployment checks.
- `uv run black --check --diff .`: enforce formatting (matches CI).
- `uv run python manage.py import_posts` / `import_tils`: import markdown posts/TILs.
- `uv run python manage.py sync_gumroad_products`: sync Gumroad product updates.
- `./build.sh`: production-style build step (`pip install`, `collectstatic`, `migrate`).

## Hosting & Production Details
- **Production domain**: `rohansweblog.com` (DNS on Cloudflare)
- **Server**: `srv1351809.hstgr.cloud` (`187.77.7.177`)
- **Project dir on server**: `/opt/rohans-weblog`
- **SSH**: `ssh -p 1026 rohan@srv1351809.hstgr.cloud` (port 22 is blocked by ufw; ufw allows only 80, 443, 1026). `rohan` has sudo with a password; no passwordless sudo.
- **Legacy**: `ygivenx.com` is an old WordPress site on Bluehost (`50.87.182.95`, `ns1/ns2.bluehost.com`). It is not this app.

### Production Stack (`docker-compose.yml`)
- `web`: Django + gunicorn (runs `migrate` and `collectstatic` on start)
- `nginx`: `nginx:alpine`, terminates TLS on 80/443, config at `/opt/rohans-weblog/nginx.conf`
- `db`: `postgres:16-alpine`
- `certbot`: loops `certbot renew` every 12h

### SSL (Let's Encrypt)
- Cert uses the **webroot** method (`/var/www/certbot`); `standalone` fails because nginx holds port 80.
- `nginx` reads the cert only at startup, so it must be reloaded after a renewal. The `nginx` service command in `docker-compose.yml` reloads it every 6h. `certbot` has `restart: unless-stopped` so it survives container restarts.
- Manual renewal (from `/opt/rohans-weblog`):
  ```bash
  sudo docker compose run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    --cert-name rohansweblog.com -d rohansweblog.com -d www.rohansweblog.com --non-interactive
  sudo docker compose exec nginx nginx -t && sudo docker compose exec nginx nginx -s reload
  ```
- **Environment Variables (Production)**:
  ```bash
  DJANGO_SECRET_KEY=your-secret-key-here
  DJANGO_DEBUG=False
  DJANGO_ALLOWED_HOSTS=rohansweblog.com,www.rohansweblog.com
  ```

## Coding Style & Naming Conventions
- Python: 4-space indentation, PEP 8, and Black formatting.
- Naming: `snake_case` for functions/variables, `PascalCase` for Django models/classes.
- Keep app logic inside `blog/`; project-wide wiring belongs in `rohans_weblog/`.
- Do not hand-edit pinned dependency entries in `requirements.txt`; regenerate from `pyproject.toml` via `uv` tooling.

## Testing Guidelines
- Frameworks: Django test runner and `pytest`/`pytest-django` are available.
- Place tests near app code (for example, `blog/tests.py` or `blog/tests/test_models.py`).
- Name tests `test_*` and prefer behavior-focused names like `test_feed_item_slug_uniqueness`.
- Run tests with `uv run python manage.py test` (and/or `uv run pytest`).

## Commit & Pull Request Guidelines
- Commit messages in history are short, imperative, and concise (examples: `fix ssl`, `add tags usage`).
- Prefer one logical change per commit and include context in the body when touching infra or deploy scripts.
- PRs should include: what changed, why, verification steps/commands, and screenshots for template/UI changes.
- Ensure CI-relevant checks pass locally (`black`, migrations, `check --deploy`) before opening or merging.
