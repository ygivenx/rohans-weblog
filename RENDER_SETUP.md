# Render Deployment Setup Guide

This guide will help you deploy your Django blog to Render.

## Prerequisites

1. A GitHub account with your repository
2. A Render account (sign up at https://render.com)

## Step 1: Create Render Account and Connect GitHub

1. Go to https://render.com and sign up/login
2. Connect your GitHub account in Render dashboard
3. Authorize Render to access your repositories

## Step 2: Create PostgreSQL Database

1. In Render dashboard, click **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name**: `rohans-weblog-db`
   - **Database**: `rohans_weblog`
   - **User**: `rohans_weblog_user`
   - **Plan**: Starter (or your preferred plan)
3. Click **"Create Database"**
4. Note the **Internal Database URL** (you'll need this)

## Step 3: Create Web Service

### Option A: Using render.yaml (Recommended)

1. In Render dashboard, click **"New +"** → **"Blueprint"**
2. Connect your GitHub repository
3. Render will automatically detect `render.yaml` and create the services
4. Review the configuration and click **"Apply"**

### Option B: Manual Setup

1. In Render dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `rohans-weblog`
   - **Environment**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn rohans_weblog.wsgi:application`
   - **Plan**: Starter (or your preferred plan)

## Step 4: Set Environment Variables

In your Web Service settings, add these environment variables:

### Required Variables

1. **DJANGO_SECRET_KEY**
   - Generate a secret key:
     ```bash
     python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
     ```
   - Copy the output and paste it as the value

2. **DJANGO_ALLOWED_HOSTS**
   - Set to your Render domain: `your-app-name.onrender.com`
   - Or use: `your-app-name.onrender.com,www.yourdomain.com` if you have a custom domain

3. **DJANGO_DEBUG**
   - Set to: `False`

4. **DATABASE_URL**
   - This is automatically set if you linked the database in render.yaml
   - Or manually: Copy the **Internal Database URL** from your PostgreSQL service

### Optional Variables

- **PYTHON_VERSION**: `3.12.0` (if not set in render.yaml)

## Step 5: Link Database to Web Service

If you didn't use render.yaml:

1. In your Web Service settings, go to **"Environment"** tab
2. Under **"Add Environment Variable"**, select **"Add Database"**
3. Select your `rohans-weblog-db` database
4. The `DATABASE_URL` will be automatically added

## Step 6: Deploy

1. Click **"Save Changes"** in your Web Service
2. Render will automatically start building and deploying
3. Watch the build logs to ensure everything works
4. Once deployed, your site will be available at `https://your-app-name.onrender.com`

## Step 7: Run Initial Setup

After first deployment, you may need to:

1. **Create a superuser** (via Render Shell):
   - Go to your Web Service → **"Shell"**
   - Run: `python manage.py createsuperuser`

2. **Import posts** (optional):
   - In Render Shell: `python manage.py import_posts`

## Step 8: Set Up CI/CD with GitHub Actions (Optional)

1. **Get Render API Credentials**:
   - Go to Render Dashboard → **Account Settings** → **API Keys**
   - Click **"Create API Key"**
   - Copy the API key

2. **Get Service ID**:
   - Go to your Web Service
   - The Service ID is in the URL: `https://dashboard.render.com/web/your-service-id`
   - Or find it in the service settings

3. **Add GitHub Secrets**:
   - Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**
   - Add secret: `RENDER_API_KEY` (paste your API key)
   - Add secret: `RENDER_SERVICE_ID` (paste your service ID)

4. **Test the Pipeline**:
   - Push a commit to `main` branch
   - Check GitHub Actions tab to see the workflow run
   - It will automatically deploy to Render after tests pass

## Troubleshooting

### Build Fails

- Check build logs in Render dashboard
- Ensure `build.sh` is executable: `chmod +x build.sh`
- Verify all dependencies are in `pyproject.toml`

### Database Connection Issues

- Verify `DATABASE_URL` is set correctly
- Check that database is linked to web service
- Ensure `dj-database-url` and `psycopg2-binary` are in dependencies

### Static Files Not Loading

- Verify `STATIC_ROOT` is set in settings
- Check that `collectstatic` runs during build
- Ensure static files are collected in `build.sh`

### 500 Errors

- Check Render logs for error details
- Verify all environment variables are set
- Ensure `DJANGO_SECRET_KEY` is set and valid

## Custom Domain Setup

1. In your Web Service settings, go to **"Custom Domains"**
2. Add your domain
3. Follow Render's DNS configuration instructions
4. Update `DJANGO_ALLOWED_HOSTS` to include your custom domain

## Monitoring

- View logs: Web Service → **"Logs"** tab
- Monitor metrics: Web Service → **"Metrics"** tab
- Set up alerts: Web Service → **"Alerts"** tab

## Support

- Render Documentation: https://render.com/docs
- Render Community: https://community.render.com
- Django Deployment Checklist: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
