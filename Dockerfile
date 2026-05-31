# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright + system dependencies ──────────────────────────────────────────
# --with-deps runs apt-get internally for Chromium's shared libraries;
# we piggyback cron onto the same apt cache before the cleanup.
RUN playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

# ── Application code ───────────────────────────────────────────────────────────
COPY checker.py ./
COPY homeassistant.py ./
COPY entrypoint.sh ./
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
COPY crontab /etc/cron.d/check-status
RUN chmod 644 /etc/cron.d/check-status
RUN sed -i 's/\r$//' /etc/cron.d/check-status

# Ensure the data directory exists inside the image as a fallback.
# The volume mount in docker-compose.yml overrides this at runtime.
RUN mkdir -p /data

# entrypoint.sh exports Docker env vars to /etc/environment so cron jobs inherit them.
ENTRYPOINT ["/app/entrypoint.sh"]
