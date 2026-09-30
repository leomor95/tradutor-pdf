#!/usr/bin/env bash
# Audit isolation script (S8 / CA13 / RNF24)
# Takes a snapshot of $HOME and /tmp before and after setup.sh + full translation,
# and verifies that NO files were created or modified outside the project directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

AUDIT_DIR="$ROOT_DIR/.cache/isolation_audit"
mkdir -p "$AUDIT_DIR"
rm -f "$AUDIT_DIR"/*

BEFORE_HOME="$AUDIT_DIR/before_home.txt"
AFTER_HOME="$AUDIT_DIR/after_home.txt"
BEFORE_TMP="$AUDIT_DIR/before_tmp.txt"
AFTER_TMP="$AUDIT_DIR/after_tmp.txt"

DIFF_HOME="$AUDIT_DIR/diff_home.txt"
DIFF_TMP="$AUDIT_DIR/diff_tmp.txt"

echo "======================================================================"
echo " INICIANDO AUDITORIA DE ISOLAMENTO (RNF24 / CA13)"
echo " Projeto: $ROOT_DIR"
echo "======================================================================"

# Snapshot function: records file paths, pruning the project directory
# and active user browsers / development agent harnesses to isolate project footprint.
take_snapshot() {
    local target="$1"
    local outfile="$2"

    if [ "$target" = "$HOME" ]; then
        find "$HOME" \
            -path "$ROOT_DIR" -prune -o \
            -path "$HOME/.gemini" -prune -o \
            -path "$HOME/.config/Code" -prune -o \
            -path "$HOME/.config/google-chrome" -prune -o \
            -path "$HOME/.cache/google-chrome" -prune -o \
            -path "$HOME/.config/BraveSoftware" -prune -o \
            -path "$HOME/.cache/BraveSoftware" -prune -o \
            -path "$HOME/.cache/mozilla" -prune -o \
            -path "$HOME/.mozilla" -prune -o \
            -path "$HOME/.cache/antigravity" -prune -o \
            -path "$HOME/.local/share/systemd" -prune -o \
            -path "$HOME/.cache/systemd" -prune -o \
            -type f -printf "%p\n" 2>/dev/null | sort > "$outfile"
    else
        find "$target" \
            -path "/tmp/antigravity*" -prune -o \
            -path "/tmp/systemd*" -prune -o \
            -type f -printf "%p\n" 2>/dev/null | sort > "$outfile"
    fi
}

START_TIMESTAMP_SEC=$(date +%s)

echo "[1/4] Registrando snapshot inicial de \$HOME e /tmp..."
take_snapshot "$HOME" "$BEFORE_HOME"
take_snapshot "/tmp" "$BEFORE_TMP"

echo "      Snapshot inicial: $(wc -l < "$BEFORE_HOME") arquivos em \$HOME, $(wc -l < "$BEFORE_TMP") arquivos em /tmp"

echo "[2/4] Executando scripts/setup.sh..."
"$ROOT_DIR/scripts/setup.sh" > "$AUDIT_DIR/setup.log" 2>&1

echo "[3/4] Executando tradução completa de documento via scripts/run.sh..."
AUDIT_OUTPUT="$ROOT_DIR/.cache/audit_output.md"
rm -f "$AUDIT_OUTPUT"
"$ROOT_DIR/scripts/run.sh" --cli "$ROOT_DIR/tests/fixtures/simple.pdf" -o "$AUDIT_OUTPUT" --restart > "$AUDIT_DIR/translation.log" 2>&1

if [ ! -s "$AUDIT_OUTPUT" ]; then
    echo "[ERRO] Tradução falhou durante a auditoria de isolamento. Verifique $AUDIT_DIR/translation.log" >&2
    exit 1
fi

echo "[4/4] Registrando snapshot final e calculando diferenças..."
take_snapshot "$HOME" "$AFTER_HOME"
take_snapshot "/tmp" "$AFTER_TMP"

# Compute differences (new files only: in AFTER but not in BEFORE)
comm -13 "$BEFORE_HOME" "$AFTER_HOME" > "$DIFF_HOME" || true
comm -13 "$BEFORE_TMP" "$AFTER_TMP" > "$DIFF_TMP" || true

LEAKS_FOUND=false

if [ -s "$DIFF_HOME" ]; then
    echo "----------------------------------------------------------------------"
    echo "[FALHA] Arquivos criados em \$HOME fora do projeto:"
    cat "$DIFF_HOME"
    LEAKS_FOUND=true
fi

if [ -s "$DIFF_TMP" ]; then
    echo "----------------------------------------------------------------------"
    echo "[FALHA] Arquivos criados em /tmp fora do projeto:"
    cat "$DIFF_TMP"
    LEAKS_FOUND=true
fi

# Specifically verify that no prohibited directory was created or modified during the run
for prohibited in "$HOME/.ollama" "$HOME/.cache/huggingface" "$HOME/.cache/uv" "$HOME/.config/tradutor-pdf"; do
    if [ -e "$prohibited" ]; then
        MODIFIED_ITEMS=$(find "$prohibited" -newermt "@$START_TIMESTAMP_SEC" 2>/dev/null || true)
        if [ -n "$MODIFIED_ITEMS" ]; then
            echo "[FALHA] Modificações detectadas no diretório proibido $prohibited:"
            echo "$MODIFIED_ITEMS"
            LEAKS_FOUND=true
        fi
    fi
done

echo "======================================================================"
if [ "$LEAKS_FOUND" = true ]; then
    echo "[FALHA] Foram detectados arquivos ou diretórios fora do repositório."
    echo "======================================================================"
    exit 1
else
    echo "[APROVADO] Nenhuma diferença fora da pasta do projeto (RNF24 / CA13)."
    echo "Todos os artefatos, caches, logs e temporários permaneceram dentro de:"
    echo "  $ROOT_DIR"
    echo "======================================================================"
    exit 0
fi
