# Afe API. Migrations run as a separate one-off task before a deploy:
#   docker run --rm <image> alembic upgrade head
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 10001 afe

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations migrations
COPY app app

USER afe
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

# Trust X-Forwarded-For only from our own proxies (load balancer, Caddy, the website), never from the
# internet: set FORWARDED_ALLOW_IPS to the private network (the VPC, or the Docker network). uvicorn
# then takes the last address that isn't one of ours, so a caller can't fake theirs to dodge rate limits.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
