FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ICE_HOST=0.0.0.0 \
    PORT=8080 \
    ICE_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app.py engine.py documents.py rulebook.py triage.py ./
COPY config ./config
COPY static ./static
COPY samples ./samples

RUN mkdir -p /data/jobs /data/uploads /data/exports \
    && useradd --system --uid 10001 --create-home ice \
    && chown -R ice:ice /app /data

USER ice
EXPOSE 8080

CMD ["python", "-X", "utf8", "app.py", "--host", "0.0.0.0", "--port", "8080", "--no-browser"]
