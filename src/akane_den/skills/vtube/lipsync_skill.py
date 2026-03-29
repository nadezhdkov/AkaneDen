"""
LipSyncSkill v3.1 — Sincronização Labial (Fake Lip Sync) para VTube Studio.

Ouve os eventos do EventBus emitidos pelo TTSSkill e injeta o parâmetro
MouthOpen no VTube Studio gerando uma oscilação natural durante a fala.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class LipSyncSkill(BaseSkill):
    """Skill de Lip Sync Dinâmico (MouthOpen)."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="lipsync",
            min_cooldown=0.0,
            max_cooldown=0.0,
        )
        super().__init__(ctx, service)
        self._vts = None
        self._connected = False
        self._is_speaking = False
        self._sync_task: asyncio.Task | None = None

    async def setup(self) -> None:
        """Conecta ao VTS e registra listeners."""
        # Checa se o lip sync está habilitado no config
        if not getattr(self.config.vtube, "lip_sync", True):
            logger.info("LipSync desabilitado no config.")
            return

        try:
            import pyvts

            plugin_info = {
                "plugin_name": "AkaneLipSync",
                "developer": "rickm",
                "authentication_token_path": "./vts_token_lipsync.txt",
            }
            self._vts = pyvts.vts(
                plugin_info=plugin_info,
                vts_port=self.config.vtube.port,
            )
            await self._vts.connect()
            await self._vts.request_authenticate_token()
            await self._vts.request_authenticate()
            self._connected = True

            # Ouve eventos do TTSSkill
            self.event_bus.on("tts_speaking_start", self._on_speaking_start)
            self.event_bus.on("tts_speaking_stop", self._on_speaking_stop)

            logger.info("LipSyncSkill conectada ao VTube Studio.")

        except Exception as e:
            logger.warning(f"LipSync não pôde iniciar: {e}")
            self._connected = False

    async def _on_speaking_start(self, data: dict) -> None:
        """Inicia o loop de movimentação labial se já não estiver rodando."""
        if not self._connected:
            return

        self._is_speaking = True
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(self._lipsync_loop())

    async def _on_speaking_stop(self, data: dict) -> None:
        """Para o loop labial e fecha a boca."""
        self._is_speaking = False
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        
        # Garante que a boca fecha quando parar de falar
        if self._connected:
            await self._inject("MouthOpen", 0.0)

    async def _lipsync_loop(self) -> None:
        """Suscita oscilações parametrizadas enquanto a fala ativa estiver True."""
        base_interval = 0.08
        smoothing = getattr(self.config.vtube, "lip_smoothing", 0.3)
        sensitivity = getattr(self.config.vtube, "lip_sensitivity", 1.0)
        
        current_val = 0.0

        while self._active and self._connected and self._is_speaking:
            try:
                # Gera um target aleatório ponderado (simulando sílabas)
                # Probabilidade maior de fechar um pouco ou abrir mais
                if random.random() > 0.7:
                    target = 0.0  # Pausa breve / consoante fechada
                else:
                    target = random.uniform(0.3, 1.0) * sensitivity

                # Clamp para garantir que não passe de 1.0
                target = min(1.0, target)

                # Aplica smoothing (interpolação)
                current_val += (1.0 - smoothing) * (target - current_val)

                await self._inject("MouthOpen", current_val)
                
                # Variação do tempo de sílaba
                await asyncio.sleep(base_interval * random.uniform(0.8, 1.2))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no loop de lipsync: {e}")
                break

    async def _inject(self, param: str, value: float) -> None:
        """Injeta ou sobrescreve um parâmetro no VTube Studio."""
        if not self._vts:
            return
        try:
            req = self._vts.vts_request.requestSetParameterValue(
                parameter=param, value=value,
            )
            await self._vts.request(req)
        except Exception:
            pass

    async def execute(self, **kwargs) -> dict:
        return {
            "active": self._connected,
            "is_speaking": self._is_speaking,
        }

    async def teardown(self) -> None:
        self._active = False
        self._is_speaking = False
        if self._sync_task:
            self._sync_task.cancel()
        if self._connected and self._vts:
            await self._inject("MouthOpen", 0.0)
            try:
                await self._vts.close()
            except Exception:
                pass
        await super().teardown()
        logger.info("LipSyncSkill encerrada.")
