"""
Main Orchestrator — AkaneDen v3.0 (Shogun Async).

Ponto de entrada principal do sistema. Inicializa e coordena:
1. Config (Pydantic) → ServiceContext → Skills
2. Brain (LangGraph) com streaming
3. Pipeline de voz (PTT → STT → Brain → TTS) com Faster First Response
4. VTube Studio (expressões + mouse tracking)
5. Visão ambiental (screenshots + webcam)
6. MCP tools (DuckDuckGo, Stagehand, ImageGen)
7. Memória de longo prazo (ChromaDB/Letta)

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
    # 1. Carrega variáveis de ambiente
    # ──────────────────────────────────────────
    from dotenv import load_dotenv
    load_dotenv()

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
    from akane_den.skills.vtube.expression_skill import ExpressionSkill
    from akane_den.skills.vtube.mouse_tracker_skill import MouseTrackerSkill

    manager = SkillManager()
    manager.register(PTTSkill(service))
    manager.register(STTSkill(service))
    manager.register(TTSSkill(service))
    manager.register(ScreenVisionSkill(service))
    manager.register(ExpressionSkill(service))
    manager.register(MouseTrackerSkill(service))

    await manager.setup_all()

    # Referências rápidas
    tts_skill: TTSSkill = manager.get_skill("tts")

    # ──────────────────────────────────────────
    # 8. Configura o pipeline de conversação
    # ──────────────────────────────────────────
    vision_skill: ScreenVisionSkill = manager.get_skill("screen_vision")

    async def on_user_text(data: dict) -> None:
        """Pipeline completo: texto → brain → TTS streaming."""
        user_text = data.get("text", "")
        if not user_text:
            return

        logger.info(f"Usuário: '{user_text}'")

        # Contexto visual (se disponível)
        vision_ctx = None
        if vision_skill and vision_skill.last_description:
            vision_ctx = vision_skill.last_description

        # Captura screenshot fresco se configurado
        if vision_skill and config.vision.enabled:
            try:
                result = await asyncio.wait_for(
                    vision_skill.execute(source="screen"),
                    timeout=5.0,
                )
                if "description" in result:
                    vision_ctx = result["description"]
            except asyncio.TimeoutError:
                logger.debug("Timeout na captura de visão — usando cache.")
            except Exception as e:
                logger.debug(f"Visão não disponível: {e}")

        # ⚡ STREAMING: Brain gera → TTS sintetiza sentença por sentença
        sentence_stream = brain.think_stream(
            user_text=user_text,
            vision_context=vision_ctx,
        )

        # Intercepta o stream para analisar emoção e disparar expressão
        async def emotion_aware_stream():
            first_sentence = True
            async for sentence in sentence_stream:
                # Analisa emoção na primeira sentença
                if first_sentence:
                    emotion, score = brain.analyze_emotion(sentence)
                    await service.event_bus.emit("emotion_detected", {
                        "emotion": emotion,
                        "score": score,
                    })
                    logger.info(
                        f"Akane ({emotion}): '{sentence[:60]}...'"
                    )
                    first_sentence = False
                yield sentence

        # Fala em streaming (Faster First Response)
        await tts_skill.speak_streaming(emotion_aware_stream())

    # Registra o pipeline no EventBus
    service.event_bus.on("user_text_ready", on_user_text)

    # ──────────────────────────────────────────
    # 9. Barge-in handler
    # ──────────────────────────────────────────
    async def on_barge_in(data: dict) -> None:
        """Interrompe TTS quando o usuário pressiona PTT."""
        await tts_skill.stop_speaking()
        logger.debug("Barge-in: TTS interrompido.")

    service.event_bus.on("barge_in", on_barge_in)

    # ──────────────────────────────────────────
    # 10. Boot message
    # ──────────────────────────────────────────
    logger.success("=" * 60)
    logger.success("  AkaneDen v3.0 ONLINE!")
    logger.success(f"  Brain: {service.llm.model_name}")
    logger.success(f"  TTS: {service.tts.engine_name}")
    logger.success(f"  ASR: {service.asr.engine_name}")
    logger.success(f"  Tools: {len(mcp_tools)} MCP tools ativos")
    logger.success(f"  Memory: {memory.backend_name if memory else 'desabilitada'}")
    logger.success(f"  Skills: {len(manager)} registradas")
    logger.success(f"  PTT Key: {config.ptt_key}")
    logger.success("=" * 60)
    logger.success("  Segure [F2] para falar com a Akane.")
    logger.success("  Ctrl+C para encerrar.")
    logger.success("=" * 60)

    # Boot TTS — Akane se apresenta
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
    # 11. Main loop — mantém o sistema vivo
    # ──────────────────────────────────────────
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown solicitado...")
    finally:
        await manager.teardown_all()
        logger.info("AkaneDen v3.0 encerrado. Até a próxima, baka.")


def cli_entry() -> None:
    """Ponto de entrada CLI: `akane` command."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_entry()
