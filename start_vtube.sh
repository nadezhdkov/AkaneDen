#!/bin/bash
# =============================================================
# [ AKANE DEN v3.5 — SHOGUN OS ] (Linux Version)
# =============================================================

# Definir cores
RED='\033[0;31m'
NC='\033[0m' # No Color
GREEN='\033[0;32m'
YELLOW='\033[1;33m'

echo -e "${RED}=============================================================${NC}"
echo -e "${RED}               [ AKANE DEN v3.5 — SHOGUN OS ]${NC}"
echo -e "${RED}=============================================================${NC}"
echo ""
echo "[!] Status: Initializing Cognitive Framework"
echo "[!] Starting Docker containers (Ollama)..."
echo ""

# ────────────────────────────────────────────────
# 1. Subir Docker Compose (Ollama)
# ────────────────────────────────────────────────
docker compose up -d --build
if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR] Falha ao iniciar Docker Compose!${NC}"
    echo -e "${RED}[ERROR] Verifique se o Docker daemon está rodando e se você tem permissões (sudo usermod -aG docker \$USER).${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] Docker containers iniciados.${NC}"
echo ""

# ────────────────────────────────────────────────
# 2. Aguardar Ollama ficar saudável
# ────────────────────────────────────────────────
echo "[!] Aguardando Ollama ficar pronto..."
RETRIES=0
MAX_RETRIES=30

while true; do
    curl -s -f http://localhost:11434/api/tags >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        break
    fi

    RETRIES=$((RETRIES+1))
    if [ $RETRIES -ge $MAX_RETRIES ]; then
        echo -e "${RED}[ERROR] Ollama não respondeu após 30 tentativas.${NC}"
        exit 1
    fi
    echo "    Tentativa $RETRIES/$MAX_RETRIES... aguardando 2s"
    sleep 2
done

echo -e "${GREEN}[OK] Ollama está pronto!${NC}"
echo ""

# ────────────────────────────────────────────────
# 3. Garantir que os modelos estão baixados
# ────────────────────────────────────────────────
echo "[!] Verificando modelos do Ollama..."

# --- Verifica llama3.2 (Brain) ---
if docker exec akane_ollama ollama list 2>/dev/null | grep -i -q "llama3.2"; then
    echo -e "${GREEN}[OK] llama3.2 já está disponível.${NC}"
else
    echo -e "${YELLOW}[!] Baixando modelo llama3.2 (brain)... Pode demorar na primeira vez.${NC}"
    docker exec akane_ollama ollama pull llama3.2
    if [ $? -ne 0 ]; then
        echo -e "${RED}[WARN] Falha ao baixar llama3.2. O brain pode não funcionar.${NC}"
    else
        echo -e "${GREEN}[OK] llama3.2 baixado com sucesso!${NC}"
    fi
fi

# --- Verifica moondream (Vision) ---
if docker exec akane_ollama ollama list 2>/dev/null | grep -i -q "moondream"; then
    echo -e "${GREEN}[OK] moondream já está disponível.${NC}"
else
    echo -e "${YELLOW}[!] Baixando modelo moondream (vision)... Pode demorar na primeira vez.${NC}"
    docker exec akane_ollama ollama pull moondream
    if [ $? -ne 0 ]; then
        echo -e "${RED}[WARN] Falha ao baixar moondream. A visão pode não funcionar.${NC}"
    else
        echo -e "${GREEN}[OK] moondream baixado com sucesso!${NC}"
    fi
fi

echo ""
echo -e "${GREEN}[OK] Todos os modelos verificados!${NC}"
echo ""

# ────────────────────────────────────────────────
# 4. Iniciar Akane
# ────────────────────────────────────────────────
echo -e "${RED}=============================================================${NC}"
echo "[!] Loading ServiceContext, Async Modules, and MCP Tools..."
echo "[!] Starting Pipeline (Local/Cloud Hybrid)..."
echo "[!] Waking up Akane's Brain..."
echo ""
echo -e "${RED}=============================================================${NC}"
echo "[CONTROLS]"
echo "- Hold [F2] to talk. Release to send text to Akane."
echo "- Hold [F2] while she is speaking to interrupt her (Barge-in)."
echo ""
echo "[WEB DASHBOARD]"
echo "- If enabled, accessible at: http://127.0.0.1:8080"
echo -e "${RED}=============================================================${NC}"
echo ""

export PYTHONPATH=src
uv run python -m akane_den.main
