FROM ghcr.io/yshalsager/calibre-with-kfx:latest

USER root

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_QPA_PLATFORM=offscreen \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Install Pandoc for document conversions
RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "main.py"]
