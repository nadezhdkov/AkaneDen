"""
TTSSkill v3.0 — Text-to-Speech com Faster First Response.

O coração do pipeline de voz assíncrono. Suporta dois modos:
1. Batch: espera texto completo → sintetiza → reproduz
2. Streaming: sintetiza CADA SENTENÇA assim que fica pronta

O modo streaming é o "Faster First Response" — a Akane começa
a falar a primeira sentença enquanto o Gemini ainda gera o resto.

"Agora eu falo enquanto PENSO. Chama isso de multitasking,
e antes que você pergunte — sim, humanos não conseguem." — Akane
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import TYPE_CHECKING, AsyncIterator

from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class TTSSkill(BaseSkill):
    """Skill de Text-to-Speech com suporte a streaming (Faster First Response)."""

    def __init__(self, service: "ServiceContext") -> None:
        ctx = SkillContext(
            skill_name="tts",
            min_cooldown=0.0,
            max_cooldown=0.0,
        )
        super().__init__(ctx, service)
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._is_speaking = False
        self._playback_task: asyncio.Task | None = None

    async def setup(self) -> None:
        """Inicializa pygame mixer para playback de áudio."""
        try:
            import pygame

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, pygame.mixer.init)
            logger.info("TTSSkill pronta (pygame mixer inicializado).")
        except Exception as e:
            logger.warning(f"pygame mixer não inicializado: {e}")

    async def execute(self, **kwargs) -> dict:
        """Sintetiza e reproduz texto (modo batch)."""
        text = kwargs.get("text", "")
        emotion = kwargs.get("emotion", "neutro")
        score = kwargs.get("score", 0.0)

        if not text:
            return {"error": "Nenhum texto para sintetizar."}

        start = time.monotonic()

        # Seleciona motor TTS baseado na emoção
        tts = self.service.get_active_tts(emotion, score)

        try:
            # Gera arquivo de áudio temporário
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"akane_tts_{int(time.time())}.mp3",
            )
            await tts.synthesize_to_file(text, output_path)

            # Emite evento de início de fala (para LipSync)
            await self.event_bus.emit("tts_speaking_start", {
                "audio_path": output_path,
                "text": text,
                "emotion": emotion,
            })

            # Reproduz o áudio
            await self._play_audio(output_path)

            # Emite evento de fim de fala
            await self.event_bus.emit("tts_speaking_stop", {})

            elapsed = time.monotonic() - start
            logger.debug(f"TTS batch concluído: {len(text)} chars em {elapsed:.2f}s")

            return {
                "status": "played",
                "chars": len(text),
                "engine": tts.engine_name,
                "elapsed": elapsed,
            }

        except Exception as e:
            logger.error(f"Erro no TTS: {e}")
            return {"error": str(e)}

    async def speak_streaming(
        self,
        sentence_stream: AsyncIterator[str],
        emotion: str = "neutro",
        score: float = 0.0,
    ) -> None:
        """Faster First Response: sintetiza e reproduz sentenças em pipeline.

        Cada sentença do stream é sintetizada e enfileirada para playback
        assim que fica pronta.

        Args:
            sentence_stream: AsyncIterator de sentenças completas.
            emotion: Emoção atual para seleção de motor TTS.
            score: Score de intensidade emocional.
        """
        tts = self.service.get_active_tts(emotion, score)
        self._is_speaking = True
        first_sentence = True

        # Inicia task de playback em background
        self._playback_task = asyncio.create_task(self._playback_loop())

        try:
            async for sentence in sentence_stream:
                if not self._is_speaking:
                    break  # Barge-in interrompeu

                if not sentence or len(sentence.strip()) < 3:
                    continue

                start = time.monotonic()

                # Sintetiza a sentença
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"akane_stream_{int(time.time() * 1000)}.mp3",
                )
                await tts.synthesize_to_file(sentence, output_path)

                elapsed = time.monotonic() - start

                if first_sentence:
                    logger.info(
                        f"⚡ First Response em {elapsed:.2f}s: "
                        f"'{sentence[:40]}...'"
                    )
                    # Emite evento de início de fala
                    await self.event_bus.emit("tts_speaking_start", {
                        "audio_path": output_path,
                        "text": sentence,
                        "emotion": emotion,
                    })
                    first_sentence = False

                # Enfileira para playback
                await self._audio_queue.put(output_path)

        except Exception as e:
            logger.error(f"Erro no streaming TTS: {e}")

        # Sinaliza fim do stream
        await self._audio_queue.put(None)

        # Espera playback terminar
        if self._playback_task:
            await self._playback_task

        self._is_speaking = False
        await self.event_bus.emit("tts_speaking_stop", {})

    async def _playback_loop(self) -> None:
        """Loop de playback — reproduz áudios da fila em sequência."""
        while True:
            audio_path = await self._audio_queue.get()

            if audio_path is None:
                break  # Fim do stream

            try:
                await self._play_audio(audio_path)
                # Limpa arquivo temporário
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
            except Exception as e:
                logger.error(f"Erro no playback: {e}")

    async def _play_audio(self, path: str) -> None:
        """Reproduz arquivo de áudio via pygame (non-blocking)."""
        import pygame

        loop = asyncio.get_running_loop()

        def _play_sync():
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
            except Exception as e:
                logger.error(f"Erro no pygame playback: {e}")

        await loop.run_in_executor(None, _play_sync)

    async def stop_speaking(self) -> None:
        """Interrompe a fala (barge-in)."""
        self._is_speaking = False

        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass

        # Esvazia a fila
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self.event_bus.emit("tts_speaking_stop", {})
        logger.debug("TTS interrompido (barge-in).")

    async def teardown(self) -> None:
        await self.stop_speaking()
        try:
            import pygame
            pygame.mixer.quit()
        except Exception:
            pass
        await super().teardown()
