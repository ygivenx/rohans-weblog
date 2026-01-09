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

## Deployment to Render

This project is configured for deployment on [Render](https://render.com).

### Setup on Render

1. **Create a new Web Service** on Render:
   - Connect your GitHub repository
   - Select the `render.yaml` file for configuration
   - Or manually configure:
     - **Build Command**: `./build.sh`
     - **Start Command**: `gunicorn rohans_weblog.wsgi:application`
     - **Environment**: Python 3

2. **Set Environment Variables** in Render dashboard:
   - `DJANGO_SECRET_KEY`: Generate a secure secret key
     ```bash
     python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
     ```
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: Your Render domain (e.g., `your-app.onrender.com`)
   - `DATABASE_URL`: Automatically set by Render if you create a PostgreSQL database

3. **Create a PostgreSQL Database**:
   - In Render dashboard, create a new PostgreSQL database
   - The `render.yaml` configuration will automatically connect it

4. **Enable Auto-Deploy**:
   - Render will automatically deploy when you push to the `main` branch

### CI/CD with GitHub Actions

The project includes a GitHub Actions workflow that:
- Runs tests on every push and pull request
- Automatically deploys to Render when pushing to `main`

**Required GitHub Secrets**:
- `RENDER_SERVICE_ID`: Your Render service ID (found in Render dashboard)
- `RENDER_API_KEY`: Your Render API key (generate in Render dashboard → Account Settings → API Keys)

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
├── render.yaml            # Render deployment configuration
├── build.sh               # Build script for Render
├── Procfile               # Process file for Render
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
- `DATABASE_URL`: PostgreSQL connection string (automatically set by Render)

### Optional
- `DJANGO_DEBUG`: Set to `False` in production (default: `True`)

## License

Personal project - All rights reserved.
