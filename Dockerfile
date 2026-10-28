# Full image: Calibre + Pandoc + the optional converter packages, so every /convert route works.
# Render: create the service with "Docker" instead of "Python" and point it at this file.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_QPA_PLATFORM=offscreen

RUN apt-get update \
    && apt-get install -y --no-install-recommends calibre pandoc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-converter.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-converter.txt
COPY . .

CMD ["python", "main.py"]
