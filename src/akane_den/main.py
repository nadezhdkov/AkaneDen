"""
Main Orchestrator — AkaneDen v3.0 (Shogun Async).

Ponto de entrada principal do sistema. Inicializa e coordena:
1. Config (Pydantic) → ServiceContext → Skills
2. Brain (LangGraph) com streaming + persistência SQLite
3. Pipeline de voz (PTT → STT → Brain → TTS) com Faster First Response
4. VTube Studio (expressões + mouse tracking)
5. Visão ambiental (screenshots + webcam)
6. MCP tools (DuckDuckGo, Stagehand, ImageGen)
7. Memória de longo prazo (ChromaDB/Letta)
8. [v3.5] Web Dashboard (config manager)

"Eu sou o maestro dessa orquestra digital. Cada skill é um
instrumento, e eu faço todos tocarem em harmonia.
...Menos você. Você é o triângulo." — Akane
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from loguru import logger


async def main() -> None:
    """Ponto de entrada principal do AkaneDen v3.0."""
    # ──────────────────────────────────────────
    # 1. Carrega variáveis de ambiente e silenciamentos
    # ──────────────────────────────────────────
    from dotenv import load_dotenv
    load_dotenv()

    # Oculta aviso chato de symlink do HuggingFace Hub no Windows
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

    logger.info("=" * 60)
    logger.info("  AkaneDen v3.0 — Shogun Async Architecture")
    logger.info("  'Não é como se eu quisesse acordar...'")
    logger.info("=" * 60)

    # ──────────────────────────────────────────
    # 2. Carrega e valida config
    # ──────────────────────────────────────────
    from akane_den.core.config_loader import load_config
    config = load_config()
    logger.info(f"Config: brain={config.brain.provider}, tts={config.tts.default_engine}, asr={config.asr.provider}")

    # ──────────────────────────────────────────
    # 3. Cria ServiceContext (instancia engines)
    # ──────────────────────────────────────────
    from akane_den.core.service_context import ServiceContext
    service = await ServiceContext.create(config)

    # ──────────────────────────────────────────
    # 4. Inicializa memória de longo prazo
    # ──────────────────────────────────────────
    from akane_den.brain.memory_handler import create_memory_handler
    memory = create_memory_handler(config.memory)
    if memory:
        try:
            await memory.setup()
        except Exception as e:
            logger.warning(f"Memória não inicializada: {e}")
            memory = None

    # ──────────────────────────────────────────
    # 5. Coleta MCP tools
    # ──────────────────────────────────────────
    from akane_den.core.mcp_handler import MCPToolRegistry
    mcp_tools = MCPToolRegistry.get_tools(config.mcp)

    # ──────────────────────────────────────────
    # 6. Inicializa o Brain (LangGraph + streaming)
    # ──────────────────────────────────────────
    from akane_den.brain.graph_state import AkaneBrain
    brain = AkaneBrain(service)
    await brain.setup(tools=mcp_tools, memory=memory)

    # ──────────────────────────────────────────
    # 7. Registra e inicializa Skills
    # ──────────────────────────────────────────
    from akane_den.core.skill_manager import SkillManager
    from akane_den.skills.voice.ptt_skill import PTTSkill
    from akane_den.skills.voice.stt_skill import STTSkill
    from akane_den.skills.voice.tts_skill import TTSSkill
    from akane_den.skills.vision.screen_vision_skill import ScreenVisionSkill
    from akane_den.skills.system.proactive_speak_skill import ProactiveSpeakSkill
    from akane_den.skills.live.twitch_chat_skill import TwitchChatSkill
    from akane_den.skills.vtube.expression_skill import ExpressionSkill
    from akane_den.skills.vtube.mouse_tracker_skill import MouseTrackerSkill
    from akane_den.skills.vtube.lipsync_skill import LipSyncSkill

    manager = SkillManager()
    manager.register(PTTSkill(service))
    manager.register(STTSkill(service))
    manager.register(TTSSkill(service))
    manager.register(ScreenVisionSkill(service))
    manager.register(ProactiveSpeakSkill(service, timeout_seconds=300))
    manager.register(TwitchChatSkill(service))
    manager.register(ExpressionSkill(service))
    manager.register(MouseTrackerSkill(service))
    manager.register(LipSyncSkill(service))

    await manager.setup_all()

    # ──────────────────────────────────────────
    # 8. Configura o pipeline de conversação
    # ──────────────────────────────────────────
    from akane_den.core.pipeline import ConversationPipeline

    tts_skill: TTSSkill = manager.get_skill("tts")
    vision_skill: ScreenVisionSkill = manager.get_skill("screen_vision")

    pipeline = ConversationPipeline(
        service=service,
        brain=brain,
        tts_skill=tts_skill,
        vision_skill=vision_skill,
        config=config,
    )
    pipeline.register_handlers()

    # ──────────────────────────────────────────
    # 10. Boot message
    # ──────────────────────────────────────────
    logger.success("="  * 60)
    logger.success("  AkaneDen v3.5 ONLINE!")
    logger.success(f"  Brain: {service.llm.model_name}")
    logger.success(f"  TTS: {service.tts.engine_name}")
    logger.success(f"  ASR: {service.asr.engine_name}")
    logger.success(f"  VAD: {service.vad.engine_name if service.vad else 'Desativado (PTT)'}")
    logger.success(f"  Tools: {len(mcp_tools)} MCP tools ativos")
    logger.success(f"  Memory: {memory.backend_name if memory else 'desabilitada'}")
    logger.success(f"  ChatHistory: {'SQLite' if service.chat_history else 'desabilitado'}")
    logger.success(f"  Skills: {len(manager)} registradas")
    logger.success(f"  PTT Key: {config.ptt_key}")
    logger.success("=" * 60)
    logger.success("  Segure [F2] para falar com a Akane.")
    logger.success("  Ctrl+C para encerrar.")
    logger.success("=" * 60)

    # ──────────────────────────────────────────
    # 11. Web Dashboard (opcional)
    # ──────────────────────────────────────────
    dashboard_thread = None
    if config.dashboard.enabled:
        import threading

        from akane_den.server.app import create_dashboard_app

        main_loop = asyncio.get_running_loop()
        dash_app = create_dashboard_app(service_context=service, main_loop=main_loop)
        dash_host = config.dashboard.host
        dash_port = config.dashboard.port

        def _run_dashboard():
            import uvicorn
            uvicorn.run(
                dash_app, host=dash_host, port=dash_port,
                log_level="warning",
            )

        dashboard_thread = threading.Thread(
            target=_run_dashboard, daemon=True, name="dashboard"
        )
        dashboard_thread.start()
        logger.success(
            f"  Dashboard: http://{dash_host}:{dash_port}"
        )
    else:
        logger.info("  Dashboard: desativado (dashboard.enabled=false)")

    # ──────────────────────────────────────────
    # 12. Boot TTS
    # ──────────────────────────────────────────
    try:
        await tts_skill.execute(
            text="Hmpf! Estou online, baka. "
                 "Não pense que eu estava ansiosa pra te ver! "
                 "Agora fala logo o que você quer.",
            emotion="tedio",
        )
    except Exception:
        pass  # Boot message é opcional

    # ──────────────────────────────────────────
    # 13. Main loop — mantém o sistema vivo
    # ──────────────────────────────────────────
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown solicitado...")
    finally:
        # Fecha ChatHistory
        if service.chat_history:
            service.chat_history.close()
        await manager.teardown_all()
        logger.info("AkaneDen v3.5 encerrado. Até a próxima, baka.")


def cli_entry() -> None:
    """Ponto de entrada CLI: `akane` command."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_entry()
