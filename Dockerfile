FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
# Usuário sem privilégios
RUN useradd --system --uid 10001 bpo && chown -R bpo /srv
USER bpo
WORKDIR /srv/backend
EXPOSE 8000
ENV PORT=8000
HEALTHCHECK CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/saude')" || exit 1
# PORT é definida pela plataforma (o Render usa 10000)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
