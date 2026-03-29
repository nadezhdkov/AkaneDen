"""
ScreenVisionSkill v3.0 — Visão ambiental com Gemini Vision.

Captura screenshots e/ou frames da webcam e analisa com
Gemini Vision, permitindo que a Akane comente o que o
usuário está fazendo no Windows em tempo real.

"Eu VEJO tudo que você faz. Se você abrir uma aba suspeita,
eu vou saber. E vou comentar. Em público." — Akane
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import time
from typing import TYPE_CHECKING

from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class ScreenVisionSkill(BaseSkill):
    """Skill de visão: analisa tela e webcam com Gemini Vision."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="screen_vision",
            min_cooldown=5.0,
            max_cooldown=15.0,
        )
        super().__init__(ctx, service)
        self._last_description = ""
        self._model = None
        self._auto_task: asyncio.Task | None = None

    async def setup(self) -> None:
        """Inicializa o modelo Gemini Vision."""
        try:
            import google.generativeai as genai

            api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(
                    self.config.vision.gemini_model
                )
                logger.info(
                    f"ScreenVisionSkill pronta: "
                    f"model={self.config.vision.gemini_model}"
                )

                # Auto-capture se configurado
                interval = self.config.vision.auto_capture_interval
                if interval > 0:
                    self._auto_task = asyncio.create_task(
                        self._auto_capture_loop(interval)
                    )
                    logger.info(
                        f"Auto-capture ativo: a cada {interval}s"
                    )
            else:
                logger.warning("GOOGLE_API_KEY não encontrada. Vision desabilitada.")
        except ImportError:
            logger.warning("google-generativeai não instalado.")

    async def execute(self, **kwargs) -> dict:
        """Captura e analisa a tela atual."""
        source = kwargs.get("source", "screen")
        prompt = kwargs.get(
            "prompt",
            "Descreva de forma concisa o que você vê na tela. "
            "Foque no programa aberto, conteúdo visível e atividade do usuário."
        )

        if source == "webcam":
            return await self._analyze_webcam(prompt)
        else:
            return await self._analyze_screen(prompt)

    async def _analyze_screen(self, prompt: str) -> dict:
        """Captura screenshot e analisa com Gemini Vision."""
        if not self._model:
            return {"error": "Gemini Vision não disponível."}

        loop = asyncio.get_running_loop()

        # Captura screenshot em thread
        def _capture():
            from PIL import ImageGrab
            return ImageGrab.grab()

        try:
            screenshot = await loop.run_in_executor(None, _capture)

            # Converte para bytes
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            # Envia para Gemini Vision
            description = await self._analyze_image(img_bytes, prompt)
            self._last_description = description

            # Emite evento
            await self.event_bus.emit("screen_captured", {
                "description": description,
            })

            logger.debug(f"Visão: {description[:80]}...")
            return {"description": description}

        except Exception as e:
            logger.error(f"Erro na captura de tela: {e}")
            return {"error": str(e)}

    async def _analyze_webcam(self, prompt: str) -> dict:
        """Captura frame da webcam e analisa com Gemini Vision."""
        if not self._model:
            return {"error": "Gemini Vision não disponível."}

        loop = asyncio.get_running_loop()

        def _capture_webcam():
            try:
                import cv2

                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()

                if not ret:
                    return None

                # Converte BGR → RGB → PNG bytes
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                from PIL import Image
                img = Image.fromarray(frame_rgb)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            except ImportError:
                logger.warning("opencv-python não instalado para webcam.")
                return None
            except Exception as e:
                logger.error(f"Erro na webcam: {e}")
                return None

        img_bytes = await loop.run_in_executor(None, _capture_webcam)

        if not img_bytes:
            return {"error": "Webcam não disponível ou erro na captura."}

        webcam_prompt = (
            f"{prompt}\n\n"
            "Esta imagem é da webcam do usuário. "
            "Descreva o que você vê: aparência, expressão, ambiente."
        )
        description = await self._analyze_image(img_bytes, webcam_prompt)

        await self.event_bus.emit("webcam_captured", {
            "description": description,
        })

        return {"description": description, "source": "webcam"}

    async def _analyze_image(self, img_bytes: bytes, prompt: str) -> str:
        """Envia imagem para Gemini Vision e retorna descrição."""
        import google.generativeai as genai

        loop = asyncio.get_running_loop()

        def _generate_sync():
            image_part = {
                "mime_type": "image/png",
                "data": img_bytes,
            }
            response = self._model.generate_content(
                [prompt, image_part],
                generation_config=genai.GenerationConfig(
                    max_output_tokens=300,
                    temperature=0.3,
                ),
            )
            return response.text

        return await loop.run_in_executor(None, _generate_sync)

    async def _auto_capture_loop(self, interval: int) -> None:
        """Loop de captura automática (background)."""
        while self._active:
            try:
                await asyncio.sleep(interval)
                if self._active and self.context.can_trigger():
                    await self._analyze_screen(
                        "Descreva brevemente o que o usuário está fazendo."
                    )
                    self.context.mark_triggered()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no auto-capture: {e}")

    @property
    def last_description(self) -> str:
        """Última descrição da tela capturada."""
        return self._last_description

    async def teardown(self) -> None:
        if self._auto_task:
            self._auto_task.cancel()
            try:
                await self._auto_task
            except asyncio.CancelledError:
                pass
        await super().teardown()
        logger.info("ScreenVisionSkill encerrada.")
