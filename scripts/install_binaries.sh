#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p bin calibre-bin

echo "Checking Pandoc..."
if ! command -v pandoc &>/dev/null && [ ! -f "bin/pandoc" ]; then
    echo "Downloading standalone Pandoc..."
    curl -sSL "https://github.com/jgm/pandoc/releases/download/3.6.3/pandoc-3.6.3-linux-amd64.tar.gz" | tar -xz -C bin --strip-components=2 "pandoc-3.6.3/bin/pandoc" 2>/dev/null || true
    chmod +x bin/pandoc 2>/dev/null || true
fi

echo "Checking Calibre..."
if ! command -v ebook-convert &>/dev/null && [ ! -f "calibre-bin/ebook-convert" ] && [ ! -f "calibre-bin/calibre/ebook-convert" ]; then
    echo "Installing isolated Calibre..."
    curl -sSL https://download.calibre-ebook.com/linux-installer.sh | sh /dev/stdin install_dir="$ROOT_DIR/calibre-bin" isolated=y 2>/dev/null || true
fi
echo "Binary setup complete."
