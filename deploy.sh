#!/bin/bash
set -e

# Hostinger SFTP deployment configuration
# Override these when running, for example:
# REMOTE_HOST=example.com REMOTE_USER=user@example.com REMOTE_PATH=/home/user/public_html ./deploy.sh
REMOTE_HOST="${REMOTE_HOST:-your-hostinger-server-or-domain}"
REMOTE_USER="${REMOTE_USER:-your-hostinger-username}"
REMOTE_PATH="${REMOTE_PATH:-/home/your-hostinger-user/public_html}"

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Preparing deployment package..."
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

if command -v rsync &> /dev/null; then
  rsync -av --exclude='venv/' \
            --exclude='.venv/' \
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
  mkdir -p "$TEMP_DIR"/{blog,rohans_weblog,static,content}
  cp -r blog/* "$TEMP_DIR/blog/" 2>/dev/null || true
  cp -r rohans_weblog/* "$TEMP_DIR/rohans_weblog/" 2>/dev/null || true
  cp -r static/* "$TEMP_DIR/static/" 2>/dev/null || true
  cp manage.py pyproject.toml requirements.txt "$TEMP_DIR/" 2>/dev/null || true
fi

if [ -d "staticfiles" ]; then
  cp -r staticfiles "$TEMP_DIR/"
fi

echo "Deploying to $REMOTE_HOST..."
lftp -e "
  set sftp:auto-confirm yes
  open sftp://$REMOTE_USER@$REMOTE_HOST
  mirror -R --delete --verbose $TEMP_DIR/ $REMOTE_PATH/
  bye
"

echo ""
echo "Deployment complete! Files uploaded to $REMOTE_HOST"
echo ""
echo "Next steps on Hostinger server:"
echo "1. SSH into the server: ssh $REMOTE_USER@$REMOTE_HOST"
echo "2. Navigate to: cd $REMOTE_PATH"
echo "3. Install/update dependencies: pip install -r requirements.txt"
echo "4. Run migrations: python3 manage.py migrate"
echo "5. Restart your Gunicorn/systemd service"
echo "6. Confirm Nginx is proxying to your app"
