# Repository Guidelines

## Project Structure & Module Organization
This is a Django monorepo-style app.

- `blog/`: main app (`models.py`, `views.py`, `urls.py`, admin config, templates, static assets, and custom management commands in `management/commands/`).
- `rohans_weblog/`: project config (`settings.py`, root `urls.py`, `wsgi.py`, `asgi.py`).
- `.github/workflows/`: CI and deployment workflows.
- Operational files: `docker-compose.yml`, `Dockerfile`, `nginx*.conf`, `deploy*.sh`, `setup-ssl.sh`.
- Data and generated artifacts: `db.sqlite3`, `staticfiles/`.

## Build, Test, and Development Commands
Use `uv` for local development.

- `uv sync --extra dev`: install runtime + dev dependencies.
- `uv run python manage.py migrate`: apply database migrations.
- `uv run python manage.py runserver`: start local server at `127.0.0.1:8000`.
- `uv run python manage.py collectstatic --noinput`: collect static files.
- `uv run python manage.py check --deploy`: run Django deployment checks.
- `uv run black --check --diff .`: enforce formatting (matches CI).
- `./build.sh`: production-style build step (`pip install`, `collectstatic`, `migrate`).

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
