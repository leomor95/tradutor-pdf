#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== [1/6] Verificando pré-requisitos do sistema ==="

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

# Garantir arquivos complementares do Tesseract (osd e configs) em bin/tessdata
if [ -d "$ROOT_DIR/bin/tessdata" ]; then
    if [ ! -f "$ROOT_DIR/bin/tessdata/osd.traineddata" ]; then
        if [ -f "/usr/share/tessdata/osd.traineddata" ]; then
            cp "/usr/share/tessdata/osd.traineddata" "$ROOT_DIR/bin/tessdata/"
        else
            echo "[INFO] Baixando osd.traineddata para bin/tessdata/..."
            curl -fsSL -o "$ROOT_DIR/bin/tessdata/osd.traineddata" \
                "https://github.com/tesseract-ocr/tessdata_fast/raw/main/osd.traineddata"
        fi
    fi
    if [ ! -d "$ROOT_DIR/bin/tessdata/configs" ] && [ -d "/usr/share/tessdata/configs" ]; then
        cp -r "/usr/share/tessdata/configs" "$ROOT_DIR/bin/tessdata/"
    fi
    if [ ! -d "$ROOT_DIR/bin/tessdata/tessconfigs" ] && [ -d "/usr/share/tessdata/tessconfigs" ]; then
        cp -r "/usr/share/tessdata/tessconfigs" "$ROOT_DIR/bin/tessdata/"
    fi
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

echo "=== [2/6] Sincronizando dependências Python com uv ==="
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.cache/uv}"
mkdir -p "$UV_CACHE_DIR"
(cd "$ROOT_DIR" && uv sync)
echo "[OK] Ambiente Python sincronizado em .venv/"

echo "=== [3/6] Verificando binário do Ollama ==="
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

echo "=== [4/6] Verificando epubcheck e ambiente Java isolado ==="
if [ -x "$ROOT_DIR/bin/jre/bin/java" ]; then
    echo "[OK] JRE isolada encontrada em bin/jre/"
elif command -v java >/dev/null 2>&1; then
    echo "[OK] Java encontrado no sistema: $(java -version 2>&1 | head -n 1)"
else
    echo "[INFO] Java não encontrado no sistema. Baixando JRE portátil (Temurin 21) para bin/jre/..."
    mkdir -p "$ROOT_DIR/.cache" "$ROOT_DIR/bin/jre"
    JRE_ARCHIVE="$ROOT_DIR/.cache/jre-temurin21.tar.gz"
    curl -fsSL -o "$JRE_ARCHIVE" "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz"
    tar -xzf "$JRE_ARCHIVE" -C "$ROOT_DIR/bin/jre" --strip-components=1
    rm -f "$JRE_ARCHIVE"
    echo "[OK] JRE portátil instalada com sucesso em bin/jre/"
fi

if [ -f "$ROOT_DIR/bin/epubcheck-pkg/epubcheck.jar" ]; then
    echo "[OK] epubcheck.jar já instalado em bin/epubcheck-pkg/"
else
    echo "[INFO] Baixando epubcheck para bin/..."
    mkdir -p "$ROOT_DIR/.cache" "$ROOT_DIR/bin"
    EPUBCHECK_ZIP="$ROOT_DIR/.cache/epubcheck.zip"
    curl -fsSL -o "$EPUBCHECK_ZIP" "https://github.com/w3c/epubcheck/releases/download/v5.2.1/epubcheck-5.2.1.zip"
    unzip -q "$EPUBCHECK_ZIP" -d "$ROOT_DIR/bin/"
    rm -rf "$ROOT_DIR/bin/epubcheck-pkg"
    mv "$ROOT_DIR/bin/epubcheck-5.2.1" "$ROOT_DIR/bin/epubcheck-pkg"
    rm -f "$EPUBCHECK_ZIP"
    echo "[OK] epubcheck descompactado com sucesso em bin/epubcheck-pkg/"
fi

cat << 'EOF' > "$ROOT_DIR/bin/epubcheck"
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -x "$ROOT_DIR/bin/jre/bin/java" ]; then
    JAVA_CMD="$ROOT_DIR/bin/jre/bin/java"
elif command -v java >/dev/null 2>&1; then
    JAVA_CMD="java"
else
    echo "[ERRO] Java não encontrado. Execute ./scripts/setup.sh para baixar a JRE isolada." >&2
    exit 1
fi

JAR_FILE="$ROOT_DIR/bin/epubcheck-pkg/epubcheck.jar"
if [ ! -f "$JAR_FILE" ]; then
    echo "[ERRO] epubcheck.jar não encontrado em $JAR_FILE. Execute ./scripts/setup.sh." >&2
    exit 1
fi

exec "$JAVA_CMD" -jar "$JAR_FILE" "$@"
EOF
chmod +x "$ROOT_DIR/bin/epubcheck"
echo "[OK] bin/epubcheck configurado: $("$ROOT_DIR/bin/epubcheck" --version 2>&1)"

echo "=== [5/6] Determinando modelo configurado ==="
MODEL="qwen2.5:7b-instruct-q4_K_M"
SETTINGS_FILE="$ROOT_DIR/config/settings.toml"
if [ -f "$SETTINGS_FILE" ]; then
    PARSED_MODEL=$(grep -E '^[[:space:]]*model[[:space:]]*=' "$SETTINGS_FILE" | head -n 1 | sed -E 's/.*=[[:space:]]*["'"'"']([^"'"'"']+)["'"'"'].*/\1/' || true)
    if [ -n "$PARSED_MODEL" ]; then
        MODEL="$PARSED_MODEL"
    fi
fi
echo "[INFO] Modelo configurado: $MODEL"

echo "=== [6/6] Verificando e baixando modelo no Ollama ==="
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
