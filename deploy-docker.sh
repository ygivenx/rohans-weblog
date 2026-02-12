#!/bin/bash
set -e

# Hostinger VPS deployment script for Docker
# Configuration
VPS_IP="${VPS_IP:-187.77.7.177}"
VPS_USER="${VPS_USER:-rohan}"
VPS_PORT="${VPS_PORT:-1026}"
PROJECT_NAME="rohans-weblog"
DEPLOY_PATH="/opt/$PROJECT_NAME"

echo "🚀 Deploying $PROJECT_NAME to Hostinger VPS..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "❗ Please edit .env with your actual configuration before deploying!"
    exit 1
fi

# Create deployment archive
echo -e "${BLUE}📦 Creating deployment package...${NC}"
tar -czf /tmp/deploy.tar.gz \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='db.sqlite3' \
    --exclude='staticfiles' \
    --exclude='media' \
    --exclude='.DS_Store' \
    --exclude='content' \
    .

# Upload to VPS
echo -e "${BLUE}📤 Uploading to VPS...${NC}"
scp -P $VPS_PORT /tmp/deploy.tar.gz $VPS_USER@$VPS_IP:/tmp/

# Deploy on VPS
echo -e "${BLUE}🔧 Deploying on VPS...${NC}"
ssh -p $VPS_PORT $VPS_USER@$VPS_IP << 'ENDSSH'
    set -e

    # Create project directory if it doesn't exist
    mkdir -p /opt/rohans-weblog
    cd /opt/rohans-weblog

    # Extract deployment
    tar -xzf /tmp/deploy.tar.gz
    rm /tmp/deploy.tar.gz

    # Build and start containers
    echo "Building Docker images..."
    docker compose build

    echo "Starting containers..."
    docker compose up -d

    # Wait for services to be ready
    echo "Waiting for services to start..."
    sleep 10

    # Import existing posts if needed
    echo "Checking for posts to import..."
    docker compose exec -T web python manage.py import_posts || true

    echo "✅ Deployment complete!"
    echo "🌐 Your site should be available at: http://187.77.7.177"
    echo ""
    echo "📋 Useful commands:"
    echo "  - View logs: docker compose logs -f"
    echo "  - Restart: docker compose restart"
    echo "  - Stop: docker compose down"
    echo "  - Shell: docker compose exec web bash"
ENDSSH

# Cleanup
rm /tmp/deploy.tar.gz

echo -e "${GREEN}✨ Deployment completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Point your Cloudflare DNS for rohansweblog.com to: $VPS_IP"
echo "2. SSH to VPS: ssh -p $VPS_PORT $VPS_USER@$VPS_IP"
echo "3. Get SSL certificate: cd /opt/rohans-weblog && ./setup-ssl.sh"
echo "4. Create admin user: docker compose exec web python manage.py createsuperuser"
