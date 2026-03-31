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
    """Skill de visão: analisa tela e webcam com Gemini Vision.

    v3.5: Rate limiting inteligente com backoff exponencial.
    Detecta 429 (quota exceeded) e pausa automaticamente em vez
    de spammar o log com erros a cada 20s.
    """

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
        # Rate limiting
        self._backoff_until: float = 0.0  # timestamp até quando pausar
        self._consecutive_429s: int = 0
        self._quota_exhausted: bool = False
        self._inference_running: bool = False  # Trava contra inferências paralelas

    async def setup(self) -> None:
        """Inicializa o modelo Gemini ou Ollama Vision."""
        provider = self.config.vision.provider

        if provider == "gemini":
            try:
                import google.generativeai as genai

                api_key = os.environ.get("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._model = genai.GenerativeModel(
                        self.config.vision.gemini_model
                    )
                    logger.info(
                        f"ScreenVisionSkill pronta (Gemini): "
                        f"model={self.config.vision.gemini_model}"
                    )
                else:
                    logger.warning("GOOGLE_API_KEY não encontrada. Gemini Vision desabilitada.")
            except ImportError:
                logger.warning("google-generativeai não instalado.")
        elif provider == "ollama":
            self._model = "ollama"  # Marca como ativo
            logger.info(
                f"ScreenVisionSkill pronta (Ollama): "
                f"model={self.config.vision.vision_model} "
                f"@{self.config.vision.ollama_base_url}"
            )
        else:
            logger.warning(f"Provider de visão '{provider}' desconhecido.")

        # Auto-capture se configurado e modelo ativo
        if self._model:
            interval = self.config.vision.auto_capture_interval
            if interval > 0:
                self._auto_task = asyncio.create_task(
                    self._auto_capture_loop(interval)
                )
                logger.info(
                    f"Auto-capture ativo: a cada {interval}s"
                )

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

    def _is_rate_limited(self) -> bool:
        """Verifica se estamos em período de backoff."""
        if self._quota_exhausted:
            return True
        return time.time() < self._backoff_until

    def _handle_rate_limit(self, error_msg: str) -> None:
        """Aplica backoff exponencial em erros 429."""
        self._consecutive_429s += 1

        # Extrai retry_delay do erro se disponível
        import re
        retry_match = re.search(r"retry in ([\d.]+)s", error_msg, re.IGNORECASE)
        if retry_match:
            wait_seconds = float(retry_match.group(1)) + 5  # margem extra
        else:
            # Backoff exponencial: 30s, 60s, 120s, 240s, ...
            wait_seconds = min(30 * (2 ** (self._consecutive_429s - 1)), 600)

        # Se atingiu free tier diário, pausa até resetar
        if "FreeTier" in error_msg or self._consecutive_429s >= 3:
            self._quota_exhausted = True
            logger.warning(
                f"🛑 Gemini Vision: quota FREE TIER esgotada! "
                f"Auto-capture PAUSADO até reiniciar o sistema. "
                f"(Dica: aumente auto_capture_interval ou use API paga)"
            )
            return

        self._backoff_until = time.time() + wait_seconds
        logger.warning(
            f"⏳ Gemini Vision: backoff de {wait_seconds:.0f}s "
            f"(429 #{self._consecutive_429s})"
        )

    async def _analyze_screen(self, prompt: str) -> dict:
        """Captura screenshot e analisa com a Visão."""
        if not self._model:
            return {"error": "Modelo de Visão não disponível."}

        if self._is_rate_limited():
            return {"description": self._last_description, "cached": True}

        # Se já tem uma inferência rodando, retorna cache em vez de enfileirar
        if self._inference_running:
            logger.debug("Visão: inferência já em andamento, usando cache.")
            return {"description": self._last_description, "cached": True}

        loop = asyncio.get_running_loop()

        # Captura screenshot e converte em thread para não bloquear o event loop
        def _capture_and_encode():
            from PIL import ImageGrab
            import io
            screenshot = ImageGrab.grab()
            
            max_size = 768
            width, height = screenshot.size
            if max(width, height) > max_size:
                if width > height:
                    new_w = max_size
                    new_h = int(max_size * height / width)
                else:
                    new_h = max_size
                    new_w = int(max_size * width / height)
                screenshot = screenshot.resize((new_w, new_h))

            buf = io.BytesIO()
            screenshot.save(buf, format="PNG", optimize=False)
            return buf.getvalue()

        self._inference_running = True
        try:
            img_bytes = await loop.run_in_executor(None, _capture_and_encode)

            # Envia para Gemini/Ollama Vision
            description = await self._analyze_image(img_bytes, prompt)
            self._last_description = description
            self._consecutive_429s = 0  # Reset no sucesso

            # Emite evento
            await self.event_bus.emit("screen_captured", {
                "description": description,
            })

            logger.debug(f"Visão: {description[:80]}...")
            return {"description": description}

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                self._handle_rate_limit(error_msg)
                return {"description": self._last_description, "cached": True}
            logger.error(f"Erro na captura de tela: {e}")
            return {"error": error_msg}
        finally:
            self._inference_running = False

    async def _analyze_webcam(self, prompt: str) -> dict:
        """Captura frame da webcam e analisa com Visão."""
        if not self._model:
            return {"error": "Modelo de Visão não disponível."}

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
                
                max_size = 768
                width, height = img.size
                if max(width, height) > max_size:
                    if width > height:
                        new_w = max_size
                        new_h = int(max_size * height / width)
                    else:
                        new_h = max_size
                        new_w = int(max_size * width / height)
                    img = img.resize((new_w, new_h))

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
        """Envia imagem para o provedor de Visão selecionado."""
        if self.config.vision.provider == "ollama":
            import httpx

            b64_image = base64.b64encode(img_bytes).decode("utf-8")
            base = self.config.vision.ollama_base_url.rstrip("/")
            model_name = self.config.vision.vision_model

            # Usa /api/chat (multimodal) com fallback para /api/generate
            url = f"{base}/api/chat"
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64_image],
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 300,
                },
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    # /api/chat retorna message.content
                    msg = result.get("message", {})
                    return msg.get("content", result.get("response", ""))
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        # Modelo pode não ter sido baixado
                        logger.error(
                            f"Ollama Vision 404: modelo '{model_name}' "
                            f"não encontrado. Execute: "
                            f"docker exec akane_ollama ollama pull {model_name}"
                        )
                        # Desativa auto-capture para não spammar logs
                        self._quota_exhausted = True
                        return (
                            f"Modelo de visão '{model_name}' não encontrado no Ollama. "
                            f"Precisa ser baixado primeiro."
                        )
                    logger.error(f"Erro HTTP na visão Ollama: {e}")
                    return f"Desculpe, a visão local falhou: {e}"
                except httpx.ConnectError:
                    logger.error(
                        "Ollama não acessível em "
                        f"{base}. Verifique se o Docker está rodando."
                    )
                    self._quota_exhausted = True
                    return "Ollama não está acessível. Verifique o Docker."
                except Exception as e:
                    logger.error(f"Erro na visão Ollama: {e}")
                    return f"Desculpe, a visão local falhou: {e}"
        else:
            # Gemini Provider
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
        """Loop de captura automática (background).

        Aguarda a inferência terminar ANTES de dormir o intervalo,
        evitando acúmulo de requests quando CPU é lenta.
        """
        # Intervalo mínimo de segurança para CPU (evita spam)
        effective_interval = max(interval, 60)
        if effective_interval != interval:
            logger.info(
                f"Auto-capture: intervalo ajustado de {interval}s → "
                f"{effective_interval}s (mínimo seguro para CPU)"
            )

        while self._active:
            try:
                await asyncio.sleep(effective_interval)
                if self._active and self.context.can_trigger():
                    t0 = time.time()
                    await self._analyze_screen(
                        "Descreva brevemente o que o usuário está fazendo."
                    )
                    elapsed = time.time() - t0
                    self.context.mark_triggered()
                    logger.debug(
                        f"Auto-capture concluído em {elapsed:.1f}s"
                    )
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
