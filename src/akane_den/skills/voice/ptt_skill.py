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

        def _on_press_thread(k):
            try:
                asyncio.run_coroutine_threadsafe(self._on_press(k), loop)
            except Exception as e:
                logger.error(f"Erro ao agendar _on_press: {e}")

        def _on_release_thread(k):
            try:
                asyncio.run_coroutine_threadsafe(self._on_release(k), loop)
            except Exception as e:
                logger.error(f"Erro ao agendar _on_release: {e}")

        def _start_listener():
            self._listener = keyboard.Listener(
                on_press=_on_press_thread,
                on_release=_on_release_thread,
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
        # Se os objetos forem idênticos (ex: Key.f2 == Key.f2)
        if self._ptt_key and key == self._ptt_key:
            return True
        
        # Se for um caractere (ex: 'v')
        if hasattr(key, "char") and key.char:
            if key.char.lower() == str(self.config.ptt_key).lower():
                return True
                
        # Proteção extra: comparar via string representação
        key_str = str(key).replace("Key.", "").replace("'", "").lower()
        if key_str == str(self.config.ptt_key).lower():
            return True
            
        return False

    async def _on_press(self, key) -> None:
        """Handler de tecla pressionada."""
        if not self._is_ptt_key(key):
            return

        if self._recording:
            return

        self._recording = True
        self._audio_buffer = []

        # Emite barge-in se a Akane estiver falando
        if self.event_bus.has_listeners("barge_in"):
            await self.event_bus.emit("barge_in", {})

        await self.event_bus.emit("ptt_pressed", {})

        logger.info("🎤 PTT: F2 Pressionado! Gravação iniciada.")

        # Inicia gravação em thread separada
        loop = asyncio.get_running_loop()
        asyncio.create_task(self._record_audio())

    async def _on_release(self, key) -> None:
        """Handler de tecla solta."""
        if not self._is_ptt_key(key):
            return
            
        if not self._recording:
            return

        self._recording = False
        await self.event_bus.emit("ptt_released", {})
        logger.info(f"🎙 PTT: F2 Solto! Processando {len(self._audio_buffer)} chunks de áudio...")

        if self._audio_buffer:
            audio = np.concatenate(self._audio_buffer)
            # Emite áudio para processamento STT (fire_and_forget:
            # o handler de tecla retorna imediato, transcrição em background)
            await self.event_bus.emit("user_speech_ready", {
                "audio": audio,
                "sample_rate": self._sample_rate,
            }, fire_and_forget=True)

    async def _record_audio(self) -> None:
        """Grava áudio do microfone enquanto PTT está pressionado."""
        loop = asyncio.get_running_loop()

        def _record_sync():
            import queue

            q = queue.Queue()

            def callback(indata, frames, time, status):
                if status:
                    logger.warning(f"Audio status: {status}")
                if self._recording:
                    q.put(indata.copy())

            # Usa um InputStream contínuo em vez de reiniciar o sd.rec() repetidamente.
            # sd.rec reinicia o hardware de áudio a cada chamada, o que come a maior parte do tempo.
            try:
                with sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=callback,
                ):
                    while self._recording:
                        # Espera passivamente até que self._recording fique False,
                        # mas processa a fila
                        import time
                        time.sleep(0.01)
                        while not q.empty():
                            self._audio_buffer.append(q.get().flatten())
                            
                    # Pega o que sobrou na fila após encerrar
                    while not q.empty():
                        self._audio_buffer.append(q.get().flatten())

            except Exception as e:
                logger.error(f"Erro na gravação contínua: {e}")

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
