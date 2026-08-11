FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Erst die Abhängigkeiten, damit Codeänderungen den Layer-Cache nicht wegwerfen.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" \
        "pydantic-settings>=2.6" "psycopg[binary,pool]>=3.2" "httpx>=0.27" \
        "numpy>=2.1" "pillow>=11.0"

COPY app ./app

RUN useradd --system --uid 10001 sofi && mkdir -p /data && chown sofi /data
USER sofi

EXPOSE 8000
# --no-access-log: Caddy protokolliert bereits, und von den beiden Logs ist
# dieser der mit den Koordinaten in der URI (Audit H1). Fehler und Warnungen
# der Anwendung gehen weiter nach stdout — nur die Zugriffszeile entfällt.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
