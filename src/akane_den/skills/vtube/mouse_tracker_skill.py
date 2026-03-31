"""
MouseTrackerSkill v3.3 — Avatar segue o cursor do mouse.

Rastreia a posição do mouse e injeta parâmetros FaceAngleX/Y
no VTube Studio, fazendo o avatar seguir o cursor em tempo real.

v3.3: Yields estratégicos para priorizar responsividade do event loop.

Migrada para ServiceContext na v3.0.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pyautogui
from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class MouseTrackerSkill(BaseSkill):
    """Skill de mouse tracking — avatar segue o cursor."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="mouse_tracker",
            min_cooldown=0.0,
            max_cooldown=0.0,
        )
        super().__init__(ctx, service)
        self._task: asyncio.Task | None = None
        self._vts = None
        self._vts_connected = False
        pyautogui.FAILSAFE = False

    async def setup(self) -> None:
        """Conecta ao VTS e inicia tracking loop."""
        if not self.config.vtube.mouse_tracking:
            logger.info("Mouse tracking desabilitado no config.")
            return

        try:
            import pyvts

            plugin_info = {
                "plugin_name": "AkaneMouseTracker",
                "developer": "rickm",
                "authentication_token_path": "./vts_token_mouse.txt",
            }
            self._vts = pyvts.vts(
                plugin_info=plugin_info,
                vts_port=self.config.vtube.port,
            )
            await self._vts.connect()
            await self._vts.request_authenticate_token()
            await self._vts.request_authenticate()
            self._vts_connected = True

            self._task = asyncio.create_task(self._tracking_loop())
            logger.info("MouseTrackerSkill ativa — avatar seguindo cursor.")

        except Exception as e:
            logger.warning(f"Mouse tracker não pôde iniciar: {e}")

    async def _tracking_loop(self) -> None:
        """Loop de tracking a ~30fps com watchdog de starvation.

        v3.3: Yields estratégicos (asyncio.sleep(0)) garantem que o
        event loop respire entre operações, priorizando responsividade.
        """
        import time

        screen_w, screen_h = pyautogui.size()
        sensitivity = self.config.vtube.mouse_sensitivity
        smooth_x, smooth_y = 0.0, 0.0
        alpha = 0.3
        last_frame = time.monotonic()

        while self._active and self._vts_connected:
            try:
                now = time.monotonic()
                delta = now - last_frame
                if delta > 0.25:
                    logger.warning(
                        f"⚠ Event Loop Starvation: {delta*1000:.0f}ms "
                        f"entre frames do mouse tracker"
                    )
                last_frame = now

                x, y = pyautogui.position()
                target_x = ((x / screen_w) - 0.5) * 60 * sensitivity
                target_y = ((y / screen_h) - 0.5) * -60 * sensitivity

                # Clamp values para sanear coordenadas de multi-monitores
                target_x = max(-30.0, min(30.0, target_x))
                target_y = max(-30.0, min(30.0, target_y))

                smooth_x += alpha * (target_x - smooth_x)
                smooth_y += alpha * (target_y - smooth_y)

                # Yield: permite que o event loop processe outros eventos
                # ANTES da injeção no VTS (prioriza responsividade)
                await asyncio.sleep(0)

                await self._inject("FaceAngleX", smooth_x)
                # Yield: respira entre as duas injeções de parâmetros
                await asyncio.sleep(0)
                await self._inject("FaceAngleY", smooth_y)
                await asyncio.sleep(0.033)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no tracking: {e}")
                break

    async def _inject(self, param: str, value: float) -> None:
        try:
            req = self._vts.vts_request.requestSetParameterValue(
                parameter=param, value=value,
            )
            await self._vts.request(req)
        except Exception:
            pass

    async def execute(self, **kwargs) -> dict:
        return {
            "active": self._vts_connected and self._task is not None,
            "sensitivity": self.config.vtube.mouse_sensitivity,
        }

    async def teardown(self) -> None:
        self._active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._vts:
            try:
                await self._vts.close()
            except Exception:
                pass
        await super().teardown()
        logger.info("MouseTrackerSkill encerrada.")
