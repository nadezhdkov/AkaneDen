"""
STTSkill v3.3 — Speech-to-Text com ASR Engine (ProcessPool).

Escuta o evento 'user_speech_ready' (do PTTSkill), transcreve
o áudio usando o ASR Engine do ServiceContext, e emite o texto
via evento 'user_text_ready'.

v3.3: ASR Engine agora roda em ProcessPoolExecutor dedicado,
eliminando starvation do event loop durante inferência Whisper.

"Eu entendo TUDO que você fala. Até os murmúrios
patéticos que você faz quando erra o código." — Akane
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class STTSkill(BaseSkill):
    """Skill de Speech-to-Text: transcreve áudio capturado pelo PTT."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="stt",
            min_cooldown=0.0,
            max_cooldown=0.0,
        )
        super().__init__(ctx, service)

    async def setup(self) -> None:
        """Registra listener para evento de áudio."""
        self.event_bus.on("user_speech_ready", self._on_speech_ready)
        logger.info(
            f"STTSkill pronta: engine={self.service.asr.engine_name}"
        )

    async def _on_speech_ready(self, data: dict) -> None:
        """Handler: recebe áudio e transcreve."""
        audio = data.get("audio")
        sample_rate = data.get("sample_rate", 16000)

        if audio is None or len(audio) < 1600:  # < 0.1s de áudio
            logger.debug("Áudio muito curto, ignorando.")
            return

        logger.debug(
            f"Transcrevendo áudio: {len(audio)} samples "
            f"({len(audio)/sample_rate:.1f}s)"
        )

        try:
            text = await self.service.asr.transcribe(audio, sample_rate)

            if text and text.strip():
                logger.info(f"STT: '{text}'")
                await self.event_bus.emit("user_text_ready", {
                    "text": text.strip(),
                    "audio_duration": len(audio) / sample_rate,
                }, fire_and_forget=True)
            else:
                logger.debug("STT: transcrição vazia.")

        except Exception as e:
            logger.error(f"Erro na transcrição: {e}")

    async def execute(self, **kwargs) -> dict:
        """Transcrição manual (sem evento)."""
        audio = kwargs.get("audio")
        sample_rate = kwargs.get("sample_rate", 16000)

        if audio is None:
            return {"error": "Sem áudio para transcrever."}

        text = await self.service.asr.transcribe(audio, sample_rate)
        return {"text": text}

    async def teardown(self) -> None:
        self.event_bus.off("user_speech_ready", self._on_speech_ready)
        # Encerra o ProcessPoolExecutor do ASR (se disponível)
        if hasattr(self.service.asr, "shutdown"):
            self.service.asr.shutdown()
        await super().teardown()
        logger.info("STTSkill encerrada (ProcessPool liberado).")
