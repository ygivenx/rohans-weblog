# Important: Directory Rename Required

To complete the project rename from "personal-website" to "rohans-weblog", you need to rename the Django project directory.

## Step 1: Rename the Django Project Directory

The directory `personal-website/` needs to be renamed to `rohans_weblog/` (note: use underscores, not hyphens, for Python package naming).

**From your project root, run:**
```bash
mv personal-website rohans_weblog
```

## Step 2: Verify Everything Works

After renaming, test that everything still works:

```bash
# Run migrations (if needed)
uv run python manage.py migrate

# Run the development server
uv run python manage.py runserver
```

## Why Underscores?

Python package names cannot contain hyphens. The directory name must use underscores to match the import statements:
- Directory: `rohans_weblog/`
- Import: `from rohans_weblog import settings`

## Files Already Updated

The following files have been updated to use the new project name:
- ✅ `manage.py` - Settings module reference
- ✅ `Procfile` - WSGI application path
- ✅ `render.yaml` - Service names and database references
- ✅ `README.md` - Project structure and references
- ✅ `RENDER_SETUP.md` - Deployment instructions
- ✅ `deploy.sh` - Directory references
- ✅ `pyproject.toml` - Project name and description
- ✅ `personal-website/wsgi.py` - Settings module reference
- ✅ `personal-website/asgi.py` - Settings module reference
- ✅ `personal-website/settings.py` - Project name in docstring
- ✅ `personal-website/urls.py` - Project name in docstring

## After Renaming

Once you've renamed the directory, all imports and references will work correctly with the new name `rohans_weblog`.
