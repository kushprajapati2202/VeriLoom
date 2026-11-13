# Use official lightweight Python 3.12 image
FROM python:3.12-slim

# Install system dependencies (git is required for repo intelligence & commit pinning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency specifications first for Docker layer caching
COPY requirements.txt pyproject.toml /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

# Copy application source code and verified sample packages
COPY veriloom/ /app/veriloom/
COPY examples/ /app/examples/
COPY scripts/ /app/scripts/
COPY README.md /app/

# Configure git identity for local patch evaluation
RUN git config --global user.name "VeriLoom Cloud" && \
    git config --global user.email "cloud@veriloom.ai"

# Expose HTTP port
EXPOSE 8000

# Environment variables
ENV PYTHONPATH="/app"
ENV PORT=8000

# Run FastAPI dashboard and API server
CMD ["sh", "-c", "uvicorn veriloom.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]

