"""
Dashboard App — FastAPI Web Dashboard para gerenciamento de configuração.

Este NÃO é um substituído do VTube Studio. É exclusivamente um
painel de controle para:
1. Editar config.yaml via interface web
2. Gerenciar personas (upload/switch)
3. Configurar chaves de API
4. Visualizar logs e status do sistema

"Um painel de controle? Hmph, pelo menos assim você para
 de cuspir cheitos mexendo direto no YAML!" — Akane
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
import asyncio


# ── Config ──

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
PERSONAS_DIR = PROJECT_ROOT / "src" / "akane_den" / "agents" / "persona"
DASHBOARD_DIR = Path(__file__).parent / "dashboard"


# ── Pydantic Request Models ──


class ConfigUpdate(BaseModel):
    """Payload para atualização parcial de config."""
    section: str  # ex: "tts", "brain", "asr"
    data: dict[str, Any]


class APIKeyUpdate(BaseModel):
    """Payload para atualização de chave de API."""
    key_name: str
    key_value: str


# ── App Factory ──


def create_dashboard_app(service_context=None, main_loop=None) -> FastAPI:
    """Cria a aplicação FastAPI do Web Dashboard."""

    app = FastAPI(
        title="AkaneDen Dashboard",
        description="Painel de Controle da Akane — Config, Personas, API Keys",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rotas: Config ──

    @app.get("/api/config", response_class=JSONResponse)
    async def get_config():
        """Retorna o config.yaml completo como JSON."""
        try:
            config = _load_yaml(CONFIG_PATH)
            return JSONResponse(content=config)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/config", response_class=JSONResponse)
    async def update_config(update: ConfigUpdate):
        """Atualiza uma seção específica do config.yaml.

        Body:
            section: "tts", "brain", "asr", etc.
            data: { "default_engine": "edge", ... }
        """
        try:
            config = _load_yaml(CONFIG_PATH)
            akane = config.get("akane", {})

            if update.section in akane:
                if isinstance(akane[update.section], dict):
                    akane[update.section].update(update.data)
                else:
                    akane[update.section] = update.data
            else:
                akane[update.section] = update.data

            config["akane"] = akane
            _save_yaml(CONFIG_PATH, config)

            # Recarrega no loop principal
            _trigger_reload(config)

            logger.info(f"Dashboard: Config '{update.section}' atualizado.")
            return {"status": "ok", "section": update.section}

        except Exception as e:
            logger.error(f"Dashboard: Erro ao salvar config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/config/full", response_class=JSONResponse)
    async def update_full_config(config_data: dict):
        """Substitui o config.yaml inteiro (uso avançado)."""
        try:
            _save_yaml(CONFIG_PATH, config_data)
            _trigger_reload(config_data)
            logger.info("Dashboard: Config completo substituído.")
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Rotas: Personas ──

    @app.get("/api/personas", response_class=JSONResponse)
    async def list_personas():
        """Lista todas as personas disponíveis."""
        PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
        personas = []
        for f in PERSONAS_DIR.glob("*.yaml"):
            try:
                content = _load_yaml(f)
                personas.append({
                    "filename": f.name,
                    "name": content.get("name", f.stem),
                    "archetype": content.get("archetype", ""),
                    "description": content.get("description", "")[:100],
                })
            except Exception:
                personas.append({"filename": f.name, "name": f.stem, "error": True})
        return JSONResponse(content=personas)

    @app.get("/api/personas/{filename}", response_class=JSONResponse)
    async def get_persona(filename: str):
        """Retorna o conteúdo de um arquivo de persona."""
        filepath = PERSONAS_DIR / filename
        if not filepath.exists():
            raise HTTPException(status_code=404, detail="Persona não encontrada")
        content = _load_yaml(filepath)
        return JSONResponse(content=content)

    @app.post("/api/personas/upload", response_class=JSONResponse)
    async def upload_persona(file: UploadFile = File(...)):
        """Upload de um novo arquivo de persona YAML."""
        if not file.filename.endswith((".yaml", ".yml")):
            raise HTTPException(
                status_code=400,
                detail="Apenas arquivos .yaml são aceitos, baka!",
            )

        PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
        content = await file.read()

        # Valida YAML
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=400,
                detail=f"YAML inválido: {e}",
            )

        filepath = PERSONAS_DIR / file.filename
        filepath.write_bytes(content)
        logger.info(f"Dashboard: Persona '{file.filename}' uploaded.")
        return {"status": "ok", "filename": file.filename}

    @app.put("/api/personas/switch/{persona_name}", response_class=JSONResponse)
    async def switch_persona(persona_name: str):
        """Troca a persona ativa no config.yaml."""
        config = _load_yaml(CONFIG_PATH)
        config.setdefault("akane", {})["persona"] = persona_name
        _save_yaml(CONFIG_PATH, config)
        _trigger_reload(config)
        logger.info(f"Dashboard: Persona trocada para '{persona_name}'.")
        return {"status": "ok", "persona": persona_name}

    # ── Rotas: API Keys ──

    @app.get("/api/keys", response_class=JSONResponse)
    async def list_api_keys():
        """Lista as chaves de API configuradas (mascaradas)."""
        import os

        keys_of_interest = [
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
            "OPENAI_API_KEY",
            "ELEVENLABS_API_KEY",
            "FAL_KEY",
        ]
        result = {}
        for key in keys_of_interest:
            val = os.environ.get(key, "")
            if val:
                result[key] = f"{val[:4]}...{val[-4:]}" if len(val) > 8 else "***"
            else:
                result[key] = None

        return JSONResponse(content=result)

    @app.put("/api/keys", response_class=JSONResponse)
    async def update_api_key(update: APIKeyUpdate):
        """Atualiza uma chave de API no .env."""
        env_path = PROJECT_ROOT / ".env"
        lines = []

        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        # Encontra e substitui, ou adiciona
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{update.key_name}="):
                lines[i] = f"{update.key_name}={update.key_value}"
                found = True
                break

        if not found:
            lines.append(f"{update.key_name}={update.key_value}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Atualiza em runtime
        import os
        os.environ[update.key_name] = update.key_value

        logger.info(f"Dashboard: API key '{update.key_name}' atualizada.")
        return {"status": "ok", "key": update.key_name}

    # ── Rotas: Status ──

    @app.get("/api/status", response_class=JSONResponse)
    async def get_status():
        """Retorna status do sistema (básico)."""
        return {
            "status": "online",
            "version": "3.0.0",
            "config_path": str(CONFIG_PATH),
            "personas_dir": str(PERSONAS_DIR),
        }

    # ── Logs & Telemetry SSE ──

    # Fila de broadcast para clientes SSE
    log_clients = set()

    def logs_sink(msg):
        # Envia a mensagem apenas se houver clientes
        if log_clients:
            record = msg.record
            data = {
                "time": record["time"].strftime("%H:%M:%S"),
                "level": record["level"].name,
                "message": record["message"],
            }
            json_data = json.dumps(data)
            # Envia via queue para os clientes (thread-safe no loop do fastapi)
            for queue in list(log_clients):
                queue.put_nowait(json_data)

    # Adiciona o sink do loguru para o dashboard
    logger.add(logs_sink, format="{message}", level="DEBUG", enqueue=True)

    @app.get("/api/logs/stream")
    async def stream_logs():
        """Endpoint SSE para emitir logs em tempo real ao Dashboard."""
        queue = asyncio.Queue()
        log_clients.add(queue)

        async def event_generator():
            try:
                # Envia um evento de conexão inicial
                yield f"data: {json.dumps({'time': '', 'level': 'INFO', 'message': 'Conectado ao AkaneDen SSE Logs'})}\n\n"
                while True:
                    # Trava até ter log
                    log_json = await queue.get()
                    yield f"data: {log_json}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                log_clients.discard(queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # ── Dashboard HTML ──

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page():
        """Serve o Web Dashboard (SPA)."""
        html_path = DASHBOARD_DIR / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

        # Fallback inline template
        return HTMLResponse(content=_get_fallback_html())

    # Helper function for triggering reload in the main event loop
    def _trigger_reload(config_data: dict):
        if service_context and main_loop:
            import asyncio
            from akane_den.core.config import AkaneConfig
            
            try:
                new_akane = AkaneConfig(**config_data.get("akane", {}))
                asyncio.run_coroutine_threadsafe(
                    service_context.reload_config(new_akane), main_loop
                )
                logger.info("Dashboard: sinal de reload do ServiceContext disparado.")
            except Exception as e:
                logger.error(f"Dashboard falhou ao disparar reload_config: {e}")

    return app


# ── Helpers ──


def _load_yaml(path: Path) -> dict:
    """Carrega arquivo YAML."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict) -> None:
    """Salva dicionário em YAML com formatação."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2,
        )


def _get_fallback_html() -> str:
    """HTML de fallback se o arquivo dashboard não existir."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>AkaneDen Dashboard</title></head>
    <body style="background:#111;color:#eee;font-family:sans-serif;text-align:center;padding:50px">
        <h1>🏯 AkaneDen Dashboard</h1>
        <p>Dashboard HTML not found. Place index.html in server/dashboard/</p>
    </body>
    </html>
    """


# ── Standalone Entry ──


def run_dashboard(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Roda o Dashboard como servidor standalone."""
    import uvicorn

    app = create_dashboard_app()
    logger.info(f"Dashboard rodando em http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_dashboard()
