"""
TTSEngine — Interface abstrata e implementações para provedores de TTS.

Padrão Factory: cada provedor herda de TTSEngine e implementa
synthesize() e synthesize_to_file() assíncronos.

Provedores implementados:
    - EdgeTTSEngine (default, grátis)
    - ElevenLabsTTSEngine (premium, picos emocionais)

"Não reclame da minha voz! O Edge é grátis e funciona. Se quiser
emoção de verdade, pague pelo ElevenLabs, velho!" — Akane
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import AsyncIterator

from loguru import logger

from akane_den.core.config import AkaneConfig


class TTSEngine(ABC):
    """Interface abstrata para provedores de Text-to-Speech."""

    def __init__(self, config: AkaneConfig) -> None:
        self.config = config

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza texto completo em áudio (retorna bytes MP3/WAV)."""
        ...

    @abstractmethod
    async def synthesize_to_file(self, text: str, output_path: str) -> str:
        """Sintetiza texto e salva em arquivo. Retorna o path."""
        ...

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Sintetiza em streaming (yield de chunks de áudio)."""
        ...

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Nome do motor TTS ativo."""
        ...


# ──────────────────────────────────────────────
# Implementação: Edge-TTS (Grátis)
# ──────────────────────────────────────────────


class EdgeTTSEngine(TTSEngine):
    """TTS Engine usando Microsoft Edge-TTS (grátis, sem limites)."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._voice = config.tts.edge_voice
        self._pitch = config.tts.edge_pitch
        self._rate = config.tts.edge_rate
        logger.info(f"EdgeTTSEngine inicializado: voice={self._voice}")

    async def synthesize(self, text: str) -> bytes:
        """Sintetiza texto completo com Edge-TTS."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text, self._voice,
            pitch=self._pitch,
            rate=self._rate,
        )

        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    async def synthesize_to_file(self, text: str, output_path: str) -> str:
        """Sintetiza e salva em arquivo MP3."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text, self._voice,
            pitch=self._pitch,
            rate=self._rate,
        )
        await communicate.save(output_path)
        return output_path

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming de chunks de áudio do Edge-TTS."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text, self._voice,
            pitch=self._pitch,
            rate=self._rate,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    @property
    def engine_name(self) -> str:
        return "edge"


# ──────────────────────────────────────────────
# Implementação: ElevenLabs (Premium)
# ──────────────────────────────────────────────


class ElevenLabsTTSEngine(TTSEngine):
    """TTS Engine usando ElevenLabs API (premium, alta qualidade emocional)."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._voice_id = config.tts.elevenlabs_voice_id
        self._model_id = config.tts.elevenlabs_model
        self._client = None

        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if api_key:
            try:
                from elevenlabs import ElevenLabs

                self._client = ElevenLabs(api_key=api_key)
                logger.info(
                    f"ElevenLabsTTSEngine inicializado: "
                    f"voice_id={self._voice_id}"
                )
            except ImportError:
                logger.warning("Pacote 'elevenlabs' não instalado.")
        else:
            logger.warning(
                "ELEVENLABS_API_KEY não encontrada. "
                "ElevenLabs TTS não disponível."
            )

    @property
    def is_available(self) -> bool:
        """Verifica se o cliente ElevenLabs está ativo."""
        return self._client is not None

    async def synthesize(self, text: str) -> bytes:
        """Sintetiza texto completo com ElevenLabs."""
        if not self._client:
            raise RuntimeError("ElevenLabs não inicializado.")

        import asyncio

        loop = asyncio.get_running_loop()

        def _sync_synthesize():
            audio_gen = self._client.text_to_speech.convert(
                text=text,
                voice_id=self._voice_id,
                model_id=self._model_id,
                output_format="mp3_22050_32",
            )
            return b"".join(audio_gen)

        return await loop.run_in_executor(None, _sync_synthesize)

    async def synthesize_to_file(self, text: str, output_path: str) -> str:
        """Sintetiza e salva em arquivo MP3."""
        audio = await self.synthesize(text)
        with open(output_path, "wb") as f:
            f.write(audio)
        return output_path

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming de chunks do ElevenLabs."""
        if not self._client:
            raise RuntimeError("ElevenLabs não inicializado.")

        import asyncio

        loop = asyncio.get_running_loop()

        def _sync_stream():
            return list(
                self._client.text_to_speech.convert(
                    text=text,
                    voice_id=self._voice_id,
                    model_id=self._model_id,
                    output_format="mp3_22050_32",
                )
            )

        chunks = await loop.run_in_executor(None, _sync_stream)
        for chunk in chunks:
            yield chunk

    @property
    def engine_name(self) -> str:
        return "elevenlabs"
