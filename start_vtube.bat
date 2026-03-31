@echo off
setlocal enabledelayedexpansion
title Akane OS v3.5 — Shogun Architecture (Terminal)
color 0C
echo =============================================================
echo               [ AKANE DEN v3.5 — SHOGUN OS ]
echo =============================================================
echo.
echo [!] Status: Initializing Cognitive Framework
echo [!] Starting Docker containers (Ollama)...
echo.

:: ────────────────────────────────────────────────
:: 1. Subir Docker Compose (Ollama)
:: ────────────────────────────────────────────────
docker compose up -d --build
if !errorlevel! neq 0 (
    echo [ERROR] Falha ao iniciar Docker Compose!
    echo [ERROR] Verifique se o Docker Desktop esta rodando.
    pause
    exit /b 1
)
echo [OK] Docker containers iniciados.
echo.

:: ────────────────────────────────────────────────
:: 2. Aguardar Ollama ficar saudável
:: ────────────────────────────────────────────────
echo [!] Aguardando Ollama ficar pronto...
set RETRIES=0

:wait_ollama
curl -s -f http://localhost:11434/api/tags >nul 2>&1
if !errorlevel! equ 0 goto ollama_ready

set /a RETRIES+=1
if !RETRIES! geq 30 (
    echo [ERROR] Ollama nao respondeu apos 30 tentativas.
    pause
    exit /b 1
)
echo     Tentativa !RETRIES!/30... aguardando 2s
timeout /t 2 /nobreak >nul
goto wait_ollama

:ollama_ready
echo [OK] Ollama esta pronto!
echo.

:: ────────────────────────────────────────────────
:: 3. Garantir que os modelos estão baixados
:: ────────────────────────────────────────────────
echo [!] Verificando modelos do Ollama...

:: --- Verifica llama3.2 (Brain) ---
docker exec akane_ollama ollama list 2>nul | findstr /i "llama3.2" >nul 2>&1
if !errorlevel! equ 0 goto llama_ok

echo [!] Baixando modelo llama3.2 (brain)... Pode demorar na primeira vez.
docker exec akane_ollama ollama pull llama3.2
if !errorlevel! neq 0 (
    echo [WARN] Falha ao baixar llama3.2. O brain pode nao funcionar.
) else (
    echo [OK] llama3.2 baixado com sucesso!
)
goto check_moondream

:llama_ok
echo [OK] llama3.2 ja esta disponivel.

:check_moondream
:: --- Verifica moondream (Vision) ---
docker exec akane_ollama ollama list 2>nul | findstr /i "moondream" >nul 2>&1
if !errorlevel! equ 0 goto moondream_ok

echo [!] Baixando modelo moondream (vision)... Pode demorar na primeira vez.
docker exec akane_ollama ollama pull moondream
if !errorlevel! neq 0 (
    echo [WARN] Falha ao baixar moondream. A visao pode nao funcionar.
) else (
    echo [OK] moondream baixado com sucesso!
)
goto models_done

:moondream_ok
echo [OK] moondream ja esta disponivel.

:models_done
echo.
echo [OK] Todos os modelos verificados!
echo.

:: ────────────────────────────────────────────────
:: 4. Iniciar Akane
:: ────────────────────────────────────────────────
echo =============================================================
echo [!] Loading ServiceContext, Async Modules, and MCP Tools...
echo [!] Starting Pipeline (Local/Cloud Hybrid)...
echo [!] Waking up Akane's Brain...
echo.
echo =============================================================
echo [CONTROLS]
echo - Hold [F2] to talk. Release to send text to Akane.
echo - Hold [F2] while she is speaking to interrupt her (Barge-in).
echo.
echo [WEB DASHBOARD]
echo - If enabled, accessible at: http://127.0.0.1:8080
echo =============================================================
echo.
set PYTHONPATH=src
uv run python -m akane_den.main
pause
endlocal
