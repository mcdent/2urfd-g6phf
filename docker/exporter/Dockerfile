FROM python:3.12-slim

RUN pip install --no-cache-dir prometheus_client

WORKDIR /app
COPY exporter/exporter.py .

CMD ["python", "exporter.py"]
