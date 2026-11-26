# VeriLoom pipeline image (judges' standardised environment).
#
#   docker build -t veriloom .
#   docker run --rm veriloom pytest -q                                   # offline unit tests
#   docker run --rm veriloom python scripts/replay_evidence.py           # re-validate shipped click tasks, no API key
#   docker run --rm -e GEMINI_API_KEY=... veriloom sh -c \
#       "python -m veriloom ideate target_repos/click --out /tmp/ideas.json && \
#        python scripts/generate_evidence.py target_repos/click --ideas /tmp/ideas.json --candidates 0-4 --out /tmp/run --harbor"
#
# Harbor trials (`harbor run -a nop|oracle`) need a Docker daemon, so they run on the host:
#   bash scripts/harbor_validate.sh evidence/click/harbor_tasks
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt pyproject.toml /app/
COPY veriloom/ /app/veriloom/
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY test_repos/ /app/test_repos/
COPY evidence/ /app/evidence/
COPY README.md SUBMISSION.md TECHNICAL.md .gitattributes /app/

RUN git config --global user.name "VeriLoom" && git config --global user.email "veriloom@localhost" \
    && git config --global advice.detachedHead false

# Target repository (pallets/click 8.5.1) and its isolated test environment.
RUN python scripts/setup_click.py --skip-tests

ENV PYTHONPATH="/app" PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn veriloom.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
