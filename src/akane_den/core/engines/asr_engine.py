"""
ASREngine — Interface abstrata e implementações para provedores de ASR.

Padrão Factory: cada provedor herda de ASREngine e implementa
transcribe() assíncrono.

Provedores implementados:
    - WhisperASREngine (default, faster-whisper)
    - SherpaOnnxASREngine (opcional, SenseVoiceSmall int8)

"Fala mais alto, baka! E não culpe meu ouvido digital se você
gagueja que nem um CD riscado!" — Akane
"""

from __future__ import annotations

import asyncio
import functools
from abc import ABC, abstractmethod

import numpy as np
from loguru import logger

from akane_den.core.config import AkaneConfig


class ASREngine(ABC):
    """Interface abstrata para provedores de Speech-to-Text."""

    def __init__(self, config: AkaneConfig) -> None:
        self.config = config

    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio float32 para texto.

        Args:
            audio: Array NumPy float32 normalizado (-1.0 a 1.0).
            sample_rate: Taxa de amostragem do áudio.

        Returns:
            Texto transcrito.
        """
        ...

    @abstractmethod
    async def setup(self) -> None:
        """Carrega modelos pesados (chamado no boot)."""
        ...

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Nome do motor ASR ativo."""
        ...


# ──────────────────────────────────────────────
# Implementação: Faster-Whisper (Default)
# ──────────────────────────────────────────────


class WhisperASREngine(ASREngine):
    """ASR Engine usando faster-whisper (CTranslate2)."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._model = None
        self._model_size = config.asr.model_size
        self._device = config.asr.device
        self._language = config.asr.language

    async def setup(self) -> None:
        """Carrega o modelo Whisper em thread pool (operação pesada)."""
        from faster_whisper import WhisperModel

        compute_type = "int8" if self._device == "cpu" else "float16"

        logger.info(
            f"Carregando Whisper '{self._model_size}' "
            f"({self._device}, {compute_type})..."
        )

        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(
            None,
            functools.partial(
                WhisperModel,
                self._model_size,
                device=self._device,
                compute_type=compute_type,
            ),
        )

        logger.success(f"Whisper '{self._model_size}' carregado.")

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        """Transcrição síncrona — NUNCA chamar do event loop!"""
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=1,
            vad_filter=True,
            without_timestamps=True,
        )
        return " ".join(seg.text for seg in segments).strip()

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio float32 em thread pool (non-blocking)."""
        if self._model is None:
            raise RuntimeError("Modelo Whisper não carregado. Chame setup() primeiro.")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio)

    @property
    def engine_name(self) -> str:
        return f"whisper-{self._model_size}"


# ──────────────────────────────────────────────
# Implementação: Sherpa-onnx (Opcional, SenseVoiceSmall)
# ──────────────────────────────────────────────


class SherpaOnnxASREngine(ASREngine):
    """ASR Engine usando sherpa-onnx com SenseVoiceSmall int8.

    Mais rápido que Whisper em CPU. Requer instalação opcional:
        uv pip install 'akane-den[sherpa]'
    """

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._recognizer = None
        self._model_path = config.asr.sherpa_model_path
        self._tokens_path = config.asr.sherpa_tokens_path

    async def setup(self) -> None:
        """Inicializa o reconhecedor Sherpa-onnx."""
        try:
            import sherpa_onnx

            logger.info("Inicializando Sherpa-onnx ASR (SenseVoiceSmall int8)...")

            # SenseVoiceSmall config
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=self._model_path,
                tokens=self._tokens_path,
                use_itn=True,
                num_threads=4,
                debug=False,
            )

            logger.success("Sherpa-onnx ASR inicializado.")

        except ImportError:
            raise ImportError(
                "sherpa-onnx não instalado! Instale com: "
                "uv pip install 'akane-den[sherpa]'"
            )
        except Exception as e:
            logger.error(f"Falha ao inicializar Sherpa-onnx: {e}")
            raise

    def _transcribe_sync(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcrição síncrona com sherpa-onnx."""
        import sherpa_onnx

        stream = self._recognizer.create_stream()

        # sherpa-onnx espera float32 samples
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        stream.accept_waveform(sample_rate, audio.tolist())
        self._recognizer.decode_stream(stream)

        return stream.result.text.strip()

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio em thread pool (non-blocking)."""
        if self._recognizer is None:
            raise RuntimeError(
                "Sherpa-onnx não inicializado. Chame setup() primeiro."
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._transcribe_sync, audio, sample_rate
        )

    @property
    def engine_name(self) -> str:
        return "sherpa-onnx-sensevoice"
