FROM python:3.13-slim

WORKDIR /code
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_URL=sqlite:////data/pizarra.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
RUN mkdir /data && useradd --create-home appuser && chown appuser /data
USER appuser
VOLUME /data

EXPOSE 8000
# Render (y otros hostings) indican el puerto en $PORT; en local se usa 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips "*"
