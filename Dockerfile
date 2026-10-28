FROM ghcr.io/yshalsager/calibre-with-kfx:latest

USER root

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     QT_QPA_PLATFORM=offscreen     QTWEBENGINE_DISABLE_SANDBOX=1     QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --headless --disable-dev-shm-usage --single-process --no-zygote"     LIBGL_ALWAYS_SOFTWARE=1     DBUS_SESSION_BUS_ADDRESS=/dev/null     HOME=/tmp     CALIBRE_CONFIG_DIRECTORY=/tmp/calibre-config     PIP_BREAK_SYSTEM_PACKAGES=1

# Install Pandoc and system fonts for Calibre PDF rendering
RUN apt-get update     && apt-get install -y --no-install-recommends         pandoc fontconfig fonts-dejavu-core fonts-liberation ca-certificates curl     && fc-cache -f     && rm -rf /var/lib/apt/lists/*

EXPOSE 8080 10000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN chown -R calibre:calibre /app /tmp && chmod -R 777 /tmp

USER calibre

# Reset entrypoint so container executes python main.py directly
ENTRYPOINT []
CMD ["python", "main.py"]
