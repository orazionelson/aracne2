FROM python:3.12-slim

WORKDIR /app

# gcc and libpq-dev required by asyncpg; curl required by healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Cache layer: copy requirements before source code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security. /app/schemas and /app/media are mountpoints
# for named volumes — pre-create them so Docker propagates appuser ownership
# to the volume on first creation (only happens when the volume is empty).
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/schemas /app/media \
    && chown -R appuser /app
USER appuser

EXPOSE 8000
