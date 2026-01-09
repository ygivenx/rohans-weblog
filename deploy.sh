#!/bin/bash
set -e

# Configuration
REMOTE_HOST="ygivenx.com"
REMOTE_USER="ygivenx@ygivenx.com"
REMOTE_PATH="/home4/ygivenxc/public_html"

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Preparing deployment package..."
# Create a temporary directory for files to deploy
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy Django project files (excluding unnecessary files)
# Note: rsync is used here for filtering; if not available, adjust the approach
if command -v rsync &> /dev/null; then
  rsync -av --exclude='venv/' \
            --exclude='.git/' \
            --exclude='__pycache__/' \
            --exclude='*.pyc' \
            --exclude='.hugo_build.lock' \
            --exclude='db.sqlite3' \
            --exclude='staticfiles/' \
            --exclude='media/' \
            --exclude='.env' \
            --exclude='*.log' \
            --exclude='.DS_Store' \
            ./ "$TEMP_DIR/"
else
  echo "Warning: rsync not found. Copying files manually..."
  # Fallback: copy essential directories
  mkdir -p "$TEMP_DIR"/{blog,rohans_weblog,static,content}
  cp -r blog/* "$TEMP_DIR/blog/" 2>/dev/null || true
  cp -r rohans_weblog/* "$TEMP_DIR/rohans_weblog/" 2>/dev/null || true
  cp -r static/* "$TEMP_DIR/static/" 2>/dev/null || true
  cp manage.py pyproject.toml "$TEMP_DIR/" 2>/dev/null || true
fi

# Copy collected static files
if [ -d "staticfiles" ]; then
  cp -r staticfiles "$TEMP_DIR/"
fi

echo "Deploying to $REMOTE_HOST..."
# Using lftp for reliable SFTP transfer (install with: brew install lftp)
lftp -e "
  set sftp:auto-confirm yes
  open sftp://$REMOTE_USER@$REMOTE_HOST
  mirror -R --delete --verbose $TEMP_DIR/ $REMOTE_PATH/
  bye
"

echo ""
echo "Deployment complete! Files uploaded to $REMOTE_HOST"
echo ""
echo "IMPORTANT: Next steps on the server:"
echo "1. SSH into the server: ssh $REMOTE_USER@$REMOTE_HOST"
echo "2. Navigate to: cd $REMOTE_PATH"
echo "3. Run migrations: python3 manage.py migrate"
echo "4. Ensure Python dependencies are installed (uv or pip)"
echo "5. Configure WSGI/ASGI for Bluehost (check their Python hosting docs)"
echo "6. Set environment variables (DJANGO_SECRET_KEY, ALLOWED_HOSTS, etc.)"
echo ""
echo "Note: Bluehost may require specific WSGI configuration."
echo "Check their Python hosting documentation for setup details."
