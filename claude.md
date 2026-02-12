# Rohan's Weblog

## Project Overview
Rohan Singh's weblog built with Django.

## Stack
- **Framework**: Django 5.0+
- **Database**: SQLite (development), consider PostgreSQL for production
- **Markdown**: python-markdown with syntax highlighting (Pygments)
- **Package Manager**: uv
- **Hosting**: Bluehost

## Hosting Details
- **Domain**: ygivenx.com
- **Hosting Provider**: Bluehost
- **Server IP**: 50.87.182.95
- **Home Directory**: /home4/ygivenxc/public_html

## SFTP Access
- **Hostname**: ygivenx.com
- **Username**: ygivenx@ygivenx.com
- **Port**: SFTP (22)

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
DJANGO_ALLOWED_HOSTS=ygivenx.com,www.ygivenx.com
```

## URLs
- `/` - Blog post listing
- `/posts/<slug>/` - Single blog post
- `/til/` - TIL entries
- `/til/<slug>/` - Single TIL
- `/bookmarks/` - Bookmarks listing
- `/search/` - Full-text search
- `/admin/` - Django admin interface
