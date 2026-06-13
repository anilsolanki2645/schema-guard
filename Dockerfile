# Schema Guard — Docker Image
# Lightweight image for CI/CD pipelines
#
# Build:   docker build -t schema-guard .
# Run:     docker run --rm -v "$(pwd)":/app -w /app schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
# Help:    docker run --rm schema-guard --help

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system-level dependencies needed by some DB drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only dependency files first for better layer caching
COPY pyproject.toml README.md ./
COPY src/ src/

# Install schema-guard with all optional database connectors
RUN pip install --no-cache-dir -e ".[all]"

# --- Runtime stage ---
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from build stage
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin/schema-guard /usr/local/bin/schema-guard

WORKDIR /app

ENTRYPOINT ["schema-guard"]
CMD ["--help"]
