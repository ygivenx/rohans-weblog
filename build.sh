#!/bin/bash
set -e

echo "Installing dependencies..."

# Try to use uv if available, otherwise use pip
if command -v uv &> /dev/null; then
    echo "Using uv to install dependencies..."
    uv pip install --system -e .
else
    echo "Using pip to install dependencies..."
    pip install -e .
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running migrations..."
python manage.py migrate --noinput

echo "Build complete!"
