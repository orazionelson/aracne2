FROM python:3.12-slim

WORKDIR /app

# gcc and libpq-dev required by asyncpg; curl required by healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Cache layer: copy requirements before source code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
