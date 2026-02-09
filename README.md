# Rohan Singh's Weblog

A Django-based personal blog with support for blog posts, TIL entries, bookmarks, and LaTeX math rendering.

## Features

- Blog posts with markdown support
- Today I Learned (TIL) entries
- Bookmarks
- Full-text search
- LaTeX math rendering with MathJax
- Syntax highlighting for code blocks
- Tag system
- RSS feeds (coming soon)

## Local Development

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd rohans-weblog
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Run migrations:
   ```bash
   uv run python manage.py migrate
   ```

4. Create a superuser:
   ```bash
   uv run python manage.py createsuperuser
   ```

5. Import existing posts (optional):
   ```bash
   uv run python manage.py import_posts
   ```

6. Run the development server:
   ```bash
   uv run python manage.py runserver
   ```

7. Visit `http://127.0.0.1:8000/` in your browser.

## Deployment to Hostinger

This project is ready to deploy on a Hostinger VPS using Gunicorn + Nginx.

### Quick Steps

1. Provision a Hostinger VPS and point your domain DNS to the server.
2. Install system dependencies (`python3`, `python3-venv`, `nginx`, `git`).
3. Clone this repository on the server.
4. Set production environment variables.
5. Run migrations and collect static files.
6. Configure a `systemd` service for Gunicorn.
7. Configure Nginx reverse proxy and enable HTTPS.

For complete, copy-paste instructions, see [`HOSTINGER_SETUP.md`](HOSTINGER_SETUP.md).

## Project Structure

```
rohans-weblog/
├── blog/                    # Django app
│   ├── models.py           # BlogPost, TIL, Bookmark, Tag models
│   ├── views.py            # View functions
│   ├── urls.py             # URL routing
│   ├── admin.py            # Django admin configuration
│   ├── templates/          # HTML templates
│   ├── management/         # Custom management commands
│   └── utils.py            # Utility functions (markdown rendering)
├── rohans_weblog/         # Django project settings
│   ├── settings.py         # Django settings
│   ├── urls.py             # Root URL configuration
│   └── wsgi.py            # WSGI configuration
├── content/               # Source markdown files (for import)
├── static/                # Static files (images, CSS)
├── build.sh               # Build script for production-style setup
├── Procfile               # Optional process file (legacy)
└── pyproject.toml         # Python dependencies
```

## Management Commands

### Import Posts
```bash
uv run python manage.py import_posts
```

Options:
- `--update`: Update existing posts
- `--skip-existing`: Skip posts that already exist
- `--posts-dir`: Custom directory path (default: `content/posts`)

## Environment Variables

### Required for Production
- `DJANGO_SECRET_KEY`: Django secret key
- `DJANGO_ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `DATABASE_URL`: PostgreSQL connection string

### Optional
- `DJANGO_DEBUG`: Set to `False` in production (default: `True`)

## License

Personal project - All rights reserved.
