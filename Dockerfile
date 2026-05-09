# ── Python base image with Playwright deps ────────────────
FROM python:3.11-slim

# Install system dependencies for Playwright + WeasyPrint
RUN apt-get update && apt-get install -y \
    # Playwright Chromium deps
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    # WeasyPrint deps
    libgdk-pixbuf-2.0-0 libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev libssl-dev \
    # General & Fonts
    wget curl ca-certificates fonts-liberation fonts-noto-color-emoji fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only)
# Manual dependencies already installed above to avoid --with-deps errors on trixie
RUN playwright install chromium

# Copy application
COPY backend/ /app/
COPY frontend/ /app/frontend/

# Create reports directory
RUN mkdir -p /app/reports

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV REPORTS_DIR=/app/reports

EXPOSE 8000

# Start via python to ensure environment variables are handled correctly
CMD ["python", "main.py"]
