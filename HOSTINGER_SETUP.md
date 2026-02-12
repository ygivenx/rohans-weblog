# Hostinger Deployment Setup Guide

This guide migrates the project from a Render-style deployment to a Hostinger VPS deployment using Gunicorn + Nginx.

## Prerequisites

- A Hostinger VPS (Ubuntu 22.04/24.04 recommended)
- A domain pointed to your VPS IP (A record)
- SSH access to the server

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

## 2. Clone app on server

```bash
cd /var/www
sudo git clone <your-repo-url> rohans-weblog
sudo chown -R $USER:$USER /var/www/rohans-weblog
cd /var/www/rohans-weblog
```

## 3. Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Set production environment variables

Create `/var/www/rohans-weblog/.env`:

```bash
DJANGO_SECRET_KEY=<generate-a-strong-secret>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

Generate a secret key:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 5. Run migrations and collect static files

```bash
cd /var/www/rohans-weblog
source .venv/bin/activate
set -a; source .env; set +a
python manage.py migrate
python manage.py collectstatic --noinput
```

## 6. Create systemd service (Gunicorn)

Create `/etc/systemd/system/rohans-weblog.service`:

```ini
[Unit]
Description=Gunicorn for Rohan's Weblog
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/rohans-weblog
EnvironmentFile=/var/www/rohans-weblog/.env
ExecStart=/var/www/rohans-weblog/.venv/bin/gunicorn --workers 3 --bind unix:/run/rohans-weblog.sock rohans_weblog.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo chown -R www-data:www-data /var/www/rohans-weblog
sudo systemctl daemon-reload
sudo systemctl enable rohans-weblog
sudo systemctl start rohans-weblog
sudo systemctl status rohans-weblog
```

## 7. Configure Nginx

Create `/etc/nginx/sites-available/rohans-weblog`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /var/www/rohans-weblog/staticfiles/;
    }

    location /media/ {
        alias /var/www/rohans-weblog/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/rohans-weblog.sock;
    }
}
```

Enable site and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/rohans-weblog /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Enable HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## 9. Verify deployment

- Open `https://yourdomain.com`
- Check app logs:

```bash
sudo journalctl -u rohans-weblog -f
```

## 10. Optional cleanup from Render

After confirming Hostinger works:

- Remove Render environment variables/secrets from GitHub
- Delete `render.yaml` and `RENDER_SETUP.md` if you no longer need Render docs
- Decommission Render service/database to avoid extra cost

## Notes

- Keep `DJANGO_DEBUG=False` in production.
- If you use SQLite locally, prefer PostgreSQL in production for reliability.
- Any time dependencies change: reinstall requirements and restart service.
