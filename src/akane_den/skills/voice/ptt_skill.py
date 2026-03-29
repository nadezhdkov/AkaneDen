"""
PTTSkill v3.0 — Push-to-Talk com captura de áudio.

Escuta a hotkey configurada, captura áudio enquanto pressionada,
e emite evento 'user_speech_ready' com o áudio capturado.

Migrada para ServiceContext na v3.0.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd
from loguru import logger
from pynput import keyboard

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class PTTSkill(BaseSkill):
    """Skill de Push-to-Talk: captura áudio quando a hotkey é segurada."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="ptt",
            min_cooldown=0.0,
            max_cooldown=0.0,
        )
        super().__init__(ctx, service)
        self._ptt_key = getattr(keyboard.Key, service.config.ptt_key, None)
        if self._ptt_key is None:
            self._ptt_key_char = service.config.ptt_key
        else:
            self._ptt_key_char = None
        self._recording = False
        self._audio_buffer: list[np.ndarray] = []
        self._listener: keyboard.Listener | None = None
        self._sample_rate = 16000

    async def setup(self) -> None:
        """Inicia o listener de teclado em background."""
        loop = asyncio.get_running_loop()

        def _start_listener():
            self._listener = keyboard.Listener(
                on_press=lambda k: loop.call_soon_threadsafe(
                    asyncio.ensure_future, self._on_press(k)
                ),
                on_release=lambda k: loop.call_soon_threadsafe(
                    asyncio.ensure_future, self._on_release(k)
                ),
            )
            self._listener.daemon = True
            self._listener.start()

        await loop.run_in_executor(None, _start_listener)
        logger.info(
            f"PTTSkill pronta: hotkey={self.config.ptt_key} "
            f"(segure para falar)"
        )

    def _is_ptt_key(self, key) -> bool:
        """Verifica se a tecla pressionada é a hotkey PTT."""
        if self._ptt_key and key == self._ptt_key:
            return True
        if self._ptt_key_char:
            try:
                return hasattr(key, "char") and key.char == self._ptt_key_char
            except AttributeError:
                return False
        return False

    async def _on_press(self, key) -> None:
        """Handler de tecla pressionada."""
        if not self._is_ptt_key(key) or self._recording:
            return

        self._recording = True
        self._audio_buffer = []

        # Emite barge-in se a Akane estiver falando
        if self.event_bus.has_listeners("barge_in"):
            await self.event_bus.emit("barge_in", {})

        logger.debug("PTT: gravação iniciada.")

        # Inicia gravação em thread separada
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(self._record_audio())

    async def _on_release(self, key) -> None:
        """Handler de tecla solta."""
        if not self._is_ptt_key(key) or not self._recording:
            return

        self._recording = False
        logger.debug(f"PTT: gravação finalizada. Chunks: {len(self._audio_buffer)}")

        if self._audio_buffer:
            audio = np.concatenate(self._audio_buffer)
            # Emite áudio para processamento STT
            await self.event_bus.emit("user_speech_ready", {
                "audio": audio,
                "sample_rate": self._sample_rate,
            })

    async def _record_audio(self) -> None:
        """Grava áudio do microfone enquanto PTT está pressionado."""
        loop = asyncio.get_running_loop()

        def _record_sync():
            chunk_size = 1024
            while self._recording:
                try:
                    data = sd.rec(
                        chunk_size,
                        samplerate=self._sample_rate,
                        channels=1,
                        dtype="float32",
                        blocking=True,
                    )
                    self._audio_buffer.append(data.flatten())
                except Exception as e:
                    logger.error(f"Erro na gravação: {e}")
                    break

        await loop.run_in_executor(None, _record_sync)

    async def execute(self, **kwargs) -> dict:
        """Retorna status do PTT."""
        return {
            "recording": self._recording,
            "key": self.config.ptt_key,
            "buffer_chunks": len(self._audio_buffer),
        }

    async def teardown(self) -> None:
        self._recording = False
        if self._listener:
            self._listener.stop()
        await super().teardown()
        logger.info("PTTSkill encerrada.")
