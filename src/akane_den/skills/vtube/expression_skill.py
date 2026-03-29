"""
ExpressionSkill v3.0 — Controle de expressões faciais no VTube Studio.

Dispara expressões baseadas nas emoções detectadas pelo EmotionAnalyzer.
Conecta via WebSocket ao VTube Studio API.

Migrada para ServiceContext na v3.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class ExpressionSkill(BaseSkill):
    """Skill de expressões faciais no VTube Studio."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="expression",
            min_cooldown=1.0,
            max_cooldown=3.0,
        )
        super().__init__(ctx, service)
        self._vts = None
        self._connected = False
        self._emotion_map = service.config.vtube.emotion_map

    async def setup(self) -> None:
        """Conecta ao VTube Studio."""
        try:
            import pyvts

            plugin_info = {
                "plugin_name": "AkaneExpression",
                "developer": "rickm",
                "authentication_token_path": "./vts_token_expr.txt",
            }

            self._vts = pyvts.vts(
                plugin_info=plugin_info,
                vts_port=self.config.vtube.port,
            )
            await self._vts.connect()
            await self._vts.request_authenticate_token()
            await self._vts.request_authenticate()
            self._connected = True

            # Registra listener para emoções
            self.event_bus.on("emotion_detected", self._on_emotion)

            logger.info("ExpressionSkill conectada ao VTube Studio.")

        except Exception as e:
            logger.warning(f"VTube Studio não disponível: {e}")
            self._connected = False

    async def _on_emotion(self, data: dict) -> None:
        """Handler: aplica expressão baseada na emoção."""
        emotion = data.get("emotion", "neutro")
        await self.trigger_expression(emotion)

    async def trigger_expression(self, emotion: str) -> None:
        """Dispara expressão facial no VTube Studio."""
        if not self._connected or not self._vts:
            return

        expression_file = self._emotion_map.get(emotion)
        if not expression_file:
            return

        try:
            req = self._vts.vts_request.requestTriggerHotkey(expression_file)
            await self._vts.request(req)
            logger.debug(f"Expressão disparada: {emotion} -> {expression_file}")
        except Exception as e:
            logger.error(f"Erro ao disparar expressão: {e}")
            self._connected = False

    async def execute(self, **kwargs) -> dict:
        """Dispara expressão manualmente."""
        emotion = kwargs.get("emotion", "neutro")
        await self.trigger_expression(emotion)
        return {"expression": emotion, "connected": self._connected}

    async def teardown(self) -> None:
        if self._vts:
            try:
                await self._vts.close()
            except Exception:
                pass
        await super().teardown()
        logger.info("ExpressionSkill encerrada.")
