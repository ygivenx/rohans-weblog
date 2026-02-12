#!/bin/bash
# Run this script ON the VPS after DNS is configured
# Usage: ./setup-ssl.sh your-email@example.com rohansweblog.com

set -e

EMAIL="${1:-admin@rohansweblog.com}"
DOMAIN="${2:-rohansweblog.com}"

echo "🔒 Setting up SSL certificate for $DOMAIN"

# Get initial certificate
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# Uncomment SSL lines in nginx.conf
sed -i 's/# ssl_certificate /ssl_certificate /g' nginx.conf

# Reload nginx
docker compose restart nginx

echo "✅ SSL certificate installed successfully!"
echo "🌐 Your site should now be available at: https://$DOMAIN"
