# OrphicOS brain — production image.
# Contains ONLY server/ (never client/). Secrets come from the env file at runtime
# (compose `env_file`), NEVER baked into a layer (CLAUDE.md Rules 4 & 6).
FROM python:3.12-slim

RUN useradd --create-home --shell /usr/sbin/nologin orphic
WORKDIR /srv

COPY requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY app.py auth.py brain.py __init__.py server/

# Per-user token store lives on a volume so tokens survive redeploys.
RUN mkdir -p /srv/data && chown orphic:orphic /srv/data
ENV ORPHIC_TOKENS_PATH=/srv/data/tokens.json

USER orphic
EXPOSE 8000
# One worker: metering + token store are in-process (see scripts/deploy.md).
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
