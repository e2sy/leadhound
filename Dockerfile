# leadhound — the gig sniper, self-hosted in one container.
#
#   docker build -t leadhound .
#   docker run -d -p 7800:7800 -v leadhound_data:/data leadhound
#
# Data (SQLite + config) lives in /data, set via LEADHOUND_HOME, so the
# container is disposable and your gig history is not.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LEADHOUND_HOME=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY leadhound ./leadhound
COPY entry.py ./

RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 7800

# init is idempotent — it seeds config.toml/profile.toml/DB only if missing,
# so your volume data always wins over the packaged defaults.
CMD ["sh", "-c", "leadhound init && exec leadhound web --host 0.0.0.0 --port 7800 --no-browser"]
