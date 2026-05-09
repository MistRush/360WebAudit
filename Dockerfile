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
    libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
    libffi-dev libssl-dev \
    # General
    wget curl ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only)
RUN playwright install chromium --with-deps

# Copy application
COPY backend/ ./

# Create reports directory
RUN mkdir -p /app/reports

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV REPORTS_DIR=/app/reports

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
