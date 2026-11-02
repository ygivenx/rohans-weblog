# Rohan's Weblog

## Project Overview
Rohan Singh's weblog built with Django.

## Stack
- **Framework**: Django 5.0+
- **Database**: SQLite (development), PostgreSQL 16 (production, in Docker)
- **Markdown**: python-markdown with syntax highlighting (Pygments)
- **Package Manager**: uv
- **Hosting**: Hostinger VPS (KVM 2, Ubuntu 24.04), Docker Compose

## Hosting Details
- **Production domain**: rohansweblog.com (DNS on Cloudflare)
- **Server**: srv1351809.hstgr.cloud (187.77.7.177)
- **Project dir on server**: /opt/rohans-weblog
- **SSH**: `ssh -p 1026 rohan@srv1351809.hstgr.cloud` (port 22 is blocked by ufw; ufw allows only 80, 443, 1026). `rohan` has sudo with a password; no passwordless sudo.
- **Legacy**: ygivenx.com is still an old WordPress site on Bluehost (50.87.182.95, ns1/ns2.bluehost.com). It is not this app.

## Production Stack (docker-compose.yml)
- `web`: Django + gunicorn (runs migrate and collectstatic on start)
- `nginx`: nginx:alpine, terminates TLS on 80/443, config at `/opt/rohans-weblog/nginx.conf`
- `db`: postgres:16-alpine
- `certbot`: loops `certbot renew` every 12h

## SSL (Let's Encrypt)
- Cert uses the **webroot** method (`/var/www/certbot`); `standalone` fails because nginx holds port 80.
- nginx reads the cert only at startup, so it must be reloaded after a renewal. The nginx service command in docker-compose.yml reloads it every 6h. certbot has `restart: unless-stopped` so it survives container restarts.
- Manual renewal (from /opt/rohans-weblog):
  ```bash
  sudo docker compose run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    --cert-name rohansweblog.com -d rohansweblog.com -d www.rohansweblog.com --non-interactive
  sudo docker compose exec nginx nginx -t && sudo docker compose exec nginx nginx -s reload
  ```
- History: the cert expired May 13, 2026 because the certbot container wasn't running and the renewal config used `standalone`. Fixed Oct 8, 2026; next expiry Jan 6, 2027. On Oct 24, 2026 certbot was found stopped again (it had no restart policy); fixed in 9ce077c.

## Directory Structure
```
blog/
  models.py        # BlogPost, TIL, Bookmark, Tag models
  views.py         # View functions for all pages
  urls.py          # URL routing
  admin.py         # Django admin configuration
  search.py        # Full-text search functionality
  utils.py         # Markdown rendering utility
  templates/blog/  # HTML templates
  management/      # Import commands

rohans_weblog/
  settings.py      # Django settings
  urls.py          # Root URL configuration

content/posts/     # Markdown source files (legacy Hugo)
static/            # Static assets (CSS, images)
```

## Models
- **BlogPost**: Blog posts with markdown, tags, publish status
- **TIL**: Today I Learned short entries
- **Bookmark**: Saved links with descriptions
- **Tag**: Reusable tags for all content types

## Workflow
```bash
# Install dependencies
uv sync

# Run development server
uv run python manage.py runserver

# Import markdown posts from content/posts/
uv run python manage.py import_posts

# Create migrations after model changes
uv run python manage.py makemigrations
uv run python manage.py migrate

# Create admin user
uv run python manage.py createsuperuser

# Deploy
./deploy.sh
```

## Environment Variables (Production)
```bash
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=rohansweblog.com,www.rohansweblog.com
```

## URLs
- `/` - Blog post listing
- `/posts/<slug>/` - Single blog post
- `/til/` - TIL entries
- `/til/<slug>/` - Single TIL
- `/search/` - Full-text search
- `/admin/` - Django admin interface
