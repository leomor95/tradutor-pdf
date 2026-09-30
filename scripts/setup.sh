#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== [1/5] Verificando pré-requisitos do sistema ==="

# 1. Tesseract
if ! command -v tesseract >/dev/null 2>&1; then
    echo "[ERRO] 'tesseract' não foi encontrado no PATH do sistema." >&2
    echo "Instale o Tesseract através do gerenciador de pacotes do sistema operacional:" >&2
    echo "  - Arch/CachyOS: sudo pacman -S tesseract" >&2
    echo "  - Debian/Ubuntu: sudo apt install tesseract-ocr" >&2
    echo "  - Fedora: sudo dnf install tesseract" >&2
    exit 1
fi
echo "[OK] Tesseract encontrado: $(tesseract --version 2>&1 | head -n 1)"

# 2. Idioma 'eng' do Tesseract
TESSDATA_FOUND=false
if tesseract --list-langs 2>&1 | grep -q "^eng$"; then
    TESSDATA_FOUND=true
    echo "[OK] Pacote de idioma 'eng' disponível no sistema."
elif [ -f "$ROOT_DIR/bin/tessdata/eng.traineddata" ]; then
    export TESSDATA_PREFIX="$ROOT_DIR/bin/tessdata"
    if tesseract --list-langs 2>&1 | grep -q "^eng$"; then
        TESSDATA_FOUND=true
        echo "[OK] Pacote de idioma 'eng' encontrado localmente em bin/tessdata/."
    fi
fi

if [ "$TESSDATA_FOUND" = false ]; then
    echo "[INFO] Idioma 'eng' não encontrado no sistema."
    echo "[INFO] Baixando eng.traineddata para bin/tessdata/ como fallback isolado..."
    mkdir -p "$ROOT_DIR/bin/tessdata"
    curl -fsSL -o "$ROOT_DIR/bin/tessdata/eng.traineddata" \
        "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
    export TESSDATA_PREFIX="$ROOT_DIR/bin/tessdata"
    if ! tesseract --list-langs 2>&1 | grep -q "^eng$"; then
        echo "[ERRO] Falha ao configurar idioma 'eng' com TESSDATA_PREFIX." >&2
        exit 1
    fi
    echo "[OK] Idioma 'eng' configurado com sucesso em bin/tessdata/."
fi

# 3. GPU (nvidia-smi opcional)
if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || echo "NVIDIA GPU")
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -n 1 || echo "desconhecida")
    echo "[OK] GPU detectada: $GPU_NAME ($GPU_MEM VRAM)"
else
    echo "[AVISO] 'nvidia-smi' não encontrado. O Ollama funcionará em modo CPU."
fi

# 4. uv
if ! command -v uv >/dev/null 2>&1; then
    echo "[ERRO] 'uv' não foi encontrado no PATH." >&2
    echo "Instale o uv antes de continuar: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi
echo "[OK] uv encontrado: $(uv --version)"

echo "=== [2/5] Sincronizando dependências Python com uv ==="
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.cache/uv}"
mkdir -p "$UV_CACHE_DIR"
(cd "$ROOT_DIR" && uv sync)
echo "[OK] Ambiente Python sincronizado em .venv/"

echo "=== [3/5] Verificando binário do Ollama ==="
mkdir -p "$ROOT_DIR/bin" "$ROOT_DIR/logs" "$ROOT_DIR/models" "$ROOT_DIR/.cache"

if [ -x "$ROOT_DIR/bin/ollama" ]; then
    echo "[OK] Ollama já instalado: $("$ROOT_DIR/bin/ollama" --version 2>&1 || echo 'bin/ollama')"
else
    echo "[INFO] Baixando Ollama para bin/..."
    OLLAMA_ARCHIVE="$ROOT_DIR/.cache/ollama-linux-amd64.tar.zst"
    curl -fL --progress-bar -o "$OLLAMA_ARCHIVE" \
        "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst"
    echo "[INFO] Extraindo Ollama..."
    tar --zstd -xf "$OLLAMA_ARCHIVE" -C "$ROOT_DIR"
    chmod +x "$ROOT_DIR/bin/ollama"
    rm -f "$OLLAMA_ARCHIVE"
    echo "[OK] Ollama instalado com sucesso em bin/ollama"
fi

echo "=== [4/5] Determinando modelo configurado ==="
MODEL="qwen2.5:7b-instruct-q4_K_M"
SETTINGS_FILE="$ROOT_DIR/config/settings.toml"
if [ -f "$SETTINGS_FILE" ]; then
    PARSED_MODEL=$(grep -E '^[[:space:]]*model[[:space:]]*=' "$SETTINGS_FILE" | head -n 1 | sed -E 's/.*=[[:space:]]*["'"'"']([^"'"'"']+)["'"'"'].*/\1/' || true)
    if [ -n "$PARSED_MODEL" ]; then
        MODEL="$PARSED_MODEL"
    fi
fi
echo "[INFO] Modelo configurado: $MODEL"

echo "=== [5/5] Verificando e baixando modelo no Ollama ==="
export OLLAMA_MODELS="$ROOT_DIR/models"
export OLLAMA_HOST="127.0.0.1:11434"

OLLAMA_STARTED_BY_SCRIPT=false
if ! curl -s "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "[INFO] Iniciando Ollama local para verificação..."
    "$ROOT_DIR/bin/ollama" serve > "$ROOT_DIR/logs/ollama_setup.log" 2>&1 &
    OLLAMA_PID=$!
    OLLAMA_STARTED_BY_SCRIPT=true

    # Aguardar subida do Ollama
    TRIES=0
    MAX_TRIES=30
    until curl -s "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; do
        sleep 0.5
        TRIES=$((TRIES + 1))
        if [ "$TRIES" -ge "$MAX_TRIES" ]; then
            echo "[ERRO] Não foi possível iniciar o Ollama em http://$OLLAMA_HOST" >&2
            if [ -n "${OLLAMA_PID:-}" ]; then
                kill "$OLLAMA_PID" 2>/dev/null || true
            fi
            exit 1
        fi
    done
fi

cleanup() {
    if [ "$OLLAMA_STARTED_BY_SCRIPT" = true ] && [ -n "${OLLAMA_PID:-}" ]; then
        echo "[INFO] Encerrando instância temporária do Ollama (PID $OLLAMA_PID)..."
        kill "$OLLAMA_PID" 2>/dev/null || true
        wait "$OLLAMA_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Verificar se o modelo já existe
if curl -s "http://$OLLAMA_HOST/api/tags" | grep -q "\"$MODEL\""; then
    echo "[OK] Modelo '$MODEL' já está presente em models/."
else
    echo "[INFO] Baixando modelo '$MODEL' (armazenado em models/)..."
    "$ROOT_DIR/bin/ollama" pull "$MODEL"
    echo "[OK] Modelo '$MODEL' baixado com sucesso."
fi

echo "=== Setup concluído com sucesso! ==="
