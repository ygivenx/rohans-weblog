#!/bin/bash
# Run this script ON the VPS after DNS is configured.
# Usage: ./setup-ssl.sh your-email@example.com rohansweblog.com

set -euo pipefail

EMAIL="${1:-admin@rohansweblog.com}"
DOMAIN="${2:-rohansweblog.com}"
BACKUP_FILE="nginx.conf.pre-ssl.bak"

echo "Setting up SSL certificate for $DOMAIN"

if [ ! -f "nginx.http-only.conf" ]; then
    echo "Missing nginx.http-only.conf. Cannot perform SSL bootstrap."
    exit 1
fi

# Step 1: switch to HTTP-only nginx so ACME challenge can be served even without cert files.
cp nginx.conf "$BACKUP_FILE"
cp nginx.http-only.conf nginx.conf
docker compose up -d nginx certbot

# Step 2: get initial certificate.
docker compose exec -T certbot certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# Step 3: restore HTTPS-enabled nginx config.
mv "$BACKUP_FILE" nginx.conf
docker compose up -d nginx

echo "SSL certificate installed successfully."
echo "Site should now be available at: https://$DOMAIN"
