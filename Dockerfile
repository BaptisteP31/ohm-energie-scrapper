FROM python:3.14-slim

WORKDIR /app

# Création d'un utilisateur non-root sans privilèges (UID/GID 1000)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/sh -d /app appuser

# Installation des dépendances en amont pour optimiser le cache Docker
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code applicatif uniquement
COPY ohm_scraper ./ohm_scraper

# Bascule sur l'utilisateur non-root
USER appuser

ENV PYTHONUNBUFFERED=1 \
    SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c 'import os, urllib.request; port = os.environ.get("SERVICE_PORT", "8080"); urllib.request.urlopen(f"http://127.0.0.1:{port}/health")' || exit 1

CMD ["python", "-m", "ohm_scraper", "serve"]
