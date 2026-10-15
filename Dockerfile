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
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/saude')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
