#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Export project-isolated environment variables (spec RNF24)
export OLLAMA_MODELS="$ROOT_DIR/models"
export OLLAMA_HOST="127.0.0.1:11434"
export XDG_CACHE_HOME="$ROOT_DIR/.cache"
export HF_HOME="$ROOT_DIR/.cache/hf"
export UV_CACHE_DIR="$ROOT_DIR/.cache/uv"

if [ -d "$ROOT_DIR/bin/tessdata" ]; then
    export TESSDATA_PREFIX="${TESSDATA_PREFIX:-$ROOT_DIR/bin/tessdata}"
fi

mkdir -p "$OLLAMA_MODELS" "$XDG_CACHE_HOME" "$HF_HOME" "$UV_CACHE_DIR" "$ROOT_DIR/logs"

# Start Ollama local server if not already running
if ! curl -s "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "[INFO] Iniciando Ollama local em http://$OLLAMA_HOST..."
    if [ ! -x "$ROOT_DIR/bin/ollama" ]; then
        echo "[ERRO] Binário do Ollama não encontrado em bin/ollama. Execute scripts/setup.sh primeiro." >&2
        exit 1
    fi
    nohup "$ROOT_DIR/bin/ollama" serve > "$ROOT_DIR/logs/ollama.log" 2>&1 &
    
    TRIES=0
    MAX_TRIES=30
    until curl -s "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; do
        sleep 0.5
        TRIES=$((TRIES + 1))
        if [ "$TRIES" -ge "$MAX_TRIES" ]; then
            echo "[ERRO] Não foi possível iniciar o Ollama em http://$OLLAMA_HOST após 15 segundos." >&2
            exit 1
        fi
    done
    echo "[OK] Ollama iniciado com sucesso (logs em logs/ollama.log)."
fi

# Model check mode (--check)
if [ "${1:-}" = "--check" ]; then
    MODEL="qwen2.5:7b-instruct-q4_K_M"
    SETTINGS_FILE="$ROOT_DIR/config/settings.toml"
    if [ -f "$SETTINGS_FILE" ]; then
        PARSED_MODEL=$(grep -E '^[[:space:]]*model[[:space:]]*=' "$SETTINGS_FILE" | head -n 1 | sed -E 's/.*=[[:space:]]*["'"'"']([^"'"'"']+)["'"'"'].*/\1/' || true)
        if [ -n "$PARSED_MODEL" ]; then
            MODEL="$PARSED_MODEL"
        fi
    fi

    echo "[INFO] Testando resposta do modelo '$MODEL' no Ollama..."
    RESPONSE=$(curl -s "http://$OLLAMA_HOST/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$MODEL\", \"prompt\": \"Diga ok\", \"stream\": false}")
    
    if echo "$RESPONSE" | grep -q '"response"'; then
        echo "[OK] Ollama está ativo e o modelo '$MODEL' respondeu com sucesso."
        exit 0
    else
        echo "[ERRO] Falha ao obter resposta do modelo '$MODEL'. Resposta:" >&2
        echo "$RESPONSE" >&2
        exit 1
    fi
fi

# Execute application
cd "$ROOT_DIR"
exec uv run python -m tradutor_pdf "$@"
