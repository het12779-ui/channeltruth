FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DATABASE_URL=sqlite:////tmp/channeltruth.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# The bundled dashboard needs demo tenant switching. Set CHANNELTRUTH_DEMO=0
# when running behind a real auth proxy.
ENV CHANNELTRUTH_DEMO=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/healthz', timeout=2)"

CMD ["sh", "-c", "uvicorn channeltruth.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8080}"]
