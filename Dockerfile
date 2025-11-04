# OctoIQ Cost-Effective FSBO Scraper Dockerfile  
FROM python:3.9-slim

# Install basic dependencies only (no Chrome needed)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY fsbo_scraper.py .

# Port expose
EXPOSE 8080

# Environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Run command
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 fsbo_scraper:app